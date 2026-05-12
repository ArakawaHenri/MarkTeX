from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from marktex.backend.lualatex import make_backend_ir
from marktex.backend.lualatex.emit import emit_lualatex_from_backend_ir
from marktex.core import (
    Document,
    DocumentPatch,
    ScopeClose,
    ScopePush,
)
from marktex.driver.artifacts import (
    ORDERED_ARTIFACTS,
    ArtifactKind,
    InputStage,
    artifact_envelope,
    artifact_payload_from_text,
    json_dumps,
    normalize_input_stage,
    normalize_target,
    resolve_requested_emits,
    surface_payload_from_document,
    write_artifacts,
)
from marktex.driver.serde import document_from_json
from marktex.driver.surface_to_core import validate_document_call
from marktex.host.python import emit_host_script
from marktex.schema import SchemaRegistry, builtin_registry
from marktex.semantics import canonicalize_document
from marktex.source import MarkTeXError
from marktex.state import StateEngine
from marktex.surface import parse_surface


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
    target = normalize_target(target)

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
    document = canonicalize_document(execute_host_script(host_script, filename=filename + ".host.py"))
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
    target = normalize_target(target)
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
        document = canonicalize_document(document)
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
