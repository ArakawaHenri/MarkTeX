from __future__ import annotations

from marktex.core import DocumentPatch, ScopeClose, ScopePush

_EVENTS: list[object] = []


def invoke(obj: object) -> object:
    _EVENTS.append(obj)
    return obj


def document_patch(head: str, *args: object, **kwargs: object) -> DocumentPatch:
    from marktex.mos import CallUnit

    return DocumentPatch(CallUnit("document", head, args=args, kwargs=dict(kwargs)))


def scope_push(key: str, *args: object, scope: str = "DEFAULT", **kwargs: object) -> ScopePush:
    payload = dict(kwargs)
    payload["scope"] = scope
    return ScopePush(key, args=args, kwargs=payload)


def scope_close(key: str = "") -> ScopeClose:
    return ScopeClose(key)


def finish() -> list[object]:
    return list(_EVENTS)
