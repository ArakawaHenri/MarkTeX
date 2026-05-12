from __future__ import annotations

from marktex.core import (
    Block,
    BlockQuote,
    Citation,
    CodeBlock,
    CodeExpression,
    CodePart,
    CodeText,
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
    InlineMath,
    InlineNode,
    LineBreak,
    Link,
    ListBlock,
    ListItem,
    MathBlock,
    PageBreak,
    PageSetup,
    Paragraph,
    ScopeClose,
    ScopePush,
    Strikethrough,
    Strong,
    Table,
    Text,
    ThematicBreak,
)
from marktex.host.python.symbolic import SymbolicExpr, SymbolicValue
from marktex.mos import CallUnit, RawString, TupleValue
from marktex.source import MarkTeXError, SourceSpan
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
    SurfaceCitationNode,
    SurfaceDocument,
    SurfaceEmphasisNode,
    SurfaceFootnoteRefNode,
    SurfaceImageNode,
    SurfaceInlineCodeNode,
    SurfaceInlineExpressionNode,
    SurfaceInlineMathNode,
    SurfaceInlineNode,
    SurfaceLineBreakNode,
    SurfaceLinkNode,
    SurfaceNode,
    SurfaceReferenceImageNode,
    SurfaceReferenceLinkNode,
    SurfaceStrikethroughNode,
    SurfaceStrongNode,
    SurfaceTextNode,
    ThematicBreakNode,
)


def span_to_json(span: SourceSpan | None) -> dict[str, object] | None:
    return span.to_json() if span is not None else None


def span_from_json(payload: object) -> SourceSpan | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid source span in artifact")
    return SourceSpan(
        str(payload.get("filename", "")),
        int_value(payload.get("start"), default=0),
        int_value(payload.get("end"), default=0),
        int_value(payload.get("line"), default=1),
        int_value(payload.get("column"), default=1),
    )


def mos_value_from_json(payload: object) -> RawString | TupleValue | CallUnit:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid MOS value in artifact")
    kind = payload.get("kind")
    if kind == "raw":
        return RawString(
            str(payload.get("text", "")),
            span_from_json(payload.get("origin")),
            bool_value(payload.get("force_raw", False), "raw force_raw"),
        )
    if kind == "tuple":
        return TupleValue(
            tuple(mos_value_from_json(item) for item in as_list(payload.get("items"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "call":
        return CallUnit(
            str(payload.get("context", "")),
            str(payload.get("head", "")),
            tuple(mos_value_from_json(item) for item in as_list(payload.get("args"))),
            {
                str(key): mos_value_from_json(value)
                for key, value in as_dict(payload.get("kwargs")).items()
            },
            span_from_json(payload.get("origin")),
        )
    raise MarkTeXError(f"unsupported MOS value in artifact: {kind}")


def value_from_json(payload: object) -> object:
    if isinstance(payload, dict):
        kind = payload.get("kind")
        if kind in {"raw", "tuple", "call"}:
            return mos_value_from_json(payload)
        if kind == "symbolic_value":
            return SymbolicValue(str(payload.get("owner", "")), str(payload.get("name", "")))
        if kind == "symbolic_expr":
            return SymbolicExpr(
                str(payload.get("op", "")),
                tuple(value_from_json(item) for item in as_list(payload.get("operands"))),
            )
        if kind in CORE_KINDS:
            return core_object_from_json(payload)
        return {str(key): value_from_json(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [value_from_json(item) for item in payload]
    return payload


def document_from_json(payload: object) -> Document:
    if not isinstance(payload, dict) or payload.get("kind") != "document":
        raise MarkTeXError("artifact payload is not a canonical Document")
    return Document(
        tuple(event_from_json(item) for item in as_list(payload.get("events"))),
        tuple(block_from_json(item) for item in as_list(payload.get("blocks"))),
        tuple(footnote_from_json(item) for item in as_list(payload.get("footnotes"))),
    )


def event_from_json(payload: object) -> DocumentPatch | ScopePush | ScopeClose:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid event in artifact")
    kind = payload.get("kind")
    if kind == "document_patch":
        call = mos_value_from_json(payload.get("call"))
        if not isinstance(call, CallUnit):
            raise MarkTeXError("document patch call is not a call unit")
        return DocumentPatch(call, span_from_json(payload.get("origin")))
    if kind == "scope_push":
        return ScopePush(
            str(payload.get("key", "")),
            tuple(value_from_json(item) for item in as_list(payload.get("args"))),
            {
                str(key): value_from_json(value)
                for key, value in as_dict(payload.get("kwargs")).items()
            },
            span_from_json(payload.get("origin")),
        )
    if kind == "scope_close":
        return ScopeClose(str(payload.get("key", "")), span_from_json(payload.get("origin")))
    raise MarkTeXError(f"unsupported event in artifact: {kind}")


def footnote_from_json(payload: object) -> FootnoteDefinition:
    if not isinstance(payload, dict) or payload.get("kind") != "footnote_definition":
        raise MarkTeXError("invalid footnote definition in artifact")
    return FootnoteDefinition(
        str(payload.get("label", "")),
        tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
        span_from_json(payload.get("origin")),
    )


def block_from_json(payload: object) -> Block:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid block in artifact")
    kind = payload.get("kind")
    if kind == "paragraph":
        return Paragraph(
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "heading":
        return Heading(
            int_value(payload.get("level"), default=1),
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "code_block":
        return CodeBlock(
            str(payload.get("language", "")),
            str(payload.get("body", "")),
            bool_value(payload.get("interpolated", False), "code block interpolated"),
            span_from_json(payload.get("origin")),
            tuple(code_part_from_json(item) for item in as_list(payload.get("parts"))),
        )
    if kind == "math_block":
        return MathBlock(str(payload.get("body", "")), span_from_json(payload.get("origin")))
    if kind == "table":
        return Table(
            tuple(call_from_json(item) for item in as_list(payload.get("columns"))),
            tuple(
                tuple(inline_from_json(child) for child in as_list(cell))
                for cell in as_list(payload.get("header"))
            ),
            tuple(
                tuple(
                    tuple(inline_from_json(child) for child in as_list(cell))
                    for cell in as_list(row)
                )
                for row in as_list(payload.get("rows"))
            ),
            span_from_json(payload.get("origin")),
        )
    if kind == "list":
        return ListBlock(
            bool_value(payload.get("ordered", False), "list ordered"),
            int_value(payload.get("start"), default=1),
            bool_value(payload.get("tight", True), "list tight"),
            tuple(list_item_from_json(item) for item in as_list(payload.get("items"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "blockquote":
        return BlockQuote(
            tuple(block_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "thematic_break":
        return ThematicBreak(span_from_json(payload.get("origin")))
    if kind == "page_break":
        return PageBreak(span_from_json(payload.get("origin")))
    if kind == "page_setup":
        return PageSetup(
            str_value(payload.get("width"), "page setup width"),
            str_value(payload.get("height"), "page setup height"),
            {
                str(key): str_value(value, "page setup margin")
                for key, value in as_dict(payload.get("margins")).items()
            },
            span_from_json(payload.get("origin")),
        )
    if kind == "conditional":
        return Conditional(
            tuple(conditional_branch_from_json(item) for item in as_list(payload.get("branches"))),
            tuple(block_from_json(item) for item in as_list(payload.get("else_body"))),
            span_from_json(payload.get("origin")),
        )
    raise MarkTeXError(f"unsupported block in artifact: {kind}")


def list_item_from_json(payload: object) -> ListItem:
    if not isinstance(payload, dict) or payload.get("kind") != "list_item":
        raise MarkTeXError("invalid list item in artifact")
    return ListItem(
        tuple(block_from_json(item) for item in as_list(payload.get("children"))),
        optional_bool_value(payload.get("checked"), "list item checked"),
        span_from_json(payload.get("origin")),
    )


def conditional_branch_from_json(payload: object) -> ConditionalBranch:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid conditional branch in artifact")
    return ConditionalBranch(
        value_from_json(payload.get("condition")),
        tuple(block_from_json(item) for item in as_list(payload.get("body"))),
        span_from_json(payload.get("origin")),
    )


def code_part_from_json(payload: object) -> CodePart:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid code part in artifact")
    kind = payload.get("kind")
    if kind == "code_text":
        return CodeText(str(payload.get("value", "")), span_from_json(payload.get("origin")))
    if kind == "code_expr":
        return CodeExpression(
            str(payload.get("source", "")),
            value_from_json(payload.get("value")),
            span_from_json(payload.get("origin")),
        )
    raise MarkTeXError(f"unsupported code part in artifact: {kind}")


def inline_from_json(payload: object) -> InlineNode:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid inline node in artifact")
    kind = payload.get("kind")
    if kind == "text":
        return Text(str(payload.get("value", "")), span_from_json(payload.get("origin")))
    if kind == "inline_expr":
        return InlineExpression(
            str(payload.get("source", "")),
            value_from_json(payload.get("value")),
            span_from_json(payload.get("origin")),
        )
    if kind == "emphasis":
        return Emphasis(
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "strong":
        return Strong(
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "strikethrough":
        return Strikethrough(
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            span_from_json(payload.get("origin")),
        )
    if kind == "inline_code":
        return InlineCode(str(payload.get("value", "")), span_from_json(payload.get("origin")))
    if kind == "inline_math":
        return InlineMath(str(payload.get("body", "")), span_from_json(payload.get("origin")))
    if kind == "line_break":
        return LineBreak(bool_value(payload.get("hard", False), "line break hard"), span_from_json(payload.get("origin")))
    if kind == "link":
        return Link(
            tuple(inline_from_json(item) for item in as_list(payload.get("children"))),
            str(payload.get("target", "")),
            span_from_json(payload.get("origin")),
        )
    if kind == "image":
        return Image(
            str(payload.get("alt", "")),
            str(payload.get("target", "")),
            span_from_json(payload.get("origin")),
        )
    if kind == "footnote_ref":
        return FootnoteRef(str(payload.get("label", "")), span_from_json(payload.get("origin")))
    if kind == "citation":
        return Citation(
            tuple(str(item) for item in as_list(payload.get("keys"))),
            {str(key): str(value) for key, value in as_dict(payload.get("kwargs")).items()},
            span_from_json(payload.get("origin")),
        )
    raise MarkTeXError(f"unsupported inline node in artifact: {kind}")


def call_from_json(payload: object) -> CallUnit:
    value = mos_value_from_json(payload)
    if not isinstance(value, CallUnit):
        raise MarkTeXError("expected call unit in artifact")
    return value


def core_object_from_json(payload: dict[str, object]) -> object:
    kind = payload.get("kind")
    if kind == "document":
        return document_from_json(payload)
    if kind in EVENT_KINDS:
        return event_from_json(payload)
    if kind == "footnote_definition":
        return footnote_from_json(payload)
    if kind in BLOCK_KINDS:
        return block_from_json(payload)
    if kind == "list_item":
        return list_item_from_json(payload)
    if kind in INLINE_KINDS:
        return inline_from_json(payload)
    raise MarkTeXError(f"unsupported core object in artifact: {kind}")


def surface_document_to_json(document: SurfaceDocument) -> dict[str, object]:
    return {
        "kind": "surface_document",
        "nodes": [surface_node_to_json(node) for node in document.nodes],
    }


def surface_document_from_json(payload: object) -> SurfaceDocument:
    if not isinstance(payload, dict) or payload.get("kind") != "surface_document":
        raise MarkTeXError("artifact payload is not a SurfaceDocument")
    return SurfaceDocument(tuple(surface_node_from_json(node) for node in as_list(payload.get("nodes"))))


def surface_node_to_json(node: SurfaceNode) -> dict[str, object]:
    if isinstance(node, DocumentDirectiveNode):
        return {
            "kind": "document_directive",
            "payload": node.payload,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, ScopeOpenNode):
        return {"kind": "scope_open", "payload": node.payload, "origin": span_to_json(node.origin)}
    if isinstance(node, ScopeCloseNode):
        return {"kind": "scope_close", "key": node.key, "origin": span_to_json(node.origin)}
    if isinstance(node, HostBlockNode):
        return {
            "kind": "host_block",
            "language": node.language,
            "body": node.body,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, FootnoteDefinitionNode):
        return {
            "kind": "footnote_definition",
            "label": node.label,
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, ConditionalNode):
        return {
            "kind": "conditional",
            "marker": node.marker,
            "payload": node.payload,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, HeadingNode):
        return {
            "kind": "heading",
            "level": node.level,
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, ParagraphNode):
        return {
            "kind": "paragraph",
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, CodeFenceNode):
        return {
            "kind": "code_fence",
            "language": node.language,
            "body": node.body,
            "interpolated": node.interpolated,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, MathBlockNode):
        return {
            "kind": "math_block",
            "body": node.body,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, RichTableNode):
        return {
            "kind": "rich_table",
            "column_specs": list(node.column_specs),
            "column_spec_kinds": list(node.column_spec_kinds),
            "column_spec_offsets": [list(offsets) for offsets in node.column_spec_offsets],
            "rows": [
                [[surface_inline_to_json(child) for child in cell] for cell in row]
                for row in node.rows
            ],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, ListBlockNode):
        return {
            "kind": "list",
            "ordered": node.ordered,
            "start": node.start,
            "tight": node.tight,
            "items": [surface_list_item_to_json(item) for item in node.items],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, BlockQuoteNode):
        return {
            "kind": "blockquote",
            "children": [surface_node_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, ThematicBreakNode):
        return {"kind": "thematic_break", "origin": span_to_json(node.origin)}
    if isinstance(node, LinkReferenceDefinitionNode):
        return {
            "kind": "link_reference_definition",
            "label": node.label,
            "target": node.target,
            "origin": span_to_json(node.origin),
        }
    raise MarkTeXError(f"unsupported surface node in artifact: {node!r}")


def surface_list_item_to_json(item: ListItemNode) -> dict[str, object]:
    return {
        "kind": "list_item",
        "children": [surface_node_to_json(child) for child in item.children],
        "checked": item.checked,
        "origin": span_to_json(item.origin),
    }


def surface_inline_to_json(node: SurfaceInlineNode) -> dict[str, object]:
    if isinstance(node, SurfaceTextNode):
        return {"kind": "text", "value": node.value, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceInlineExpressionNode):
        return {"kind": "inline_expr", "source": node.source, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceEmphasisNode):
        return {
            "kind": "emphasis",
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceStrongNode):
        return {
            "kind": "strong",
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceStrikethroughNode):
        return {
            "kind": "strikethrough",
            "children": [surface_inline_to_json(child) for child in node.children],
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceInlineCodeNode):
        return {"kind": "inline_code", "value": node.value, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceInlineMathNode):
        return {"kind": "inline_math", "body": node.body, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceLineBreakNode):
        return {"kind": "line_break", "hard": node.hard, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceLinkNode):
        return {
            "kind": "link",
            "children": [surface_inline_to_json(child) for child in node.children],
            "target": node.target,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceReferenceLinkNode):
        return {
            "kind": "reference_link",
            "children": [surface_inline_to_json(child) for child in node.children],
            "label": node.label,
            "raw": node.raw,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceImageNode):
        return {"kind": "image", "alt": node.alt, "target": node.target, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceReferenceImageNode):
        return {
            "kind": "reference_image",
            "alt": node.alt,
            "label": node.label,
            "raw": node.raw,
            "origin": span_to_json(node.origin),
        }
    if isinstance(node, SurfaceFootnoteRefNode):
        return {"kind": "footnote_ref", "label": node.label, "origin": span_to_json(node.origin)}
    if isinstance(node, SurfaceCitationNode):
        return {
            "kind": "citation",
            "keys": list(node.keys),
            "kwargs": dict(node.kwargs),
            "origin": span_to_json(node.origin),
        }
    raise MarkTeXError(f"unsupported surface inline node in artifact: {node!r}")


def surface_node_from_json(payload: object) -> SurfaceNode:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid surface node in artifact")
    kind = payload.get("kind")
    origin = required_span(payload.get("origin"))
    if kind == "document_directive":
        return DocumentDirectiveNode(str(payload.get("payload", "")), origin)
    if kind == "scope_open":
        return ScopeOpenNode(str(payload.get("payload", "")), origin)
    if kind == "scope_close":
        return ScopeCloseNode(str(payload.get("key", "")), origin)
    if kind == "host_block":
        return HostBlockNode(
            str(payload.get("language", "")),
            str(payload.get("body", "")),
            origin,
        )
    if kind == "footnote_definition":
        return FootnoteDefinitionNode(
            str(payload.get("label", "")),
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "conditional":
        return ConditionalNode(
            str(payload.get("marker", "")),
            str(payload.get("payload", "")),
            origin,
        )
    if kind == "heading":
        return HeadingNode(
            int_value(payload.get("level"), default=1),
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "paragraph":
        return ParagraphNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "code_fence":
        return CodeFenceNode(
            str(payload.get("language", "")),
            str(payload.get("body", "")),
            bool_value(payload.get("interpolated", False), "code fence interpolated"),
            origin,
        )
    if kind == "math_block":
        return MathBlockNode(str(payload.get("body", "")), origin)
    if kind == "rich_table":
        return RichTableNode(
            tuple(str(item) for item in as_list(payload.get("column_specs"))),
            tuple(str(item) for item in as_list(payload.get("column_spec_kinds"))),
            tuple(
                tuple(int_value(offset) for offset in as_list(offsets))
                for offsets in as_list(payload.get("column_spec_offsets"))
            ),
            tuple(
                tuple(
                    tuple(surface_inline_from_json(child) for child in as_list(cell))
                    for cell in as_list(row)
                )
                for row in as_list(payload.get("rows"))
            ),
            origin,
        )
    if kind == "list":
        return ListBlockNode(
            bool_value(payload.get("ordered", False), "surface list ordered"),
            int_value(payload.get("start"), default=1),
            bool_value(payload.get("tight", True), "surface list tight"),
            tuple(surface_list_item_from_json(item) for item in as_list(payload.get("items"))),
            origin,
        )
    if kind == "blockquote":
        return BlockQuoteNode(
            tuple(surface_node_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "thematic_break":
        return ThematicBreakNode(origin)
    if kind == "link_reference_definition":
        return LinkReferenceDefinitionNode(
            str(payload.get("label", "")),
            str(payload.get("target", "")),
            origin,
        )
    raise MarkTeXError(f"unsupported surface node in artifact: {kind}")


def surface_list_item_from_json(payload: object) -> ListItemNode:
    if not isinstance(payload, dict) or payload.get("kind") != "list_item":
        raise MarkTeXError("invalid surface list item in artifact")
    return ListItemNode(
        tuple(surface_node_from_json(item) for item in as_list(payload.get("children"))),
        optional_bool_value(payload.get("checked"), "surface list item checked"),
        required_span(payload.get("origin")),
    )


def surface_inline_from_json(payload: object) -> SurfaceInlineNode:
    if not isinstance(payload, dict):
        raise MarkTeXError("invalid surface inline node in artifact")
    kind = payload.get("kind")
    origin = required_span(payload.get("origin"))
    if kind == "text":
        return SurfaceTextNode(str(payload.get("value", "")), origin)
    if kind == "inline_expr":
        return SurfaceInlineExpressionNode(str(payload.get("source", "")), origin)
    if kind == "emphasis":
        return SurfaceEmphasisNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "strong":
        return SurfaceStrongNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "strikethrough":
        return SurfaceStrikethroughNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            origin,
        )
    if kind == "inline_code":
        return SurfaceInlineCodeNode(str(payload.get("value", "")), origin)
    if kind == "inline_math":
        return SurfaceInlineMathNode(str(payload.get("body", "")), origin)
    if kind == "line_break":
        return SurfaceLineBreakNode(bool_value(payload.get("hard", True), "surface line break hard"), origin)
    if kind == "link":
        return SurfaceLinkNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            str(payload.get("target", "")),
            origin,
        )
    if kind == "reference_link":
        return SurfaceReferenceLinkNode(
            tuple(surface_inline_from_json(item) for item in as_list(payload.get("children"))),
            str(payload.get("label", "")),
            str(payload.get("raw", "")),
            origin,
        )
    if kind == "image":
        return SurfaceImageNode(str(payload.get("alt", "")), str(payload.get("target", "")), origin)
    if kind == "reference_image":
        return SurfaceReferenceImageNode(
            str(payload.get("alt", "")),
            str(payload.get("label", "")),
            str(payload.get("raw", "")),
            origin,
        )
    if kind == "footnote_ref":
        return SurfaceFootnoteRefNode(str(payload.get("label", "")), origin)
    if kind == "citation":
        return SurfaceCitationNode(
            tuple(str(item) for item in as_list(payload.get("keys"))),
            {str(key): str(value) for key, value in as_dict(payload.get("kwargs")).items()},
            origin,
        )
    raise MarkTeXError(f"unsupported surface inline node in artifact: {kind}")


def required_span(payload: object) -> SourceSpan:
    span = span_from_json(payload)
    if span is None:
        raise MarkTeXError("surface artifact is missing required source span")
    return span


def as_list(payload: object) -> list[object]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise MarkTeXError("artifact field is not a list")
    return payload


def as_dict(payload: object) -> dict[object, object]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise MarkTeXError("artifact field is not an object")
    return payload


def int_value(payload: object, *, default: int = 0) -> int:
    if payload is None:
        return default
    if isinstance(payload, int) and not isinstance(payload, bool):
        return payload
    raise MarkTeXError("artifact integer field is not an integer")


def bool_value(payload: object, label: str) -> bool:
    if isinstance(payload, bool):
        return payload
    raise MarkTeXError(f"{label} must be a boolean")


def optional_bool_value(payload: object, label: str) -> bool | None:
    if payload is None:
        return None
    return bool_value(payload, label)


def str_value(payload: object, label: str) -> str:
    if isinstance(payload, str):
        return payload
    raise MarkTeXError(f"{label} must be a string")


EVENT_KINDS = {"document_patch", "scope_push", "scope_close"}
INLINE_KINDS = {
    "text",
    "inline_expr",
    "emphasis",
    "strong",
    "strikethrough",
    "inline_code",
    "inline_math",
    "line_break",
    "link",
    "image",
    "footnote_ref",
    "citation",
}
BLOCK_KINDS = {
    "paragraph",
    "heading",
    "code_block",
    "math_block",
    "table",
    "list",
    "blockquote",
    "thematic_break",
    "page_break",
    "page_setup",
    "conditional",
}
CORE_KINDS = EVENT_KINDS | INLINE_KINDS | BLOCK_KINDS | {
    "document",
    "footnote_definition",
    "list_item",
}
