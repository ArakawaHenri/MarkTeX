from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from marktex.source import SourceSpan


@dataclass(frozen=True)
class RawString:
    text: str
    origin: SourceSpan | None = None
    force_raw: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "raw",
            "text": self.text,
            "force_raw": self.force_raw,
            "origin": self.origin.to_json() if self.origin else None,
        }


@dataclass(frozen=True)
class TupleValue:
    items: tuple["MosValue", ...]
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "tuple",
            "items": [value_to_json(item) for item in self.items],
            "origin": self.origin.to_json() if self.origin else None,
        }


@dataclass(frozen=True)
class CallUnit:
    context: str
    head: str
    args: tuple["MosValue", ...] = ()
    kwargs: dict[str, "MosValue"] = field(default_factory=dict)
    origin: SourceSpan | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "kind": "call",
            "context": self.context,
            "head": self.head,
            "args": [value_to_json(arg) for arg in self.args],
            "kwargs": {key: value_to_json(value) for key, value in self.kwargs.items()},
            "origin": self.origin.to_json() if self.origin else None,
        }


MosValue: TypeAlias = RawString | TupleValue | CallUnit


def value_to_json(value: MosValue) -> dict[str, object]:
    return value.to_json()
