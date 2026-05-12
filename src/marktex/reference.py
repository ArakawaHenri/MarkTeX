from __future__ import annotations

from marktex.core import Citation
from marktex.mos import RawString, parse_mos_cooked
from marktex.source import CookedText, MarkTeXError, SourceSpan

CITATION_KWARGS = frozenset(("page", "pages", "locator", "p"))


def citation_from_cooked_payload(
    payload: CookedText,
    origin: SourceSpan,
    source: str,
) -> Citation | None:
    if not starts_citation_payload(payload):
        return None
    try:
        calls = parse_mos_cooked(
            payload,
            context="reference",
            filename=origin.filename,
            raw_source=source,
        )
    except MarkTeXError:
        return None
    if len(calls) != 1 or calls[0].head != "cite":
        return None
    keys: list[str] = []
    kwargs: dict[str, str] = {}
    for arg in calls[0].args:
        if not isinstance(arg, RawString):
            return None
        key = arg.text.strip()
        if key:
            keys.append(key)
    for key, value in calls[0].kwargs.items():
        if key not in CITATION_KWARGS or not isinstance(value, RawString):
            return None
        kwargs[key] = value.text.strip()
    if not keys:
        return None
    return Citation(tuple(keys), kwargs, origin)


def starts_citation_payload(payload: CookedText) -> bool:
    cursor = 0
    while cursor < len(payload.text) and payload.text[cursor] in {" ", "\t"}:
        cursor += 1
    if not payload.startswith("cite", cursor):
        return False
    cursor += 4
    while cursor < len(payload.text) and payload.text[cursor] in {" ", "\t"}:
        cursor += 1
    return payload.char_is(cursor, ":")

