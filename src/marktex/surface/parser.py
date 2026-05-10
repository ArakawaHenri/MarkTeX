from __future__ import annotations

import re

from marktex.source import MarkTeXError, SourceSpan
from marktex.surface.grammar import FOOTNOTE_DEFINITION_RE
from marktex.surface.model import (
    CodeFenceNode,
    ConditionalNode,
    DocumentDirectiveNode,
    FootnoteDefinitionNode,
    HeadingNode,
    HostBlockNode,
    ParagraphNode,
    RichTableNode,
    ScopeCloseNode,
    ScopeOpenNode,
    SurfaceDocument,
    SurfaceNode,
)


def parse_surface(source: str, *, filename: str) -> SurfaceDocument:
    lines = source.splitlines(keepends=True)
    nodes: list[SurfaceNode] = []
    paragraph: list[str] = []
    paragraph_start = 0
    index = 0
    offset = 0

    def flush_paragraph(end_offset: int) -> None:
        nonlocal paragraph, paragraph_start
        if not paragraph:
            return
        text = " ".join(part for part in paragraph if part)
        if text:
            nodes.append(ParagraphNode(text, span(filename, paragraph_start, end_offset, source)))
        paragraph = []
        paragraph_start = end_offset

    while index < len(lines):
        line = lines[index]
        stripped_newline = line.rstrip("\n")
        line_start = offset

        if stripped_newline.startswith("```"):
            flush_paragraph(line_start)
            fence_node, index, offset = parse_code_fence(lines, index, offset, source, filename)
            nodes.append(fence_node)
            continue

        if stripped_newline.startswith("$$$"):
            flush_paragraph(line_start)
            host_node, index, offset = parse_host_block(lines, index, offset, source, filename)
            nodes.append(host_node)
            continue

        footnote = FOOTNOTE_DEFINITION_RE.match(stripped_newline)
        if footnote:
            flush_paragraph(line_start)
            nodes.append(
                FootnoteDefinitionNode(
                    footnote.group(1),
                    footnote.group(2),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        if stripped_newline.startswith("+++"):
            flush_paragraph(line_start)
            table_node, index, offset = parse_rich_table(lines, index, offset, source, filename)
            nodes.append(table_node)
            continue

        conditional_marker = conditional_start(stripped_newline)
        if conditional_marker is not None:
            flush_paragraph(line_start)
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
            flush_paragraph(line_start)
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
            flush_paragraph(line_start)
            nodes.append(
                DocumentDirectiveNode(
                    stripped_newline[2:].lstrip(),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        if stripped_newline.startswith("!@"):
            flush_paragraph(line_start)
            nodes.append(
                ScopeOpenNode(
                    stripped_newline[2:].lstrip(),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped_newline)
        if heading:
            flush_paragraph(line_start)
            raw_text = heading.group(2)
            leading_trim = len(raw_text) - len(raw_text.lstrip())
            text = raw_text.strip()
            text_start = line_start + heading.start(2) + leading_trim
            nodes.append(
                HeadingNode(
                    len(heading.group(1)),
                    text,
                    tuple(range(text_start, text_start + len(text) + 1)),
                    span(filename, line_start, line_start + len(stripped_newline), source),
                )
            )
            index += 1
            offset += len(line)
            continue

        if not stripped_newline.strip():
            flush_paragraph(line_start)
            index += 1
            offset += len(line)
            continue

        if not paragraph:
            paragraph_start = line_start
        if stripped_newline.endswith("\\"):
            paragraph.append(stripped_newline[:-1] + " ")
        else:
            paragraph.append(stripped_newline.strip())
        index += 1
        offset += len(line)

    flush_paragraph(offset)
    return SurfaceDocument(tuple(nodes))


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


def parse_rich_table(
    lines: list[str],
    index: int,
    offset: int,
    source: str,
    filename: str,
) -> tuple[RichTableNode, int, int]:
    opener = lines[index].rstrip("\n")
    marker = re.match(r"^(\+{3,})(.*)$", opener)
    if not marker:
        raise MarkTeXError("malformed rich table", span(filename, offset, offset + len(opener), source))
    fence = marker.group(1)
    column_specs = tuple(spec.strip() for spec in split_unescaped_pipe(marker.group(2).strip()))
    if not column_specs:
        raise MarkTeXError("rich table requires at least one column", span(filename, offset, offset, source))

    start_offset = offset
    index += 1
    offset += len(lines[index - 1])
    rows: list[tuple[str, ...]] = []
    cell_offsets: list[tuple[tuple[int, ...], ...]] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.rstrip("\n")
        if stripped == fence:
            if not rows:
                raise MarkTeXError("rich table requires a header row", span(filename, start_offset, offset, source))
            offset += len(line)
            index += 1
            return (
                RichTableNode(
                    column_specs,
                    tuple(rows),
                    tuple(cell_offsets),
                    span(filename, start_offset, offset, source),
                ),
                index,
                offset,
            )
        if not stripped:
            raise MarkTeXError("blank lines are not allowed inside rich tables", span(filename, offset, offset, source))
        row_cells: list[str] = []
        row_offsets: list[tuple[int, ...]] = []
        for cell, offsets in split_unescaped_pipe_with_offsets(stripped, offset):
            stripped_cell, stripped_offsets = strip_cell_offsets(cell, offsets)
            row_cells.append(stripped_cell)
            row_offsets.append(stripped_offsets)
        cells = tuple(row_cells)
        if len(cells) != len(column_specs):
            raise MarkTeXError(
                f"rich table row has {len(cells)} cells; expected {len(column_specs)}",
                span(filename, offset, offset + len(stripped), source),
            )
        rows.append(cells)
        cell_offsets.append(tuple(row_offsets))
        offset += len(line)
        index += 1
    raise MarkTeXError("unclosed rich table", span(filename, start_offset, start_offset, source))


def split_unescaped_pipe(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    parts.append("".join(current))
    return parts


def split_unescaped_pipe_with_offsets(text: str, base_offset: int) -> list[tuple[str, tuple[int, ...]]]:
    parts: list[tuple[str, tuple[int, ...]]] = []
    current: list[str] = []
    offsets: list[int] = [base_offset]
    index = 0
    while index < len(text):
        char = text[index]
        absolute = base_offset + index
        if char == "\\":
            if index + 1 < len(text):
                current.append(text[index + 1])
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


def span(filename: str, start: int, end: int, source: str) -> SourceSpan:
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start + 1 if last_newline == -1 else start - last_newline
    return SourceSpan(filename, start, end, line, column)
