from __future__ import annotations

from .emitter import emit_latex
from .lexer import lex
from .resolver import resolve


def compile_marktex_to_latex(source: str) -> str:
    events = list(lex(source))
    resolved = resolve(events)
    return emit_latex(resolved)
