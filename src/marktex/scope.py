from __future__ import annotations

from collections.abc import Mapping

from marktex.mos import RawString
from marktex.source import MarkTeXError, SourceSpan

DEFAULT_SCOPE_TARGET = "DEFAULT"
BUILTIN_SCOPE_TARGETS = frozenset(
    (
        DEFAULT_SCOPE_TARGET,
        "w",
        "e",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    )
)


def validate_scope_target(value: str, origin: SourceSpan | None = None) -> str:
    target = value.strip()
    if target not in BUILTIN_SCOPE_TARGETS:
        expected = ", ".join(sorted(BUILTIN_SCOPE_TARGETS))
        raise MarkTeXError(
            f"unsupported scope target: {target}; expected one of {expected}",
            origin,
        )
    return target


def scope_target_from_kwargs(
    kwargs: Mapping[str, object],
    origin: SourceSpan | None = None,
) -> str:
    value = kwargs.get("scope")
    if value is None:
        return DEFAULT_SCOPE_TARGET
    if isinstance(value, RawString):
        return validate_scope_target(value.text, value.origin or origin)
    return validate_scope_target(str(value), origin)
