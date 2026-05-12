from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from marktex.reference import citation_from_cooked_payload
from marktex.source import CookedText, MarkTeXError, SourceSpan, span_from_range
from marktex.surface.model import (
    CodeFenceNode,
    ConditionalNode,
    DocumentDirectiveNode,
    HostBlockNode,
    MathBlockNode,
    ScopeCloseNode,
    ScopeOpenNode,
    SurfaceCitationNode,
    SurfaceInlineCodeNode,
    SurfaceInlineExpressionNode,
    SurfaceInlineMathNode,
    SurfaceInlineNode,
)


@dataclass(frozen=True)
class RawTextSegment:
    text: str
    offsets: tuple[int, ...]

    @property
    def start(self) -> int:
        return self.offsets[0]

    @property
    def end(self) -> int:
        return self.offsets[-1]

    def slice(self, start: int, end: int | None = None) -> RawTextSegment:
        resolved_end = len(self.text) if end is None else end
        return RawTextSegment(
            self.text[start:resolved_end],
            self.offsets[start : resolved_end + 1],
        )


LinePart: TypeAlias = RawTextSegment | SurfaceInlineNode


@dataclass(frozen=True)
class SegmentedLine:
    parts: tuple[LinePart, ...]
    start: int
    end: int

    @classmethod
    def from_source_line(
        cls,
        line: str,
        start: int,
        *,
        filename: str,
        source: str,
    ) -> SegmentedLine:
        text = line.rstrip("\n")
        offsets = tuple(range(start, start + len(text) + 1))
        return cls(
            segment_marktex_inline(text, offsets, filename=filename, source=source),
            start,
            start + len(text),
        )

    @classmethod
    def from_raw(
        cls,
        text: str,
        offsets: tuple[int, ...],
        *,
        filename: str,
        source: str,
    ) -> SegmentedLine:
        return cls(
            segment_marktex_inline(text, offsets, filename=filename, source=source),
            offsets[0],
            offsets[-1],
        )

    @classmethod
    def empty(cls, offset: int) -> SegmentedLine:
        return cls((), offset, offset)

    @property
    def raw_prefix(self) -> str:
        text: list[str] = []
        for part in self.parts:
            if not isinstance(part, RawTextSegment):
                break
            text.append(part.text)
        return "".join(text)

    @property
    def all_raw(self) -> bool:
        return all(isinstance(part, RawTextSegment) for part in self.parts)

    @property
    def raw_text(self) -> str:
        if not self.all_raw:
            raise ValueError("line contains MarkTeX inline islands")
        return "".join(part.text for part in self.parts if isinstance(part, RawTextSegment))

    @property
    def raw_offsets(self) -> tuple[int, ...]:
        if not self.all_raw:
            raise ValueError("line contains MarkTeX inline islands")
        offsets: list[int] = []
        for part in self.parts:
            if not isinstance(part, RawTextSegment):
                continue
            if not offsets:
                offsets.extend(part.offsets)
            else:
                offsets.extend(part.offsets[1:])
        return tuple(offsets) if offsets else (self.start,)

    def is_blank(self) -> bool:
        return not self.parts or (self.all_raw and self.raw_text == "")

    def drop_prefix_chars(self, count: int) -> SegmentedLine:
        remaining = count
        new_parts: list[LinePart] = []
        new_start = self.start
        dropped = False
        for part in self.parts:
            if remaining <= 0:
                new_parts.append(part)
                continue
            if not isinstance(part, RawTextSegment):
                raise ValueError("prefix crosses a MarkTeX inline island")
            if remaining < len(part.text):
                sliced = part.slice(remaining)
                new_start = sliced.start
                new_parts.append(sliced)
                remaining = 0
                dropped = True
            else:
                new_start = part.offsets[len(part.text)]
                remaining -= len(part.text)
                dropped = True
        if remaining:
            raise ValueError("prefix is longer than the line")
        if not dropped:
            new_start = self.start
        return SegmentedLine(tuple(new_parts), new_start, self.end)


@dataclass(frozen=True)
class MarkTeXFallbackRun:
    lines: tuple[SegmentedLine, ...]


@dataclass(frozen=True)
class MarkTeXRichTableNode:
    column_specs: tuple[str, ...]
    column_spec_kinds: tuple[str, ...]
    column_spec_offsets: tuple[tuple[int, ...], ...]
    rows: tuple[tuple[SegmentedLine, ...], ...]
    origin: SourceSpan


MarkTeXLayerNode: TypeAlias = (
    DocumentDirectiveNode
    | ScopeOpenNode
    | ScopeCloseNode
    | HostBlockNode
    | ConditionalNode
    | CodeFenceNode
    | MathBlockNode
    | MarkTeXRichTableNode
    | MarkTeXFallbackRun
)


@dataclass(frozen=True)
class MarkTeXLayerDocument:
    nodes: tuple[MarkTeXLayerNode, ...]


def parse_marktex_layer(source: str, *, filename: str) -> MarkTeXLayerDocument:
    lines = source.splitlines(keepends=True)
    nodes: list[MarkTeXLayerNode] = []
    fallback: list[SegmentedLine] = []
    index = 0
    offset = 0

    def flush_fallback() -> None:
        nonlocal fallback
        if fallback:
            nodes.append(MarkTeXFallbackRun(tuple(fallback)))
            fallback = []

    while index < len(lines):
        line = lines[index]
        stripped_newline = line.rstrip("\n")
        line_start = offset

        if stripped_newline.startswith("```"):
            flush_fallback()
            fence_node, index, offset = parse_code_fence(lines, index, offset, source, filename)
            nodes.append(fence_node)
            continue

        if stripped_newline.startswith("$$$"):
            flush_fallback()
            host_node, index, offset = parse_host_block(lines, index, offset, source, filename)
            nodes.append(host_node)
            continue

        if stripped_newline == "$$":
            flush_fallback()
            math_node, index, offset = parse_math_block(lines, index, offset, source, filename)
            nodes.append(math_node)
            continue

        if stripped_newline.startswith("+++"):
            flush_fallback()
            table_node, index, offset = parse_rich_table(lines, index, offset, source, filename)
            nodes.append(table_node)
            continue

        conditional_marker = conditional_start(stripped_newline)
        if conditional_marker is not None:
            flush_fallback()
            nodes.append(
                ConditionalNode(
                    conditional_marker,
                    stripped_newline[len(conditional_marker) :].strip(),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        if stripped_newline.startswith("!!@"):
            flush_fallback()
            nodes.append(
                ScopeCloseNode(
                    stripped_newline[3:].strip(),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        if stripped_newline.startswith("!#"):
            flush_fallback()
            payload, origin, index, offset = collect_control_payload(
                lines,
                index,
                offset,
                prefix_length=2,
                source=source,
                filename=filename,
            )
            nodes.append(DocumentDirectiveNode(payload, origin))
            continue

        if stripped_newline.startswith("!@"):
            flush_fallback()
            payload, origin, index, offset = collect_control_payload(
                lines,
                index,
                offset,
                prefix_length=2,
                source=source,
                filename=filename,
            )
            nodes.append(ScopeOpenNode(payload, origin))
            continue

        fallback.append(
            SegmentedLine.from_source_line(
                line,
                line_start,
                filename=filename,
                source=source,
            )
        )
        index += 1
        offset += len(line)

    flush_fallback()
    return MarkTeXLayerDocument(tuple(nodes))


def segment_marktex_inline(
    text: str,
    offsets: tuple[int, ...],
    *,
    filename: str,
    source: str,
) -> tuple[LinePart, ...]:
    parts: list[LinePart] = []
    cursor = 0

    def token_span(start: int, end: int) -> SourceSpan:
        return span(filename, offsets[start], offsets[end], source)

    def append_raw(start: int, end: int) -> None:
        if start >= end:
            return
        segment = RawTextSegment(text[start:end], offsets[start : end + 1])
        if parts and isinstance(parts[-1], RawTextSegment):
            previous = parts[-1]
            parts[-1] = RawTextSegment(
                previous.text + segment.text,
                previous.offsets[:-1] + segment.offsets,
            )
        else:
            parts.append(segment)

    while cursor < len(text):
        if text[cursor] == "\\":
            append_raw(cursor, min(cursor + 2, len(text)))
            cursor = min(cursor + 2, len(text))
            continue

        parsed = (
            parse_inline_code(text, offsets, cursor, token_span)
            or parse_inline_expression(text, cursor, token_span)
            or parse_inline_citation(text, offsets, cursor, filename, source, token_span)
            or parse_inline_math(text, cursor, token_span)
        )
        if parsed is not None:
            node, next_cursor = parsed
            parts.append(node)
            cursor = next_cursor
            continue

        next_special = next_marktex_inline_special(text, cursor + 1)
        append_raw(cursor, next_special)
        cursor = next_special

    return tuple(parts)


def parse_inline_code(
    text: str,
    offsets: tuple[int, ...],
    cursor: int,
    token_span: SpanFactory,
) -> tuple[SurfaceInlineCodeNode, int] | None:
    if text[cursor] != "`":
        return None
    run_end = cursor
    while run_end < len(text) and text[run_end] == "`":
        run_end += 1
    marker = text[cursor:run_end]
    close = text.find(marker, run_end)
    if close == -1:
        return None
    raw = text[run_end:close].replace("\n", " ")
    if len(raw) >= 2 and raw.startswith(" ") and raw.endswith(" ") and raw.strip():
        raw = raw[1:-1]
    return SurfaceInlineCodeNode(raw, token_span(cursor, close + len(marker))), close + len(marker)


def parse_inline_expression(
    text: str,
    cursor: int,
    token_span: SpanFactory,
) -> tuple[SurfaceInlineExpressionNode, int] | None:
    if not text.startswith("[$", cursor):
        return None
    close = closing_bracket(text, cursor + 2)
    if close is None:
        return None
    expr = text[cursor + 2 : close].strip()
    return SurfaceInlineExpressionNode(expr, token_span(cursor, close + 1)), close + 1


def parse_inline_citation(
    text: str,
    offsets: tuple[int, ...],
    cursor: int,
    filename: str,
    source: str,
    token_span: SpanFactory,
) -> tuple[SurfaceCitationNode, int] | None:
    if not text.startswith("[^", cursor):
        return None
    close = closing_bracket(text, cursor + 2)
    if close is None:
        return None
    origin = token_span(cursor, close + 1)
    payload = CookedText.from_raw(text[cursor + 2 : close], offsets[cursor + 2 : close + 1])
    citation = citation_from_cooked_payload(payload, origin, source)
    if citation is None:
        return None
    return SurfaceCitationNode(citation.keys, dict(citation.kwargs), origin), close + 1


def parse_inline_math(
    text: str,
    cursor: int,
    token_span: SpanFactory,
) -> tuple[SurfaceInlineMathNode, int] | None:
    if not is_single_dollar(text, cursor):
        return None
    close = closing_math_dollar(text, cursor + 1)
    if close is None:
        return None
    return SurfaceInlineMathNode(text[cursor + 1 : close], token_span(cursor, close + 1)), close + 1


def conditional_start(line: str) -> str | None:
    for marker in ("!?!?", "!!?", "!?!", "!?"):
        if line.startswith(marker):
            return marker
    return None


def parse_code_fence(
    lines: list[str],
    index: int,
    offset: int,
    source: str,
    filename: str,
) -> tuple[CodeFenceNode, int, int]:
    opener = lines[index].rstrip("\n")
    fence = re.match(r"^(`{3,})(.*)$", opener)
    if not fence:
        raise MarkTeXError("malformed code fence", span(filename, offset, offset + len(opener), source))
    marker = fence.group(1)
    info = fence.group(2).strip()
    interpolated = info.startswith("$")
    language = info[1:].strip() if interpolated else info
    start_offset = offset
    index += 1
    offset += len(lines[index - 1])
    body: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.rstrip("\n") == marker:
            offset += len(line)
            index += 1
            return (
                CodeFenceNode(language, "".join(body), interpolated, span(filename, start_offset, offset, source)),
                index,
                offset,
            )
        body.append(line)
        offset += len(line)
        index += 1
    raise MarkTeXError("unclosed code fence", span(filename, start_offset, start_offset, source))


def parse_host_block(
    lines: list[str],
    index: int,
    offset: int,
    source: str,
    filename: str,
) -> tuple[HostBlockNode, int, int]:
    opener = lines[index].rstrip("\n")
    marker = re.match(r"^(\${3,})(.*)$", opener)
    if marker is None:
        raise MarkTeXError("malformed host block", span(filename, offset, offset + len(opener), source))
    fence = marker.group(1)
    language = marker.group(2).strip() or "python"
    start_offset = offset
    index += 1
    offset += len(lines[index - 1])
    body: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.rstrip("\n") == fence:
            offset += len(line)
            index += 1
            return (
                HostBlockNode(language, "".join(body).rstrip("\n"), span(filename, start_offset, offset, source)),
                index,
                offset,
            )
        body.append(line)
        offset += len(line)
        index += 1
    raise MarkTeXError("unclosed host block", span(filename, start_offset, start_offset, source))


def parse_math_block(
    lines: list[str],
    index: int,
    offset: int,
    source: str,
    filename: str,
) -> tuple[MathBlockNode, int, int]:
    start_offset = offset
    index += 1
    offset += len(lines[index - 1])
    body: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.rstrip("\n") == "$$":
            offset += len(line)
            index += 1
            return MathBlockNode("".join(body), span(filename, start_offset, offset, source)), index, offset
        body.append(line)
        offset += len(line)
        index += 1
    raise MarkTeXError("unclosed math block", span(filename, start_offset, start_offset, source))


def collect_control_payload(
    lines: list[str],
    index: int,
    offset: int,
    *,
    prefix_length: int,
    source: str,
    filename: str,
) -> tuple[str, SourceSpan, int, int]:
    start_offset = offset
    pieces: list[str] = []
    first = True
    end_offset = offset

    while index < len(lines):
        line = lines[index]
        text = line.rstrip("\n")
        line_start = offset
        payload = text[prefix_length:] if first else text
        if first:
            payload = payload.lstrip()
        first = False

        continuing = line.endswith("\n") and text.endswith("\\") and index + 1 < len(lines)
        pieces.append(payload + ("\n" if continuing else ""))
        end_offset = line_start + len(text)
        index += 1
        offset += len(line)
        if not continuing:
            break

    return "".join(pieces), span(filename, start_offset, end_offset, source), index, offset


def parse_rich_table(
    lines: list[str],
    index: int,
    offset: int,
    source: str,
    filename: str,
) -> tuple[MarkTeXRichTableNode, int, int]:
    opener = lines[index].rstrip("\n")
    marker = re.match(r"^(\+{3,})(.*)$", opener)
    if not marker:
        raise MarkTeXError("malformed rich table", span(filename, offset, offset + len(opener), source))
    fence = marker.group(1)
    raw_specs = split_unescaped_pipe_with_offsets(marker.group(2), offset + marker.start(2))
    stripped_specs = tuple(strip_cell_offsets(spec, offsets) for spec, offsets in raw_specs)
    column_specs = tuple(spec for spec, _offsets in stripped_specs if spec)
    column_spec_offsets = tuple(offsets for spec, offsets in stripped_specs if spec)
    if not column_specs:
        raise MarkTeXError("rich table requires at least one column", span(filename, offset, offset, source))

    start_offset = offset
    index += 1
    offset += len(lines[index - 1])
    rows: list[tuple[SegmentedLine, ...]] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.rstrip("\n")
        if stripped == fence:
            if not rows:
                raise MarkTeXError("rich table requires a header row", span(filename, start_offset, offset, source))
            offset += len(line)
            index += 1
            return (
                MarkTeXRichTableNode(
                    column_specs,
                    tuple("mos" for _spec in column_specs),
                    column_spec_offsets,
                    tuple(rows),
                    span(filename, start_offset, offset, source),
                ),
                index,
                offset,
            )
        if not stripped:
            raise MarkTeXError("blank lines are not allowed inside rich tables", span(filename, offset, offset, source))
        row_cells: list[SegmentedLine] = []
        for cell, cell_offsets in split_unescaped_pipe_with_offsets(stripped, offset):
            stripped_cell, stripped_offsets = strip_cell_offsets(cell, cell_offsets)
            row_cells.append(
                SegmentedLine.from_raw(stripped_cell, stripped_offsets, filename=filename, source=source)
            )
        cells = tuple(row_cells)
        if len(cells) != len(column_specs):
            raise MarkTeXError(
                f"rich table row has {len(cells)} cells; expected {len(column_specs)}",
                span(filename, offset, offset + len(stripped), source),
            )
        rows.append(cells)
        offset += len(line)
        index += 1
    raise MarkTeXError("unclosed rich table", span(filename, start_offset, start_offset, source))


def split_unescaped_pipe_with_offsets(text: str, base_offset: int) -> list[tuple[str, tuple[int, ...]]]:
    parts: list[tuple[str, tuple[int, ...]]] = []
    current: list[str] = []
    offsets: list[int] = [base_offset]
    index = 0
    while index < len(text):
        char = text[index]
        absolute = base_offset + index
        if char == "\\":
            if index + 1 < len(text) and text[index + 1] == "|":
                current.append("|")
                offsets.append(base_offset + index + 2)
                index += 2
            elif index + 1 < len(text):
                current.append("\\")
                current.append(text[index + 1])
                offsets.append(base_offset + index + 1)
                offsets.append(base_offset + index + 2)
                index += 2
            else:
                current.append("\\")
                offsets.append(absolute + 1)
                index += 1
        elif char == "|":
            parts.append(("".join(current), tuple(offsets)))
            current = []
            offsets = [absolute + 1]
            index += 1
        else:
            current.append(char)
            offsets.append(absolute + 1)
            index += 1
    parts.append(("".join(current), tuple(offsets)))
    return parts


def strip_cell_offsets(text: str, offsets: tuple[int, ...]) -> tuple[str, tuple[int, ...]]:
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    if end < start:
        end = start
    return text[start:end], offsets[start : end + 1]


def closing_bracket(text: str, start: int) -> int | None:
    depth = 1
    cursor = start
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == "\n":
            return None
        if text[cursor] == "[":
            depth += 1
        elif text[cursor] == "]":
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    return None


def is_single_dollar(text: str, cursor: int) -> bool:
    return (
        text[cursor] == "$"
        and (cursor == 0 or text[cursor - 1] != "$")
        and (cursor + 1 >= len(text) or text[cursor + 1] != "$")
    )


def closing_math_dollar(text: str, cursor: int) -> int | None:
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == "\n":
            return None
        if is_single_dollar(text, cursor):
            return cursor
        cursor += 1
    return None


def next_marktex_inline_special(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor] not in MARKTEX_INLINE_SPECIAL_CHARS:
        cursor += 1
    return cursor


SpanFactory: TypeAlias = Callable[[int, int], SourceSpan]
MARKTEX_INLINE_SPECIAL_CHARS = set("\\[`$")
span = span_from_range
