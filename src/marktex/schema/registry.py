from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from marktex.mos import CallUnit, MosValue, RawString


@dataclass(frozen=True)
class ParamSpec:
    name: str
    required: bool = False


@dataclass(frozen=True)
class CallSpec:
    head: str
    lowerer: str
    positional: tuple[ParamSpec, ...] = ()
    kwargs: Mapping[str, ParamSpec] = field(default_factory=dict)
    accepts_raw_args: bool = True
    invokable: bool = False


@dataclass(frozen=True)
class ShadeSpec:
    head: str
    lowerer: str
    payload: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextSpec:
    id: str
    calls: Mapping[str, CallSpec] = field(default_factory=dict)
    shade: Mapping[str, ShadeSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaValidationResult:
    ok: bool
    code: str = "ok"
    message: str = ""


class SchemaRegistry:
    def __init__(self, contexts: Mapping[str, ContextSpec]) -> None:
        self._contexts = dict(contexts)

    def context(self, context_id: str) -> ContextSpec:
        if context_id in self._contexts:
            return self._contexts[context_id]
        return ContextSpec(context_id)

    def call(self, context_id: str, head: str) -> CallSpec | None:
        return self.context(context_id).calls.get(head)

    def validate_call(self, context_id: str, call: CallUnit) -> SchemaValidationResult:
        if call.head == "":
            return SchemaValidationResult(True)
        spec = self.call(context_id, call.head)
        if spec is None:
            return SchemaValidationResult(
                False,
                "unknown-head",
                f"unknown call head {call.head!r} in context {context_id!r}",
            )
        allowed_kwargs = set(spec.kwargs)
        if allowed_kwargs:
            unknown = sorted(set(call.kwargs) - allowed_kwargs)
            if unknown:
                return SchemaValidationResult(
                    False,
                    "unknown-kwarg",
                    f"unknown kwargs for {call.head!r}: {', '.join(unknown)}",
                )
        if not spec.accepts_raw_args and call.args:
            return SchemaValidationResult(
                False,
                "wrong-arity",
                f"{call.head!r} does not accept positional arguments",
            )
        return SchemaValidationResult(True)

    def shade(self, context_id: str, value: RawString) -> CallUnit | RawString:
        if value.force_raw:
            return value
        lookup = value.text.strip()
        if not lookup:
            return value
        spec = self.context(context_id).shade.get(lookup)
        if spec is None:
            return value
        return CallUnit(
            context_id,
            spec.head,
            kwargs={key: RawString(raw, value.origin) for key, raw in spec.payload.items()},
            origin=value.origin,
        )

    def shade_value(self, context_id: str, value: MosValue) -> MosValue:
        if isinstance(value, RawString):
            return self.shade(context_id, value)
        if isinstance(value, CallUnit):
            return self.resolve_call(value)
        return value

    def resolve_call(self, call: CallUnit) -> CallUnit:
        value_context = f"{call.head}.value"
        args = tuple(self.shade_value(value_context, arg) for arg in call.args)
        kwargs = {
            key: self.shade_value(f"{call.head}.{key}", value)
            for key, value in call.kwargs.items()
        }
        return replace(call, args=args, kwargs=kwargs)

    def resolve_calls(self, calls: list[CallUnit]) -> list[CallUnit]:
        return [self.resolve_call(call) for call in calls]
