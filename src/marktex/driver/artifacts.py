from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from marktex._version import __version__
from marktex.driver.serde import surface_document_to_json
from marktex.source import MarkTeXError
from marktex.surface import SurfaceDocument


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


def normalize_input_stage(stage: InputStage | str) -> InputStage:
    if isinstance(stage, InputStage):
        return stage
    stage = stage.strip()
    try:
        return InputStage(stage)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in InputStage)
        raise MarkTeXError(f"unsupported input stage: {stage}; expected one of {allowed}") from exc


def normalize_target(target: str) -> Literal["lualatex"]:
    normalized = target.strip()
    if normalized == "lualatex":
        return "lualatex"
    raise MarkTeXError(f"unsupported target: {target}; 0.1 only supports lualatex")


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

    target_dir = out_dir or (Path.cwd() / f"{input_path.stem}.mtxbuild")
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
    return Path.cwd() / artifact_filename(input_path, kind, target)


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
