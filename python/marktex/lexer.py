from __future__ import annotations

import re
from typing import Iterator

from .inline import lex_inline
from .model import (
    BlockContext,
    DirectiveEvent,
    Event,
    LineBreakEvent,
    ScopeSetEvent,
    ScopeUnsetEvent,
    SourceSpan,
)
from .tags import parse_tag_list

_DIRECTIVE_RE = re.compile(r"^!#\s*(.*)$")
_SCOPE_SET_RE = re.compile(r"^\*([a-zA-Z0-9*]*)\((.*)\)\s*$")
_SCOPE_UNSET_RE = re.compile(r"^!\s*(?:\[([^\]]+)\]|([a-zA-Z0-9*]+))\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

_SCOPE_ALIASES = {
    "": "all",
    "*": "all",
    "all": "all",
    "w": "western",
    "western": "western",
    "e": "eastern",
    "eastern": "eastern",
    "l": "link",
    "link": "link",
    "h": "heading",
    "heading": "heading",
    "h1": "h1",
    "h2": "h2",
    "h3": "h3",
    "h4": "h4",
    "h5": "h5",
    "h6": "h6",
}


def lex(text: str) -> Iterator[Event]:
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        span = SourceSpan(line=line_no, col_start=1, col_end=len(line) + 1)

        directive_match = _DIRECTIVE_RE.match(line)
        if directive_match is not None:
            yield DirectiveEvent(body=directive_match.group(1), span=span)
            continue

        scope_set_match = _SCOPE_SET_RE.match(line)
        if scope_set_match is not None:
            scope = _normalize_scope(scope_set_match.group(1))
            styles = parse_tag_list(scope_set_match.group(2))
            yield ScopeSetEvent(scope=scope, styles=styles, span=span)
            continue

        scope_unset_match = _SCOPE_UNSET_RE.match(line)
        if scope_unset_match is not None:
            target = scope_unset_match.group(1) or scope_unset_match.group(2) or ""
            target = target.strip().lower()
            if target in {"**", "all"}:
                yield ScopeUnsetEvent(scope=None, all_scopes=True, span=span)
            else:
                yield ScopeUnsetEvent(scope=_normalize_scope(target), all_scopes=False, span=span)
            continue

        block, content = _parse_block_context(line)
        if content:
            for event in lex_inline(content, line_no=line_no, col_start=1, block=block):
                yield event
        yield LineBreakEvent(line_no=line_no, block=block)


def _parse_block_context(line: str) -> tuple[BlockContext, str]:
    heading_match = _HEADING_RE.match(line)
    if heading_match is None:
        return BlockContext(kind="paragraph"), line
    level = len(heading_match.group(1))
    return BlockContext(kind="heading", heading_level=level), heading_match.group(2)


def _normalize_scope(raw_scope: str) -> str:
    normalized = raw_scope.strip().lower()
    return _SCOPE_ALIASES.get(normalized, normalized)
