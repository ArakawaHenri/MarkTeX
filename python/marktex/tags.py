from __future__ import annotations

import re
from typing import Iterable

from .model import StyleMap

_BOOL_KEYS = {"bold", "italic", "underline", "strikethrough"}
_NUMERIC_KEYS = {"size", "linespacing", "rowspacing"}
_LINK_KEYS = {"href", "link"}


def split_top_level_commas(raw: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(raw):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(raw[start:i].strip())
            start = i + 1
    tail = raw[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_tag_list(raw: str) -> StyleMap:
    styles: StyleMap = {}
    tokens = split_top_level_commas(raw)
    for token in tokens:
        if not token:
            continue
        key, value = _split_key_value(token)
        if key is None:
            _apply_shorthand(token, styles)
            continue
        _apply_key_value(key, value, styles)
    return styles


def is_plain_url(raw: str) -> bool:
    stripped = raw.strip()
    if "," in stripped:
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$", stripped))


def parse_mm_number(raw: str) -> float:
    token = raw.strip().lower()
    if token.endswith("mm"):
        token = token[:-2].strip()
    return float(token)


def parse_pt_number(raw: str) -> float:
    token = raw.strip().lower()
    if token.endswith("pt"):
        token = token[:-2].strip()
    return float(token)


def _split_key_value(token: str) -> tuple[str | None, str]:
    depth = 0
    for i, ch in enumerate(token):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            return token[:i].strip(), token[i + 1 :].strip()
    return None, token


def _apply_shorthand(token: str, styles: StyleMap) -> None:
    lowered = token.strip().lower()
    if not lowered:
        return
    if lowered in _BOOL_KEYS:
        styles[lowered] = True
        return
    if lowered.endswith("pt"):
        try:
            styles["size"] = parse_pt_number(lowered)
            return
        except ValueError:
            pass
    styles["color"] = token.strip()


def _apply_key_value(key: str, value: str, styles: StyleMap) -> None:
    lowered = key.strip().lower()
    if lowered in _LINK_KEYS:
        styles["href"] = value.strip()
        return
    if lowered in _BOOL_KEYS:
        styles[lowered] = _parse_bool(value)
        return
    if lowered in _NUMERIC_KEYS:
        styles[lowered] = parse_pt_number(value)
        return
    if lowered == "color":
        styles["color"] = _parse_color(value)
        return
    if lowered == "font":
        styles["font"] = value.strip()
        return
    if lowered == "align":
        styles["align"] = value.strip().lower()
        return
    if lowered == "pages":
        styles["pages"] = value.strip()
        return
    styles[lowered] = value.strip()


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean literal: {value}")


def _parse_color(value: str) -> str | tuple[int, int, int]:
    stripped = value.strip()
    rgb_match = re.match(
        r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$",
        stripped,
        re.IGNORECASE,
    )
    if rgb_match is None:
        return stripped
    rgb = tuple(int(part) for part in rgb_match.groups())
    if any(channel < 0 or channel > 255 for channel in rgb):
        raise ValueError(f"Invalid rgb color: {value}")
    return rgb  # type: ignore[return-value]


def merge_style_patches(patches: Iterable[StyleMap]) -> StyleMap:
    merged: StyleMap = {}
    for patch in patches:
        merged.update(patch)
    return merged
