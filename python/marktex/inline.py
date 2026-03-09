from __future__ import annotations

from typing import Iterable

from .model import (
    BibEntryEvent,
    BlockContext,
    CitationEvent,
    Event,
    InlinePopEvent,
    InlinePushEvent,
    SourceSpan,
    TextEvent,
)
from .tags import is_plain_url, parse_tag_list


def lex_inline(
    text: str,
    line_no: int,
    col_start: int,
    block: BlockContext,
) -> list[Event]:
    return _lex_inline_recursive(text, line_no=line_no, col_offset=col_start, block=block)


def _lex_inline_recursive(
    text: str,
    *,
    line_no: int,
    col_offset: int,
    block: BlockContext,
) -> list[Event]:
    events: list[Event] = []
    i = 0
    plain_start = 0

    while i < len(text):
        if text[i] != "[":
            i += 1
            continue

        close_bracket = _find_matching(text, i, "[", "]")
        if close_bracket is None:
            i += 1
            continue

        label = text[i + 1 : close_bracket]
        open_paren = close_bracket + 1 if close_bracket + 1 < len(text) and text[close_bracket + 1] == "(" else None
        close_paren = _find_matching(text, open_paren, "(", ")") if open_paren is not None else None

        plain_end = i
        _emit_plain_text(
            events,
            text[plain_start:plain_end],
            line_no=line_no,
            col_start=col_offset + plain_start,
            block=block,
        )

        if open_paren is None:
            if _emit_citation_without_pages(events, label, line_no, col_offset + i, block):
                i = close_bracket + 1
                plain_start = i
                continue
            events.append(
                TextEvent(
                    text=text[i : close_bracket + 1],
                    span=SourceSpan(
                        line=line_no,
                        col_start=col_offset + i + 1,
                        col_end=col_offset + close_bracket + 1,
                    ),
                    block=block,
                    line_no=line_no,
                )
            )
            i = close_bracket + 1
            plain_start = i
            continue

        if close_paren is None:
            events.append(
                TextEvent(
                    text=text[i : close_bracket + 1],
                    span=SourceSpan(
                        line=line_no,
                        col_start=col_offset + i + 1,
                        col_end=col_offset + close_bracket + 1,
                    ),
                    block=block,
                    line_no=line_no,
                )
            )
            i = close_bracket + 1
            plain_start = i
            continue

        payload = text[open_paren + 1 : close_paren]
        if _emit_reference_events(
            events,
            label=label,
            payload=payload,
            line_no=line_no,
            col_offset=col_offset + i,
            block=block,
        ):
            i = close_paren + 1
            plain_start = i
            continue

        styles = _parse_inline_styles(payload)
        if styles is None:
            events.append(
                TextEvent(
                    text=text[i : close_paren + 1],
                    span=SourceSpan(
                        line=line_no,
                        col_start=col_offset + i + 1,
                        col_end=col_offset + close_paren + 1,
                    ),
                    block=block,
                    line_no=line_no,
                )
            )
            i = close_paren + 1
            plain_start = i
            continue

        events.append(
            InlinePushEvent(
                styles=styles,
                span=SourceSpan(
                    line=line_no,
                    col_start=col_offset + i + 1,
                    col_end=col_offset + close_paren + 1,
                ),
            )
        )
        nested = _lex_inline_recursive(
            label,
            line_no=line_no,
            col_offset=col_offset + i + 1,
            block=block,
        )
        events.extend(nested)
        events.append(
            InlinePopEvent(
                span=SourceSpan(
                    line=line_no,
                    col_start=col_offset + i + 1,
                    col_end=col_offset + close_paren + 1,
                )
            )
        )
        i = close_paren + 1
        plain_start = i

    _emit_plain_text(
        events,
        text[plain_start:],
        line_no=line_no,
        col_start=col_offset + plain_start,
        block=block,
    )
    return events


def _find_matching(
    text: str,
    start: int | None,
    open_char: str,
    close_char: str,
) -> int | None:
    if start is None or start >= len(text) or text[start] != open_char:
        return None

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "\\":
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i
    return None


def _emit_plain_text(
    events: list[Event],
    text: str,
    *,
    line_no: int,
    col_start: int,
    block: BlockContext,
) -> None:
    if not text:
        return
    events.append(
        TextEvent(
            text=text,
            span=SourceSpan(
                line=line_no,
                col_start=col_start + 1,
                col_end=col_start + len(text),
            ),
            block=block,
            line_no=line_no,
        )
    )


def _parse_inline_styles(payload: str) -> dict[str, object] | None:
    stripped = payload.strip()
    if not stripped:
        return None
    if is_plain_url(stripped):
        return {"href": stripped}
    try:
        return parse_tag_list(stripped)
    except ValueError:
        return None


def _emit_reference_events(
    events: list[Event],
    *,
    label: str,
    payload: str,
    line_no: int,
    col_offset: int,
    block: BlockContext,
) -> bool:
    stripped_label = label.strip()
    if stripped_label == "#" and payload.lstrip().startswith("@"):
        events.append(
            BibEntryEvent(
                entry=payload.strip(),
                span=SourceSpan(
                    line=line_no,
                    col_start=col_offset + 1,
                    col_end=col_offset + len(label) + len(payload) + 3,
                ),
            )
        )
        return True

    if not stripped_label.startswith("#") or stripped_label == "#":
        return False

    key = stripped_label[1:].strip()
    if not key:
        return False
    pages = _parse_pages(payload)
    events.append(
        CitationEvent(
            key=key,
            pages=pages,
            span=SourceSpan(
                line=line_no,
                col_start=col_offset + 1,
                col_end=col_offset + len(label) + len(payload) + 3,
            ),
            block=block,
            line_no=line_no,
        )
    )
    return True


def _emit_citation_without_pages(
    events: list[Event],
    label: str,
    line_no: int,
    col_offset: int,
    block: BlockContext,
) -> bool:
    stripped = label.strip()
    if not stripped.startswith("#") or stripped == "#":
        return False
    key = stripped[1:].strip()
    if not key:
        return False
    events.append(
        CitationEvent(
            key=key,
            pages=None,
            span=SourceSpan(
                line=line_no,
                col_start=col_offset + 1,
                col_end=col_offset + len(label) + 2,
            ),
            block=block,
            line_no=line_no,
        )
    )
    return True


def _parse_pages(payload: str) -> str | None:
    if not payload.strip():
        return None
    try:
        tags = parse_tag_list(payload)
    except ValueError:
        return None
    pages = tags.get("pages")
    if isinstance(pages, str):
        return pages
    return None
