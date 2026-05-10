from __future__ import annotations

from dataclasses import dataclass, field

from marktex.core import DocumentPatch, ScopeClose, ScopePush
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
