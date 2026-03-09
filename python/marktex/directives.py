from __future__ import annotations

from .model import DocumentConfig
from .tags import parse_mm_number, split_top_level_commas

_HEADER_FOOTER_MARKERS: list[tuple[str, str]] = [
    ("-`-", "header_center"),
    ("-.-", "footer_center"),
    ("`-", "header_left"),
    ("-`", "header_right"),
    (".-", "footer_left"),
    ("-.", "footer_right"),
]

_MARGIN_KEYS = {
    "t": "top",
    "top": "top",
    "b": "bottom",
    "bottom": "bottom",
    "l": "left",
    "left": "left",
    "r": "right",
    "right": "right",
}


def apply_directive(config: DocumentConfig, body: str) -> None:
    stripped = body.strip()
    if not stripped:
        return
    config.raw_directives.append(stripped)

    marker_result = _parse_header_footer_marker(stripped)
    if marker_result is not None:
        slot, text = marker_result
        config.header_footer[slot] = text
        return

    if ":" not in stripped:
        return

    key, value = stripped.split(":", 1)
    normalized_key = key.strip().lower()
    value = value.strip()

    if normalized_key == "layout":
        _apply_layout(config, value)
        return
    if normalized_key == "margin":
        _apply_margin(config, value)
        return
    if normalized_key == "column":
        config.column_rules_raw = value
        return
    if normalized_key == "column-margin":
        config.column_margin_rules_raw = value
        return
    if normalized_key == "bib":
        _apply_bib_files(config, value)
        return
    if normalized_key == "bibstyle":
        config.bibstyle = _strip_brackets(value)
        return
    if normalized_key == "citestyle":
        config.citestyle = _strip_brackets(value)
        return


def _parse_header_footer_marker(raw: str) -> tuple[str, str] | None:
    for marker, slot in _HEADER_FOOTER_MARKERS:
        if raw.startswith(marker):
            content = raw[len(marker) :].strip()
            return slot, content
    return None


def _apply_layout(config: DocumentConfig, value: str) -> None:
    parts = split_top_level_commas(value)
    if not parts:
        return

    first = parts[0].strip()
    if _is_float(first):
        if len(parts) < 2 or not _is_float(parts[1].strip()):
            return
        config.paper_size_mm = (parse_mm_number(first), parse_mm_number(parts[1].strip()))
        config.layout_name = None
    else:
        config.layout_name = first.lower()
        config.paper_size_mm = None

    if len(parts) >= 2:
        maybe_orientation = parts[-1].strip().lower()
        if maybe_orientation in {"portrait", "landscape"}:
            config.orientation = maybe_orientation  # type: ignore[assignment]


def _apply_margin(config: DocumentConfig, value: str) -> None:
    parts = split_top_level_commas(value)
    if not parts:
        return

    if len(parts) == 1 and ":" not in parts[0]:
        uniform = parse_mm_number(parts[0])
        config.margins_mm = {
            "top": uniform,
            "bottom": uniform,
            "left": uniform,
            "right": uniform,
        }
        return

    if len(parts) == 4 and all(":" not in token for token in parts):
        top, bottom, left, right = (parse_mm_number(token) for token in parts)
        config.margins_mm = {
            "top": top,
            "bottom": bottom,
            "left": left,
            "right": right,
        }
        return

    updated = dict(config.margins_mm)
    for token in parts:
        if ":" not in token:
            continue
        key, raw_number = token.split(":", 1)
        normalized_key = _MARGIN_KEYS.get(key.strip().lower())
        if normalized_key is None:
            continue
        updated[normalized_key] = parse_mm_number(raw_number.strip())
    if updated:
        config.margins_mm = updated


def _apply_bib_files(config: DocumentConfig, value: str) -> None:
    for token in split_top_level_commas(value):
        if not token:
            continue
        config.bib_files.append(_strip_brackets(token))


def _strip_brackets(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return stripped


def _is_float(raw: str) -> bool:
    token = raw.strip().lower()
    if token.endswith("mm"):
        token = token[:-2].strip()
    try:
        float(token)
    except ValueError:
        return False
    return True
