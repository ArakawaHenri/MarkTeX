from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from marktex.mos.model import CallUnit, MosValue, RawString, TupleValue
from marktex.source import MarkTeXError, SourceSpan

STRUCTURAL = {":", ",", ";", "=", "(", ")"}


@dataclass
class _Segment:
    text: str
    start: int
    end: int
    force_raw: bool = False


class _Parser:
    def __init__(self, source: str, *, context: str, filename: str) -> None:
        self.source = source
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
            if self.peek == ")":
                self.error("unmatched ')' in MOS payload")

            segment = self.read_segment()
            if self.peek == "=":
                self.index += 1
                name = segment.text.strip()
                if not name:
                    self.error("empty named argument in MOS payload", segment.start)
                root_kwargs[name] = self.parse_value()
            elif self.peek == ":":
                self._flush_root_kwargs(units, root_kwargs, root_start)
                self.index += 1
                head = segment.text.strip()
                if not head:
                    self.error("empty call head in MOS payload", segment.start)
                units.append(self.parse_frame(head, segment.start))
            else:
                self._flush_root_kwargs(units, root_kwargs, root_start)
                head = segment.text.strip()
                if head:
                    units.append(
                        CallUnit(
                            self.context,
                            head,
                            origin=self.span(segment.start, segment.end),
                        )
                    )

            if self.peek == ",":
                self.index += 1
            elif self.peek == ";":
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
            if self.peek == ";":
                self.index += 1
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek == ")":
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek == ",":
                self.index += 1
                continue
            if self._skip_spaces_before_tuple():
                args.append(self.parse_tuple())
                continue

            segment = self.read_segment()
            if self.peek == "=":
                self.index += 1
                name = segment.text.strip()
                if not name:
                    self.error("empty named argument in MOS call", segment.start)
                kwargs[name] = self.parse_value()
            elif self.peek == ":":
                self.index += 1
                nested_head = segment.text.strip()
                if not nested_head:
                    self.error("empty nested call head in MOS call", segment.start)
                args.append(self.parse_frame(nested_head, segment.start))
            elif segment.text or segment.force_raw:
                args.append(self.raw_from_segment(segment))
            elif not self.eof:
                self.error(f"unexpected {self.peek!r} in MOS call")

            if self.peek == ",":
                self.index += 1
                continue
            if self.peek == ";":
                self.index += 1
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))
            if self.peek == ")":
                return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))

        return CallUnit(self.context, head, tuple(args), kwargs, self.span(start, self.index))

    def parse_value(self) -> MosValue:
        if self.peek == "(" or self._skip_spaces_before_tuple():
            return self.parse_tuple()

        segment = self.read_segment()
        if self.peek == ":":
            self.index += 1
            head = segment.text.strip()
            if not head:
                self.error("empty nested call head in MOS value", segment.start)
            return self.parse_frame(head, segment.start)
        return self.raw_from_segment(segment)

    def _skip_spaces_before_tuple(self) -> bool:
        start = self.index
        while not self.eof and self.peek in {" ", "\t"}:
            self.index += 1
        if not self.eof and self.peek == "(":
            return True
        self.index = start
        return False

    def parse_tuple(self) -> TupleValue:
        start = self.index
        self.index += 1
        items: list[MosValue] = []
        while not self.eof:
            if self.peek == ")":
                self.index += 1
                return TupleValue(tuple(items), self.span(start, self.index))
            if self.peek == ",":
                self.index += 1
                continue
            items.append(self.parse_value())
            if not self.eof and self.peek not in {",", ")"}:
                self.error("expected ',' or ')' in MOS tuple")
            if self.peek == ",":
                self.index += 1
        self.error("unclosed tuple in MOS payload", start)

    def read_segment(self) -> _Segment:
        start = self.index
        parts: list[str] = []
        force_raw = False

        while not self.eof:
            char = self.peek
            if char in STRUCTURAL:
                break
            if char == "\\":
                parts.append(self.read_escape())
                continue
            if char == "`":
                force_raw = True
                if parts and "".join(parts).strip() == "":
                    parts = []
                parts.append(self.read_raw_literal())
                continue
            parts.append(char)
            self.index += 1

        return _Segment("".join(parts), start, self.index, force_raw)

    def read_escape(self) -> str:
        self.index += 1
        if self.eof:
            return "\\"
        if self.peek == "\n":
            self.index += 1
            return ""
        char = self.peek
        self.index += 1
        return char

    def read_raw_literal(self) -> str:
        self.index += 1
        parts: list[str] = []
        while not self.eof:
            if self.peek == "\\":
                parts.append(self.read_escape())
                continue
            if self.peek == "`":
                self.index += 1
                return "".join(parts)
            parts.append(self.peek)
            self.index += 1
        self.error("unclosed raw literal in MOS payload")

    def raw_from_segment(self, segment: _Segment) -> RawString:
        return RawString(segment.text, self.span(segment.start, segment.end), segment.force_raw)

    def _skip_root_separators(self) -> None:
        while not self.eof and self.peek in {",", ";"}:
            self.index += 1

    @property
    def eof(self) -> bool:
        return self.index >= len(self.source)

    @property
    def peek(self) -> str:
        if self.eof:
            return ""
        return self.source[self.index]

    def span(self, start: int, end: int) -> SourceSpan:
        line = self.source.count("\n", 0, start) + 1
        last_newline = self.source.rfind("\n", 0, start)
        column = start + 1 if last_newline == -1 else start - last_newline
        return SourceSpan(self.filename, start, end, line, column)

    def error(self, message: str, index: int | None = None) -> NoReturn:
        where = self.index if index is None else index
        raise MarkTeXError(message, self.span(where, where))


def parse_mos(source: str, *, context: str = "root", filename: str = "<mos>") -> list[CallUnit]:
    """Parse a MOS payload into top-level call units.

    The parser is intentionally schema-agnostic. It does not know presets,
    dimensions, booleans, or tag-like shorthands.
    """

    return _Parser(source, context=context, filename=filename).parse_root()
