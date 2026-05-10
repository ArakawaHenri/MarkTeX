from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from marktex.backend.lualatex import emit_lualatex, make_backend_ir
from marktex.core import (
    Citation,
    CodeBlock,
    Conditional,
    ConditionalBranch,
    Document,
    DocumentPatch,
    Emphasis,
    FootnoteDefinition,
    FootnoteRef,
    Heading,
    Image,
    InlineCode,
    InlineExpression,
    InlineNode,
    Link,
    Paragraph,
    ScopeClose,
    ScopePush,
    Strong,
    Table,
    Text,
)
from marktex.host.python import PythonHost, SymbolicValue, emit_host_script
from marktex.mos import CallUnit, RawString, parse_mos
from marktex.schema import SchemaRegistry, builtin_registry
from marktex.source import MarkTeXError, SourceSpan
from marktex.state import StateEngine
from marktex.surface import (
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
    parse_surface,
)


class ArtifactKind(str, Enum):
    TEX = "tex"
    HOST = "host"
    AST = "ast"
    EIR = "eir"
    BACKEND_IR = "backend-ir"


ALL_ARTIFACTS = {
    ArtifactKind.HOST,
    ArtifactKind.AST,
    ArtifactKind.EIR,
    ArtifactKind.BACKEND_IR,
    ArtifactKind.TEX,
}


@dataclass(frozen=True)
class CompileResult:
    artifacts: dict[ArtifactKind, str]
    written: dict[ArtifactKind, Path] = field(default_factory=dict)


@dataclass
class _Build:
    document: Document
    state: StateEngine
    host_script: str
    backend_ir: dict[str, object]
    tex: str


@dataclass
class _ConditionalFrame:
    origin: SourceSpan
    branches: list[ConditionalBranch] = field(default_factory=list)
    current_condition: object | None = None
    current_origin: SourceSpan | None = None
    current_body: list[object] = field(default_factory=list)
    else_body: list[object] | None = None

    def push_branch(self) -> None:
        if self.current_condition is None:
            return
        self.branches.append(
            ConditionalBranch(
                self.current_condition,
                tuple(self.current_body),  # type: ignore[arg-type]
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
    schema_paths: tuple[Path, ...] = (),
    strict: bool = False,
    no_host: bool = False,
) -> CompileResult:
    if target != "lualatex":
        raise MarkTeXError(f"unsupported target: {target}; V0 only supports lualatex")
    if schema_paths:
        # The CLI accepts the hook now; the loader is intentionally a later
        # addition so built-in schema behavior remains deterministic.
        for schema_path in schema_paths:
            if not schema_path.exists():
                raise MarkTeXError(f"schema file does not exist: {schema_path}")

    resolved_emits = set(emits or {ArtifactKind.TEX})
    if not resolved_emits:
        resolved_emits = {ArtifactKind.TEX}

    source = input_path.read_text(encoding="utf-8")
    registry = builtin_registry()
    build = build_document(
        source,
        filename=str(input_path),
        registry=registry,
        strict=strict,
        no_host=no_host,
    )

    artifacts = artifact_texts(build, resolved_emits)
    written = write_artifacts(input_path, artifacts, output_path=output_path, out_dir=out_dir)
    return CompileResult(artifacts, written)


def build_document(
    source: str,
    *,
    filename: str,
    registry: SchemaRegistry | None = None,
    strict: bool = False,
    no_host: bool = False,
) -> _Build:
    registry = registry or builtin_registry()
    events: list[object] = []
    blocks: list[object] = []
    footnotes: list[FootnoteDefinition] = []
    state = StateEngine()
    host = PythonHost(no_host=no_host)
    surface = parse_surface(source, filename=filename, strict=strict)
    conditional_stack: list[_ConditionalFrame] = []

    def append_block(block: object) -> None:
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
                events.append(obj)
                state.invoke(obj, obj.origin)
        elif isinstance(node, ScopeOpenNode):
            calls = parse_mos(node.payload, context="scope", filename=filename)
            for call in calls:
                push = scope_push_from_call(call, node.origin)
                events.append(push)
                state.invoke(push, push.origin)
        elif isinstance(node, ScopeCloseNode):
            close = ScopeClose(node.key, node.origin)
            events.append(close)
            state.invoke(close, close.origin)
        elif isinstance(node, HostBlockNode):
            if node.language != "python":
                raise MarkTeXError(
                    f"unsupported host block language: {node.language}; MVP only supports python",
                    node.origin,
                )
            host.execute_block(node.body, node.origin)
        elif isinstance(node, FootnoteDefinitionNode):
            footnotes.append(
                FootnoteDefinition(
                    node.label,
                    parse_inline_nodes(node.body, host, node.origin, source, strict=strict),
                    node.origin,
                )
            )
        elif isinstance(node, ConditionalNode):
            handle_conditional_node(node, host, conditional_stack, blocks)
        elif isinstance(node, HeadingNode):
            append_block(
                Heading(
                    node.level,
                    parse_inline_nodes(
                        node.text,
                        host,
                        span_from_offsets(filename, node.text_offsets, source),
                        source,
                        strict=strict,
                        source_offsets=node.text_offsets,
                    ),
                    node.origin,
                )
            )
        elif isinstance(node, ParagraphNode):
            append_block(
                Paragraph(
                    parse_inline_nodes(node.text, host, node.origin, source, strict=strict),
                    node.origin,
                )
            )
        elif isinstance(node, CodeFenceNode):
            body = render_interpolated_text(node.body, host, node.origin, source) if node.interpolated else node.body
            append_block(CodeBlock(node.language, body, node.interpolated, node.origin))
        elif isinstance(node, RichTableNode):
            rows = node.rows
            columns = tuple(column_call(spec, filename, registry) for spec in node.column_specs)
            header = tuple(
                parse_inline_nodes(
                    cell,
                    host,
                    span_from_offsets(filename, offsets, source),
                    source,
                    strict=strict,
                    source_offsets=offsets,
                )
                for cell, offsets in zip(rows[0], node.cell_offsets[0], strict=True)
            )
            table_body = tuple(
                tuple(
                    parse_inline_nodes(
                        cell,
                        host,
                        span_from_offsets(filename, offsets, source),
                        source,
                        strict=strict,
                        source_offsets=offsets,
                    )
                    for cell, offsets in zip(row, offset_row, strict=True)
                )
                for row, offset_row in zip(rows[1:], node.cell_offsets[1:], strict=True)
            )
            append_block(Table(columns, header, table_body, node.origin))

    if conditional_stack:
        raise MarkTeXError("unclosed conditional block", conditional_stack[-1].origin)

    document = Document(tuple(events), tuple(blocks), tuple(footnotes))  # type: ignore[arg-type]
    host_script = emit_host_script(document)
    if host.executed_blocks:
        host_script += "\n# User host blocks executed during compilation.\n"
        host_script += "\n\n".join(host.executed_blocks) + "\n"
    backend_ir = make_backend_ir(document)
    tex = emit_lualatex(document)
    return _Build(document, state, host_script, backend_ir, tex)


def scope_push_from_call(call: CallUnit, fallback_origin: SourceSpan) -> ScopePush:
    return ScopePush(call.head, args=call.args, kwargs=call.kwargs, origin=call.origin or fallback_origin)


def validate_document_call(registry: SchemaRegistry, call: CallUnit) -> None:
    result = registry.validate_call("document", call)
    if not result.ok:
        raise MarkTeXError(result.message, call.origin)


def handle_conditional_node(
    node: ConditionalNode,
    host: PythonHost,
    stack: list[_ConditionalFrame],
    root_blocks: list[object],
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
        conditional = Conditional(
            tuple(frame.branches),
            tuple(frame.else_body or ()),  # type: ignore[arg-type]
            frame.origin,
        )
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


def eval_condition_payload(payload: str, host: PythonHost, origin: SourceSpan) -> object:
    match = re.fullmatch(r"\[\$\s*(.*?)\s*\](?:\s+#.*)?", payload)
    if not match:
        raise MarkTeXError("conditional condition must be a [$ ... ] host expression", origin)
    return host.eval_expr(match.group(1), origin)


def parse_inline_nodes(
    text: str,
    host: PythonHost,
    origin: SourceSpan,
    source: str,
    *,
    strict: bool = False,
    source_offsets: tuple[int, ...] | None = None,
) -> tuple[InlineNode, ...]:
    nodes: list[InlineNode] = []
    last = 0

    def token_span(start: int, end: int) -> SourceSpan:
        if source_offsets is not None:
            return absolute_span(origin.filename, source_offsets[start], source_offsets[end], source)
        return offset_span(origin, start, end, source)

    def child_offsets(start: int, end: int) -> tuple[int, ...] | None:
        if source_offsets is None:
            return None
        return source_offsets[start : end + 1]

    token = re.compile(
        r"!\[([^\]]*)\]\(([^)]*)\)"
        r"|\[\^([^\]]+)\]"
        r"|\[([^\]]+)\]\(([^)]*)\)"
        r"|`([^`]*)`"
        r"|\*\*([^*]+)\*\*"
        r"|\*([^*]+)\*"
        r"|\[\$\s*(.*?)\s*\]"
    )
    for match in token.finditer(text):
        if match.start() > last:
            nodes.append(Text(text[last : match.start()], token_span(last, match.start())))
        token_origin = token_span(match.start(), match.end())
        if match.group(1) is not None:
            nodes.append(Image(match.group(1), match.group(2), token_origin))
        elif match.group(3) is not None:
            nodes.append(reference_node(match.group(3), token_origin, strict=strict))
        elif match.group(4) is not None:
            nodes.append(
                Link(
                    parse_inline_nodes(
                        match.group(4),
                        host,
                        token_span(match.start(4), match.end(4)),
                        source,
                        strict=strict,
                        source_offsets=child_offsets(match.start(4), match.end(4)),
                    ),
                    match.group(5),
                    token_origin,
                )
            )
        elif match.group(6) is not None:
            nodes.append(InlineCode(match.group(6), token_origin))
        elif match.group(7) is not None:
            nodes.append(
                Strong(
                    parse_inline_nodes(
                        match.group(7),
                        host,
                        token_span(match.start(7), match.end(7)),
                        source,
                        strict=strict,
                        source_offsets=child_offsets(match.start(7), match.end(7)),
                    ),
                    token_origin,
                )
            )
        elif match.group(8) is not None:
            nodes.append(
                Emphasis(
                    parse_inline_nodes(
                        match.group(8),
                        host,
                        token_span(match.start(8), match.end(8)),
                        source,
                        strict=strict,
                        source_offsets=child_offsets(match.start(8), match.end(8)),
                    ),
                    token_origin,
                )
            )
        else:
            expr = match.group(9)
            nodes.append(InlineExpression(expr, host.eval_expr(expr, token_origin), token_origin))
        last = match.end()
    if last < len(text):
        nodes.append(Text(text[last:], token_span(last, len(text))))
    if not nodes:
        nodes.append(Text(text, origin))
    return tuple(nodes)


def reference_node(payload: str, origin: SourceSpan, *, strict: bool) -> FootnoteRef | Citation:
    if payload.strip().startswith("@") and strict:
        raise MarkTeXError("legacy citation shorthand is not supported in strict mode", origin)
    calls = parse_mos(payload, context="reference", filename=origin.filename)
    if len(calls) == 1 and calls[0].head == "cite":
        keys: list[str] = []
        kwargs: dict[str, str] = {}
        for arg in calls[0].args:
            if isinstance(arg, RawString):
                keys.append(arg.text.strip())
        for key, value in calls[0].kwargs.items():
            if isinstance(value, RawString):
                kwargs[key] = value.text.strip()
        if not keys:
            raise MarkTeXError("citation requires at least one key", origin)
        return Citation(tuple(keys), kwargs, origin)
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", payload.strip()):
        return FootnoteRef(payload.strip(), origin)
    raise MarkTeXError(f"unsupported reference payload: {payload}", origin)


def render_interpolated_text(text: str, host: PythonHost, origin: SourceSpan, source: str) -> str:
    pieces: list[str] = []
    last = 0
    for match in re.finditer(r"\[\$\s*(.*?)\s*\]", text):
        pieces.append(text[last : match.start()])
        value = host.eval_expr(match.group(1), offset_span(origin, match.start(), match.end(), source))
        pieces.append(symbolic_text(value))
        last = match.end()
    pieces.append(text[last:])
    return "".join(pieces)


def symbolic_text(value: object) -> str:
    if isinstance(value, SymbolicValue):
        return f"{value.owner}.{value.name}"
    return str(value)


def column_call(spec: str, filename: str, registry: SchemaRegistry) -> CallUnit:
    calls = parse_mos(spec, context="table-column", filename=filename)
    if not calls:
        return CallUnit("table-column", "column")
    if len(calls) == 1:
        return registry.resolve_call(calls[0])
    return CallUnit("table-column", "column", args=tuple(calls))


def artifact_texts(build: _Build, emits: set[ArtifactKind]) -> dict[ArtifactKind, str]:
    artifacts: dict[ArtifactKind, str] = {}
    if ArtifactKind.HOST in emits:
        artifacts[ArtifactKind.HOST] = build.host_script
    if ArtifactKind.AST in emits:
        artifacts[ArtifactKind.AST] = json_dumps(build.document.to_json())
    if ArtifactKind.EIR in emits:
        artifacts[ArtifactKind.EIR] = json_dumps(
            {
                "kind": "eir",
                "document": build.document.to_json(),
                "state": build.state.to_json(),
            }
        )
    if ArtifactKind.BACKEND_IR in emits:
        artifacts[ArtifactKind.BACKEND_IR] = json_dumps(build.backend_ir)
    if ArtifactKind.TEX in emits:
        artifacts[ArtifactKind.TEX] = build.tex
    return artifacts


def write_artifacts(
    input_path: Path,
    artifacts: dict[ArtifactKind, str],
    *,
    output_path: Path | None,
    out_dir: Path | None,
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
        path = output_path or default_single_output(input_path, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written[kind] = path
        return written

    target_dir = out_dir or input_path.with_suffix(".mtxbuild")
    target_dir.mkdir(parents=True, exist_ok=True)
    for kind, text in artifacts.items():
        path = target_dir / artifact_filename(input_path, kind)
        path.write_text(text, encoding="utf-8")
        written[kind] = path
    return written


def default_single_output(input_path: Path, kind: ArtifactKind) -> Path:
    if kind == ArtifactKind.TEX:
        return input_path.with_suffix(".tex")
    return input_path.with_name(artifact_filename(input_path, kind))


def artifact_filename(input_path: Path, kind: ArtifactKind) -> str:
    stem = input_path.stem
    suffixes = {
        ArtifactKind.HOST: ".host.py",
        ArtifactKind.AST: ".ast.json",
        ArtifactKind.EIR: ".eir.json",
        ArtifactKind.BACKEND_IR: ".backend-ir.json",
        ArtifactKind.TEX: ".tex",
    }
    return stem + suffixes[kind]


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
