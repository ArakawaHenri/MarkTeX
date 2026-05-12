from __future__ import annotations
from collections.abc import Mapping

from marktex.core import (
    Citation,
    Emphasis,
    FootnoteRef,
    Image,
    InlineCode,
    InlineExpression,
    InlineMath,
    InlineNode,
    LineBreak,
    Link,
    Strong,
    Strikethrough,
    Text,
)
from marktex.host.python import PythonHost
from marktex.mos import RawString, parse_mos
from marktex.semantics import CITATION_KWARGS
from marktex.source import MarkTeXError, SourceSpan
from marktex.surface.grammar import is_footnote_label


def parse_inline_nodes(
    text: str,
    host: PythonHost,
    origin: SourceSpan,
    source: str,
    *,
    source_offsets: tuple[int, ...],
    link_refs: Mapping[str, str] | None = None,
) -> tuple[InlineNode, ...]:
    return _InlineParser(text, host, origin, source, source_offsets, link_refs or {}).parse_range(
        0, len(text)
    )


class _InlineParser:
    def __init__(
        self,
        text: str,
        host: PythonHost,
        origin: SourceSpan,
        source: str,
        source_offsets: tuple[int, ...],
        link_refs: Mapping[str, str],
    ) -> None:
        self.text = text
        self.host = host
        self.origin = origin
        self.source = source
        self.source_offsets = source_offsets
        self.link_refs = link_refs

    def parse_range(self, start: int, end: int) -> tuple[InlineNode, ...]:
        nodes: list[InlineNode] = []
        cursor = start
        while cursor < end:
            if self.text[cursor] == "\n":
                nodes.append(LineBreak(True, self.token_span(cursor, cursor + 1)))
                cursor += 1
                continue
            if self.text[cursor] == "\\":
                if cursor + 1 < end and self.text[cursor + 1] == "\n":
                    cursor += 2
                elif cursor + 1 < end:
                    self.append_text(nodes, self.text[cursor + 1], cursor, cursor + 2)
                    cursor += 2
                else:
                    self.append_text(nodes, "\\", cursor, cursor + 1)
                    cursor += 1
                continue

            parsed = (
                self.parse_image(cursor, end)
                or self.parse_reference(cursor, end)
                or self.parse_code_span(cursor, end)
                or self.parse_strikethrough(cursor, end)
                or self.parse_strong(cursor, end)
                or self.parse_emphasis(cursor, end)
                or self.parse_inline_math(cursor, end)
            )
            if parsed is not None:
                node, cursor = parsed
                nodes.append(node)
                continue

            next_special = self.next_special(cursor + 1, end)
            self.append_text(nodes, self.text[cursor:next_special], cursor, next_special)
            cursor = next_special
        if not nodes:
            return (Text("", self.token_span(start, end)),)
        return tuple(nodes)

    def parse_child(self, start: int, end: int) -> tuple[InlineNode, ...]:
        origin = self.token_span(start, end)
        return _InlineParser(
            self.text[start:end],
            self.host,
            origin,
            self.source,
            self.source_offsets[start : end + 1],
            self.link_refs,
        ).parse_range(0, end - start)

    def parse_image(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        if not self.text.startswith("![", cursor):
            return None
        label_start = cursor + 2
        label_end = self.find_closing_bracket(label_start - 1, end)
        if label_end is None:
            return None
        target = self.link_target_after(label_end, end) or self.reference_target_after(
            cursor + 1,
            label_end,
            end,
        )
        if target is None:
            return None
        destination, next_cursor = target
        return Image(self.text[label_start:label_end], destination, self.token_span(cursor, next_cursor)), next_cursor

    def parse_reference(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        if not self.text.startswith("[", cursor):
            return None
        if self.text.startswith("[^", cursor):
            close = self.text.find("]", cursor + 2, self.physical_line_end(cursor, end))
            if close == -1:
                return None
            return reference_node(self.text[cursor + 2 : close], self.token_span(cursor, close + 1)), close + 1
        if self.text.startswith("[$", cursor):
            expr_close = self.find_closing_bracket(cursor, self.physical_line_end(cursor, end))
            if expr_close is None:
                return None
            expr = self.text[cursor + 2 : expr_close].strip()
            origin = self.token_span(cursor, expr_close + 1)
            return InlineExpression(expr, self.host.eval_expr(expr, origin), origin), expr_close + 1

        label_end = self.find_closing_bracket(cursor, end)
        if label_end is None:
            return None
        direct_target = self.link_target_after(label_end, end)
        if direct_target is not None:
            destination, next_cursor = direct_target
            return (
                Link(
                    self.parse_child(cursor + 1, label_end),
                    destination,
                    self.token_span(cursor, next_cursor),
                ),
                next_cursor,
            )
        ref_target = self.reference_target_after(cursor, label_end, end)
        if ref_target is None:
            return None
        destination, next_cursor = ref_target
        return (
            Link(
                self.parse_child(cursor + 1, label_end),
                destination,
                self.token_span(cursor, next_cursor),
            ),
            next_cursor,
        )

    def parse_code_span(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        if self.text[cursor] != "`":
            return None
        run_end = cursor
        while run_end < end and self.text[run_end] == "`":
            run_end += 1
        marker = self.text[cursor:run_end]
        close = self.text.find(marker, run_end, end)
        if close == -1:
            return None
        raw = self.text[run_end:close].replace("\n", " ")
        if len(raw) >= 2 and raw.startswith(" ") and raw.endswith(" ") and raw.strip():
            raw = raw[1:-1]
        return InlineCode(raw, self.token_span(cursor, close + len(marker))), close + len(marker)

    def parse_strikethrough(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        if not self.text.startswith("~~", cursor):
            return None
        close = self.text.find("~~", cursor + 2, end)
        if close == -1:
            return None
        return (
            Strikethrough(self.parse_child(cursor + 2, close), self.token_span(cursor, close + 2)),
            close + 2,
        )

    def parse_strong(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        for marker in ("**", "__"):
            if self.text.startswith(marker, cursor) and delimiter_can_open(
                self.text, cursor, marker[0], 2
            ):
                close = self.find_closing_delimiter(cursor + 2, end, marker[0], 2)
                if close is not None:
                    return (
                        Strong(
                            self.parse_child(cursor + 2, close),
                            self.token_span(cursor, close + 2),
                        ),
                        close + 2,
                    )
        return None

    def parse_emphasis(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        marker = self.text[cursor]
        if marker not in "*_" or (cursor + 1 < end and self.text[cursor + 1] == marker):
            return None
        if not delimiter_can_open(self.text, cursor, marker, 1):
            return None
        close = self.find_closing_delimiter(cursor + 1, end, marker, 1)
        if close is None:
            return None
        return Emphasis(self.parse_child(cursor + 1, close), self.token_span(cursor, close + 1)), close + 1

    def parse_inline_math(self, cursor: int, end: int) -> tuple[InlineNode, int] | None:
        if not self.is_single_dollar(cursor, end):
            return None
        close = self.find_closing_math_dollar(cursor + 1, self.physical_line_end(cursor, end))
        if close is None:
            return None
        return InlineMath(self.text[cursor + 1 : close], self.token_span(cursor, close + 1)), close + 1

    def link_target_after(self, label_end: int, end: int) -> tuple[str, int] | None:
        if label_end + 1 >= end or self.text[label_end + 1] != "(":
            return None
        close = self.find_closing_paren(label_end + 1, end)
        if close is None:
            return None
        destination = normalize_link_destination(self.text[label_end + 2 : close])
        if not destination:
            return None
        if link_destination_has_title(self.text[label_end + 2 : close]):
            raise MarkTeXError("unsupported link title", self.token_span(label_end + 1, close + 1))
        return destination, close + 1

    def reference_target_after(
        self, label_start: int, label_end: int, end: int
    ) -> tuple[str, int] | None:
        if label_end + 1 < end and self.text[label_end + 1] == "[":
            close = self.text.find("]", label_end + 2, end)
            if close == -1:
                return None
            raw_label = self.text[label_end + 2 : close] or self.text[label_start + 1 : label_end]
            destination = self.link_refs.get(normalize_reference_label(raw_label))
            if destination is None:
                return None
            return destination, close + 1
        destination = self.link_refs.get(normalize_reference_label(self.text[label_start + 1 : label_end]))
        if destination is None:
            return None
        return destination, label_end + 1

    def find_closing_bracket(self, open_bracket: int, end: int) -> int | None:
        depth = 0
        cursor = open_bracket
        while cursor < end:
            char = self.text[cursor]
            if char == "\\":
                cursor += 2
                continue
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        return None

    def find_closing_paren(self, open_paren: int, end: int) -> int | None:
        depth = 0
        cursor = open_paren
        while cursor < end:
            char = self.text[cursor]
            if char == "\\":
                cursor += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        return None

    def find_closing_delimiter(
        self, cursor: int, end: int, marker: str, length: int
    ) -> int | None:
        while cursor < end:
            if self.text[cursor] == "`":
                code = self.parse_code_span(cursor, end)
                if code is not None:
                    cursor = code[1]
                    continue
            if self.text.startswith(marker * length, cursor) and delimiter_can_close(
                self.text, cursor, marker, length
            ):
                return cursor
            cursor += 1
        return None

    def find_closing_math_dollar(self, cursor: int, end: int) -> int | None:
        while cursor < end:
            if self.text[cursor] == "\\":
                cursor += 2
                continue
            if self.is_single_dollar(cursor, end):
                return cursor
            cursor += 1
        return None

    def is_single_dollar(self, cursor: int, end: int) -> bool:
        return (
            self.text[cursor] == "$"
            and (cursor == 0 or self.text[cursor - 1] != "$")
            and (cursor + 1 >= end or self.text[cursor + 1] != "$")
        )

    def physical_line_end(self, cursor: int, end: int) -> int:
        line_end = self.text.find("\n", cursor, end)
        return end if line_end == -1 else line_end

    def next_special(self, cursor: int, end: int) -> int:
        while cursor < end and self.text[cursor] not in INLINE_SPECIAL_CHARS:
            cursor += 1
        return cursor

    def append_text(self, nodes: list[InlineNode], value: str, start: int, end: int) -> None:
        if value:
            nodes.append(Text(value, self.token_span(start, end)))

    def token_span(self, start: int, end: int) -> SourceSpan:
        return absolute_span(
            self.origin.filename,
            self.source_offsets[start],
            self.source_offsets[end],
            self.source,
        )


INLINE_SPECIAL_CHARS = set("\\\n![`*_~$")


def normalize_link_destination(raw: str) -> str:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        return text[1 : text.index(">")]
    return text.split()[0] if text.split() else ""


def link_destination_has_title(raw: str) -> bool:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        return bool(text[text.index(">") + 1 :].strip())
    return len(text.split()) > 1


def normalize_reference_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def delimiter_can_open(text: str, start: int, marker: str, length: int) -> bool:
    left, right = delimiter_flanking(text, start, length)
    if marker == "_":
        previous = text[start - 1] if start > 0 else "\n"
        return left and (not right or is_punctuation(previous))
    return left


def delimiter_can_close(text: str, start: int, marker: str, length: int) -> bool:
    left, right = delimiter_flanking(text, start, length)
    if marker == "_":
        next_char = text[start + length] if start + length < len(text) else "\n"
        return right and (not left or is_punctuation(next_char))
    return right


def delimiter_flanking(text: str, start: int, length: int) -> tuple[bool, bool]:
    previous = text[start - 1] if start > 0 else "\n"
    next_char = text[start + length] if start + length < len(text) else "\n"
    left = not next_char.isspace() and (
        not is_punctuation(next_char) or previous.isspace() or is_punctuation(previous)
    )
    right = not previous.isspace() and (
        not is_punctuation(previous) or next_char.isspace() or is_punctuation(next_char)
    )
    return left, right


def is_punctuation(char: str) -> bool:
    return not char.isalnum() and not char.isspace()


def reference_node(payload: str, origin: SourceSpan) -> FootnoteRef | Citation:
    calls = parse_mos(payload, context="reference", filename=origin.filename)
    if len(calls) == 1 and calls[0].head == "cite":
        keys: list[str] = []
        kwargs: dict[str, str] = {}
        for arg in calls[0].args:
            if isinstance(arg, RawString):
                keys.append(arg.text.strip())
        for key, value in calls[0].kwargs.items():
            if key not in CITATION_KWARGS:
                raise MarkTeXError(f"unknown citation kwargs: {key}", origin)
            if isinstance(value, RawString):
                kwargs[key] = value.text.strip()
        if not keys:
            raise MarkTeXError("citation requires at least one key", origin)
        return Citation(tuple(keys), kwargs, origin)
    if is_footnote_label(payload.strip()):
        return FootnoteRef(payload.strip(), origin)
    raise MarkTeXError(f"unsupported reference payload: {payload}", origin)


def absolute_span(filename: str, start: int, end: int, source: str) -> SourceSpan:
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start + 1 if last_newline == -1 else start - last_newline
    return SourceSpan(filename, start, end, line, column)
