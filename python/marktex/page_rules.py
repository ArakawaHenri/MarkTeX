from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .tags import split_top_level_commas

T = TypeVar("T")


@dataclass(frozen=True)
class PageRuleSpec(Generic[T]):
    explicit_rules: list[tuple[int, T]]
    prefix_values: list[T]
    suffix_values: list[T]
    global_default: T | None


def parse_page_rule_spec(raw: str, parse_value: Callable[[str], T]) -> PageRuleSpec[T]:
    explicit_rules: list[tuple[int, T]] = []
    prefix_values: list[T] = []
    suffix_values: list[T] = []
    global_default: T | None = None
    seen_global = False

    for token in split_top_level_commas(raw):
        if not token:
            continue
        page_no, value_token = _split_explicit_rule(token)
        if page_no is not None:
            explicit_rules.append((page_no, parse_value(value_token)))
            continue

        value_token, is_global = _split_global_value(token)
        value = parse_value(value_token)
        if is_global:
            global_default = value
            seen_global = True
            continue
        if seen_global:
            suffix_values.append(value)
        else:
            prefix_values.append(value)

    if global_default is None and prefix_values:
        global_default = prefix_values.pop()

    return PageRuleSpec(
        explicit_rules=explicit_rules,
        prefix_values=prefix_values,
        suffix_values=suffix_values,
        global_default=global_default,
    )


def evaluate_page_rule_spec(spec: PageRuleSpec[T], total_pages: int) -> dict[int, T]:
    if total_pages <= 0:
        return {}

    resolved: dict[int, T] = {}
    if spec.global_default is not None:
        for page in range(1, total_pages + 1):
            resolved[page] = spec.global_default

    prefix_targets = _apply_prefix(spec.prefix_values, total_pages, resolved)
    explicit_targets = _normalized_explicit_pages(spec.explicit_rules, total_pages)
    _apply_suffix(
        suffix_values=spec.suffix_values,
        total_pages=total_pages,
        resolved=resolved,
        occupied=prefix_targets | explicit_targets,
    )
    _apply_explicit(spec.explicit_rules, total_pages, resolved)
    return resolved


def parse_column_value(raw: str) -> int:
    value = int(raw.strip())
    if value <= 0:
        raise ValueError(f"column value must be positive: {raw}")
    return value


def _split_explicit_rule(token: str) -> tuple[int | None, str]:
    if ":" not in token:
        return None, token
    page_raw, value_raw = token.split(":", 1)
    page = int(page_raw.strip())
    return page, value_raw.strip()


def _split_global_value(token: str) -> tuple[str, bool]:
    stripped = token.strip()
    if stripped.lower().endswith("g") and stripped[:-1].strip():
        return stripped[:-1].strip(), True
    return stripped, False


def _apply_prefix(values: list[T], total_pages: int, resolved: dict[int, T]) -> set[int]:
    occupied: set[int] = set()
    for idx, value in enumerate(values, start=1):
        if idx > total_pages:
            break
        resolved[idx] = value
        occupied.add(idx)
    return occupied


def _normalized_explicit_pages(explicit_rules: list[tuple[int, T]], total_pages: int) -> set[int]:
    normalized: set[int] = set()
    for raw_page, _ in explicit_rules:
        page = _normalize_page(raw_page, total_pages)
        if page is not None:
            normalized.add(page)
    return normalized


def _apply_suffix(
    *,
    suffix_values: list[T],
    total_pages: int,
    resolved: dict[int, T],
    occupied: set[int],
) -> None:
    if not suffix_values:
        return
    candidate_pages = [page for page in range(1, total_pages + 1) if page not in occupied]
    if not candidate_pages:
        return
    assign_count = min(len(suffix_values), len(candidate_pages))
    target_pages = candidate_pages[-assign_count:]
    target_values = suffix_values[:assign_count]
    for page, value in zip(target_pages, target_values):
        resolved[page] = value


def _apply_explicit(explicit_rules: list[tuple[int, T]], total_pages: int, resolved: dict[int, T]) -> None:
    for raw_page, value in explicit_rules:
        page = _normalize_page(raw_page, total_pages)
        if page is None:
            continue
        resolved[page] = value


def _normalize_page(raw_page: int, total_pages: int) -> int | None:
    page = raw_page if raw_page > 0 else total_pages + raw_page + 1
    if page < 1 or page > total_pages:
        return None
    return page
