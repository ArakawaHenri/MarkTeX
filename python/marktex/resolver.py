from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .directives import apply_directive
from .model import (
    BibEntryEvent,
    CitationEvent,
    DirectiveEvent,
    DocumentConfig,
    Event,
    InlinePopEvent,
    InlinePushEvent,
    LineBreak,
    LineBreakEvent,
    ResolvedDocument,
    ScopeSetEvent,
    ScopeUnsetEvent,
    StyledChunk,
    StyleMap,
    TextEvent,
)

_LINK_KEY = "href"


@dataclass(frozen=True)
class _OrderedPatch:
    order: int
    styles: StyleMap


def resolve(events: Iterable[Event]) -> ResolvedDocument:
    config = DocumentConfig()
    units: list[StyledChunk | LineBreak] = []
    bib_entries: list[str] = []
    scope_layers: dict[str, list[_OrderedPatch]] = {}
    inline_stack: list[_OrderedPatch] = []
    order_counter = 0

    for event in events:
        if isinstance(event, DirectiveEvent):
            apply_directive(config, event.body)
            continue

        if isinstance(event, ScopeSetEvent):
            order_counter += 1
            scope_layers.setdefault(event.scope, []).append(
                _OrderedPatch(order=order_counter, styles=event.styles)
            )
            continue

        if isinstance(event, ScopeUnsetEvent):
            if event.all_scopes:
                _pop_latest_for_all_scopes(scope_layers)
            else:
                _pop_latest_for_scope(scope_layers, event.scope or "all")
            continue

        if isinstance(event, InlinePushEvent):
            order_counter += 1
            inline_stack.append(_OrderedPatch(order=order_counter, styles=event.styles))
            continue

        if isinstance(event, InlinePopEvent):
            if inline_stack:
                inline_stack.pop()
            continue

        if isinstance(event, BibEntryEvent):
            bib_entries.append(event.entry)
            continue

        if isinstance(event, CitationEvent):
            citation_styles = _effective_styles_for_segment(
                scope_layers=scope_layers,
                inline_stack=inline_stack,
                block=event.block,
                script="western",
                is_link=False,
            )
            citation_latex = _citation_to_latex(event.key, event.pages)
            _append_chunk(
                units,
                StyledChunk(
                    text=citation_latex,
                    styles=citation_styles,
                    block=event.block,
                    line_no=event.line_no,
                    raw_latex=True,
                ),
            )
            continue

        if isinstance(event, TextEvent):
            segments = split_by_script(event.text)
            link_active = _is_link_active(inline_stack)
            for text, script in segments:
                styles = _effective_styles_for_segment(
                    scope_layers=scope_layers,
                    inline_stack=inline_stack,
                    block=event.block,
                    script=script,
                    is_link=link_active,
                )
                _append_chunk(
                    units,
                    StyledChunk(
                        text=text,
                        styles=styles,
                        block=event.block,
                        line_no=event.line_no,
                    ),
                )
            continue

        if isinstance(event, LineBreakEvent):
            units.append(LineBreak(line_no=event.line_no, block=event.block))
            continue

    return ResolvedDocument(config=config, units=units, bib_entries=bib_entries)


def split_by_script(text: str) -> list[tuple[str, str]]:
    if not text:
        return []

    segments: list[tuple[str, str]] = []
    current_chars: list[str] = []
    current_script: str | None = None

    for char in text:
        script = _char_script(char)
        if script == "neutral":
            script = current_script or "western"
        if current_script is None:
            current_script = script
        if script != current_script:
            segments.append(("".join(current_chars), current_script))
            current_chars = [char]
            current_script = script
            continue
        current_chars.append(char)

    if current_chars:
        segments.append(("".join(current_chars), current_script or "western"))
    return segments


def _effective_styles_for_segment(
    *,
    scope_layers: dict[str, list[_OrderedPatch]],
    inline_stack: list[_OrderedPatch],
    block,
    script: str,
    is_link: bool,
) -> StyleMap:
    selected_scopes = _scope_targets(block=block, script=script, is_link=is_link)
    patches: list[_OrderedPatch] = []
    for scope in selected_scopes:
        patches.extend(scope_layers.get(scope, []))
    patches.extend(inline_stack)
    patches.sort(key=lambda patch: patch.order)

    merged: StyleMap = {}
    for patch in patches:
        merged.update(patch.styles)
    return merged


def _scope_targets(*, block, script: str, is_link: bool) -> list[str]:
    scopes = ["all"]
    if script == "western":
        scopes.append("western")
    elif script == "eastern":
        scopes.append("eastern")
    if block.kind == "heading":
        scopes.append("heading")
        if block.heading_level is not None:
            scopes.append(f"h{block.heading_level}")
    if is_link:
        scopes.append("link")
    return scopes


def _pop_latest_for_scope(scope_layers: dict[str, list[_OrderedPatch]], scope: str) -> None:
    patches = scope_layers.get(scope)
    if not patches:
        return
    patches.pop()
    if not patches:
        del scope_layers[scope]


def _pop_latest_for_all_scopes(scope_layers: dict[str, list[_OrderedPatch]]) -> None:
    for scope in list(scope_layers.keys()):
        _pop_latest_for_scope(scope_layers, scope)


def _is_link_active(inline_stack: list[_OrderedPatch]) -> bool:
    for patch in inline_stack:
        if _LINK_KEY in patch.styles and bool(patch.styles[_LINK_KEY]):
            return True
    return False


def _char_script(char: str) -> str:
    if char.isspace():
        return "neutral"
    if ord(char) < 128:
        return "western"
    width = unicodedata.east_asian_width(char)
    if width in {"W", "F"}:
        return "eastern"
    return "neutral"


def _append_chunk(units: list[StyledChunk | LineBreak], chunk: StyledChunk) -> None:
    if not chunk.text:
        return
    if not units or not isinstance(units[-1], StyledChunk):
        units.append(chunk)
        return
    prev = units[-1]
    if (
        prev.line_no == chunk.line_no
        and prev.block == chunk.block
        and prev.raw_latex == chunk.raw_latex
        and prev.styles == chunk.styles
    ):
        units[-1] = StyledChunk(
            text=prev.text + chunk.text,
            styles=prev.styles,
            block=prev.block,
            line_no=prev.line_no,
            raw_latex=prev.raw_latex,
        )
        return
    units.append(chunk)


def _citation_to_latex(key: str, pages: str | None) -> str:
    if pages:
        return rf"\cite[p.~{pages}]{{{key}}}"
    return rf"\cite{{{key}}}"
