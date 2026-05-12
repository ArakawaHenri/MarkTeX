from __future__ import annotations

import re
from dataclasses import dataclass
from math import gcd

from marktex.source import MarkTeXError, SourceSpan, span_from_range
from marktex.surface.model import (
    BlockQuoteNode,
    CodeFenceNode,
    HeadingNode,
    LinkReferenceDefinitionNode,
    ListBlockNode,
    ListItemNode,
    ParagraphNode,
    RichTableNode,
    SurfaceNode,
    ThematicBreakNode,
)


@dataclass(frozen=True)
class FallbackLine:
    text: str
    offsets: tuple[int, ...]

    @property
    def start(self) -> int:
        return self.offsets[0]

    @property
    def end(self) -> int:
        return self.offsets[-1]

    @classmethod
    def from_source_line(cls, line: str, start: int) -> FallbackLine:
        text = line.rstrip("\n")
        return cls(text, tuple(range(start, start + len(text) + 1)))

    def slice(self, start: int, end: int | None = None) -> FallbackLine:
        resolved_end = len(self.text) if end is None else end
        return FallbackLine(self.text[start:resolved_end], self.offsets[start : resolved_end + 1])


@dataclass(frozen=True)
class _ListMarker:
    ordered: bool
    start: int
    indent: int
    indent_kind: str | None
    marker_end: int
    content_start: int


@dataclass
class _ListItemBuilder:
    marker: _ListMarker
    consumed: list[FallbackLine]
    segments: list[object]
    has_blank: bool = False


@dataclass
class _ListBlockBuilder:
    ordered: bool
    start: int
    items: list[_ListItemBuilder]
    lines: list[FallbackLine]


def parse_fallback_lines(lines: list[FallbackLine], *, filename: str, source: str) -> tuple[SurfaceNode, ...]:
    return tuple(_FallbackParser(filename, source).parse_blocks(lines))


class _FallbackParser:
    def __init__(self, filename: str, source: str) -> None:
        self.filename = filename
        self.source = source

    def parse_blocks(self, lines: list[FallbackLine]) -> list[SurfaceNode]:
        nodes: list[SurfaceNode] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if is_blank(line):
                index += 1
                continue

            link_ref = parse_link_reference(line, self.filename, self.source)
            if link_ref is not None:
                nodes.append(link_ref)
                index += 1
                continue

            fence = parse_fenced_code(lines, index, self.filename, self.source)
            if fence is not None:
                fence_node, index = fence
                nodes.append(fence_node)
                continue

            if is_thematic_break(line):
                nodes.append(ThematicBreakNode(span_from_lines(self.filename, [line], self.source)))
                index += 1
                continue

            quote = self.parse_blockquote(lines, index)
            if quote is not None:
                quote_node, index = quote
                nodes.append(quote_node)
                continue

            list_block = self.parse_list(lines, index)
            if list_block is not None:
                list_nodes, index = list_block
                nodes.extend(list_nodes)
                continue

            table = parse_pipe_table(lines, index, self.filename, self.source)
            if table is not None:
                table_node, index = table
                nodes.append(table_node)
                continue

            atx = parse_atx_heading(line, self.filename, self.source)
            if atx is not None:
                nodes.append(atx)
                index += 1
                continue

            paragraph_node, index = self.parse_paragraph(lines, index)
            nodes.append(paragraph_node)
        return nodes

    def parse_blockquote(
        self, lines: list[FallbackLine], index: int
    ) -> tuple[BlockQuoteNode, int] | None:
        if blockquote_content(lines[index]) is None:
            return None
        consumed: list[FallbackLine] = []
        inner: list[FallbackLine] = []
        cursor = index
        while cursor < len(lines):
            line = lines[cursor]
            content = blockquote_content(line)
            if content is not None:
                consumed.append(line)
                inner.append(content)
                cursor += 1
                continue
            if is_blank(line):
                consumed.append(line)
                inner.append(FallbackLine("", (line.start,)))
                cursor += 1
                continue
            break
        return (
            BlockQuoteNode(
                tuple(self.parse_blocks(inner)),
                span_from_lines(self.filename, consumed, self.source),
            ),
            cursor,
        )

    def parse_list(self, lines: list[FallbackLine], index: int) -> tuple[list[ListBlockNode], int] | None:
        first_marker = list_marker(lines[index])
        if first_marker is None or first_marker.indent != 0:
            return None
        run, cursor = collect_list_run(lines, index)
        markers = [(position, marker) for position, line in enumerate(run) if (marker := list_marker(line)) is not None]
        unit, indent_kind = list_indent_unit(markers, run, self.filename, self.source)
        root_segments: list[object] = []
        stack: list[_ListItemBuilder] = []
        consumed_count = 0

        for line in run:
            marker = list_marker(line)
            if marker is not None:
                level = list_marker_level(marker, unit)
                if level > len(stack):
                    raise MarkTeXError("list nesting cannot skip levels", span_from_lines(self.filename, [line], self.source))
                parent_segments = root_segments if level == 0 else stack[level - 1].segments
                block = current_list_block(parent_segments, marker, line, self.filename, self.source)
                item = _ListItemBuilder(
                    marker,
                    [line],
                    [line.slice(marker.content_start)],
                )
                block.items.append(item)
                block.lines.append(line)
                stack = stack[:level]
                stack.append(item)
                consumed_count += 1
                continue

            if not stack:
                break
            cont_item = continuation_item(stack, line, indent_kind, self.filename, self.source)
            if cont_item is None:
                break
            cont_item.consumed.append(line)
            if is_blank(line):
                cont_item.segments.append(FallbackLine("", (line.start,)))
                cont_item.has_blank = True
                consumed_count += 1
                continue
            cont_item.segments.append(line.slice(cont_item.marker.content_start))
            consumed_count += 1

        return [
            self.finalize_list_block(block)
            for block in root_segments
            if isinstance(block, _ListBlockBuilder)
        ], index + consumed_count

    def finalize_list_block(self, block: _ListBlockBuilder) -> ListBlockNode:
        item_nodes: list[ListItemNode] = []
        loose = False
        for item in block.items:
            children, checked = self.finalize_list_item_segments(item.segments)
            item_nodes.append(
                ListItemNode(
                    tuple(children),
                    checked,
                    span_from_lines(self.filename, item.consumed, self.source),
                )
            )
            loose = loose or item.has_blank or len(children) > 1
        return ListBlockNode(
            block.ordered,
            block.start,
            not loose,
            tuple(item_nodes),
            span_from_lines(self.filename, block.lines, self.source),
        )

    def finalize_list_item_segments(self, segments: list[object]) -> tuple[list[SurfaceNode], bool | None]:
        normalized = list(segments)
        checked: bool | None = None
        if normalized and isinstance(normalized[0], FallbackLine):
            checked, normalized[0] = parse_task_marker(normalized[0])
        children: list[SurfaceNode] = []
        line_group: list[FallbackLine] = []
        for segment in normalized:
            if isinstance(segment, FallbackLine):
                line_group.append(segment)
                continue
            if line_group:
                children.extend(self.parse_blocks(trim_blank_lines(line_group)))
                line_group = []
            if isinstance(segment, _ListBlockBuilder):
                children.append(self.finalize_list_block(segment))
                continue
            raise MarkTeXError(f"unsupported list segment: {segment!r}")
        if line_group:
            children.extend(self.parse_blocks(trim_blank_lines(line_group)))
        return children, checked

    def parse_paragraph(self, lines: list[FallbackLine], index: int) -> tuple[SurfaceNode, int]:
        paragraph: list[FallbackLine] = []
        cursor = index
        while cursor < len(lines):
            line = lines[cursor]
            if is_blank(line):
                break
            if paragraph and is_setext_underline(line):
                text, offsets = join_paragraph_lines(paragraph)
                return (
                    HeadingNode(
                        1 if line.text.strip().startswith("=") else 2,
                        text,
                        offsets,
                        span_from_lines(self.filename, paragraph + [line], self.source),
                    ),
                    cursor + 1,
                )
            if paragraph and starts_block(lines, cursor):
                break
            paragraph.append(trim_paragraph_line(line))
            cursor += 1
        text, offsets = join_paragraph_lines(paragraph)
        return (
            ParagraphNode(
                text,
                span_from_lines(self.filename, lines[index:cursor], self.source),
                offsets,
            ),
            cursor,
        )


def starts_block(lines: list[FallbackLine], index: int) -> bool:
    line = lines[index]
    if is_blank(line):
        return True
    return (
        is_link_reference_start(line)
        or is_fenced_code_start(line)
        or is_thematic_break(line)
        or blockquote_content(line) is not None
        or list_marker(line) is not None
        or is_pipe_table_start(lines, index)
        or is_atx_heading_start(line)
    )


def parse_atx_heading(line: FallbackLine, filename: str, source: str) -> HeadingNode | None:
    match = re.match(r"^(#{1,6}) (.*)$", line.text)
    if match is None:
        return None
    text_line = line.slice(match.start(2), match.end(2))
    return HeadingNode(
        len(match.group(1)),
        text_line.text,
        text_line.offsets,
        span_from_lines(filename, [line], source),
    )


def parse_fenced_code(
    lines: list[FallbackLine], index: int, filename: str, source: str
) -> tuple[CodeFenceNode, int] | None:
    opener = lines[index]
    match = fenced_code_open(opener)
    if match is None:
        return None
    fence = match.group(1)
    marker = fence[0]
    length = len(fence)
    info = match.group(2).strip()
    if marker == "`" and "`" in info:
        return None
    interpolated = info.startswith("$")
    language = info[1:].strip() if interpolated else info
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        close = re.match(r"^([" + re.escape(marker) + r"]{" + str(length) + r",})$", line.text)
        if close is not None:
            return (
                CodeFenceNode(
                    language,
                    "\n".join(body) + ("\n" if body else ""),
                    interpolated,
                    span_from_lines(filename, lines[index : cursor + 1], source),
                ),
                cursor + 1,
            )
        body.append(line.text)
        cursor += 1
    raise MarkTeXError("unclosed code fence", span_from_lines(filename, lines[index:], source))


def parse_pipe_table(
    lines: list[FallbackLine], index: int, filename: str, source: str
) -> tuple[RichTableNode, int] | None:
    if not is_pipe_table_start(lines, index):
        return None
    alignments = alignment_cells(lines[index + 1])
    if alignments is None:
        return None
    header_cells = split_pipe_row(lines[index])
    if len(header_cells) != len(alignments):
        raise MarkTeXError(
            f"pipe table row has {len(header_cells)} cells; expected {len(alignments)}",
            span_from_lines(filename, [lines[index]], source),
        )
    rows: list[tuple[str, ...]] = []
    offsets: list[tuple[tuple[int, ...], ...]] = []
    header, header_offsets = strict_table_row(header_cells, len(alignments))
    rows.append(header)
    offsets.append(header_offsets)
    cursor = index + 2
    while cursor < len(lines) and not is_blank(lines[cursor]) and lines[cursor].text.startswith("|"):
        cells_raw = split_pipe_row(lines[cursor])
        if len(cells_raw) != len(alignments):
            raise MarkTeXError(
                f"pipe table row has {len(cells_raw)} cells; expected {len(alignments)}",
                span_from_lines(filename, [lines[cursor]], source),
            )
        cells, cell_offsets = strict_table_row(cells_raw, len(alignments))
        rows.append(cells)
        offsets.append(cell_offsets)
        cursor += 1
    return (
        RichTableNode(
            tuple(align for align, _offsets in alignments),
            tuple("pipe-align" for _align, _offsets in alignments),
            tuple(offsets for _align, offsets in alignments),
            tuple(rows),
            tuple(offsets),
            span_from_lines(filename, lines[index:cursor], source),
        ),
        cursor,
    )


def parse_link_reference(line: FallbackLine, filename: str, source: str) -> LinkReferenceDefinitionNode | None:
    match = link_reference_match(line)
    if match is None:
        return None
    target = match.group(2)
    trailing = match.group(3) or ""
    if trailing.strip():
        raise MarkTeXError("unsupported link title", span_from_lines(filename, [line], source))
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return LinkReferenceDefinitionNode(
        match.group(1),
        target,
        span_from_lines(filename, [line], source),
    )


def is_blank(line: FallbackLine) -> bool:
    return line.text == ""


def is_link_reference_start(line: FallbackLine) -> bool:
    return link_reference_match(line) is not None


def is_fenced_code_start(line: FallbackLine) -> bool:
    return fenced_code_open(line) is not None


def is_pipe_table_start(lines: list[FallbackLine], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].text.startswith("|")
        and alignment_cells(lines[index + 1]) is not None
    )


def is_atx_heading_start(line: FallbackLine) -> bool:
    return re.match(r"^(#{1,6}) (.*)$", line.text) is not None


def fenced_code_open(line: FallbackLine) -> re.Match[str] | None:
    return re.match(r"^(`{3,}|~{3,})(.*)$", line.text)


def link_reference_match(line: FallbackLine) -> re.Match[str] | None:
    return re.match(r"^\[([^\]]+)\]:[ \t]*(\S+)([ \t]+.*)?$", line.text)


def is_thematic_break(line: FallbackLine) -> bool:
    return line.text in {"---", "***", "___"}


def is_setext_underline(line: FallbackLine) -> bool:
    return bool(line.text) and set(line.text) in ({"="}, {"-"})


def blockquote_content(line: FallbackLine) -> FallbackLine | None:
    if line.text == ">":
        return line.slice(1)
    if not line.text.startswith("> "):
        return None
    return line.slice(2)


def list_marker(line: FallbackLine) -> _ListMarker | None:
    bullet = re.match(r"^([ \t]*)([*+-]) (.*)$", line.text)
    if bullet is not None:
        indent_text = bullet.group(1)
        indent_width, indent_kind = structural_indent(indent_text)
        marker_end = len(indent_text) + 1
        return _ListMarker(False, 1, indent_width, indent_kind, marker_end, marker_end + 1)
    ordered = re.match(r"^([ \t]*)(\d{1,9})([.)]) (.*)$", line.text)
    if ordered is not None:
        indent_text = ordered.group(1)
        indent_width, indent_kind = structural_indent(indent_text)
        marker_end = len(indent_text) + len(ordered.group(2)) + 1
        return _ListMarker(True, int(ordered.group(2)), indent_width, indent_kind, marker_end, marker_end + 1)
    return None


def parse_task_marker(line: FallbackLine) -> tuple[bool | None, FallbackLine]:
    match = re.match(r"^\[([ xX])\] ", line.text)
    if match is None:
        return None, line
    return match.group(1).lower() == "x", line.slice(match.end())


def collect_list_run(lines: list[FallbackLine], index: int) -> tuple[list[FallbackLine], int]:
    run: list[FallbackLine] = []
    cursor = index
    while cursor < len(lines):
        line = lines[cursor]
        marker = list_marker(line)
        if marker is not None:
            run.append(line)
            cursor += 1
            continue
        if is_blank(line):
            break
        if leading_indent(line.text):
            run.append(line)
            cursor += 1
            continue
        break
    return run, cursor


def list_indent_unit(
    markers: list[tuple[int, _ListMarker]],
    lines: list[FallbackLine],
    filename: str,
    source: str,
) -> tuple[int, str | None]:
    for position, marker in markers:
        if marker.indent_kind == "mixed":
            raise MarkTeXError(
                "list indentation cannot mix tabs and spaces",
                span_from_lines(filename, [lines[position]], source),
            )
    kinds = {marker.indent_kind for _position, marker in markers if marker.indent_kind is not None}
    if len(kinds) > 1:
        first_mixed = next(position for position, marker in markers if marker.indent_kind in kinds)
        raise MarkTeXError(
            "list indentation cannot mix tabs and spaces",
            span_from_lines(filename, [lines[first_mixed]], source),
        )
    positive = [marker.indent for _position, marker in markers if marker.indent > 0]
    unit = 0
    for value in positive:
        unit = value if unit == 0 else gcd(unit, value)
    return unit, next(iter(kinds)) if kinds else None


def list_marker_level(marker: _ListMarker, unit: int) -> int:
    if marker.indent == 0:
        return 0
    if unit == 0:
        return 0
    return marker.indent // unit


def current_list_block(
    segments: list[object],
    marker: _ListMarker,
    line: FallbackLine,
    filename: str,
    source: str,
) -> _ListBlockBuilder:
    if segments and isinstance(segments[-1], _ListBlockBuilder) and segments[-1].ordered == marker.ordered:
        block = segments[-1]
        if block.ordered:
            expected = block.start + len(block.items)
            if marker.start != expected:
                raise MarkTeXError(
                    f"ordered list marker must be {expected}",
                    span_from_lines(filename, [line], source),
                )
        return block
    block = _ListBlockBuilder(marker.ordered, marker.start, [], [])
    segments.append(block)
    return block


def continuation_item(
    stack: list[_ListItemBuilder],
    line: FallbackLine,
    indent_kind: str | None,
    filename: str,
    source: str,
) -> _ListItemBuilder | None:
    if is_blank(line):
        return stack[-1]
    kind = leading_indent_kind(line.text, span_from_lines(filename, [line], source))
    if kind is not None and indent_kind is not None and kind != indent_kind:
        raise MarkTeXError("list indentation cannot mix tabs and spaces", span_from_lines(filename, [line], source))
    for item in reversed(stack):
        if has_structural_prefix(line.text, item.marker.content_start):
            return item
    return None


def structural_indent(text: str) -> tuple[int, str | None]:
    if " " in text and "\t" in text:
        return len(text), "mixed"
    if not text:
        return 0, None
    return len(text), "tab" if text[0] == "\t" else "space"


def leading_indent(text: str) -> str:
    return text[: len(text) - len(text.lstrip(" \t"))]


def leading_indent_kind(text: str, origin: SourceSpan) -> str | None:
    indent = leading_indent(text)
    if " " in indent and "\t" in indent:
        raise MarkTeXError("list indentation cannot mix tabs and spaces", origin)
    if not indent:
        return None
    return "tab" if indent[0] == "\t" else "space"


def has_structural_prefix(text: str, width: int) -> bool:
    return len(text) >= width and bool(text[:width]) and all(char in " \t" for char in text[:width])


def split_pipe_row(line: FallbackLine) -> list[FallbackLine]:
    if not line.text.startswith("|") or not line.text.endswith("|"):
        return []
    row = line.slice(1, len(line.text) - 1)
    parts = split_unescaped_pipe_with_offsets(row.text, row.offsets)
    return [consume_cell_padding(part) for part in parts]


def split_unescaped_pipe_with_offsets(text: str, offsets: tuple[int, ...]) -> list[FallbackLine]:
    parts: list[FallbackLine] = []
    current: list[str] = []
    current_offsets: list[int] = [offsets[0]]
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and text[index + 1] == "|":
            current.append("|")
            current_offsets.append(offsets[index + 2])
            index += 2
            continue
        if char == "|":
            parts.append(FallbackLine("".join(current), tuple(current_offsets)))
            current = []
            current_offsets = [offsets[index + 1]]
            index += 1
            continue
        current.append(char)
        current_offsets.append(offsets[index + 1])
        index += 1
    parts.append(FallbackLine("".join(current), tuple(current_offsets)))
    return parts


def alignment_cells(line: FallbackLine) -> tuple[tuple[str, tuple[int, ...]], ...] | None:
    cells = split_pipe_row(line)
    if not cells:
        return None
    aligns: list[tuple[str, tuple[int, ...]]] = []
    for cell in cells:
        marker = cell.text
        if not re.fullmatch(r":?-+:?", marker):
            return None
        if marker.startswith(":") and marker.endswith(":"):
            aligns.append(("center", cell.offsets))
        elif marker.endswith(":"):
            aligns.append(("right", cell.offsets))
        else:
            aligns.append(("left", cell.offsets))
    return tuple(aligns)


def strict_table_row(
    cells: list[FallbackLine], count: int
) -> tuple[tuple[str, ...], tuple[tuple[int, ...], ...]]:
    return tuple(cell.text for cell in cells[:count]), tuple(cell.offsets for cell in cells[:count])


def consume_cell_padding(cell: FallbackLine) -> FallbackLine:
    start = 1 if cell.text.startswith(" ") else 0
    end = len(cell.text) - 1 if cell.text.endswith(" ") and len(cell.text) > start else len(cell.text)
    return cell.slice(start, end)


def trim_blank_lines(lines: list[FallbackLine]) -> list[FallbackLine]:
    start = 0
    end = len(lines)
    while start < end and is_blank(lines[start]):
        start += 1
    while end > start and is_blank(lines[end - 1]):
        end -= 1
    return lines[start:end]


def trim_paragraph_line(line: FallbackLine) -> FallbackLine:
    return line


def join_paragraph_lines(lines: list[FallbackLine]) -> tuple[str, tuple[int, ...]]:
    if not lines:
        return "", (0,)
    text = lines[0].text
    offsets = list(lines[0].offsets)
    for line in lines[1:]:
        text += "\n" + line.text
        offsets.append(line.offsets[0])
        offsets.extend(line.offsets[1:])
    return text, tuple(offsets)


def span_from_lines(filename: str, lines: list[FallbackLine], source: str) -> SourceSpan:
    if not lines:
        return SourceSpan(filename, 0, 0)
    return span_from_range(filename, lines[0].start, lines[-1].end, source)
