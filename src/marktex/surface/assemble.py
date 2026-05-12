from __future__ import annotations

from dataclasses import dataclass

from marktex.source import MarkTeXError, SourceSpan
from marktex.surface.fallback_layer import FallbackLayerDocument
from marktex.surface.model import (
    BlockQuoteNode,
    ConditionalNode,
    FootnoteDefinitionNode,
    LinkReferenceDefinitionNode,
    ListBlockNode,
    SurfaceDocument,
    SurfaceNode,
)


def assemble_surface(document: FallbackLayerDocument) -> SurfaceDocument:
    validate_declaration_sections(document.nodes)
    return SurfaceDocument(document.nodes)


@dataclass
class _DeclarationScope:
    declaration_section_started: bool = False

    def accept_declaration(self) -> None:
        self.declaration_section_started = True

    def accept_content(self, origin: SourceSpan) -> None:
        if self.declaration_section_started:
            raise MarkTeXError(
                "fallback declarations must appear after all content in their scope",
                origin,
            )


@dataclass
class _ConditionalDeclarationFrame:
    branch: _DeclarationScope


def validate_declaration_sections(nodes: tuple[SurfaceNode, ...]) -> None:
    root = _DeclarationScope()
    conditional_stack: list[_ConditionalDeclarationFrame] = []

    def current_scope() -> _DeclarationScope:
        return conditional_stack[-1].branch if conditional_stack else root

    for node in nodes:
        if isinstance(node, ConditionalNode):
            if node.marker == "!?":
                current_scope().accept_content(node.origin)
                conditional_stack.append(_ConditionalDeclarationFrame(_DeclarationScope()))
                continue
            if node.marker in {"!?!?", "!?!"}:
                if conditional_stack:
                    conditional_stack[-1].branch = _DeclarationScope()
                continue
            if node.marker == "!!?":
                if conditional_stack:
                    conditional_stack.pop()
                continue

        if isinstance(node, FootnoteDefinitionNode | LinkReferenceDefinitionNode):
            current_scope().accept_declaration()
            continue

        current_scope().accept_content(node.origin)
        validate_child_declaration_sections(node)


def validate_child_declaration_sections(node: SurfaceNode) -> None:
    if isinstance(node, BlockQuoteNode):
        validate_declaration_sections(node.children)
        return
    if isinstance(node, ListBlockNode):
        for item in node.items:
            validate_declaration_sections(item.children)
