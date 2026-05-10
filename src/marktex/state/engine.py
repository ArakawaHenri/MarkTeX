from __future__ import annotations

from dataclasses import dataclass

from marktex.core import DocumentPatch, MarkTeXObject, ScopeClose, ScopePush, object_to_json
from marktex.source import MarkTeXError, SourceSpan


@dataclass(frozen=True)
class InvokeEvent:
    order: int
    object: MarkTeXObject
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "order": self.order,
            "object": object_to_json(self.object),
            "origin": self.origin.to_json() if self.origin else None,
        }


@dataclass
class _ScopeFrame:
    key: str
    open_order: int
    close_order: int | None = None


class StateEngine:
    def __init__(self) -> None:
        self.events: list[InvokeEvent] = []
        self._frames: list[_ScopeFrame] = []

    def invoke(self, obj: MarkTeXObject, origin: SourceSpan | None = None) -> None:
        order = len(self.events)
        if isinstance(obj, ScopePush):
            self._frames.append(_ScopeFrame(obj.key, order))
        elif isinstance(obj, ScopeClose):
            self._close_scope(obj.key, obj.origin)
        elif not isinstance(obj, DocumentPatch):
            # Non-state objects may still appear in the log later, but the V0
            # driver only invokes state objects.
            pass
        self.events.append(InvokeEvent(order, obj, origin))

    def _close_scope(self, key: str, origin: SourceSpan | None) -> None:
        for frame in reversed(self._frames):
            if frame.key == key and frame.close_order is None:
                frame.close_order = len(self.events)
                return
        raise MarkTeXError(f"unmatched scope close for key {key!r}", origin)

    def to_json(self) -> dict[str, object]:
        return {
            "events": [event.to_json() for event in self.events],
            "scopes": [
                {
                    "key": frame.key,
                    "open_order": frame.open_order,
                    "close_order": frame.close_order,
                }
                for frame in self._frames
            ],
        }
