from __future__ import annotations

import re
from dataclasses import dataclass

from marktex.source import MarkTeXError, SourceSpan
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
    marker_end: int
    content_start: int


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

            indented = parse_indented_code(lines, index, self.filename, self.source)
            if indented is not None:
                indented_node, index = indented
                nodes.append(indented_node)
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
                list_node, index = list_block
                nodes.append(list_node)
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

    def parse_list(self, lines: list[FallbackLine], index: int) -> tuple[ListBlockNode, int] | None:
        first_marker = list_marker(lines[index])
        if first_marker is None:
            return None
        ordered = first_marker.ordered
        start = first_marker.start
        items: list[ListItemNode] = []
        loose = False
        cursor = index

        while cursor < len(lines):
            marker = list_marker(lines[cursor])
            if marker is None or marker.ordered != ordered or marker.indent != first_marker.indent:
                break

            item_start = cursor
            consumed: list[FallbackLine] = [lines[cursor]]
            item_lines: list[FallbackLine] = [lines[cursor].slice(marker.content_start)]
            cursor += 1
            item_has_blank = False

            while cursor < len(lines):
                line = lines[cursor]
                next_marker = list_marker(line)
                if (
                    next_marker is not None
                    and next_marker.ordered == ordered
                    and next_marker.indent == first_marker.indent
                ):
                    break
                if is_blank(line):
                    consumed.append(line)
                    item_lines.append(FallbackLine("", (line.start,)))
                    item_has_blank = True
                    cursor += 1
                    continue
                if leading_spaces(line.text) <= first_marker.indent:
                    break
                consumed.append(line)
                item_lines.append(strip_continuation_indent(line, marker.content_start))
                cursor += 1

            item_lines = trim_blank_lines(item_lines)
            checked = parse_task_marker(item_lines)
            children = tuple(self.parse_blocks(item_lines))
            items.append(
                ListItemNode(
                    children,
                    checked,
                    span_from_lines(self.filename, consumed or [lines[item_start]], self.source),
                )
            )
            loose = loose or item_has_blank or len(children) > 1

        return (
            ListBlockNode(
                ordered,
                start,
                not loose,
                tuple(items),
                span_from_lines(self.filename, lines[index:cursor], self.source),
            ),
            cursor,
        )

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
        or is_indented_code_start(line)
        or is_thematic_break(line)
        or blockquote_content(line) is not None
        or list_marker(line) is not None
        or is_pipe_table_start(lines, index)
        or is_atx_heading_start(line)
    )


def parse_atx_heading(line: FallbackLine, filename: str, source: str) -> HeadingNode | None:
    match = re.match(r"^( {0,3})(#{1,6})(?:[ \t]+|$)(.*)$", line.text)
    if match is None:
        return None
    raw_start = match.start(3)
    raw_end = match.end(3)
    raw_text = match.group(3)
    closing = re.search(r"[ \t]+#+[ \t]*$", raw_text)
    if closing is not None:
        raw_end = raw_start + closing.start()
    text_line = line.slice(raw_start, raw_end)
    text_line = trim_line(text_line)
    return HeadingNode(
        len(match.group(2)),
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
    fence = match.group(2)
    marker = fence[0]
    length = len(fence)
    info = match.group(3).strip()
    if marker == "`" and "`" in info:
        return None
    interpolated = info.startswith("$")
    language = info[1:].strip() if interpolated else info
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        close = re.match(r"^( {0,3})([" + re.escape(marker) + r"]{" + str(length) + r",})[ \t]*$", line.text)
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


def parse_indented_code(
    lines: list[FallbackLine], index: int, filename: str, source: str
) -> tuple[CodeFenceNode, int] | None:
    if not is_indented_code_start(lines[index]):
        return None
    cursor = index
    consumed: list[FallbackLine] = []
    body: list[str] = []
    while cursor < len(lines):
        line = lines[cursor]
        if is_blank(line):
            consumed.append(line)
            body.append("")
            cursor += 1
            continue
        if indentation(line.text) < 4:
            break
        consumed.append(line)
        body.append(line.text[4:])
        cursor += 1
    while body and body[-1] == "":
        body.pop()
    return (
        CodeFenceNode("", "\n".join(body) + ("\n" if body else ""), False, span_from_lines(filename, consumed, source)),
        cursor,
    )


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
    while cursor < len(lines) and not is_blank(lines[cursor]) and "|" in lines[cursor].text:
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
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return LinkReferenceDefinitionNode(
        match.group(1),
        target,
        span_from_lines(filename, [line], source),
    )


def is_blank(line: FallbackLine) -> bool:
    return not line.text.strip()


def is_link_reference_start(line: FallbackLine) -> bool:
    return link_reference_match(line) is not None


def is_fenced_code_start(line: FallbackLine) -> bool:
    return fenced_code_open(line) is not None


def is_indented_code_start(line: FallbackLine) -> bool:
    return indentation(line.text) >= 4


def is_pipe_table_start(lines: list[FallbackLine], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index].text
        and alignment_cells(lines[index + 1]) is not None
    )


def is_atx_heading_start(line: FallbackLine) -> bool:
    return re.match(r"^( {0,3})(#{1,6})(?:[ \t]+|$)(.*)$", line.text) is not None


def fenced_code_open(line: FallbackLine) -> re.Match[str] | None:
    return re.match(r"^( {0,3})(`{3,}|~{3,})(.*)$", line.text)


def link_reference_match(line: FallbackLine) -> re.Match[str] | None:
    return re.match(r"^ {0,3}\[([^\]]+)\]:[ \t]*(\S+)(?:[ \t]+.*)?$", line.text)


def is_thematic_break(line: FallbackLine) -> bool:
    stripped = line.text.strip()
    if len(stripped) < 3:
        return False
    compact = stripped.replace(" ", "").replace("\t", "")
    return len(compact) >= 3 and compact[0] in "*-_" and set(compact) == {compact[0]}


def is_setext_underline(line: FallbackLine) -> bool:
    stripped = line.text.strip()
    return bool(stripped) and set(stripped) in ({"="}, {"-"})


def blockquote_content(line: FallbackLine) -> FallbackLine | None:
    match = re.match(r"^( {0,3})>[ \t]?", line.text)
    if match is None:
        return None
    return line.slice(match.end())


def list_marker(line: FallbackLine) -> _ListMarker | None:
    bullet = re.match(r"^( {0,3})([*+-])(?:[ \t]+|$)", line.text)
    if bullet is not None:
        marker_end = len(bullet.group(1)) + 1
        content_start = marker_end + post_marker_padding(line.text, marker_end)
        return _ListMarker(False, 1, len(bullet.group(1)), marker_end, content_start)
    ordered = re.match(r"^( {0,3})(\d{1,9})([.)])(?:[ \t]+|$)", line.text)
    if ordered is not None:
        marker_end = len(ordered.group(1)) + len(ordered.group(2)) + 1
        content_start = marker_end + post_marker_padding(line.text, marker_end)
        return _ListMarker(True, int(ordered.group(2)), len(ordered.group(1)), marker_end, content_start)
    return None


def post_marker_padding(text: str, marker_end: int) -> int:
    padding = 0
    index = marker_end
    while index < len(text) and text[index] in " \t" and padding < 4:
        padding += 4 if text[index] == "\t" else 1
        index += 1
    return index - marker_end if padding else 0


def strip_continuation_indent(line: FallbackLine, width: int) -> FallbackLine:
    index = min(width, len(line.text))
    if line.text[:index].strip():
        index = min(leading_spaces(line.text), len(line.text))
    return line.slice(index)


def parse_task_marker(lines: list[FallbackLine]) -> bool | None:
    if not lines:
        return None
    line = lines[0]
    match = re.match(r"^\[([ xX])\][ \t]+", line.text)
    if match is None:
        return None
    lines[0] = line.slice(match.end())
    return match.group(1).lower() == "x"


def split_pipe_row(line: FallbackLine) -> list[FallbackLine]:
    row = trim_line(line)
    parts = split_unescaped_pipe_with_offsets(row.text, row.offsets)
    if parts and parts[0].text == "":
        parts = parts[1:]
    if parts and parts[-1].text == "":
        parts = parts[:-1]
    return [trim_line(part) for part in parts]


def split_unescaped_pipe_with_offsets(text: str, offsets: tuple[int, ...]) -> list[FallbackLine]:
    parts: list[FallbackLine] = []
    current: list[str] = []
    current_offsets: list[int] = [offsets[0]]
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            current.append(text[index + 1])
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
        marker = cell.text.strip()
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


def trim_blank_lines(lines: list[FallbackLine]) -> list[FallbackLine]:
    start = 0
    end = len(lines)
    while start < end and is_blank(lines[start]):
        start += 1
    while end > start and is_blank(lines[end - 1]):
        end -= 1
    return lines[start:end]


def trim_line(line: FallbackLine) -> FallbackLine:
    start = len(line.text) - len(line.text.lstrip())
    end = len(line.text.rstrip())
    if end < start:
        end = start
    return line.slice(start, end)


def trim_paragraph_line(line: FallbackLine) -> FallbackLine:
    start = len(line.text) - len(line.text.lstrip())
    return line.slice(start)


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
    return span(filename, lines[0].start, lines[-1].end, source)


def span(filename: str, start: int, end: int, source: str) -> SourceSpan:
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start + 1 if last_newline == -1 else start - last_newline
    return SourceSpan(filename, start, end, line, column)


def indentation(text: str) -> int:
    width = 0
    for char in text:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            break
    return width


def leading_spaces(text: str) -> int:
    return len(text) - len(text.lstrip(" "))
