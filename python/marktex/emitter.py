from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import DocumentConfig, LineBreak, ResolvedDocument, StyledChunk
from .page_expr import convert_page_placeholders
from .page_rules import (
    evaluate_page_rule_spec,
    parse_column_value,
    parse_page_rule_spec,
)
from .tags import parse_mm_number


def emit_latex(document: ResolvedDocument) -> str:
    column_runtime = _compute_column_runtime(document.config)
    preamble = _build_preamble(document.config, column_runtime)
    body = _render_body(document.units)
    body = _apply_column_runtime(body, column_runtime)
    bibliography = _render_bibliography(document)
    return "\n".join(
        [
            preamble,
            r"\begin{document}",
            body,
            bibliography,
            r"\end{document}",
        ]
    ).strip() + "\n"


@dataclass(frozen=True)
class _ColumnRuntime:
    has_rules: bool
    initial_count: int
    column_sep_mm: float | None
    has_page_specific_rules: bool


def _build_preamble(config: DocumentConfig, column_runtime: _ColumnRuntime) -> str:
    class_options = ["12pt"]
    if config.layout_name:
        class_options.append(config.layout_name)
    lines = [rf"\documentclass[{','.join(class_options)}]{{article}}"]
    lines.extend(
        [
            r"\usepackage{geometry}",
            r"\usepackage{xcolor}",
            r"\usepackage{hyperref}",
            r"\usepackage[normalem]{ulem}",
            r"\usepackage{fontspec}",
            r"\usepackage{lastpage}",
        ]
    )

    if _has_header_or_footer(config):
        lines.extend(
            [
                r"\usepackage{fancyhdr}",
                r"\usepackage{refcount}",
                r"\usepackage{xfp}",
                r"\pagestyle{fancy}",
                r"\fancyhf{}",
                r"\newcommand{\MarkTeXEval}[1]{\fpeval{round(#1,0)}}",
            ]
        )
        lines.extend(_render_header_footer_setup(config))

    if column_runtime.has_rules:
        lines.append(r"\usepackage{multicol}")
        if column_runtime.column_sep_mm is not None:
            lines.append(rf"\setlength{{\columnsep}}{{{column_runtime.column_sep_mm}mm}}")

    geometry_options = _geometry_options(config)
    if geometry_options:
        lines.append(rf"\geometry{{{','.join(geometry_options)}}}")

    if config.bib_files:
        lines.extend([r"\usepackage[numbers]{natbib}"])
    return "\n".join(lines)


def _render_header_footer_setup(config: DocumentConfig) -> list[str]:
    slot_map = {
        "header_left": ("head", "L"),
        "header_center": ("head", "C"),
        "header_right": ("head", "R"),
        "footer_left": ("foot", "L"),
        "footer_center": ("foot", "C"),
        "footer_right": ("foot", "R"),
    }
    lines: list[str] = []
    for slot, (hf, lr) in slot_map.items():
        content = config.header_footer.get(slot, "").strip()
        if not content:
            continue
        converted = convert_page_placeholders(content)
        lines.append(rf"\fancy{hf}[{lr}]{{{converted}}}")
    return lines


def _geometry_options(config: DocumentConfig) -> list[str]:
    options: list[str] = []
    if config.paper_size_mm is not None:
        width, height = config.paper_size_mm
        options.append(f"paperwidth={width}mm")
        options.append(f"paperheight={height}mm")
    if config.orientation == "landscape":
        options.append("landscape")
    for side in ("top", "bottom", "left", "right"):
        if side in config.margins_mm:
            options.append(f"{side}={config.margins_mm[side]}mm")
    return options


def _has_header_or_footer(config: DocumentConfig) -> bool:
    return any(value.strip() for value in config.header_footer.values())


def _compute_column_runtime(config: DocumentConfig) -> _ColumnRuntime:
    if not config.column_rules_raw:
        return _ColumnRuntime(
            has_rules=False,
            initial_count=1,
            column_sep_mm=None,
            has_page_specific_rules=False,
        )

    try:
        column_spec = parse_page_rule_spec(config.column_rules_raw, parse_column_value)
    except ValueError:
        return _ColumnRuntime(
            has_rules=False,
            initial_count=1,
            column_sep_mm=None,
            has_page_specific_rules=False,
        )

    one_page = evaluate_page_rule_spec(column_spec, total_pages=1)
    initial_count = one_page.get(1, column_spec.global_default or 1)
    has_page_specific = _has_page_specific_column_rules(column_spec, initial_count)

    column_sep_mm: float | None = None
    if initial_count > 1 and config.column_margin_rules_raw:
        try:
            margin_spec = parse_page_rule_spec(config.column_margin_rules_raw, parse_mm_number)
            margin_plan = evaluate_page_rule_spec(margin_spec, total_pages=1)
            column_sep_mm = margin_plan.get(1, margin_spec.global_default)
        except ValueError:
            column_sep_mm = None

    return _ColumnRuntime(
        has_rules=True,
        initial_count=initial_count,
        column_sep_mm=column_sep_mm,
        has_page_specific_rules=has_page_specific,
    )


def _has_page_specific_column_rules(column_spec, initial_count: int) -> bool:
    if len(column_spec.prefix_values) > 1:
        return True
    if column_spec.suffix_values:
        return True
    if column_spec.global_default is not None and column_spec.global_default != initial_count:
        return True
    if any(page != 1 for page, _ in column_spec.explicit_rules):
        return True
    return False


def _apply_column_runtime(body: str, runtime: _ColumnRuntime) -> str:
    if not runtime.has_rules:
        return body
    wrapped: list[str] = []
    if runtime.has_page_specific_rules:
        wrapped.append(
            "% MarkTeX prototype note: page-specific column rules are parsed "
            "but only the first-page column count is emitted."
        )
    if runtime.initial_count <= 1:
        wrapped.append(body)
        return "\n".join(wrapped)
    wrapped.append(rf"\begin{{multicols}}{{{runtime.initial_count}}}")
    wrapped.append(body)
    wrapped.append(r"\end{multicols}")
    return "\n".join(wrapped)


def _render_body(units: Iterable[StyledChunk | LineBreak]) -> str:
    current_chunks: list[StyledChunk] = []
    lines: list[str] = []
    for unit in units:
        if isinstance(unit, StyledChunk):
            current_chunks.append(unit)
            continue
        lines.append(_render_line(current_chunks, unit))
        current_chunks = []

    if current_chunks:
        linebreak = LineBreak(line_no=current_chunks[-1].line_no, block=current_chunks[-1].block)
        lines.append(_render_line(current_chunks, linebreak))
    return "\n".join(lines)


def _render_line(chunks: list[StyledChunk], line_break: LineBreak) -> str:
    if not chunks:
        return ""
    inline = "".join(_render_chunk(chunk) for chunk in chunks)
    if line_break.block.kind != "heading":
        return inline
    level = line_break.block.heading_level or 1
    if level == 1:
        return rf"\section{{{inline}}}"
    if level == 2:
        return rf"\subsection{{{inline}}}"
    if level == 3:
        return rf"\subsubsection{{{inline}}}"
    if level == 4:
        return rf"\paragraph{{{inline}}}"
    if level == 5:
        return rf"\subparagraph{{{inline}}}"
    return rf"\textbf{{{inline}}}\par"


def _render_chunk(chunk: StyledChunk) -> str:
    base = chunk.text if chunk.raw_latex else _escape_latex(chunk.text)
    return _apply_styles(base, chunk.styles)


def _apply_styles(text: str, styles: dict[str, object]) -> str:
    rendered = text
    if styles.get("bold") is True:
        rendered = rf"\textbf{{{rendered}}}"
    if styles.get("italic") is True:
        rendered = rf"\textit{{{rendered}}}"
    if styles.get("underline") is True:
        rendered = rf"\uline{{{rendered}}}"
    if styles.get("strikethrough") is True:
        rendered = rf"\sout{{{rendered}}}"

    color = styles.get("color")
    if isinstance(color, tuple) and len(color) == 3:
        r, g, b = color
        rendered = rf"\textcolor[rgb]{{{r/255:.3f},{g/255:.3f},{b/255:.3f}}}{{{rendered}}}"
    elif isinstance(color, str) and color.strip():
        rendered = rf"\textcolor{{{color}}}{{{rendered}}}"

    size = styles.get("size")
    if isinstance(size, (int, float)):
        baseline_skip = round(float(size) * 1.2, 2)
        rendered = rf"{{\fontsize{{{float(size)}}}{{{baseline_skip}}}\selectfont {rendered}}}"

    font = styles.get("font")
    if isinstance(font, str) and font.strip():
        rendered = rf"{{\fontspec{{{font}}}{rendered}}}"

    href = styles.get("href")
    if isinstance(href, str) and href.strip():
        rendered = rf"\href{{{href}}}{{{rendered}}}"

    return rendered


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = []
    for ch in text:
        escaped.append(replacements.get(ch, ch))
    return "".join(escaped)


def _render_bibliography(document: ResolvedDocument) -> str:
    if not document.config.bib_files and not document.bib_entries:
        return ""
    parts: list[str] = []
    if document.config.bibstyle:
        parts.append(rf"\bibliographystyle{{{document.config.bibstyle}}}")
    if document.config.bib_files:
        refs = ",".join(document.config.bib_files)
        parts.append(rf"\bibliography{{{refs}}}")
    elif document.bib_entries:
        parts.append(r"\begin{thebibliography}{99}")
        for idx, entry in enumerate(document.bib_entries, start=1):
            parts.append(rf"\bibitem{{inline{idx}}} {entry}")
        parts.append(r"\end{thebibliography}")
    return "\n".join(parts)
