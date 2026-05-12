from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from marktex.source import SourceSpan


@dataclass(frozen=True)
class SurfaceTextNode:
    value: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceInlineExpressionNode:
    source: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceEmphasisNode:
    children: tuple["SurfaceInlineNode", ...]
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceStrongNode:
    children: tuple["SurfaceInlineNode", ...]
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceStrikethroughNode:
    children: tuple["SurfaceInlineNode", ...]
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceInlineCodeNode:
    value: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceInlineMathNode:
    body: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceLineBreakNode:
    hard: bool
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceLinkNode:
    children: tuple["SurfaceInlineNode", ...]
    target: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceReferenceLinkNode:
    children: tuple["SurfaceInlineNode", ...]
    label: str
    raw: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceImageNode:
    alt: str
    target: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceReferenceImageNode:
    alt: str
    label: str
    raw: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceFootnoteRefNode:
    label: str
    origin: SourceSpan


@dataclass(frozen=True)
class SurfaceCitationNode:
    keys: tuple[str, ...]
    kwargs: dict[str, str]
    origin: SourceSpan


SurfaceInlineNode: TypeAlias = (
    SurfaceTextNode
    | SurfaceInlineExpressionNode
    | SurfaceEmphasisNode
    | SurfaceStrongNode
    | SurfaceStrikethroughNode
    | SurfaceInlineCodeNode
    | SurfaceInlineMathNode
    | SurfaceLineBreakNode
    | SurfaceLinkNode
    | SurfaceReferenceLinkNode
    | SurfaceImageNode
    | SurfaceReferenceImageNode
    | SurfaceFootnoteRefNode
    | SurfaceCitationNode
)


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
    children: tuple[SurfaceInlineNode, ...]
    origin: SourceSpan


@dataclass(frozen=True)
class ConditionalNode:
    marker: str
    payload: str
    origin: SourceSpan


@dataclass(frozen=True)
class HeadingNode:
    level: int
    children: tuple[SurfaceInlineNode, ...]
    origin: SourceSpan


@dataclass(frozen=True)
class ParagraphNode:
    children: tuple[SurfaceInlineNode, ...]
    origin: SourceSpan


@dataclass(frozen=True)
class CodeFenceNode:
    language: str
    body: str
    interpolated: bool
    origin: SourceSpan


@dataclass(frozen=True)
class MathBlockNode:
    body: str
    origin: SourceSpan


@dataclass(frozen=True)
class RichTableNode:
    column_specs: tuple[str, ...]
    column_spec_kinds: tuple[str, ...]
    column_spec_offsets: tuple[tuple[int, ...], ...]
    rows: tuple[tuple[tuple[SurfaceInlineNode, ...], ...], ...]
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
    | MathBlockNode
    | RichTableNode
    | ListBlockNode
    | BlockQuoteNode
    | ThematicBreakNode
    | LinkReferenceDefinitionNode
)


@dataclass(frozen=True)
class SurfaceDocument:
    nodes: tuple[SurfaceNode, ...]
