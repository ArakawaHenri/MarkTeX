from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from marktex.mos import CallUnit
from marktex.mos.model import value_to_json
from marktex.source import SourceSpan


def _origin(origin: SourceSpan | None) -> dict[str, object] | None:
    return origin.to_json() if origin else None


@dataclass(frozen=True)
class Text:
    value: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "text", "value": self.value, "origin": _origin(self.origin)}


@dataclass(frozen=True)
class InlineExpression:
    source: str
    value: Any
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "inline_expr",
            "source": self.source,
            "value": object_to_json(self.value),
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Emphasis:
    children: tuple["InlineNode", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "emphasis",
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Strong:
    children: tuple["InlineNode", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "strong",
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Strikethrough:
    children: tuple["InlineNode", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "strikethrough",
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class InlineCode:
    value: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "inline_code", "value": self.value, "origin": _origin(self.origin)}


@dataclass(frozen=True)
class LineBreak:
    hard: bool
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "line_break", "hard": self.hard, "origin": _origin(self.origin)}


@dataclass(frozen=True)
class Link:
    children: tuple["InlineNode", ...]
    target: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "link",
            "children": [child.to_json() for child in self.children],
            "target": self.target,
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Image:
    alt: str
    target: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "image",
            "alt": self.alt,
            "target": self.target,
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class FootnoteRef:
    label: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "footnote_ref", "label": self.label, "origin": _origin(self.origin)}


@dataclass(frozen=True)
class Citation:
    keys: tuple[str, ...]
    kwargs: dict[str, str] = field(default_factory=dict)
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "citation",
            "keys": list(self.keys),
            "kwargs": dict(self.kwargs),
            "origin": _origin(self.origin),
        }


InlineNode: TypeAlias = (
    Text
    | InlineExpression
    | Emphasis
    | Strong
    | Strikethrough
    | InlineCode
    | LineBreak
    | Link
    | Image
    | FootnoteRef
    | Citation
)


@dataclass(frozen=True)
class Paragraph:
    children: tuple[InlineNode, ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "paragraph",
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Heading:
    level: int
    children: "tuple[InlineNode, ...]"
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "heading",
            "level": self.level,
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class CodeText:
    value: str
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "code_text", "value": self.value, "origin": _origin(self.origin)}


@dataclass(frozen=True)
class CodeExpression:
    source: str
    value: Any
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "code_expr",
            "source": self.source,
            "value": object_to_json(self.value),
            "origin": _origin(self.origin),
        }


CodePart: TypeAlias = CodeText | CodeExpression


@dataclass(frozen=True)
class CodeBlock:
    language: str
    body: str
    interpolated: bool = False
    origin: SourceSpan | None = None
    parts: tuple[CodePart, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "code_block",
            "language": self.language,
            "body": self.body,
            "interpolated": self.interpolated,
            "parts": [part.to_json() for part in self.parts],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Table:
    columns: tuple[CallUnit, ...]
    header: "tuple[tuple[InlineNode, ...], ...]"
    rows: "tuple[tuple[tuple[InlineNode, ...], ...], ...]"
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "table",
            "columns": [column.to_json() for column in self.columns],
            "header": [[child.to_json() for child in cell] for cell in self.header],
            "rows": [[[child.to_json() for child in cell] for cell in row] for row in self.rows],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class ListItem:
    children: tuple["Block", ...]
    checked: bool | None = None
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "list_item",
            "checked": self.checked,
            "children": [object_to_json(child) for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class ListBlock:
    ordered: bool
    start: int
    tight: bool
    items: tuple[ListItem, ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "list",
            "ordered": self.ordered,
            "start": self.start,
            "tight": self.tight,
            "items": [item.to_json() for item in self.items],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class BlockQuote:
    children: tuple["Block", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "blockquote",
            "children": [object_to_json(child) for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class ThematicBreak:
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "thematic_break", "origin": _origin(self.origin)}


@dataclass(frozen=True)
class ConditionalBranch:
    condition: Any
    body: tuple["Block", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "condition": object_to_json(self.condition),
            "body": [object_to_json(block) for block in self.body],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class Conditional:
    branches: tuple[ConditionalBranch, ...]
    else_body: tuple["Block", ...] = ()
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "conditional",
            "branches": [branch.to_json() for branch in self.branches],
            "else_body": [object_to_json(block) for block in self.else_body],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class FootnoteDefinition:
    label: str
    children: tuple[InlineNode, ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "footnote_definition",
            "label": self.label,
            "children": [child.to_json() for child in self.children],
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class DocumentPatch:
    call: CallUnit
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "document_patch", "call": self.call.to_json(), "origin": _origin(self.origin)}


@dataclass(frozen=True)
class ScopePush:
    key: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "scope_push",
            "key": self.key,
            "args": [object_to_json(arg) for arg in self.args],
            "kwargs": {key: object_to_json(value) for key, value in self.kwargs.items()},
            "origin": _origin(self.origin),
        }


@dataclass(frozen=True)
class ScopeClose:
    key: str = ""
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {"kind": "scope_close", "key": self.key, "origin": _origin(self.origin)}


Block: TypeAlias = (
    Paragraph | Heading | CodeBlock | Table | ListBlock | BlockQuote | ThematicBreak | Conditional
)
MarkTeXObject: TypeAlias = DocumentPatch | ScopePush | ScopeClose | Block | InlineNode


@dataclass(frozen=True)
class Document:
    events: tuple[MarkTeXObject, ...] = ()
    blocks: tuple[Block, ...] = ()
    footnotes: tuple[FootnoteDefinition, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "document",
            "events": [object_to_json(event) for event in self.events],
            "blocks": [object_to_json(block) for block in self.blocks],
            "footnotes": [footnote.to_json() for footnote in self.footnotes],
        }


def object_to_json(value: Any) -> Any:
    if hasattr(value, "to_json"):
        return value.to_json()
    if isinstance(value, tuple):
        return [object_to_json(item) for item in value]
    if isinstance(value, list):
        return [object_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): object_to_json(item) for key, item in value.items()}
    if isinstance(value, CallUnit):
        return value.to_json()
    if hasattr(value, "text") and value.__class__.__name__ == "RawString":
        return value_to_json(value)
    return value
