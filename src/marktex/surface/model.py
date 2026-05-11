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
    body_offsets: tuple[int, ...]
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
    text_offsets: tuple[int, ...]
    origin: SourceSpan


@dataclass(frozen=True)
class ParagraphNode:
    text: str
    origin: SourceSpan
    text_offsets: tuple[int, ...]


@dataclass(frozen=True)
class CodeFenceNode:
    language: str
    body: str
    interpolated: bool
    origin: SourceSpan


@dataclass(frozen=True)
class RichTableNode:
    column_specs: tuple[str, ...]
    column_spec_kinds: tuple[str, ...]
    column_spec_offsets: tuple[tuple[int, ...], ...]
    rows: tuple[tuple[str, ...], ...]
    cell_offsets: tuple[tuple[tuple[int, ...], ...], ...]
    origin: SourceSpan


@dataclass(frozen=True)
class ListItemNode:
    children: tuple["SurfaceNode", ...]
    checked: bool | None
    origin: SourceSpan


@dataclass(frozen=True)
class ListBlockNode:
    ordered: bool
    start: int
    tight: bool
    items: tuple[ListItemNode, ...]
    origin: SourceSpan


@dataclass(frozen=True)
class BlockQuoteNode:
    children: tuple["SurfaceNode", ...]
    origin: SourceSpan


@dataclass(frozen=True)
class ThematicBreakNode:
    origin: SourceSpan


@dataclass(frozen=True)
class LinkReferenceDefinitionNode:
    label: str
    target: str
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
    | ListBlockNode
    | BlockQuoteNode
    | ThematicBreakNode
    | LinkReferenceDefinitionNode
)


@dataclass(frozen=True)
class SurfaceDocument:
    nodes: tuple[SurfaceNode, ...]
