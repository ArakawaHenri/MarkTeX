from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from marktex.mos.model import CallUnit, MosValue, RawString, TupleValue
from marktex.source import CookedText, MarkTeXError, SourceSpan, cook_raw, span_from_range

STRUCTURAL = {":", ",", ";", "=", "(", ")"}


@dataclass
class _Segment:
    text: str
    start: int
    end: int
    escaped: tuple[bool, ...]
    force_raw: bool = False


class _Parser:
    def __init__(
        self,
        source: str | CookedText,
        *,
        context: str,
        filename: str,
        raw_source: str | None = None,
    ) -> None:
        self.cooked = cook_raw(source) if isinstance(source, str) else source
        self.source = source if isinstance(source, str) else (raw_source or source.text)
        self.context = context
        self.filename = filename
        self.index = 0

    def parse_root(self) -> list[CallUnit]:
        units: list[CallUnit] = []
        root_kwargs: dict[str, MosValue] = {}
        root_start = 0

        while not self.eof:
            self._skip_root_separators()
            if self.eof:
                break
            if self.peek_is(")"):
                self.error("unmatched ')' in MOS payload")

            segment = self.read_segment()
            if self.peek_is("="):
                self.index += 1
                name = self.syntax_name(segment, "named argument")
                if not name:
                    self.error("empty named argument in MOS payload", segment.start)
                root_kwargs[name] = self.parse_value()
            elif self.peek_is(":"):
                self._flush_root_kwargs(units, root_kwargs, root_start)
                self.index += 1
                head = self.syntax_name(segment, "call head")
                if not head:
                    self.error("empty call head in MOS payload", segment.start)
                units.append(self.parse_frame(head, segment.start))
            else:
                self._flush_root_kwargs(units, root_kwargs, root_start)
                head = self.syntax_name(segment, "call head", allow_empty=True)
                if head:
                    units.append(
                        CallUnit(
                            self.context,
                            head,
                            origin=self.span(segment.start, segment.end),
                        )
                    )

            if self.peek_is(","):
                self.index += 1
            elif self.peek_is(";"):
                self.index += 1
                self._flush_root_kwargs(units, root_kwargs, root_start)
                root_start = self.index

        self._flush_root_kwargs(units, root_kwargs, root_start)
        return units

    def _flush_root_kwargs(
        self, units: list[CallUnit], root_kwargs: dict[str, MosValue], root_start: int
    ) -> None:
        if not root_kwargs:
            return
        units.append(
            CallUnit(
                self.context,
                "",
                kwargs=dict(root_kwargs),
                origin=self.span(root_start, self.index),
            )
        )
        root_kwargs.clear()

    def parse_frame(self, head: str, start: int) -> CallUnit:
        args: list[MosValue] = []
        kwargs: dict[str, MosValue] = {}

        while not self.eof:
            if self.peek_is(";"):
                self.index += 1
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek_is(")"):
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek_is(","):
                self.index += 1
                continue
            if self._skip_spaces_before_tuple():
                args.append(self.parse_tuple())
                continue

            segment = self.read_segment()
            if self.peek_is("="):
                self.index += 1
                name = self.syntax_name(segment, "named argument")
                if not name:
                    self.error("empty named argument in MOS call", segment.start)
                kwargs[name] = self.parse_value()
            elif self.peek_is(":"):
                self.index += 1
                nested_head = self.syntax_name(segment, "nested call head")
                if not nested_head:
                    self.error("empty nested call head in MOS call", segment.start)
                args.append(self.parse_frame(nested_head, segment.start))
            elif segment.text or segment.force_raw:
                args.append(self.raw_from_segment(segment))
            elif not self.eof:
                self.error(f"unexpected {self.peek!r} in MOS call")

            if self.peek_is(","):
                self.index += 1
                continue
            if self.peek_is(";"):
                self.index += 1
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek_is(")"):
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))

        return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))

    def parse_value(self) -> MosValue:
        if self.peek_is("(") or self._skip_spaces_before_tuple():
            return self.parse_tuple()

        segment = self.read_segment()
        if self.peek_is(":"):
            self.index += 1
            head = self.syntax_name(segment, "nested call head")
            if not head:
                self.error("empty nested call head in MOS value", segment.start)
            return self.parse_frame(head, segment.start)
        return self.raw_from_segment(segment)

    def _skip_spaces_before_tuple(self) -> bool:
        start = self.index
        while not self.eof and self.peek in {" ", "\t"}:
            self.index += 1
        if self.peek_is("("):
            return True
        self.index = start
        return False

    def parse_tuple(self) -> TupleValue:
        start = self.index
        self.index += 1
        items: list[MosValue] = []
        while not self.eof:
            if self.peek_is(")"):
                self.index += 1
                return TupleValue(tuple(items), self.span(start, self.index))
            if self.peek_is(","):
                self.index += 1
                continue
            items.append(self.parse_value())
            if not self.eof and not (self.peek_is(",") or self.peek_is(")")):
                self.error("expected ',' or ')' in MOS tuple")
            if self.peek_is(","):
                self.index += 1
        self.error("unclosed tuple in MOS payload", start)

    def read_segment(self) -> _Segment:
        start = self.index
        parts: list[str] = []
        force_raw = False

        while not self.eof:
            char = self.peek
            if self.is_structural(self.index):
                break
            if self.peek_is("`"):
                force_raw = True
                if parts and "".join(parts).strip() == "":
                    parts = []
                parts.append(self.read_raw_literal())
                continue
            parts.append(char)
            self.index += 1

        return _Segment(
            "".join(parts),
            start,
            self.index,
            self.cooked.escaped[start:self.index],
            force_raw,
        )

    def read_raw_literal(self) -> str:
        self.index += 1
        parts: list[str] = []
        while not self.eof:
            if self.peek_is("`"):
                self.index += 1
                return "".join(parts)
            parts.append(self.peek)
            self.index += 1
        self.error("unclosed raw literal in MOS payload")

    def raw_from_segment(self, segment: _Segment) -> RawString:
        return RawString(segment.text, self.span(segment.start, segment.end), segment.force_raw)

    def _skip_root_separators(self) -> None:
        while not self.eof and (self.peek_is(",") or self.peek_is(";")):
            self.index += 1

    @property
    def eof(self) -> bool:
        return self.index >= len(self.cooked.text)

    @property
    def peek(self) -> str:
        if self.eof:
            return ""
        return self.cooked.text[self.index]

    def peek_is(self, char: str) -> bool:
        return not self.eof and self.cooked.char_is(self.index, char)

    def is_structural(self, index: int) -> bool:
        return self.cooked.text[index] in STRUCTURAL and self.cooked.is_unescaped(index)

    def syntax_name(self, segment: _Segment, kind: str, *, allow_empty: bool = False) -> str:
        start = 0
        end = len(segment.text)
        while start < end and segment.text[start].isspace():
            start += 1
        while end > start and segment.text[end - 1].isspace():
            end -= 1
        if start == end:
            return "" if allow_empty else segment.text.strip()
        if any(segment.escaped[start:end]):
            self.error(f"escaped MOS {kind} cannot be used as syntax", segment.start + start)
        return segment.text[start:end]

    def span(self, start: int, end: int) -> SourceSpan:
        return span_from_range(
            self.filename,
            self.cooked.offsets[start],
            self.cooked.offsets[end],
            self.source,
        )

    def error(self, message: str, index: int | None = None) -> NoReturn:
        where = self.index if index is None else index
        raise MarkTeXError(message, self.span(where, where))


def parse_mos(source: str, *, context: str = "root", filename: str = "<mos>") -> list[CallUnit]:
    """Parse a MOS payload into top-level call units.

    The parser is intentionally schema-agnostic. It does not know presets,
    dimensions, booleans, or tag-like shorthands.
    """

    return _Parser(source, context=context, filename=filename).parse_root()


def parse_mos_cooked(
    source: CookedText,
    *,
    context: str = "root",
    filename: str = "<mos>",
    raw_source: str | None = None,
) -> list[CallUnit]:
    return _Parser(source, context=context, filename=filename, raw_source=raw_source).parse_root()
