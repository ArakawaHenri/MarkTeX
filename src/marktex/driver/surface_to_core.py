from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from marktex.core import (
    Block,
    BlockQuote,
    CodeBlock,
    CodeExpression,
    CodePart,
    CodeText,
    Conditional,
    ConditionalBranch,
    Document,
    DocumentPatch,
    FootnoteDefinition,
    Heading,
    InlineNode,
    ListBlock,
    ListItem,
    MarkTeXObject,
    MathBlock,
    PageBreak,
    PageSetup,
    Paragraph,
    ScopeClose,
    ScopePush,
    Table,
    ThematicBreak,
)
from marktex.driver.artifacts import (
    ArtifactKind,
    artifact_payload_from_object,
)
from marktex.driver.inline import normalize_reference_label, parse_inline_nodes
from marktex.driver.serde import surface_document_from_json
from marktex.host.python import PythonHost, SymbolicValue
from marktex.mos import CallUnit, MosValue, RawString, TupleValue, parse_mos
from marktex.schema import SchemaRegistry, builtin_registry
from marktex.scope import DEFAULT_SCOPE_TARGET, scope_target_from_kwargs
from marktex.semantics import (
    DocumentDirectiveResult,
    PageLayout,
    canonicalize_document,
    canonicalize_table_column,
    page_setup_from_layout,
    plan_document_directive_call,
)
from marktex.source import MarkTeXError, SourceSpan, offset_span, remap_span_to_offsets, span_from_offsets
from marktex.state import StateEngine
from marktex.surface import (
    BlockQuoteNode,
    CodeFenceNode,
    ConditionalNode,
    DocumentDirectiveNode,
    FootnoteDefinitionNode,
    HeadingNode,
    HostBlockNode,
    LinkReferenceDefinitionNode,
    ListBlockNode,
    ListItemNode,
    MathBlockNode,
    ParagraphNode,
    RichTableNode,
    ScopeCloseNode,
    ScopeOpenNode,
    SurfaceNode,
    ThematicBreakNode,
)


@dataclass
class _SurfaceBranch:
    condition: object
    body: tuple[object, ...]
    origin: SourceSpan | None = None


@dataclass
class _ConditionalFrame:
    origin: SourceSpan
    branches: list[_SurfaceBranch] = field(default_factory=list)
    current_condition: object | None = None
    current_origin: SourceSpan | None = None
    current_body: list[object] = field(default_factory=list)
    else_body: list[object] | None = None

    def push_branch(self) -> None:
        if self.current_condition is None:
            return
        self.branches.append(
            _SurfaceBranch(
                self.current_condition,
                tuple(self.current_body),
                self.current_origin,
            )
        )
        self.current_body = []


def document_from_surface_artifact(
    artifact: dict[str, object],
    *,
    no_host: bool = False,
) -> Document:
    payload = artifact_payload_from_object(artifact, expected_kind=ArtifactKind.SURFACE)
    if not isinstance(payload, dict):
        raise MarkTeXError("surface artifact payload is invalid")
    return document_from_surface_payload(payload, no_host=no_host)


def document_from_surface_payload(
    payload: dict[str, object],
    *,
    registry: SchemaRegistry | None = None,
    no_host: bool = False,
) -> Document:
    registry = registry or builtin_registry()
    events: list[MarkTeXObject] = []
    blocks: list[Block] = []
    footnotes: list[FootnoteDefinition] = []
    state = StateEngine()
    host = PythonHost(no_host=no_host)
    surface = surface_document_from_json(payload)
    source = str(payload.get("source", ""))
    filename = str(payload.get("filename", ""))
    root_link_refs = collect_root_link_references(surface.nodes)
    builder = _SurfaceCoreBuilder(filename, source, registry, host)
    conditional_stack: list[_ConditionalFrame] = []
    page_layout = PageLayout()
    content_started = False
    page_transitions = _PageTransitionQueue()

    def append_event(event: DocumentPatch | ScopePush | ScopeClose, *, update_state: bool = True) -> None:
        if isinstance(event, DocumentPatch):
            validate_document_call(registry, event.call)
        events.append(event)
        if update_state:
            state.invoke(event, event.origin)

    def append_runtime_events() -> None:
        nonlocal page_layout
        for event in host.drain_runtime_events():
            if isinstance(event, DocumentPatch):
                validate_document_call(registry, event.call)
                result = plan_document_directive_call(event.call, page_layout)
                if result.call is None:
                    raise MarkTeXError(f"{event.call.head} is not a document event", event.origin)
                page_layout = result.layout
                event = DocumentPatch(result.call, event.origin)
            append_event(event)

    def append_block(block: Block) -> None:
        nonlocal content_started
        if conditional_stack:
            frame = conditional_stack[-1]
            if frame.else_body is not None:
                frame.else_body.append(block)
            else:
                frame.current_body.append(block)
        else:
            page_transitions.flush_before(blocks)
            blocks.append(block)
            content_started = True

    def append_page_break(origin: SourceSpan) -> None:
        nonlocal content_started
        page_transitions.append_page_break(blocks, origin)
        content_started = True

    def append_pending_surface_node(node: object) -> None:
        append_to_conditional_frame(conditional_stack[-1], node)

    for node in surface.nodes:
        if conditional_stack and not isinstance(node, ConditionalNode):
            append_pending_surface_node(node)
            continue
        if isinstance(node, DocumentDirectiveNode):
            calls = parse_mos(node.payload, context="document", filename=filename)
            for call in registry.resolve_calls(calls):
                validate_document_directive_call(registry, call)
                result = plan_document_directive_call(call, page_layout)
                page_layout = result.layout
                if result.call is not None and should_append_document_event(result, content_started):
                    obj = DocumentPatch(result.call, result.call.origin or node.origin)
                    append_event(obj)
                if result.body_effect == "page_setup" and content_started:
                    page_transitions.queue_page_setup(page_layout, node.origin)
                elif result.body_effect == "page_break":
                    append_page_break(node.origin)
        elif isinstance(node, ScopeOpenNode):
            calls = parse_mos(node.payload, context="scope", filename=filename)
            for call in calls:
                push = scope_push_from_call(call, node.origin)
                append_event(push)
        elif isinstance(node, ScopeCloseNode):
            close = ScopeClose(node.key, node.origin)
            append_event(close)
        elif isinstance(node, HostBlockNode):
            if node.language != "python":
                raise MarkTeXError(
                    f"unsupported host block language: {node.language}; 0.1 only supports python",
                    node.origin,
                )
            host.execute_block(node.body, node.origin)
            append_runtime_events()
        elif isinstance(node, FootnoteDefinitionNode):
            footnotes.append(
                FootnoteDefinition(
                    node.label,
                    parse_inline_nodes(
                        node.body,
                        host,
                        span_from_offsets(filename, node.body_offsets, source),
                        source,
                        source_offsets=node.body_offsets,
                        link_refs=root_link_refs,
                    ),
                    node.origin,
                )
            )
        elif isinstance(node, ConditionalNode):
            conditional = handle_conditional_node(
                node,
                host,
                conditional_stack,
                builder,
                root_link_refs,
                page_layout,
            )
            if conditional is not None:
                append_block(conditional)
        else:
            if conditional_stack:
                frame = conditional_stack[-1]
                if frame.else_body is not None:
                    frame.else_body.append(node)
                else:
                    frame.current_body.append(node)
            else:
                for block in builder.blocks((node,), root_link_refs):
                    append_block(block)

    if conditional_stack:
        raise MarkTeXError("unclosed conditional block", conditional_stack[-1].origin)

    document = Document(tuple(events), tuple(blocks), tuple(footnotes))
    return canonicalize_document(document)


class _PageTransitionQueue:
    def __init__(self) -> None:
        self._page_setup: PageSetup | None = None

    def queue_page_setup(self, layout: PageLayout, origin: SourceSpan) -> None:
        self._page_setup = page_setup_from_layout(layout, origin)

    def append_page_break(self, blocks: list[Block], origin: SourceSpan) -> None:
        if self._page_setup is not None:
            blocks.append(self._page_setup)
            self._page_setup = None
            return
        if blocks and isinstance(blocks[-1], PageBreak | PageSetup):
            return
        blocks.append(PageBreak(origin))

    def flush_before(self, blocks: list[Block]) -> None:
        if self._page_setup is None:
            return
        blocks.append(self._page_setup)
        self._page_setup = None


class _SurfaceCoreBuilder:
    def __init__(
        self,
        filename: str,
        source: str,
        registry: SchemaRegistry,
        host: PythonHost,
    ) -> None:
        self.filename = filename
        self.source = source
        self.registry = registry
        self.host = host

    def blocks(
        self,
        nodes: tuple[object, ...],
        inherited_refs: dict[str, str],
        *,
        initial_layout: PageLayout | None = None,
    ) -> tuple[Block, ...]:
        refs = {**inherited_refs, **direct_link_references(nodes)}
        converted: list[Block] = []
        page_layout = initial_layout or PageLayout()
        page_transitions = _PageTransitionQueue()

        def append(block: Block) -> None:
            page_transitions.flush_before(converted)
            converted.append(block)

        for node in nodes:
            if isinstance(node, CORE_BLOCK_TYPES):
                append(node)
            elif isinstance(node, DocumentDirectiveNode):
                calls = parse_mos(node.payload, context="document", filename=self.filename)
                for call in self.registry.resolve_calls(calls):
                    validate_document_directive_call(self.registry, call)
                    result = plan_document_directive_call(call, page_layout)
                    page_layout = result.layout
                    if result.call is not None and result.event_policy == "always":
                        raise MarkTeXError(
                            f"document directive {call.head!r} is not supported inside conditional body",
                            call.origin or node.origin,
                        )
                    if result.body_effect == "page_setup":
                        page_transitions.queue_page_setup(page_layout, node.origin)
                    elif result.body_effect == "page_break":
                        page_transitions.append_page_break(converted, node.origin)
            elif isinstance(node, HeadingNode):
                append(
                    Heading(
                        node.level,
                        self.inlines(node.text, node.text_offsets, refs),
                        node.origin,
                    )
                )
            elif isinstance(node, ParagraphNode):
                append(
                    Paragraph(
                        self.inlines(node.text, node.text_offsets, refs),
                        node.origin,
                    )
                )
            elif isinstance(node, CodeFenceNode):
                if node.interpolated:
                    body, parts = render_interpolated_code(
                        node.body,
                        self.host,
                        node.origin,
                        self.source,
                    )
                else:
                    body = node.body
                    parts = ()
                append(CodeBlock(node.language, body, node.interpolated, node.origin, parts))
            elif isinstance(node, MathBlockNode):
                append(MathBlock(node.body, node.origin))
            elif isinstance(node, RichTableNode):
                append(self.table(node, refs))
            elif isinstance(node, ListBlockNode):
                append(
                    ListBlock(
                        node.ordered,
                        node.start,
                        node.tight,
                        tuple(self.list_item(item, refs) for item in node.items),
                        node.origin,
                    )
                )
            elif isinstance(node, BlockQuoteNode):
                append(BlockQuote(self.blocks(node.children, refs), node.origin))
            elif isinstance(node, ThematicBreakNode):
                append(ThematicBreak(node.origin))
            elif isinstance(node, LinkReferenceDefinitionNode):
                continue
            elif isinstance(node, HostBlockNode):
                raise MarkTeXError("host blocks are only supported at document root", node.origin)
            elif isinstance(node, ScopeOpenNode | ScopeCloseNode):
                raise MarkTeXError("scope directives are only supported at document root", node.origin)
            elif isinstance(node, FootnoteDefinitionNode):
                raise MarkTeXError("footnote definitions are only supported at document root", node.origin)
            elif isinstance(node, ConditionalNode):
                raise MarkTeXError("conditional blocks are not supported inside fallback containers", node.origin)
            else:
                raise MarkTeXError(f"unsupported surface node in block context: {node!r}")
        return tuple(converted)

    def list_item(self, item: ListItemNode, inherited_refs: dict[str, str]) -> ListItem:
        return ListItem(self.blocks(item.children, inherited_refs), item.checked, item.origin)

    def table(self, node: RichTableNode, refs: dict[str, str]) -> Table:
        rows = node.rows
        columns = tuple(
            column_call(spec, kind, offsets, self.filename, self.source, self.registry)
            for spec, kind, offsets in zip(
                node.column_specs,
                node.column_spec_kinds,
                node.column_spec_offsets,
                strict=True,
            )
        )
        header = tuple(
            self.inlines(cell, offsets, refs)
            for cell, offsets in zip(rows[0], node.cell_offsets[0], strict=True)
        )
        table_body = tuple(
            tuple(
                self.inlines(cell, offsets, refs)
                for cell, offsets in zip(row, offset_row, strict=True)
            )
            for row, offset_row in zip(rows[1:], node.cell_offsets[1:], strict=True)
        )
        return Table(columns, header, table_body, node.origin)

    def inlines(
        self,
        text: str,
        offsets: tuple[int, ...],
        refs: dict[str, str],
    ) -> tuple[InlineNode, ...]:
        return parse_inline_nodes(
            text,
            self.host,
            span_from_offsets(self.filename, offsets, self.source),
            self.source,
            source_offsets=offsets,
            link_refs=refs,
        )


CORE_BLOCK_TYPES = (
    Paragraph,
    Heading,
    CodeBlock,
    MathBlock,
    Table,
    ListBlock,
    BlockQuote,
    ThematicBreak,
    PageBreak,
    PageSetup,
    Conditional,
)


def scope_push_from_call(call: CallUnit, fallback_origin: SourceSpan) -> ScopePush:
    kwargs = dict(call.kwargs)
    target = scope_target_from_kwargs(kwargs, call.origin or fallback_origin)
    if target == DEFAULT_SCOPE_TARGET:
        kwargs.pop("scope", None)
    return ScopePush(call.head, args=call.args, kwargs=kwargs, origin=call.origin or fallback_origin)


def validate_document_call(registry: SchemaRegistry, call: CallUnit) -> None:
    validate_document_directive_call(registry, call)
    spec = registry.call("document", call.head)
    if spec is not None and not spec.invokable:
        raise MarkTeXError(f"{call.head!r} is not a document event", call.origin)


def validate_document_directive_call(registry: SchemaRegistry, call: CallUnit) -> None:
    result = registry.validate_call("document", call)
    if not result.ok:
        raise MarkTeXError(result.message, call.origin)


def should_append_document_event(result: DocumentDirectiveResult, content_started: bool) -> bool:
    if result.event_policy == "always":
        return True
    if result.event_policy == "before_content":
        return not content_started
    return False


def collect_root_link_references(nodes: tuple[SurfaceNode, ...]) -> dict[str, str]:
    references: dict[str, str] = {}
    conditional_depth = 0
    for node in nodes:
        if isinstance(node, ConditionalNode):
            if node.marker == "!?":
                conditional_depth += 1
            elif node.marker == "!!?":
                conditional_depth = max(0, conditional_depth - 1)
            continue
        if conditional_depth == 0 and isinstance(node, LinkReferenceDefinitionNode):
            references[normalize_reference_label(node.label)] = node.target
    return references


def direct_link_references(nodes: tuple[object, ...]) -> dict[str, str]:
    references: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, LinkReferenceDefinitionNode):
            references[normalize_reference_label(node.label)] = node.target
    return references


def append_to_conditional_frame(frame: _ConditionalFrame, node: object) -> None:
    if frame.else_body is not None:
        frame.else_body.append(node)
    else:
        frame.current_body.append(node)


def handle_conditional_node(
    node: ConditionalNode,
    host: PythonHost,
    stack: list[_ConditionalFrame],
    builder: _SurfaceCoreBuilder,
    root_link_refs: dict[str, str],
    page_layout: PageLayout,
) -> Conditional | None:
    if node.marker == "!?":
        frame = _ConditionalFrame(node.origin)
        frame.current_condition = eval_condition_payload(node.payload, host, node.origin)
        frame.current_origin = node.origin
        stack.append(frame)
        return None
    if not stack:
        raise MarkTeXError("conditional branch without active conditional", node.origin)
    frame = stack[-1]
    if node.marker == "!?!?":
        if frame.else_body is not None:
            raise MarkTeXError("else-if cannot appear after else", node.origin)
        frame.push_branch()
        frame.current_condition = eval_condition_payload(node.payload, host, node.origin)
        frame.current_origin = node.origin
        return None
    if node.marker == "!?!":
        if frame.else_body is not None:
            raise MarkTeXError("duplicate else branch in conditional", node.origin)
        frame.push_branch()
        frame.current_condition = None
        frame.current_origin = None
        frame.else_body = []
        return None
    if node.marker == "!!?":
        frame.push_branch()
        stack.pop()
        conditional = conditional_from_surface_frame(frame, builder, root_link_refs, page_layout)
        if stack:
            append_to_conditional_frame(stack[-1], conditional)
            return None
        return conditional
    raise MarkTeXError(f"unknown conditional marker: {node.marker}", node.origin)


def conditional_from_surface_frame(
    frame: _ConditionalFrame,
    builder: _SurfaceCoreBuilder,
    inherited_refs: dict[str, str],
    initial_layout: PageLayout,
) -> Conditional:
    return Conditional(
        tuple(
            ConditionalBranch(
                branch.condition,
                builder.blocks(branch.body, inherited_refs, initial_layout=initial_layout),
                branch.origin,
            )
            for branch in frame.branches
        ),
        builder.blocks(tuple(frame.else_body or ()), inherited_refs, initial_layout=initial_layout),
        frame.origin,
    )


def eval_condition_payload(payload: str, host: PythonHost, origin: SourceSpan) -> object:
    match = re.fullmatch(r"\[\$\s*(.*?)\s*\](?:\s+#.*)?", payload)
    if not match:
        raise MarkTeXError("conditional condition must be a [$ ... ] host expression", origin)
    return host.eval_expr(match.group(1), origin)


def render_interpolated_code(
    text: str,
    host: PythonHost,
    origin: SourceSpan,
    source: str,
) -> tuple[str, tuple[CodePart, ...]]:
    pieces: list[str] = []
    parts: list[CodePart] = []
    last = 0
    for match in re.finditer(r"\[\$\s*(.*?)\s*\]", text):
        if match.start() > last:
            raw = text[last : match.start()]
            pieces.append(raw)
            parts.append(CodeText(raw, offset_span(origin, last, match.start(), source)))
        expr_origin = offset_span(origin, match.start(), match.end(), source)
        expr_source = match.group(1)
        value = host.eval_expr(expr_source, expr_origin)
        pieces.append(symbolic_text(value))
        parts.append(CodeExpression(expr_source, value, expr_origin))
        last = match.end()
    if last < len(text):
        raw = text[last:]
        pieces.append(raw)
        parts.append(CodeText(raw, offset_span(origin, last, len(text), source)))
    return "".join(pieces), tuple(parts)


def symbolic_text(value: object) -> str:
    if isinstance(value, SymbolicValue):
        return f"{value.owner}.{value.name}"
    return str(value)


def column_call(
    spec: str,
    kind: str,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
    registry: SchemaRegistry,
) -> CallUnit:
    origin = span_from_offsets(filename, offsets, source)
    if kind == "pipe-align":
        return canonicalize_table_column(CallUnit(
            "table-column",
            "column",
            kwargs={"align": RawString(spec, origin)},
            origin=origin,
        ))

    calls = parse_mos(spec, context="table-column", filename=filename)
    calls = [remap_call_origin(call, offsets, filename, source) for call in calls]
    if not calls:
        return canonicalize_table_column(CallUnit("table-column", "column", origin=origin))
    if len(calls) == 1:
        return canonicalize_table_column(registry.resolve_call(calls[0]))
    raise MarkTeXError("table column accepts one column spec", origin)


def remap_call_origin(
    call: CallUnit,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
) -> CallUnit:
    args = tuple(remap_mos_value_origin(arg, offsets, filename, source) for arg in call.args)
    kwargs = {
        key: remap_mos_value_origin(value, offsets, filename, source)
        for key, value in call.kwargs.items()
    }
    return replace(
        call,
        args=args,
        kwargs=kwargs,
        origin=remap_span_to_offsets(call.origin, offsets, filename, source),
    )


def remap_mos_value_origin(
    value: MosValue,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
) -> MosValue:
    if isinstance(value, RawString):
        return replace(value, origin=remap_span_to_offsets(value.origin, offsets, filename, source))
    if isinstance(value, TupleValue):
        return replace(
            value,
            items=tuple(remap_mos_value_origin(item, offsets, filename, source) for item in value.items),
            origin=remap_span_to_offsets(value.origin, offsets, filename, source),
        )
    return remap_call_origin(value, offsets, filename, source)
