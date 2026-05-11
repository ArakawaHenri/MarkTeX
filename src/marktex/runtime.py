from __future__ import annotations

from dataclasses import dataclass, field

from marktex.core import (
    Block,
    BlockQuote,
    Citation,
    CodeBlock,
    CodePart,
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
    LineBreak,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    ScopeClose,
    ScopePush,
    Strikethrough,
    Strong,
    Table,
    Text,
    ThematicBreak,
)
from marktex.mos import CallUnit, RawString, TupleValue
from marktex.mos.model import MosValue
from marktex.source import MarkTeXError

RuntimeEvent = DocumentPatch | ScopePush | ScopeClose


@dataclass
class RuntimeSession:
    events: list[RuntimeEvent] = field(default_factory=list)

    def invoke(self, obj: object) -> object:
        if not isinstance(obj, DocumentPatch | ScopePush | ScopeClose):
            raise MarkTeXError(f"unsupported runtime object: {obj!r}")
        self.events.append(obj)
        return obj

    def raw(self, text: object, *, force_raw: bool = False) -> RawString:
        return RawString(str(text), force_raw=force_raw)

    def tuple_value(self, *items: object) -> TupleValue:
        return TupleValue(tuple(value_to_mos(item) for item in items))

    def call(
        self,
        head: str,
        *args: object,
        context: str = "document",
        **kwargs: object,
    ) -> CallUnit:
        return CallUnit(
            context,
            head,
            args=tuple(value_to_mos(arg) for arg in args),
            kwargs={key: value_to_mos(value) for key, value in kwargs.items()},
        )

    def document_patch(self, head: str, *args: object, **kwargs: object) -> DocumentPatch:
        return DocumentPatch(self.call(head, *args, context="document", **kwargs))

    def scope_push(
        self,
        key: str,
        *args: object,
        scope: str = "DEFAULT",
        **kwargs: object,
    ) -> ScopePush:
        payload = {name: value_to_mos(value) for name, value in kwargs.items()}
        if scope != "DEFAULT":
            payload["scope"] = RawString(scope)
        return ScopePush(key, args=tuple(value_to_mos(arg) for arg in args), kwargs=payload)

    def scope_close(self, key: str = "") -> ScopeClose:
        return ScopeClose(key)

    def drain(self) -> tuple[RuntimeEvent, ...]:
        events = tuple(self.events)
        self.events.clear()
        return events

    def reset(self) -> None:
        self.events.clear()

    def finish(self) -> list[RuntimeEvent]:
        return list(self.events)

    def document(
        self,
        *,
        events: tuple[RuntimeEvent, ...] = (),
        blocks: tuple[Block, ...] = (),
        footnotes: tuple[FootnoteDefinition, ...] = (),
    ) -> Document:
        return document(events=events, blocks=blocks, footnotes=footnotes)

    def text(self, value: object) -> Text:
        return text(value)

    def paragraph(self, *children: object) -> Paragraph:
        return paragraph(*children)

    def heading(self, level: int, *children: object) -> Heading:
        return heading(level, *children)

    def table(
        self,
        columns: tuple[CallUnit, ...],
        header: tuple[tuple[InlineNode, ...], ...],
        rows: tuple[tuple[tuple[InlineNode, ...], ...], ...] = (),
    ) -> Table:
        return table(columns, header, rows)

    def footnote_definition(self, label: str, *children: object) -> FootnoteDefinition:
        return footnote_definition(label, *children)


def value_to_mos(value: object) -> MosValue:
    if isinstance(value, CallUnit | RawString | TupleValue):
        return value
    if isinstance(value, tuple | list):
        return TupleValue(tuple(value_to_mos(item) for item in value))
    return RawString(str(value))


_DEFAULT_SESSION = RuntimeSession()


def invoke(obj: object) -> object:
    return _DEFAULT_SESSION.invoke(obj)


def raw(text: object, *, force_raw: bool = False) -> RawString:
    return _DEFAULT_SESSION.raw(text, force_raw=force_raw)


def tuple_value(*items: object) -> TupleValue:
    return _DEFAULT_SESSION.tuple_value(*items)


def call(head: str, *args: object, context: str = "document", **kwargs: object) -> CallUnit:
    return _DEFAULT_SESSION.call(head, *args, context=context, **kwargs)


def document_patch(head: str, *args: object, **kwargs: object) -> DocumentPatch:
    return _DEFAULT_SESSION.document_patch(head, *args, **kwargs)


def scope_push(key: str, *args: object, scope: str = "DEFAULT", **kwargs: object) -> ScopePush:
    return _DEFAULT_SESSION.scope_push(key, *args, scope=scope, **kwargs)


def scope_close(key: str = "") -> ScopeClose:
    return _DEFAULT_SESSION.scope_close(key)


def drain() -> tuple[RuntimeEvent, ...]:
    return _DEFAULT_SESSION.drain()


def reset() -> None:
    _DEFAULT_SESSION.reset()


def finish() -> list[RuntimeEvent]:
    return _DEFAULT_SESSION.finish()


def document(
    *,
    events: tuple[RuntimeEvent, ...] = (),
    blocks: tuple[Block, ...] = (),
    footnotes: tuple[FootnoteDefinition, ...] = (),
) -> Document:
    return Document(tuple(events), tuple(blocks), tuple(footnotes))


def text(value: object) -> Text:
    return Text(str(value))


def paragraph(*children: object) -> Paragraph:
    return Paragraph(tuple(inline_node(child) for child in children))


def heading(level: int, *children: object) -> Heading:
    return Heading(level, tuple(inline_node(child) for child in children))


def code_block(
    language: str,
    body: str,
    *,
    interpolated: bool = False,
    parts: tuple[CodePart, ...] = (),
) -> CodeBlock:
    return CodeBlock(language, body, interpolated=interpolated, parts=tuple(parts))


def table(
    columns: tuple[CallUnit, ...],
    header: tuple[tuple[InlineNode, ...], ...],
    rows: tuple[tuple[tuple[InlineNode, ...], ...], ...] = (),
) -> Table:
    return Table(tuple(columns), tuple(header), tuple(rows))


def footnote_definition(label: str, *children: object) -> FootnoteDefinition:
    return FootnoteDefinition(label, tuple(inline_node(child) for child in children))


def footnote_ref(label: str) -> FootnoteRef:
    return FootnoteRef(label)


def citation(*keys: str, **kwargs: str) -> Citation:
    return Citation(tuple(keys), {str(key): str(value) for key, value in kwargs.items()})


def emphasis(*children: object) -> Emphasis:
    return Emphasis(tuple(inline_node(child) for child in children))


def strong(*children: object) -> Strong:
    return Strong(tuple(inline_node(child) for child in children))


def strikethrough(*children: object) -> Strikethrough:
    return Strikethrough(tuple(inline_node(child) for child in children))


def inline_code(value: str) -> InlineCode:
    return InlineCode(value)


def line_break(*, hard: bool = True) -> LineBreak:
    return LineBreak(hard)


def link(target: str, *children: object) -> Link:
    return Link(tuple(inline_node(child) for child in children), target)


def image(alt: str, target: str) -> Image:
    return Image(alt, target)


def list_item(*children: Block, checked: bool | None = None) -> ListItem:
    return ListItem(tuple(children), checked)


def list_block(
    *items: ListItem,
    ordered: bool = False,
    start: int = 1,
    tight: bool = True,
) -> ListBlock:
    return ListBlock(ordered, start, tight, tuple(items))


def blockquote(*children: Block) -> BlockQuote:
    return BlockQuote(tuple(children))


def thematic_break() -> ThematicBreak:
    return ThematicBreak()


def inline_expr(source: str, value: object) -> InlineExpression:
    return InlineExpression(source, value)


def inline_node(value: object) -> InlineNode:
    if isinstance(
        value,
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
        | Citation,
    ):
        return value
    return Text(str(value))


def document_from_surface_artifact(
    artifact: dict[str, object],
    *,
    no_host: bool = False,
) -> Document:
    from marktex.driver.compiler import document_from_surface_artifact as build_from_surface

    return build_from_surface(artifact, no_host=no_host)


def document_from_ast_artifact(artifact: dict[str, object]) -> Document:
    from marktex.driver.compiler import ArtifactKind, artifact_payload_from_object
    from marktex.driver.serde import document_from_json

    payload = artifact_payload_from_object(artifact, expected_kind=ArtifactKind.AST)
    return document_from_json(payload)
