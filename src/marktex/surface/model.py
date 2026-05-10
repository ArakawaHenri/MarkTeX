from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from marktex.source import SourceSpan


@dataclass(frozen=True)
class DocumentDirectiveNode:
    payload: str
    origin: SourceSpan


@dataclass(frozen=True)
class ScopeOpenNode:
    payload: str
    origin: SourceSpan


@dataclass(frozen=True)
class ScopeCloseNode:
    key: str
    origin: SourceSpan


@dataclass(frozen=True)
class HostBlockNode:
    language: str
    body: str
    origin: SourceSpan


@dataclass(frozen=True)
class FootnoteDefinitionNode:
    label: str
    body: str
    origin: SourceSpan


@dataclass(frozen=True)
class ConditionalNode:
    marker: str
    payload: str
    origin: SourceSpan


@dataclass(frozen=True)
class HeadingNode:
    level: int
    text: str
    origin: SourceSpan


@dataclass(frozen=True)
class ParagraphNode:
    text: str
    origin: SourceSpan


@dataclass(frozen=True)
class CodeFenceNode:
    language: str
    body: str
    interpolated: bool
    origin: SourceSpan


@dataclass(frozen=True)
class RichTableNode:
    column_specs: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    origin: SourceSpan


SurfaceNode: TypeAlias = (
    DocumentDirectiveNode
    | ScopeOpenNode
    | ScopeCloseNode
    | HostBlockNode
    | FootnoteDefinitionNode
    | ConditionalNode
    | HeadingNode
    | ParagraphNode
    | CodeFenceNode
    | RichTableNode
)


@dataclass(frozen=True)
class SurfaceDocument:
    nodes: tuple[SurfaceNode, ...]
