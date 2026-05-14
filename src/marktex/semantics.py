from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal, Mapping

from marktex.core import (
    Block,
    BlockQuote,
    Citation,
    Conditional,
    Document,
    DocumentPatch,
    FootnoteDefinition,
    FootnoteRef,
    Heading,
    InlineNode,
    LineBreak,
    ListBlock,
    PageSetup,
    ScopeClose,
    ScopePush,
    Table,
)
from marktex.mos import CallUnit, MosValue, RawString
from marktex.reference import CITATION_KWARGS
from marktex.source import MarkTeXError, SourceSpan
from marktex.surface.grammar import is_footnote_label


@dataclass(frozen=True)
class PageSizePreset:
    height: str
    width: str


PAGE_SIZE_PRESETS: Mapping[str, PageSizePreset] = {
    "A4": PageSizePreset(height="297mm", width="210mm"),
    "A5": PageSizePreset(height="210mm", width="148mm"),
    "Letter": PageSizePreset(height="11in", width="8.5in"),
}
DEFAULT_PAGE_SIZE = PAGE_SIZE_PRESETS["A4"]
PAGE_SIZE_PRESET_LOOKUP = {key.casefold(): key for key in PAGE_SIZE_PRESETS}
ORIENTATIONS = frozenset(("portrait", "landscape"))
MARGIN_KEYS = frozenset(("top", "bottom", "left", "right"))
LAYOUT_KWARGS = frozenset(("width", "height", "orientation", *MARGIN_KEYS))
TABLE_ALIGNMENTS = frozenset(("left", "center", "right"))
DOCUMENT_RESOURCE_HEADS = frozenset(("bib", "bib+", "bib-"))
DOCUMENT_STYLE_HEADS = frozenset(("bibstyle", "citestyle"))
CITATION_STYLE_MODES = frozenset(("numeric", "author-year", "author-page", "note"))
CITATION_STYLE_FORMS = frozenset(("square", "superscript", "paren", "footnote", "plain"))
DIMENSION_RE = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)(?:pt|bp|mm|cm|in|pc|em|ex)$")
DIMENSION_TO_PT = {
    "pt": 1.0,
    "bp": 72.27 / 72.0,
    "mm": 72.27 / 25.4,
    "cm": 72.27 / 2.54,
    "in": 72.27,
    "pc": 12.0,
}
DocumentDirectiveBodyEffect = Literal["none", "page_break", "page_setup"]
DocumentDirectiveEventPolicy = Literal["always", "before_content", "never"]
LayoutOperationKind = Literal["size", "width", "height", "orientation", "margins"]


@dataclass(frozen=True)
class DocumentDirectiveSpec:
    body_effect: DocumentDirectiveBodyEffect
    event_policy: DocumentDirectiveEventPolicy


@dataclass(frozen=True)
class DocumentDirectiveResult:
    call: CallUnit | None
    layout: PageLayout
    body_effect: DocumentDirectiveBodyEffect
    event_policy: DocumentDirectiveEventPolicy


@dataclass(frozen=True)
class LayoutOperation:
    kind: LayoutOperationKind
    origin: SourceSpan | None = None
    width: str | None = None
    height: str | None = None
    orientation: str | None = None
    margins: Mapping[str, str] | None = None


DOCUMENT_DIRECTIVE_SPECS = {
    "layout": DocumentDirectiveSpec("page_setup", "before_content"),
    "margin": DocumentDirectiveSpec("page_setup", "before_content"),
    "bib": DocumentDirectiveSpec("none", "always"),
    "bib+": DocumentDirectiveSpec("none", "always"),
    "bib-": DocumentDirectiveSpec("none", "always"),
    "bibstyle": DocumentDirectiveSpec("none", "always"),
    "citestyle": DocumentDirectiveSpec("none", "always"),
    "newpage": DocumentDirectiveSpec("page_break", "never"),
}


@dataclass(frozen=True)
class PageLayout:
    width: str = DEFAULT_PAGE_SIZE.width
    height: str = DEFAULT_PAGE_SIZE.height
    margins: dict[str, str] | None = None

    def margin_dict(self) -> dict[str, str]:
        return dict(self.margins or {})

    def with_size(self, width: str, height: str) -> PageLayout:
        return replace(self, width=width, height=height)

    def with_margins(self, margins: dict[str, str]) -> PageLayout:
        merged = self.margin_dict()
        merged.update(margins)
        return replace(self, margins=merged)


def normalize_choice(
    raw: str,
    allowed: frozenset[str],
    label: str,
    origin: SourceSpan | None = None,
    *,
    aliases: dict[str, str] | None = None,
    casefold: bool = True,
) -> str:
    value = raw.strip()
    lookup = value.casefold() if casefold else value
    if aliases is not None:
        mapped = aliases.get(lookup)
        if mapped is not None:
            return mapped
    if lookup in allowed:
        return lookup
    expected = ", ".join(sorted(allowed))
    raise MarkTeXError(f"unsupported {label}: {value}; expected one of {expected}", origin)


def raw_text(value: MosValue, label: str, origin: SourceSpan | None = None) -> str:
    if isinstance(value, RawString):
        return value.text
    raise MarkTeXError(f"{label} must be a raw string", value_origin(value) or origin)


def value_origin(value: object) -> SourceSpan | None:
    return getattr(value, "origin", None)


def normalize_page_size_preset(raw: str, origin: SourceSpan | None = None) -> str:
    value = raw.strip()
    preset = PAGE_SIZE_PRESET_LOOKUP.get(value.casefold())
    if preset is not None:
        return preset
    expected = ", ".join(PAGE_SIZE_PRESETS)
    raise MarkTeXError(f"unsupported page size preset: {value}; expected one of {expected}", origin)


def page_size(raw: str, origin: SourceSpan | None = None) -> tuple[str, str]:
    preset = PAGE_SIZE_PRESETS[normalize_page_size_preset(raw, origin)]
    return preset.width, preset.height


def normalize_orientation(raw: str, origin: SourceSpan | None = None) -> str:
    return normalize_choice(raw, ORIENTATIONS, "orientation", origin)


def normalize_dimension(raw: str, label: str, origin: SourceSpan | None = None) -> str:
    value = raw.strip()
    if not DIMENSION_RE.fullmatch(value):
        raise MarkTeXError(f"invalid {label} dimension: {value}", origin)
    return value


def apply_orientation(layout: PageLayout, orientation: str, origin: SourceSpan | None = None) -> PageLayout:
    order = dimension_order(layout.width, layout.height, origin)
    if orientation == "portrait" and order <= 0:
        return layout
    if orientation == "landscape" and order >= 0:
        return layout
    return layout.with_size(layout.height, layout.width)


def dimension_order(width: str, height: str, origin: SourceSpan | None = None) -> int:
    parsed_width = parse_dimension(width)
    parsed_height = parse_dimension(height)
    if parsed_width is None or parsed_height is None:
        raise MarkTeXError(f"cannot compare dimensions for orientation: {width}, {height}", origin)
    width_points = dimension_points(parsed_width)
    height_points = dimension_points(parsed_height)
    if width_points is None or height_points is None:
        if parsed_width[1] != parsed_height[1]:
            raise MarkTeXError(f"cannot compare dimensions for orientation: {width}, {height}", origin)
        width_points = parsed_width[0]
        height_points = parsed_height[0]
    if width_points == height_points:
        return 0
    return 1 if width_points > height_points else -1


def parse_dimension(value: str) -> tuple[float, str] | None:
    match = re.fullmatch(r"((?:\d+(?:\.\d+)?)|\.\d+)([A-Za-z]+)", value.strip())
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def dimension_points(parsed: tuple[float, str]) -> float | None:
    factor = DIMENSION_TO_PT.get(parsed[1])
    if factor is None:
        return None
    return parsed[0] * factor


def apply_layout_call(call: CallUnit, layout: PageLayout) -> tuple[CallUnit, PageLayout]:
    unknown = sorted(set(call.kwargs) - LAYOUT_KWARGS)
    if unknown:
        raise MarkTeXError(f"unknown layout kwargs: {', '.join(unknown)}", call.origin)

    next_layout = layout
    for operation in layout_operations(call):
        next_layout = apply_layout_operation(next_layout, operation)

    return layout_call_from_state(next_layout, call.origin), next_layout


def layout_operations(call: CallUnit) -> tuple[LayoutOperation, ...]:
    indexed_operations: list[tuple[int, int, LayoutOperation]] = []
    fallback_index = 0

    for arg in call.args:
        for operation in layout_arg_operations(arg, call.origin):
            indexed_operations.append((operation_sort_key(operation, fallback_index), fallback_index, operation))
            fallback_index += 1

    for key, value in call.kwargs.items():
        operation = layout_kwarg_operation(key, value, call.origin)
        indexed_operations.append((operation_sort_key(operation, fallback_index), fallback_index, operation))
        fallback_index += 1

    return tuple(operation for _, _, operation in sorted(indexed_operations))


def operation_sort_key(operation: LayoutOperation, fallback: int) -> int:
    if operation.origin is not None:
        return operation.origin.start
    return fallback


def layout_kwarg_operation(key: str, value: MosValue, origin: SourceSpan | None) -> LayoutOperation:
    value_span = value_origin(value)
    if key == "width":
        return LayoutOperation(
            "width",
            value_span,
            width=normalize_dimension(raw_text(value, "width", origin), "width", value_span),
        )
    if key == "height":
        return LayoutOperation(
            "height",
            value_span,
            height=normalize_dimension(raw_text(value, "height", origin), "height", value_span),
        )
    if key == "orientation":
        return LayoutOperation(
            "orientation",
            value_span,
            orientation=normalize_orientation(raw_text(value, "orientation", origin), value_span),
        )
    if key in MARGIN_KEYS:
        return LayoutOperation(
            "margins",
            value_span,
            margins={
                key: normalize_dimension(raw_text(value, key, origin), key, value_span),
            },
        )
    raise MarkTeXError(f"unknown layout kwargs: {key}", origin)


def layout_arg_operations(arg: MosValue, origin: SourceSpan | None) -> tuple[LayoutOperation, ...]:
    if isinstance(arg, RawString):
        text = arg.text.strip()
        try:
            width, height = page_size(text, arg.origin)
            return (LayoutOperation("size", arg.origin, width=width, height=height),)
        except MarkTeXError:
            try:
                return (
                    LayoutOperation(
                        "orientation",
                        arg.origin,
                        orientation=normalize_orientation(text, arg.origin),
                    ),
                )
            except MarkTeXError as exc:
                raise MarkTeXError(f"unsupported layout argument: {text}", arg.origin) from exc
    if isinstance(arg, CallUnit):
        unknown = sorted(set(arg.kwargs) - LAYOUT_KWARGS)
        if unknown:
            raise MarkTeXError(f"unknown layout kwargs: {', '.join(unknown)}", arg.origin or origin)
        if arg.args:
            raise MarkTeXError("unsupported nested layout argument", arg.origin or origin)
        if set(arg.kwargs) == {"width", "height"}:
            width_origin = value_origin(arg.kwargs["width"])
            height_origin = value_origin(arg.kwargs["height"])
            return (
                LayoutOperation(
                    "size",
                    arg.origin,
                    width=normalize_dimension(raw_text(arg.kwargs["width"], "width", arg.origin), "width", width_origin),
                    height=normalize_dimension(
                        raw_text(arg.kwargs["height"], "height", arg.origin),
                        "height",
                        height_origin,
                    ),
                ),
            )
        if arg.kwargs:
            operations = tuple(layout_kwarg_operation(key, value, arg.origin or origin) for key, value in arg.kwargs.items())
            return operations
        if arg.head:
            try:
                width, height = page_size(arg.head, arg.origin)
                return (LayoutOperation("size", arg.origin, width=width, height=height),)
            except MarkTeXError:
                try:
                    return (
                        LayoutOperation(
                            "orientation",
                            arg.origin,
                            orientation=normalize_orientation(arg.head, arg.origin),
                        ),
                    )
                except MarkTeXError as exc:
                    raise MarkTeXError(f"unsupported layout argument: {arg.head}", arg.origin or origin) from exc
    raise MarkTeXError("unsupported layout argument", value_origin(arg) or origin)


def apply_layout_operation(layout: PageLayout, operation: LayoutOperation) -> PageLayout:
    if operation.kind == "size":
        if operation.width is None or operation.height is None:
            raise MarkTeXError("internal layout size operation is incomplete", operation.origin)
        return layout.with_size(operation.width, operation.height)
    if operation.kind == "width":
        if operation.width is None:
            raise MarkTeXError("internal layout width operation is incomplete", operation.origin)
        return layout.with_size(operation.width, layout.height)
    if operation.kind == "height":
        if operation.height is None:
            raise MarkTeXError("internal layout height operation is incomplete", operation.origin)
        return layout.with_size(layout.width, operation.height)
    if operation.kind == "orientation":
        if operation.orientation is None:
            raise MarkTeXError("internal layout orientation operation is incomplete", operation.origin)
        return apply_orientation(layout, operation.orientation, operation.origin)
    if operation.kind == "margins":
        return layout.with_margins(dict(operation.margins or {}))
    raise MarkTeXError(f"unknown layout operation: {operation.kind}", operation.origin)


def apply_margin_call(call: CallUnit, layout: PageLayout) -> tuple[CallUnit, PageLayout]:
    if call.args:
        raise MarkTeXError("margin does not accept positional arguments", call.origin)
    unknown = sorted(set(call.kwargs) - MARGIN_KEYS)
    if unknown:
        raise MarkTeXError(f"unknown margin kwargs: {', '.join(unknown)}", call.origin)
    margins = {
        key: normalize_dimension(raw_text(value, key, call.origin), key, value_origin(value))
        for key, value in call.kwargs.items()
    }
    next_layout = layout.with_margins(margins)
    return margin_call(margins, call.origin), next_layout


def layout_call_from_state(layout: PageLayout, origin: SourceSpan | None = None) -> CallUnit:
    kwargs: dict[str, MosValue] = {
        "width": RawString(layout.width, origin),
        "height": RawString(layout.height, origin),
        **{key: RawString(value, origin) for key, value in layout.margin_dict().items()},
    }
    return CallUnit("document", "layout", kwargs=kwargs, origin=origin)


def margin_call(margins: dict[str, str], origin: SourceSpan | None = None) -> CallUnit:
    kwargs: dict[str, MosValue] = {key: RawString(value, origin) for key, value in margins.items()}
    return CallUnit(
        "document",
        "margin",
        kwargs=kwargs,
        origin=origin,
    )


def page_setup_from_layout(layout: PageLayout, origin: SourceSpan | None = None) -> PageSetup:
    return PageSetup(layout.width, layout.height, layout.margin_dict(), origin)


def plan_document_directive_call(call: CallUnit, layout: PageLayout) -> DocumentDirectiveResult:
    spec = DOCUMENT_DIRECTIVE_SPECS.get(call.head, DocumentDirectiveSpec("none", "always"))
    if call.head == "layout":
        canonical, next_layout = apply_layout_call(call, layout)
        return DocumentDirectiveResult(canonical, next_layout, spec.body_effect, spec.event_policy)
    if call.head == "margin":
        canonical, next_layout = apply_margin_call(call, layout)
        return DocumentDirectiveResult(canonical, next_layout, spec.body_effect, spec.event_policy)
    if call.head in DOCUMENT_RESOURCE_HEADS:
        if call.kwargs:
            raise MarkTeXError(f"{call.head} does not accept named arguments", call.origin)
        for arg in call.args:
            raw_text(arg, f"{call.head} path", call.origin)
        return DocumentDirectiveResult(call, layout, spec.body_effect, spec.event_policy)
    if call.head in DOCUMENT_STYLE_HEADS:
        return DocumentDirectiveResult(
            canonicalize_style_selector_call(call),
            layout,
            spec.body_effect,
            spec.event_policy,
        )
    if call.head == "newpage":
        if call.args or call.kwargs:
            raise MarkTeXError("newpage does not accept arguments", call.origin)
        return DocumentDirectiveResult(None, layout, spec.body_effect, spec.event_policy)
    return DocumentDirectiveResult(call, layout, spec.body_effect, spec.event_policy)


def canonicalize_document_call(call: CallUnit, layout: PageLayout) -> tuple[CallUnit, PageLayout, bool]:
    result = plan_document_directive_call(call, layout)
    if result.call is None:
        raise MarkTeXError(f"{call.head} is not a document event", call.origin)
    return result.call, result.layout, result.body_effect == "page_setup"


def canonicalize_style_selector_call(call: CallUnit) -> CallUnit:
    if set(call.kwargs) - {"name"}:
        unknown = ", ".join(sorted(set(call.kwargs) - {"name"}))
        raise MarkTeXError(f"unknown kwargs for {call.head!r}: {unknown}", call.origin)
    args = list(call.args)
    if "name" in call.kwargs:
        if args:
            raise MarkTeXError(f"{call.head} accepts either a positional style or name=, not both", call.origin)
        args = [RawString(raw_text(call.kwargs["name"], "style name", call.origin).strip(), value_origin(call.kwargs["name"]))]
    if len(args) > 1:
        raise MarkTeXError(f"{call.head} accepts at most one style selector", call.origin)
    for arg in args:
        raw_text(arg, "style selector", call.origin)
    return CallUnit(call.context, call.head, args=tuple(args), origin=call.origin)


def canonicalize_table_column(call: CallUnit) -> CallUnit:
    if call.head not in {"", "column"}:
        raise MarkTeXError(f"unknown table column call: {call.head}", call.origin)
    if call.args:
        raise MarkTeXError("table column does not accept positional arguments", call.origin)
    unknown = sorted(set(call.kwargs) - {"align"})
    if unknown:
        raise MarkTeXError(f"unknown table column kwargs: {', '.join(unknown)}", call.origin)
    align = "left"
    if "align" in call.kwargs:
        align = normalize_choice(
            raw_text(call.kwargs["align"], "table column alignment", call.origin),
            TABLE_ALIGNMENTS,
            "table column alignment",
            value_origin(call.kwargs["align"]),
        )
    return CallUnit(
        "table-column",
        "column",
        kwargs={"align": RawString(align, value_origin(call.kwargs.get("align")) or call.origin)},
        origin=call.origin,
    )


def validate_citation(citation: Citation) -> None:
    if not citation.keys:
        raise MarkTeXError("citation requires at least one key", citation.origin)
    for key in citation.keys:
        if not key.strip():
            raise MarkTeXError("citation key cannot be empty", citation.origin)
    unknown = sorted(set(citation.kwargs) - CITATION_KWARGS)
    if unknown:
        raise MarkTeXError(f"unknown citation kwargs: {', '.join(unknown)}", citation.origin)


def canonicalize_document(document: Document) -> Document:
    layout = PageLayout()
    events: list[DocumentPatch | ScopePush | ScopeClose] = []
    for event in document.events:
        if isinstance(event, DocumentPatch):
            result = plan_document_directive_call(event.call, layout)
            if result.call is None:
                raise MarkTeXError(f"{event.call.head} is not a document event", event.origin)
            layout = result.layout
            events.append(DocumentPatch(result.call, event.origin))
        elif isinstance(event, ScopePush | ScopeClose):
            events.append(event)
        else:
            raise MarkTeXError(f"unsupported document event: {event!r}")
    blocks = tuple(validate_block(block) for block in document.blocks)
    footnotes = tuple(validate_footnotes(document.footnotes))
    return Document(tuple(events), blocks, footnotes)


def validate_footnotes(footnotes: tuple[FootnoteDefinition, ...]) -> tuple[FootnoteDefinition, ...]:
    seen: set[str] = set()
    for footnote in footnotes:
        if not is_footnote_label(footnote.label):
            raise MarkTeXError(f"invalid footnote label: {footnote.label}", footnote.origin)
        if footnote.label in seen:
            raise MarkTeXError(f"duplicate footnote label: {footnote.label}", footnote.origin)
        seen.add(footnote.label)
        for child in footnote.children:
            validate_inline(child)
    return footnotes


def validate_block(block: Block) -> Block:
    if isinstance(block, Heading):
        if block.level < 1 or block.level > 6:
            raise MarkTeXError(f"heading level out of range: {block.level}", block.origin)
        for inline_child in block.children:
            validate_inline(inline_child)
    elif isinstance(block, Table):
        if len(block.columns) != len(block.header):
            raise MarkTeXError("table column count does not match header width", block.origin)
        for column in block.columns:
            canonicalize_table_column(column)
        for row in block.rows:
            if len(row) != len(block.header):
                raise MarkTeXError("table row width does not match header width", block.origin)
        for cell in block.header:
            for child in cell:
                validate_inline(child)
        for row in block.rows:
            for cell in row:
                for child in cell:
                    validate_inline(child)
    elif isinstance(block, ListBlock):
        if block.start < 1:
            raise MarkTeXError("ordered list start must be >= 1", block.origin)
        for item in block.items:
            if item.checked is not None and not isinstance(item.checked, bool):
                raise MarkTeXError("list item checked must be a boolean", item.origin)
            for block_child in item.children:
                validate_block(block_child)
    elif isinstance(block, BlockQuote):
        for block_child in block.children:
            validate_block(block_child)
    elif isinstance(block, Conditional):
        for branch in block.branches:
            for block_child in branch.body:
                validate_block(block_child)
        for block_child in block.else_body:
            validate_block(block_child)
    elif isinstance(block, PageSetup):
        normalize_dimension(block.width, "width", block.origin)
        normalize_dimension(block.height, "height", block.origin)
        for key, value in block.margins.items():
            if key not in MARGIN_KEYS:
                raise MarkTeXError(f"unknown margin key: {key}", block.origin)
            normalize_dimension(value, key, block.origin)
    else:
        children = getattr(block, "children", ())
        for inline_child in children:
            validate_inline(inline_child)
    return block


def validate_inline(node: InlineNode) -> None:
    if isinstance(node, Citation):
        validate_citation(node)
    elif isinstance(node, FootnoteRef):
        if not is_footnote_label(node.label):
            raise MarkTeXError(f"invalid footnote label: {node.label}", node.origin)
    elif isinstance(node, LineBreak):
        if not isinstance(node.hard, bool):
            raise MarkTeXError("line break hard must be a boolean", node.origin)
    else:
        for child in getattr(node, "children", ()):
            validate_inline(child)
