from __future__ import annotations

import re
from dataclasses import dataclass
from math import gcd
from typing import TypeAlias

from marktex.source import CookedText, MarkTeXError, SourceSpan, span_from_range
from marktex.surface.grammar import is_footnote_label
from marktex.surface.marktex_layer import (
    LinePart,
    MarkTeXFallbackRun,
    MarkTeXLayerDocument,
    MarkTeXRichTableNode,
    RawTextSegment,
    SegmentedLine,
)
from marktex.surface.model import (
    BlockQuoteNode,
    FootnoteDefinitionNode,
    HeadingNode,
    LinkReferenceDefinitionNode,
    ListBlockNode,
    ListItemNode,
    ParagraphNode,
    RichTableNode,
    SurfaceEmphasisNode,
    SurfaceFootnoteRefNode,
    SurfaceImageNode,
    SurfaceInlineNode,
    SurfaceLineBreakNode,
    SurfaceLinkNode,
    SurfaceNode,
    SurfaceReferenceImageNode,
    SurfaceReferenceLinkNode,
    SurfaceStrikethroughNode,
    SurfaceStrongNode,
    SurfaceTextNode,
    ThematicBreakNode,
)


@dataclass(frozen=True)
class FallbackLayerDocument:
    nodes: tuple[SurfaceNode, ...]


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
    consumed: list[SegmentedLine]
    segments: list[object]
    has_blank: bool = False


@dataclass
class _ListBlockBuilder:
    ordered: bool
    start: int
    items: list[_ListItemBuilder]
    lines: list[SegmentedLine]


@dataclass(frozen=True)
class RawChar:
    value: str
    escaped: bool
    start: int
    end: int


@dataclass(frozen=True)
class LineContinuation:
    start: int
    end: int


TapeAtom: TypeAlias = RawChar | LineContinuation | SurfaceInlineNode


def parse_fallback_layer(
    document: MarkTeXLayerDocument,
    *,
    filename: str,
    source: str,
) -> FallbackLayerDocument:
    parser = _FallbackParser(filename, source)
    nodes: list[SurfaceNode] = []
    for node in document.nodes:
        if isinstance(node, MarkTeXFallbackRun):
            nodes.extend(parser.parse_blocks(list(node.lines)))
        elif isinstance(node, MarkTeXRichTableNode):
            nodes.append(table_from_marktex_table(node, filename, source))
        else:
            nodes.append(node)
    return FallbackLayerDocument(tuple(nodes))


def table_from_marktex_table(
    node: MarkTeXRichTableNode,
    filename: str,
    source: str,
) -> RichTableNode:
    return RichTableNode(
        node.column_specs,
        node.column_spec_kinds,
        node.column_spec_offsets,
        tuple(tuple(inline_content(cell.parts, filename, source) for cell in row) for row in node.rows),
        node.origin,
    )


class _FallbackParser:
    def __init__(self, filename: str, source: str) -> None:
        self.filename = filename
        self.source = source

    def parse_blocks(self, lines: list[SegmentedLine]) -> list[SurfaceNode]:
        nodes: list[SurfaceNode] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if is_blank(line):
                index += 1
                continue

            footnote = parse_footnote_definition(line, self.filename, self.source)
            if footnote is not None:
                nodes.append(footnote)
                index += 1
                continue

            link_ref = parse_link_reference(line, self.filename, self.source)
            if link_ref is not None:
                nodes.append(link_ref)
                index += 1
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
        self,
        lines: list[SegmentedLine],
        index: int,
    ) -> tuple[BlockQuoteNode, int] | None:
        if blockquote_content(lines[index]) is None:
            return None
        consumed: list[SegmentedLine] = []
        inner: list[SegmentedLine] = []
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
                inner.append(SegmentedLine.empty(line.start))
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

    def parse_list(self, lines: list[SegmentedLine], index: int) -> tuple[list[ListBlockNode], int] | None:
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
                    raise MarkTeXError(
                        "list nesting cannot skip levels",
                        span_from_lines(self.filename, [line], self.source),
                    )
                parent_segments = root_segments if level == 0 else stack[level - 1].segments
                block = current_list_block(parent_segments, marker, line, self.filename, self.source)
                item = _ListItemBuilder(
                    marker,
                    [line],
                    [line.drop_prefix_chars(marker.content_start)],
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
                cont_item.segments.append(SegmentedLine.empty(line.start))
                cont_item.has_blank = True
                consumed_count += 1
                continue
            cont_item.segments.append(line.drop_prefix_chars(cont_item.marker.content_start))
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
        if normalized and isinstance(normalized[0], SegmentedLine):
            checked, normalized[0] = parse_task_marker(normalized[0])
        children: list[SurfaceNode] = []
        line_group: list[SegmentedLine] = []
        for segment in normalized:
            if isinstance(segment, SegmentedLine):
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

    def parse_paragraph(self, lines: list[SegmentedLine], index: int) -> tuple[SurfaceNode, int]:
        paragraph: list[SegmentedLine] = []
        cursor = index
        while cursor < len(lines):
            line = lines[cursor]
            if is_blank(line):
                break
            if paragraph and is_setext_underline(line):
                level = 1 if line.raw_text.startswith("=") else 2
                return (
                    HeadingNode(
                        level,
                        inline_content(join_paragraph_parts(paragraph), self.filename, self.source),
                        span_from_lines(self.filename, paragraph + [line], self.source),
                    ),
                    cursor + 1,
                )
            if paragraph and starts_block(lines, cursor):
                break
            paragraph.append(line)
            cursor += 1
        return (
            ParagraphNode(
                inline_content(join_paragraph_parts(paragraph), self.filename, self.source),
                span_from_lines(self.filename, lines[index:cursor], self.source),
            ),
            cursor,
        )


class _FallbackInlineParser:
    def __init__(
        self,
        atoms: tuple[TapeAtom, ...],
        filename: str,
        source: str,
    ) -> None:
        self.atoms = atoms
        self.filename = filename
        self.source = source

    def parse_range(self, start: int, end: int) -> tuple[SurfaceInlineNode, ...]:
        nodes: list[SurfaceInlineNode] = []
        cursor = start
        while cursor < end:
            atom = self.atoms[cursor]
            if isinstance(atom, LineContinuation):
                cursor += 1
                continue
            if not isinstance(atom, RawChar):
                nodes.append(atom)
                cursor += 1
                continue
            if atom.escaped:
                nodes.append(SurfaceTextNode(atom.value, self.token_span(cursor, cursor + 1)))
                cursor += 1
                continue
            if atom.value == "\n":
                nodes.append(SurfaceLineBreakNode(True, self.token_span(cursor, cursor + 1)))
                cursor += 1
                continue
            parsed = (
                self.parse_image(cursor, end)
                or self.parse_reference(cursor, end)
                or self.parse_strikethrough(cursor, end)
                or self.parse_strong(cursor, end)
                or self.parse_emphasis(cursor, end)
            )
            if parsed is not None:
                node, cursor = parsed
                nodes.append(node)
                continue
            next_special = self.next_special(cursor + 1, end)
            nodes.append(SurfaceTextNode(self.raw_text(cursor, next_special), self.token_span(cursor, next_special)))
            cursor = next_special
        if not nodes:
            return (SurfaceTextNode("", self.empty_span(start, end)),)
        return tuple(nodes)

    def parse_child(self, start: int, end: int) -> tuple[SurfaceInlineNode, ...]:
        return _FallbackInlineParser(self.atoms, self.filename, self.source).parse_range(start, end)

    def parse_image(self, cursor: int, end: int) -> tuple[SurfaceInlineNode, int] | None:
        if not self.raw_startswith(cursor, "!["):
            return None
        label_start = cursor + 2
        label_end = self.find_closing_bracket(label_start - 1, self.physical_line_end(cursor, end))
        if label_end is None:
            return None
        direct_target = self.link_target_after(label_end, end)
        if direct_target is not None:
            destination, next_cursor = direct_target
            alt = self.raw_text_or_none(label_start, label_end)
            if alt is None:
                return None
            return SurfaceImageNode(alt, destination, self.token_span(cursor, next_cursor)), next_cursor
        ref_target = self.reference_label_after(cursor + 1, label_end, end)
        if ref_target is None:
            return None
        label, next_cursor = ref_target
        alt = self.raw_text_or_none(label_start, label_end)
        if alt is None:
            return None
        return (
            SurfaceReferenceImageNode(
                alt,
                label,
                self.raw_text(cursor, next_cursor),
                self.token_span(cursor, next_cursor),
            ),
            next_cursor,
        )

    def parse_reference(self, cursor: int, end: int) -> tuple[SurfaceInlineNode, int] | None:
        if not self.raw_char_is(cursor, "["):
            return None
        if self.raw_startswith(cursor, "[^"):
            close = self.find_closing_bracket(cursor, self.physical_line_end(cursor, end))
            if close is None:
                return None
            label = self.raw_text_or_none(cursor + 2, close)
            if label is None or not is_footnote_label(label):
                return None
            return SurfaceFootnoteRefNode(label, self.token_span(cursor, close + 1)), close + 1

        label_end = self.find_closing_bracket(cursor, self.physical_line_end(cursor, end))
        if label_end is None:
            return None
        direct_target = self.link_target_after(label_end, end)
        if direct_target is not None:
            destination, next_cursor = direct_target
            return (
                SurfaceLinkNode(
                    self.parse_child(cursor + 1, label_end),
                    destination,
                    self.token_span(cursor, next_cursor),
                ),
                next_cursor,
            )
        ref_target = self.reference_label_after(cursor, label_end, end)
        if ref_target is None:
            return None
        label, next_cursor = ref_target
        return (
            SurfaceReferenceLinkNode(
                self.parse_child(cursor + 1, label_end),
                label,
                self.raw_text(cursor, next_cursor),
                self.token_span(cursor, next_cursor),
            ),
            next_cursor,
        )

    def parse_strikethrough(self, cursor: int, end: int) -> tuple[SurfaceInlineNode, int] | None:
        if not self.raw_startswith(cursor, "~~"):
            return None
        close = self.find_closing_pair(cursor + 2, self.physical_line_end(cursor, end), "~~")
        if close is None:
            return None
        return SurfaceStrikethroughNode(self.parse_child(cursor + 2, close), self.token_span(cursor, close + 2)), close + 2

    def parse_strong(self, cursor: int, end: int) -> tuple[SurfaceInlineNode, int] | None:
        for marker in ("**", "__"):
            if self.raw_startswith(cursor, marker):
                close = self.find_closing_pair(cursor + 2, self.physical_line_end(cursor, end), marker)
                if close is not None:
                    return SurfaceStrongNode(self.parse_child(cursor + 2, close), self.token_span(cursor, close + 2)), close + 2
        return None

    def parse_emphasis(self, cursor: int, end: int) -> tuple[SurfaceInlineNode, int] | None:
        marker = self.raw_char(cursor)
        if marker not in {"*", "_"} or self.raw_char_is(cursor + 1, marker):
            return None
        close = self.find_closing_pair(cursor + 1, self.physical_line_end(cursor, end), marker)
        if close is None:
            return None
        return SurfaceEmphasisNode(self.parse_child(cursor + 1, close), self.token_span(cursor, close + 1)), close + 1

    def link_target_after(self, label_end: int, end: int) -> tuple[str, int] | None:
        if not self.raw_char_is(label_end + 1, "("):
            return None
        close = self.find_closing_paren(label_end + 1, self.physical_line_end(label_end + 1, end))
        if close is None:
            return None
        raw = self.raw_text_or_none(label_end + 2, close)
        if raw is None:
            return None
        destination = normalize_link_destination(raw)
        if not destination:
            return None
        if link_destination_has_title(raw):
            raise MarkTeXError("unsupported link title", self.token_span(label_end + 1, close + 1))
        return destination, close + 1

    def reference_label_after(
        self,
        label_start: int,
        label_end: int,
        end: int,
    ) -> tuple[str, int] | None:
        if self.raw_char_is(label_end + 1, "["):
            close = self.find_closing_bracket(label_end + 1, self.physical_line_end(label_end + 1, end))
            if close is None:
                return None
            raw_label = self.raw_text_or_none(label_end + 2, close)
            if raw_label is None:
                return None
            if raw_label == "":
                raw_label = self.raw_text_or_none(label_start + 1, label_end)
                if raw_label is None:
                    return None
            return raw_label, close + 1
        raw_label = self.raw_text_or_none(label_start + 1, label_end)
        if raw_label is None:
            return None
        return raw_label, label_end + 1

    def find_closing_bracket(self, open_bracket: int, end: int) -> int | None:
        depth = 0
        cursor = open_bracket
        while cursor < end:
            if self.raw_char_is(cursor, "["):
                depth += 1
            elif self.raw_char_is(cursor, "]"):
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        return None

    def find_closing_paren(self, open_paren: int, end: int) -> int | None:
        depth = 0
        cursor = open_paren
        while cursor < end:
            if self.raw_char_is(cursor, "("):
                depth += 1
            elif self.raw_char_is(cursor, ")"):
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        return None

    def find_closing_pair(self, cursor: int, end: int, marker: str) -> int | None:
        while cursor < end:
            if self.raw_startswith(cursor, marker):
                return cursor
            cursor += 1
        return None

    def physical_line_end(self, cursor: int, end: int) -> int:
        while cursor < end:
            atom = self.atoms[cursor]
            if isinstance(atom, LineContinuation):
                return cursor
            if self.raw_char_is(cursor, "\n", unescaped=False):
                return cursor
            cursor += 1
        return end

    def next_special(self, cursor: int, end: int) -> int:
        while cursor < end:
            atom = self.atoms[cursor]
            if isinstance(atom, LineContinuation):
                break
            if not isinstance(atom, RawChar):
                break
            if atom.escaped:
                break
            if atom.value in FALLBACK_INLINE_SPECIAL_CHARS and not atom.escaped:
                break
            cursor += 1
        return cursor

    def raw_char(self, index: int) -> str:
        if index < 0 or index >= len(self.atoms):
            return ""
        atom = self.atoms[index]
        return atom.value if isinstance(atom, RawChar) and not atom.escaped else ""

    def raw_char_is(self, index: int, value: str, *, unescaped: bool = True) -> bool:
        if index < 0 or index >= len(self.atoms):
            return False
        atom = self.atoms[index]
        if not isinstance(atom, RawChar) or atom.value != value:
            return False
        return not atom.escaped if unescaped else True

    def raw_startswith(self, index: int, value: str) -> bool:
        if index + len(value) > len(self.atoms):
            return False
        return all(self.raw_char_is(index + offset, char) for offset, char in enumerate(value))

    def raw_text(self, start: int, end: int) -> str:
        text = self.raw_text_or_none(start, end)
        if text is None:
            raise ValueError("range contains a MarkTeX inline island")
        return text

    def raw_text_or_none(self, start: int, end: int) -> str | None:
        chars: list[str] = []
        for atom in self.atoms[start:end]:
            if not isinstance(atom, RawChar):
                return None
            chars.append(atom.value)
        return "".join(chars)

    def token_span(self, start: int, end: int) -> SourceSpan:
        if start >= end:
            return self.empty_span(start, end)
        return span_from_range(self.filename, atom_start(self.atoms[start]), atom_end(self.atoms[end - 1]), self.source)

    def empty_span(self, start: int, end: int) -> SourceSpan:
        if start < len(self.atoms):
            offset = atom_start(self.atoms[start])
        elif end > 0 and end - 1 < len(self.atoms):
            offset = atom_end(self.atoms[end - 1])
        else:
            offset = 0
        return span_from_range(self.filename, offset, offset, self.source)


def inline_content(
    parts: tuple[LinePart, ...] | list[LinePart],
    filename: str,
    source: str,
) -> tuple[SurfaceInlineNode, ...]:
    atoms = tape_from_parts(parts)
    return _FallbackInlineParser(atoms, filename, source).parse_range(0, len(atoms))


def tape_from_parts(parts: tuple[LinePart, ...] | list[LinePart]) -> tuple[TapeAtom, ...]:
    atoms: list[TapeAtom] = []
    raw_text: list[str] = []
    raw_offsets: list[int] = []

    def flush_raw() -> None:
        nonlocal raw_text, raw_offsets
        if not raw_text:
            return
        text = "".join(raw_text)
        offsets = tuple(raw_offsets)
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\\":
                index += 1
                if index >= len(text):
                    atoms.append(RawChar("\\", True, offsets[index - 1], offsets[index]))
                    continue
                if text[index] == "\n":
                    atoms.append(LineContinuation(offsets[index - 1], offsets[index + 1]))
                    index += 1
                    continue
                atoms.append(RawChar(text[index], True, offsets[index - 1], offsets[index + 1]))
                index += 1
                continue
            atoms.append(RawChar(char, False, offsets[index], offsets[index + 1]))
            index += 1
        raw_text = []
        raw_offsets = []

    for part in parts:
        if isinstance(part, RawTextSegment):
            if not raw_offsets:
                raw_offsets.extend(part.offsets)
            else:
                raw_offsets.extend(part.offsets[1:])
            raw_text.append(part.text)
        else:
            flush_raw()
            atoms.append(part)
    flush_raw()
    return tuple(atoms)


def starts_block(lines: list[SegmentedLine], index: int) -> bool:
    line = lines[index]
    if is_blank(line):
        return True
    return (
        is_footnote_definition_start(line)
        or is_link_reference_start(line)
        or is_thematic_break(line)
        or blockquote_content(line) is not None
        or list_marker(line) is not None
        or is_pipe_table_start(lines, index)
        or is_atx_heading_start(line)
    )


def parse_atx_heading(line: SegmentedLine, filename: str, source: str) -> HeadingNode | None:
    match = re.match(r"^(#{1,6}) ", line.raw_prefix)
    if match is None:
        return None
    content = line.drop_prefix_chars(match.end())
    return HeadingNode(
        len(match.group(1)),
        inline_content(content.parts, filename, source),
        span_from_lines(filename, [line], source),
    )


def parse_pipe_table(
    lines: list[SegmentedLine],
    index: int,
    filename: str,
    source: str,
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
    rows: list[tuple[tuple[SurfaceInlineNode, ...], ...]] = []
    rows.append(tuple(inline_content(cell, filename, source) for cell in strict_table_row(header_cells, len(alignments))))
    cursor = index + 2
    while cursor < len(lines) and not is_blank(lines[cursor]) and line_startswith_raw(lines[cursor], "|"):
        cells_raw = split_pipe_row(lines[cursor])
        if len(cells_raw) != len(alignments):
            raise MarkTeXError(
                f"pipe table row has {len(cells_raw)} cells; expected {len(alignments)}",
                span_from_lines(filename, [lines[cursor]], source),
            )
        rows.append(tuple(inline_content(cell, filename, source) for cell in strict_table_row(cells_raw, len(alignments))))
        cursor += 1
    return (
        RichTableNode(
            tuple(align for align, _offsets in alignments),
            tuple("pipe-align" for _align, _offsets in alignments),
            tuple(offsets for _align, offsets in alignments),
            tuple(rows),
            span_from_lines(filename, lines[index:cursor], source),
        ),
        cursor,
    )


def parse_link_reference(line: SegmentedLine, filename: str, source: str) -> LinkReferenceDefinitionNode | None:
    parsed = link_reference_parts(line)
    if parsed is None:
        return None
    label, target, trailing = parsed
    if trailing.strip():
        raise MarkTeXError("unsupported link title", span_from_lines(filename, [line], source))
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return LinkReferenceDefinitionNode(label, target, span_from_lines(filename, [line], source))


def parse_footnote_definition(line: SegmentedLine, filename: str, source: str) -> FootnoteDefinitionNode | None:
    parsed = footnote_definition_parts(line)
    if parsed is None:
        return None
    label, body_parts = parsed
    if not label:
        return None
    return FootnoteDefinitionNode(
        label,
        inline_content(body_parts, filename, source),
        span_from_lines(filename, [line], source),
    )


def is_blank(line: SegmentedLine) -> bool:
    return line.is_blank()


def is_footnote_definition_start(line: SegmentedLine) -> bool:
    return footnote_definition_parts(line) is not None


def is_link_reference_start(line: SegmentedLine) -> bool:
    return link_reference_parts(line) is not None


def is_pipe_table_start(lines: list[SegmentedLine], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and line_startswith_raw(lines[index], "|")
        and alignment_cells(lines[index + 1]) is not None
    )


def is_atx_heading_start(line: SegmentedLine) -> bool:
    return re.match(r"^(#{1,6}) ", line.raw_prefix) is not None


def link_reference_parts(line: SegmentedLine) -> tuple[str, str, str] | None:
    if not line.all_raw or line.raw_text.startswith("[^"):
        return None
    cooked = CookedText.from_raw(line.raw_text, line.raw_offsets)
    if not cooked.startswith("["):
        return None
    close = cooked.find_unescaped("]", 1)
    if close <= 1:
        return None
    if close + 1 >= len(cooked.text) or not cooked.char_is(close + 1, ":"):
        return None
    cursor = close + 2
    while cursor < len(cooked.text) and cooked.text[cursor] in {" ", "\t"}:
        cursor += 1
    if cursor >= len(cooked.text):
        return None
    target_start = cursor
    if cooked.text[cursor] == "<":
        target_end = cooked.find_unescaped(">", cursor + 1)
        if target_end == -1:
            return None
        target = cooked.text[target_start : target_end + 1]
        trailing = cooked.text[target_end + 1 :]
    else:
        while cursor < len(cooked.text) and cooked.text[cursor] not in {" ", "\t"}:
            cursor += 1
        target = cooked.text[target_start:cursor]
        trailing = cooked.text[cursor:]
    return cooked.text[1:close], target, trailing


def footnote_definition_parts(line: SegmentedLine) -> tuple[str, tuple[LinePart, ...]] | None:
    raw_prefix, raw_offsets = raw_prefix_text_offsets(line)
    cooked = CookedText.from_raw(raw_prefix, raw_offsets)
    if not cooked.startswith("[^"):
        return None
    close = cooked.find_unescaped("]", 2)
    if close <= 2:
        return None
    if close + 1 >= len(cooked.text) or not cooked.char_is(close + 1, ":"):
        return None
    body_start = close + 2
    if body_start < len(cooked.text) and cooked.text[body_start] == " ":
        body_start += 1
    label = cooked.text[2:close]
    return label, line_parts_from_offset(line, cooked.offsets[body_start])


def is_thematic_break(line: SegmentedLine) -> bool:
    return line.all_raw and line.raw_text in {"---", "***", "___"}


def is_setext_underline(line: SegmentedLine) -> bool:
    return line.all_raw and bool(line.raw_text) and set(line.raw_text) in ({"="}, {"-"})


def blockquote_content(line: SegmentedLine) -> SegmentedLine | None:
    if line.raw_prefix == ">":
        return line.drop_prefix_chars(1)
    if not line.raw_prefix.startswith("> "):
        return None
    return line.drop_prefix_chars(2)


def list_marker(line: SegmentedLine) -> _ListMarker | None:
    bullet = re.match(r"^([ \t]*)([*+-]) ", line.raw_prefix)
    if bullet is not None:
        indent_text = bullet.group(1)
        indent_width, indent_kind = structural_indent(indent_text)
        marker_end = len(indent_text) + 1
        return _ListMarker(False, 1, indent_width, indent_kind, marker_end, marker_end + 1)
    ordered = re.match(r"^([ \t]*)(\d{1,9})([.)]) ", line.raw_prefix)
    if ordered is not None:
        indent_text = ordered.group(1)
        indent_width, indent_kind = structural_indent(indent_text)
        marker_end = len(indent_text) + len(ordered.group(2)) + 1
        return _ListMarker(True, int(ordered.group(2)), indent_width, indent_kind, marker_end, marker_end + 1)
    return None


def parse_task_marker(line: SegmentedLine) -> tuple[bool | None, SegmentedLine]:
    match = re.match(r"^\[([ xX])\] ", line.raw_prefix)
    if match is None:
        return None, line
    return match.group(1).lower() == "x", line.drop_prefix_chars(match.end())


def collect_list_run(lines: list[SegmentedLine], index: int) -> tuple[list[SegmentedLine], int]:
    run: list[SegmentedLine] = []
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
        if leading_indent(line.raw_prefix):
            run.append(line)
            cursor += 1
            continue
        break
    return run, cursor


def list_indent_unit(
    markers: list[tuple[int, _ListMarker]],
    lines: list[SegmentedLine],
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
    if marker.indent == 0 or unit == 0:
        return 0
    return marker.indent // unit


def current_list_block(
    segments: list[object],
    marker: _ListMarker,
    line: SegmentedLine,
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
    line: SegmentedLine,
    indent_kind: str | None,
    filename: str,
    source: str,
) -> _ListItemBuilder | None:
    if is_blank(line):
        return stack[-1]
    kind = leading_indent_kind(line.raw_prefix, span_from_lines(filename, [line], source))
    if kind is not None and indent_kind is not None and kind != indent_kind:
        raise MarkTeXError("list indentation cannot mix tabs and spaces", span_from_lines(filename, [line], source))
    for item in reversed(stack):
        if has_structural_prefix(line.raw_prefix, item.marker.content_start):
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


def split_pipe_row(line: SegmentedLine) -> list[tuple[LinePart, ...]]:
    if not line_startswith_raw(line, "|"):
        return []
    cells: list[list[LinePart]] = []
    current: list[LinePart] = []
    started = False
    trailing: list[LinePart] = []

    def append_raw(text: str, offsets: tuple[int, ...]) -> None:
        target = current if started else trailing
        if target and isinstance(target[-1], RawTextSegment):
            previous = target[-1]
            target[-1] = RawTextSegment(previous.text + text, previous.offsets[:-1] + offsets)
        else:
            target.append(RawTextSegment(text, offsets))

    for part in line.parts:
        if not isinstance(part, RawTextSegment):
            (current if started else trailing).append(part)
            continue
        index = 0
        while index < len(part.text):
            char = part.text[index]
            if char == "\\" and index + 1 < len(part.text) and part.text[index + 1] == "|":
                append_raw("|", (part.offsets[index], part.offsets[index + 2]))
                index += 2
                continue
            if char == "|":
                if not started:
                    started = True
                    current = []
                else:
                    cells.append(current)
                    current = []
                index += 1
                continue
            append_raw(char, part.offsets[index : index + 2])
            index += 1

    if not started or has_content(current):
        return []
    return [tuple(consume_cell_padding(cell)) for cell in cells]


def alignment_cells(line: SegmentedLine) -> tuple[tuple[str, tuple[int, ...]], ...] | None:
    cells = split_pipe_row(line)
    if not cells:
        return None
    aligns: list[tuple[str, tuple[int, ...]]] = []
    for cell in cells:
        if not all(isinstance(part, RawTextSegment) for part in cell):
            return None
        text, offsets = raw_parts_text_offsets(cell)
        if not re.fullmatch(r":?-+:?", text):
            return None
        if text.startswith(":") and text.endswith(":"):
            aligns.append(("center", offsets))
        elif text.endswith(":"):
            aligns.append(("right", offsets))
        else:
            aligns.append(("left", offsets))
    return tuple(aligns)


def strict_table_row(cells: list[tuple[LinePart, ...]], count: int) -> tuple[tuple[LinePart, ...], ...]:
    return tuple(cells[:count])


def consume_cell_padding(cell: list[LinePart]) -> list[LinePart]:
    result = list(cell)
    if result and isinstance(result[0], RawTextSegment) and result[0].text.startswith(" "):
        first = result[0].slice(1)
        result = ([first] if first.text else []) + result[1:]
    if result and isinstance(result[-1], RawTextSegment) and result[-1].text.endswith(" "):
        last = result[-1].slice(0, len(result[-1].text) - 1)
        result = result[:-1] + ([last] if last.text else [])
    return result


def trim_blank_lines(lines: list[SegmentedLine]) -> list[SegmentedLine]:
    start = 0
    end = len(lines)
    while start < end and is_blank(lines[start]):
        start += 1
    while end > start and is_blank(lines[end - 1]):
        end -= 1
    return lines[start:end]


def join_paragraph_parts(lines: list[SegmentedLine]) -> tuple[LinePart, ...]:
    if not lines:
        return ()
    parts: list[LinePart] = []
    for index, line in enumerate(lines):
        if index:
            previous = lines[index - 1]
            parts.append(RawTextSegment("\n", (previous.end, line.start)))
        parts.extend(line.parts)
    return tuple(parts)


def raw_parts_text_offsets(parts: tuple[LinePart, ...] | list[LinePart]) -> tuple[str, tuple[int, ...]]:
    text: list[str] = []
    offsets: list[int] = []
    for part in parts:
        if not isinstance(part, RawTextSegment):
            raise ValueError("parts contain a MarkTeX inline island")
        if not offsets:
            offsets.extend(part.offsets)
        else:
            offsets.extend(part.offsets[1:])
        text.append(part.text)
    return "".join(text), tuple(offsets) if offsets else (0,)


def raw_prefix_text_offsets(line: SegmentedLine) -> tuple[str, tuple[int, ...]]:
    text: list[str] = []
    offsets: list[int] = []
    for part in line.parts:
        if not isinstance(part, RawTextSegment):
            break
        if not offsets:
            offsets.extend(part.offsets)
        else:
            offsets.extend(part.offsets[1:])
        text.append(part.text)
    return "".join(text), tuple(offsets) if offsets else (line.start,)


def line_parts_from_offset(line: SegmentedLine, offset: int) -> tuple[LinePart, ...]:
    parts: list[LinePart] = []
    for part in line.parts:
        if isinstance(part, RawTextSegment):
            if part.end <= offset:
                continue
            if part.start >= offset:
                parts.append(part)
                continue
            index = next(
                (position for position, source_offset in enumerate(part.offsets) if source_offset >= offset),
                len(part.text),
            )
            if index < len(part.text):
                parts.append(part.slice(index))
            continue
        if part.origin.end <= offset:
            continue
        if part.origin.start >= offset:
            parts.append(part)
    return tuple(parts)


def line_startswith_raw(line: SegmentedLine, value: str) -> bool:
    return line.raw_prefix.startswith(value)


def has_content(parts: list[LinePart]) -> bool:
    for part in parts:
        if isinstance(part, RawTextSegment):
            if part.text:
                return True
        else:
            return True
    return False


def atom_start(atom: TapeAtom) -> int:
    if isinstance(atom, RawChar | LineContinuation):
        return atom.start
    return atom.origin.start


def atom_end(atom: TapeAtom) -> int:
    if isinstance(atom, RawChar | LineContinuation):
        return atom.end
    return atom.origin.end


def span_from_lines(filename: str, lines: list[SegmentedLine], source: str) -> SourceSpan:
    if not lines:
        return SourceSpan(filename, 0, 0)
    return span_from_range(filename, lines[0].start, lines[-1].end, source)


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
    return " ".join(CookedText.from_raw(label).text.split()).casefold()


FALLBACK_INLINE_SPECIAL_CHARS = set("\n![*_~")
