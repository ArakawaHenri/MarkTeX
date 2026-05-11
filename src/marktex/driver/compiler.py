from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Literal

from marktex.backend.lualatex import make_backend_ir
from marktex.backend.lualatex.emit import emit_lualatex_from_backend_ir
from marktex._version import __version__
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
    Paragraph,
    ScopeClose,
    ScopePush,
    Table,
    ThematicBreak,
)
from marktex.driver.inline import normalize_reference_label, parse_inline_nodes
from marktex.driver.serde import (
    document_from_json,
    surface_document_from_json,
    surface_document_to_json,
)
from marktex.host.python import PythonHost, SymbolicValue, emit_host_script
from marktex.mos import CallUnit, MosValue, RawString, TupleValue, parse_mos
from marktex.schema import SchemaRegistry, builtin_registry
from marktex.source import MarkTeXError, SourceSpan
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
    ParagraphNode,
    RichTableNode,
    ScopeCloseNode,
    ScopeOpenNode,
    SurfaceDocument,
    SurfaceNode,
    ThematicBreakNode,
    parse_surface,
)


class ArtifactKind(str, Enum):
    SURFACE = "surface"
    TARGET = "target"
    HOST = "host"
    AST = "ast"
    EIR = "eir"
    BACKEND_IR = "backend-ir"


class InputStage(str, Enum):
    MTX = "mtx"
    SURFACE = "surface"
    HOST = "host"
    AST = "ast"
    EIR = "eir"
    BACKEND_IR = "backend-ir"


ALL_ARTIFACTS = {
    ArtifactKind.SURFACE,
    ArtifactKind.HOST,
    ArtifactKind.AST,
    ArtifactKind.EIR,
    ArtifactKind.BACKEND_IR,
    ArtifactKind.TARGET,
}

ARTIFACT_VERSION = 1
ORDERED_ARTIFACTS = (
    ArtifactKind.SURFACE,
    ArtifactKind.HOST,
    ArtifactKind.AST,
    ArtifactKind.EIR,
    ArtifactKind.BACKEND_IR,
    ArtifactKind.TARGET,
)
CURRENT_STAGE_ARTIFACT = {
    InputStage.SURFACE: ArtifactKind.SURFACE,
    InputStage.HOST: ArtifactKind.HOST,
    InputStage.AST: ArtifactKind.AST,
    InputStage.EIR: ArtifactKind.EIR,
    InputStage.BACKEND_IR: ArtifactKind.BACKEND_IR,
}
REACHABLE_ARTIFACTS = {
    InputStage.MTX: ORDERED_ARTIFACTS,
    InputStage.SURFACE: (
        ArtifactKind.HOST,
        ArtifactKind.AST,
        ArtifactKind.EIR,
        ArtifactKind.BACKEND_IR,
        ArtifactKind.TARGET,
    ),
    InputStage.HOST: (
        ArtifactKind.AST,
        ArtifactKind.EIR,
        ArtifactKind.BACKEND_IR,
        ArtifactKind.TARGET,
    ),
    InputStage.AST: (
        ArtifactKind.EIR,
        ArtifactKind.BACKEND_IR,
        ArtifactKind.TARGET,
    ),
    InputStage.EIR: (ArtifactKind.BACKEND_IR, ArtifactKind.TARGET),
    InputStage.BACKEND_IR: (ArtifactKind.TARGET,),
}


@dataclass(frozen=True)
class CompileResult:
    artifacts: dict[ArtifactKind, str]
    written: dict[ArtifactKind, Path] = field(default_factory=dict)


@dataclass
class _Build:
    surface_payload: dict[str, object] | None
    document: Document
    state: StateEngine
    host_script: str
    backend_ir: dict[str, object]
    target_text: str


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


def compile_file(
    input_path: Path,
    *,
    emits: set[ArtifactKind] | None = None,
    output_path: Path | None = None,
    out_dir: Path | None = None,
    target: Literal["lualatex"] = "lualatex",
    from_stage: InputStage | str = InputStage.MTX,
    no_host: bool = False,
) -> CompileResult:
    if target != "lualatex":
        raise MarkTeXError(f"unsupported target: {target}; 0.1 only supports lualatex")

    stage = normalize_input_stage(from_stage)
    requested_emits = set(emits or {ArtifactKind.TARGET})
    if not requested_emits:
        requested_emits = {ArtifactKind.TARGET}
    resolved_emits = resolve_requested_emits(stage, requested_emits)

    source = input_path.read_text(encoding="utf-8")
    artifacts = compile_text_from_stage(
        source,
        filename=str(input_path),
        input_stage=stage,
        emits=resolved_emits,
        target=target,
        no_host=no_host,
    )
    written = write_artifacts(
        input_path,
        artifacts,
        output_path=output_path,
        out_dir=out_dir,
        target=target,
    )
    return CompileResult(artifacts, written)


def build_document(
    source: str,
    *,
    filename: str,
    registry: SchemaRegistry | None = None,
    no_host: bool = False,
) -> _Build:
    surface = parse_surface(source, filename=filename)
    surface_payload = surface_payload_from_document(surface, source=source, filename=filename)
    host_script = emit_host_script(artifact_envelope(ArtifactKind.SURFACE, surface_payload), no_host=no_host)
    document = execute_host_script(host_script, filename=filename + ".host.py")
    state = state_from_document(document, registry=registry)
    backend_ir = make_backend_ir(document)
    target_text = emit_lualatex_from_backend_ir(backend_ir)
    return _Build(surface_payload, document, state, host_script, backend_ir, target_text)


def compile_text_from_stage(
    source: str,
    *,
    filename: str,
    input_stage: InputStage,
    emits: set[ArtifactKind],
    target: Literal["lualatex"],
    no_host: bool,
) -> dict[ArtifactKind, str]:
    registry = builtin_registry()
    surface_payload: dict[str, object] | None = None
    host_script: str | None = None
    document: Document | None = None
    state: StateEngine | None = None
    backend_ir: dict[str, object] | None = None
    target_text: str | None = None

    if input_stage == InputStage.MTX:
        surface = parse_surface(source, filename=filename)
        surface_payload = surface_payload_from_document(surface, source=source, filename=filename)
    elif input_stage == InputStage.SURFACE:
        payload = artifact_payload_from_text(
            source,
            expected_kind=ArtifactKind.SURFACE,
        )
        if not isinstance(payload, dict):
            raise MarkTeXError("surface artifact payload is invalid")
        surface_payload = payload
    elif input_stage == InputStage.HOST:
        if no_host:
            raise MarkTeXError("--from host cannot be used with --no-host")
        host_script = source
    elif input_stage == InputStage.AST:
        document = document_from_json(
            artifact_payload_from_text(source, expected_kind=ArtifactKind.AST)
        )
    elif input_stage == InputStage.EIR:
        payload = artifact_payload_from_text(source, expected_kind=ArtifactKind.EIR)
        if not isinstance(payload, dict):
            raise MarkTeXError("eir artifact payload is invalid")
        document = document_from_json(payload.get("document"))
    elif input_stage == InputStage.BACKEND_IR:
        payload = artifact_payload_from_text(
            source,
            expected_kind=ArtifactKind.BACKEND_IR,
        )
        if not isinstance(payload, dict):
            raise MarkTeXError("backend-ir artifact payload is invalid")
        backend_ir = payload

    def ensure_surface_payload() -> dict[str, object]:
        nonlocal surface_payload
        if surface_payload is None:
            raise MarkTeXError(f"{input_stage.value} input cannot produce a surface artifact")
        return surface_payload

    def ensure_host_script() -> str:
        nonlocal host_script
        if host_script is None:
            host_script = emit_host_script(
                artifact_envelope(ArtifactKind.SURFACE, ensure_surface_payload()),
                no_host=no_host,
            )
        return host_script

    def ensure_document() -> Document:
        nonlocal document
        if document is None:
            document = execute_host_script(ensure_host_script(), filename=filename + ".host.py")
        return document

    def ensure_state() -> StateEngine:
        nonlocal state
        if state is None:
            state = state_from_document(ensure_document(), registry=registry)
        return state

    def ensure_backend_ir() -> dict[str, object]:
        nonlocal backend_ir
        if backend_ir is None:
            backend_ir = make_backend_ir(ensure_document())
        if backend_ir.get("target") != target:
            raise MarkTeXError(f"backend-ir target is {backend_ir.get('target')!r}, not {target!r}")
        return backend_ir

    def ensure_target_text() -> str:
        nonlocal target_text
        if target_text is None:
            target_text = emit_lualatex_from_backend_ir(ensure_backend_ir())
        return target_text

    artifacts: dict[ArtifactKind, str] = {}
    for kind in ORDERED_ARTIFACTS:
        if kind not in emits:
            continue
        if kind == ArtifactKind.SURFACE:
            artifacts[kind] = json_dumps(artifact_envelope(kind, ensure_surface_payload()))
        elif kind == ArtifactKind.HOST:
            artifacts[kind] = ensure_host_script()
        elif kind == ArtifactKind.AST:
            artifacts[kind] = json_dumps(artifact_envelope(kind, ensure_document().to_json()))
        elif kind == ArtifactKind.EIR:
            artifacts[kind] = json_dumps(
                artifact_envelope(
                    kind,
                    {
                        "kind": "eir",
                        "document": ensure_document().to_json(),
                        "state": ensure_state().to_json(),
                    },
                )
            )
        elif kind == ArtifactKind.BACKEND_IR:
            artifacts[kind] = json_dumps(artifact_envelope(kind, ensure_backend_ir()))
        elif kind == ArtifactKind.TARGET:
            artifacts[kind] = ensure_target_text()
    return artifacts


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

    def append_event(event: DocumentPatch | ScopePush | ScopeClose) -> None:
        if isinstance(event, DocumentPatch):
            validate_document_call(registry, event.call)
        events.append(event)
        state.invoke(event, event.origin)

    def append_runtime_events() -> None:
        for event in host.drain_runtime_events():
            append_event(event)

    def append_block(block: Block) -> None:
        if conditional_stack:
            frame = conditional_stack[-1]
            if frame.else_body is not None:
                frame.else_body.append(block)
            else:
                frame.current_body.append(block)
        else:
            blocks.append(block)

    for node in surface.nodes:
        if isinstance(node, DocumentDirectiveNode):
            calls = parse_mos(node.payload, context="document", filename=filename)
            for call in registry.resolve_calls(calls):
                validate_document_call(registry, call)
                obj = DocumentPatch(call, call.origin or node.origin)
                append_event(obj)
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
            handle_conditional_node(node, host, conditional_stack, blocks, builder, root_link_refs)
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
    return document


def normalize_input_stage(stage: InputStage | str) -> InputStage:
    if isinstance(stage, InputStage):
        return stage
    try:
        return InputStage(stage)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in InputStage)
        raise MarkTeXError(f"unsupported input stage: {stage}; expected one of {allowed}") from exc


def resolve_requested_emits(
    stage: InputStage,
    requested_emits: set[ArtifactKind],
) -> set[ArtifactKind]:
    if requested_emits == ALL_ARTIFACTS:
        return set(REACHABLE_ARTIFACTS[stage])
    allowed = set(REACHABLE_ARTIFACTS[stage])
    current = CURRENT_STAGE_ARTIFACT.get(stage)
    if current is not None:
        allowed.add(current)
    unsupported = requested_emits - allowed
    if unsupported:
        unsupported_text = ", ".join(sorted(kind.value for kind in unsupported))
        allowed_text = ", ".join(kind.value for kind in ORDERED_ARTIFACTS if kind in allowed)
        raise MarkTeXError(
            f"--from {stage.value} cannot emit {unsupported_text}; expected one of {allowed_text}"
        )
    return requested_emits


def surface_payload_from_document(
    surface: SurfaceDocument,
    *,
    source: str,
    filename: str,
) -> dict[str, object]:
    payload = surface_document_to_json(surface)
    payload["source"] = source
    payload["filename"] = filename
    return payload


def artifact_envelope(kind: ArtifactKind, payload: object) -> dict[str, object]:
    return {
        "kind": kind.value,
        "marktex_version": __version__,
        "artifact_version": ARTIFACT_VERSION,
        "payload": payload,
    }


def artifact_payload_from_text(
    text: str,
    *,
    expected_kind: ArtifactKind,
) -> object:
    try:
        artifact = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MarkTeXError(f"invalid {expected_kind.value} artifact JSON: {exc}", None) from exc
    return artifact_payload_from_object(artifact, expected_kind=expected_kind)


def artifact_payload_from_object(
    artifact: object,
    *,
    expected_kind: ArtifactKind,
) -> object:
    if not isinstance(artifact, dict):
        raise MarkTeXError(f"{expected_kind.value} artifact must be a JSON object")
    actual_kind = artifact.get("kind")
    if actual_kind != expected_kind.value:
        raise MarkTeXError(
            f"expected {expected_kind.value} artifact, got {actual_kind!r}"
        )
    if artifact.get("artifact_version") != ARTIFACT_VERSION:
        raise MarkTeXError(
            f"unsupported {expected_kind.value} artifact version: {artifact.get('artifact_version')!r}"
        )
    if "marktex_version" not in artifact:
        raise MarkTeXError(f"{expected_kind.value} artifact is missing marktex_version")
    if "payload" not in artifact:
        raise MarkTeXError(f"{expected_kind.value} artifact is missing payload")
    return artifact["payload"]


def execute_host_script(script: str, *, filename: str) -> Document:
    namespace: dict[str, object] = {"__name__": "__marktex_host_artifact__"}
    try:
        exec(compile(script, filename, "exec"), namespace)
    except MarkTeXError:
        raise
    except Exception as exc:  # pragma: no cover - host artifact exceptions vary
        raise MarkTeXError(f"host artifact failed: {exc}") from exc
    document = namespace.get("document")
    if not isinstance(document, Document):
        raise MarkTeXError("host artifact did not produce a canonical Document named 'document'")
    return document


def state_from_document(
    document: Document,
    *,
    registry: SchemaRegistry | None = None,
) -> StateEngine:
    registry = registry or builtin_registry()
    state = StateEngine()
    for event in document.events:
        if isinstance(event, DocumentPatch):
            validate_document_call(registry, event.call)
        if isinstance(event, DocumentPatch | ScopePush | ScopeClose):
            state.invoke(event, event.origin)
    return state


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

    def blocks(self, nodes: tuple[object, ...], inherited_refs: dict[str, str]) -> tuple[Block, ...]:
        refs = {**inherited_refs, **direct_link_references(nodes)}
        converted: list[Block] = []
        for node in nodes:
            if isinstance(node, CORE_BLOCK_TYPES):
                converted.append(node)
            elif isinstance(node, HeadingNode):
                converted.append(
                    Heading(
                        node.level,
                        self.inlines(node.text, node.text_offsets, refs),
                        node.origin,
                    )
                )
            elif isinstance(node, ParagraphNode):
                converted.append(
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
                converted.append(CodeBlock(node.language, body, node.interpolated, node.origin, parts))
            elif isinstance(node, RichTableNode):
                converted.append(self.table(node, refs))
            elif isinstance(node, ListBlockNode):
                converted.append(
                    ListBlock(
                        node.ordered,
                        node.start,
                        node.tight,
                        tuple(self.list_item(item, refs) for item in node.items),
                        node.origin,
                    )
                )
            elif isinstance(node, BlockQuoteNode):
                converted.append(BlockQuote(self.blocks(node.children, refs), node.origin))
            elif isinstance(node, ThematicBreakNode):
                converted.append(ThematicBreak(node.origin))
            elif isinstance(node, LinkReferenceDefinitionNode):
                continue
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
    Table,
    ListBlock,
    BlockQuote,
    ThematicBreak,
    Conditional,
)


def scope_push_from_call(call: CallUnit, fallback_origin: SourceSpan) -> ScopePush:
    return ScopePush(call.head, args=call.args, kwargs=call.kwargs, origin=call.origin or fallback_origin)


def validate_document_call(registry: SchemaRegistry, call: CallUnit) -> None:
    result = registry.validate_call("document", call)
    if not result.ok:
        raise MarkTeXError(result.message, call.origin)


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


def handle_conditional_node(
    node: ConditionalNode,
    host: PythonHost,
    stack: list[_ConditionalFrame],
    root_blocks: list[Block],
    builder: _SurfaceCoreBuilder,
    root_link_refs: dict[str, str],
) -> None:
    if node.marker == "!?":
        frame = _ConditionalFrame(node.origin)
        frame.current_condition = eval_condition_payload(node.payload, host, node.origin)
        frame.current_origin = node.origin
        stack.append(frame)
        return
    if not stack:
        raise MarkTeXError("conditional branch without active conditional", node.origin)
    frame = stack[-1]
    if node.marker == "!?!?":
        if frame.else_body is not None:
            raise MarkTeXError("else-if cannot appear after else", node.origin)
        frame.push_branch()
        frame.current_condition = eval_condition_payload(node.payload, host, node.origin)
        frame.current_origin = node.origin
        return
    if node.marker == "!?!":
        if frame.else_body is not None:
            raise MarkTeXError("duplicate else branch in conditional", node.origin)
        frame.push_branch()
        frame.current_condition = None
        frame.current_origin = None
        frame.else_body = []
        return
    if node.marker == "!!?":
        frame.push_branch()
        stack.pop()
        conditional = conditional_from_surface_frame(frame, builder, root_link_refs)
        if stack:
            parent = stack[-1]
            if parent.else_body is not None:
                parent.else_body.append(conditional)
            else:
                parent.current_body.append(conditional)
        else:
            root_blocks.append(conditional)
        return
    raise MarkTeXError(f"unknown conditional marker: {node.marker}", node.origin)


def conditional_from_surface_frame(
    frame: _ConditionalFrame,
    builder: _SurfaceCoreBuilder,
    inherited_refs: dict[str, str],
) -> Conditional:
    return Conditional(
        tuple(
            ConditionalBranch(
                branch.condition,
                builder.blocks(branch.body, inherited_refs),
                branch.origin,
            )
            for branch in frame.branches
        ),
        builder.blocks(tuple(frame.else_body or ()), inherited_refs),
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
        return CallUnit(
            "table-column",
            "column",
            kwargs={"align": RawString(spec, origin)},
            origin=origin,
        )

    calls = parse_mos(spec, context="table-column", filename=filename)
    calls = [remap_call_origin(call, offsets, filename, source) for call in calls]
    if not calls:
        return CallUnit("table-column", "column", origin=origin)
    if len(calls) == 1:
        return registry.resolve_call(calls[0])
    return CallUnit(
        "table-column",
        "column",
        args=tuple(registry.resolve_call(call) for call in calls),
        origin=origin,
    )


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
        origin=remap_origin(call.origin, offsets, filename, source),
    )


def remap_mos_value_origin(
    value: MosValue,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
) -> MosValue:
    if isinstance(value, RawString):
        return replace(value, origin=remap_origin(value.origin, offsets, filename, source))
    if isinstance(value, TupleValue):
        return replace(
            value,
            items=tuple(remap_mos_value_origin(item, offsets, filename, source) for item in value.items),
            origin=remap_origin(value.origin, offsets, filename, source),
        )
    return remap_call_origin(value, offsets, filename, source)


def remap_origin(
    origin: SourceSpan | None,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
) -> SourceSpan | None:
    if origin is None:
        return None
    start_index = min(max(origin.start, 0), len(offsets) - 1)
    end_index = min(max(origin.end, 0), len(offsets) - 1)
    return absolute_span(filename, offsets[start_index], offsets[end_index], source)


def artifact_texts(build: _Build, emits: set[ArtifactKind]) -> dict[ArtifactKind, str]:
    artifacts: dict[ArtifactKind, str] = {}
    if ArtifactKind.SURFACE in emits:
        if build.surface_payload is None:
            raise MarkTeXError("build has no surface artifact")
        artifacts[ArtifactKind.SURFACE] = json_dumps(
            artifact_envelope(ArtifactKind.SURFACE, build.surface_payload)
        )
    if ArtifactKind.HOST in emits:
        artifacts[ArtifactKind.HOST] = build.host_script
    if ArtifactKind.AST in emits:
        artifacts[ArtifactKind.AST] = json_dumps(
            artifact_envelope(ArtifactKind.AST, build.document.to_json())
        )
    if ArtifactKind.EIR in emits:
        artifacts[ArtifactKind.EIR] = json_dumps(
            artifact_envelope(
                ArtifactKind.EIR,
                {
                    "kind": "eir",
                    "document": build.document.to_json(),
                    "state": build.state.to_json(),
                },
            )
        )
    if ArtifactKind.BACKEND_IR in emits:
        artifacts[ArtifactKind.BACKEND_IR] = json_dumps(
            artifact_envelope(ArtifactKind.BACKEND_IR, build.backend_ir)
        )
    if ArtifactKind.TARGET in emits:
        artifacts[ArtifactKind.TARGET] = build.target_text
    return artifacts


def write_artifacts(
    input_path: Path,
    artifacts: dict[ArtifactKind, str],
    *,
    output_path: Path | None,
    out_dir: Path | None,
    target: Literal["lualatex"],
) -> dict[ArtifactKind, Path]:
    if output_path is not None and out_dir is not None:
        raise MarkTeXError("--output and --out-dir cannot be used together")
    if output_path is not None and len(artifacts) != 1:
        raise MarkTeXError("--output can only be used with a single emitted artifact")
    if output_path is not None and str(output_path) == "-":
        return {}

    written: dict[ArtifactKind, Path] = {}
    if len(artifacts) == 1 and out_dir is None:
        kind, text = next(iter(artifacts.items()))
        path = output_path or default_single_output(input_path, kind, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written[kind] = path
        return written

    target_dir = out_dir or input_path.with_suffix(".mtxbuild")
    target_dir.mkdir(parents=True, exist_ok=True)
    for kind, text in artifacts.items():
        path = target_dir / artifact_filename(input_path, kind, target)
        path.write_text(text, encoding="utf-8")
        written[kind] = path
    return written


def default_single_output(
    input_path: Path,
    kind: ArtifactKind,
    target: Literal["lualatex"],
) -> Path:
    if kind == ArtifactKind.TARGET:
        return input_path.with_suffix(target_artifact_suffix(target))
    return input_path.with_name(artifact_filename(input_path, kind, target))


def artifact_filename(input_path: Path, kind: ArtifactKind, target: Literal["lualatex"]) -> str:
    stem = input_path.stem
    suffixes = {
        ArtifactKind.SURFACE: ".surface.json",
        ArtifactKind.HOST: ".host.py",
        ArtifactKind.AST: ".ast.json",
        ArtifactKind.EIR: ".eir.json",
        ArtifactKind.BACKEND_IR: ".backend-ir.json",
        ArtifactKind.TARGET: target_artifact_suffix(target),
    }
    return stem + suffixes[kind]


def target_artifact_suffix(target: Literal["lualatex"]) -> str:
    if target == "lualatex":
        return ".tex"
    raise MarkTeXError(f"unsupported target: {target}; 0.1 only supports lualatex")


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def span_from_offsets(filename: str, offsets: tuple[int, ...], source: str) -> SourceSpan:
    return absolute_span(filename, offsets[0], offsets[-1], source)


def absolute_span(filename: str, start: int, end: int, source: str) -> SourceSpan:
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start + 1 if last_newline == -1 else start - last_newline
    return SourceSpan(filename, start, end, line, column)


def offset_span(origin: SourceSpan, start_delta: int, end_delta: int, source: str) -> SourceSpan:
    start = origin.start + start_delta
    end = origin.start + end_delta
    return absolute_span(origin.filename, start, end, source)
