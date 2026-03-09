from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(r"<([^<>]+)>")
_ALLOWED_EXPR_RE = re.compile(r"^[NnMm0-9+\-*/().\s]+$")


def convert_page_placeholders(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        return _compile_placeholder(expr) or match.group(0)

    return _PLACEHOLDER_RE.sub(replace, text)


def _compile_placeholder(expr: str) -> str | None:
    normalized = expr.strip()
    if not normalized:
        return None
    if normalized == "N":
        return r"\thepage"
    if normalized == "M":
        return r"\pageref{LastPage}"

    if not _ALLOWED_EXPR_RE.match(normalized):
        return None

    rewritten = _rewrite_symbols(normalized)
    if rewritten is None:
        return None
    return rf"\MarkTeXEval{{{rewritten}}}"


def _rewrite_symbols(expr: str) -> str | None:
    upper = expr.upper()
    if not _ALLOWED_EXPR_RE.match(upper):
        return None
    upper = re.sub(r"\bN\b", r"(\\value{page})", upper)
    upper = re.sub(r"\bM\b", r"(\\getpagerefnumber{LastPage})", upper)
    return upper
