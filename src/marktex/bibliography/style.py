from __future__ import annotations

from pathlib import Path

from marktex.bibliography.model import BibliographyStyle, CitationStyle
from marktex.mos import CallUnit, RawString, parse_mos
from marktex.source import MarkTeXError


BUILTIN_CITATION_STYLES = {
    "numeric": "style: name=numeric; citation: mode=numeric, form=square;",
    "superscript": "style: name=superscript; citation: mode=numeric, form=superscript;",
    "apa": "style: name=apa; citation: mode=author-year, form=paren, year-separator=`, `, locator-prefix=`, p. `;",
    "mla": "style: name=mla; citation: mode=author-page, form=paren, year-separator=` `, locator-prefix=` `;",
    "chicago-notes": "style: name=chicago-notes; citation: mode=note, form=footnote;",
    "chicago-author-date": "style: name=chicago-author-date; citation: mode=author-year, form=paren, year-separator=` `, locator-prefix=`, `;",
}

BUILTIN_BIBLIOGRAPHY_STYLES = {
    "numeric": (
        "style: name=numeric; "
        "references: title=References, include=cited, sort=citation-order, placement=new-page, label=numeric; "
        "template: default, author, title, container, year, publisher, pages, doi, url;"
    ),
    "apa": (
        "style: name=apa; "
        "references: title=References, include=cited, sort=author-year, placement=new-page, label=none; "
        "template: default, author, year, title, container, publisher, pages, doi, url;"
    ),
    "mla": (
        "style: name=mla; "
        "references: title=`Works Cited`, include=cited, sort=author-title, placement=new-page, label=none; "
        "template: default, author, title, container, publisher, year, pages, url;"
    ),
    "chicago-notes-bibliography": (
        "style: name=chicago-notes-bibliography; "
        "references: title=Bibliography, include=cited, sort=author-title, placement=new-page, label=none; "
        "template: default, author, title, container, publisher, year, pages, doi, url;"
    ),
    "chicago-author-date": (
        "style: name=chicago-author-date; "
        "references: title=References, include=cited, sort=author-year, placement=new-page, label=none; "
        "template: default, author, year, title, container, publisher, pages, doi, url;"
    ),
}


def load_citation_style(raw_name: str | None, base_dir: Path) -> CitationStyle:
    name = (raw_name or "numeric").strip()
    source, label = style_source(name, ".mtxcs", BUILTIN_CITATION_STYLES, base_dir)
    return parse_citation_style(source, label)


def load_bibliography_style(raw_name: str | None, base_dir: Path) -> BibliographyStyle:
    name = (raw_name or "numeric").strip()
    source, label = style_source(name, ".mtxbs", BUILTIN_BIBLIOGRAPHY_STYLES, base_dir)
    return parse_bibliography_style(source, label)


def style_source(
    name: str,
    extension: str,
    builtins: dict[str, str],
    base_dir: Path,
) -> tuple[str, str]:
    if name in builtins:
        return builtins[name], name
    if not looks_like_path(name, extension):
        expected = ", ".join(sorted(builtins))
        raise MarkTeXError(f"unknown style {name!r}; expected built-in one of {expected} or a {extension} path")
    path = Path(name)
    if path.suffix == "":
        path = path.with_suffix(extension)
    if not path.is_absolute():
        path = base_dir / path
    try:
        return path.read_text(encoding="utf-8"), str(path)
    except OSError as exc:
        raise MarkTeXError(f"style file cannot be read: {path}") from exc


def looks_like_path(value: str, extension: str) -> bool:
    return value.endswith(extension) or "/" in value or "\\" in value or value.startswith(".")


def parse_citation_style(source: str, label: str) -> CitationStyle:
    name = Path(label).stem
    mode = "numeric"
    form = "square"
    delimiter = "; "
    year_separator = ", "
    locator_prefix = ", "
    for call in parse_mos(source, context="citation-style", filename=label):
        if call.head == "style":
            name = raw_kw(call, "name") or name
        elif call.head == "citation":
            mode = raw_kw(call, "mode") or mode
            form = raw_kw(call, "form") or form
            delimiter = raw_kw(call, "delimiter", preserve_raw=True) or delimiter
            year_separator = raw_kw(call, "year-separator", preserve_raw=True) or year_separator
            locator_prefix = raw_kw(call, "locator-prefix", preserve_raw=True) or locator_prefix
        else:
            raise MarkTeXError(f"unknown citation style call: {call.head}", call.origin)
    validate_choice("citation mode", mode, {"numeric", "author-year", "author-page", "note"})
    validate_choice("citation form", form, {"square", "superscript", "paren", "footnote", "plain"})
    return CitationStyle(name, mode, form, delimiter, year_separator, locator_prefix)


def parse_bibliography_style(source: str, label: str) -> BibliographyStyle:
    name = Path(label).stem
    title = "References"
    include = "cited"
    sort = "citation-order"
    placement = "new-page"
    label_style = "numeric"
    templates: dict[str, tuple[str, ...]] = {}
    for call in parse_mos(source, context="bibliography-style", filename=label):
        if call.head == "style":
            name = raw_kw(call, "name") or name
        elif call.head == "references":
            title = raw_kw(call, "title") or title
            include = raw_kw(call, "include") or include
            sort = raw_kw(call, "sort") or sort
            placement = raw_kw(call, "placement") or placement
            label_style = raw_kw(call, "label") or label_style
        elif call.head == "template":
            entry_type, fields = parse_template(call)
            templates[entry_type] = fields
        else:
            raise MarkTeXError(f"unknown bibliography style call: {call.head}", call.origin)
    validate_choice("references include", include, {"cited", "all"})
    validate_choice("references sort", sort, {"citation-order", "author-year", "author-title", "key"})
    validate_choice("references placement", placement, {"new-page", "inline"})
    validate_choice("references label", label_style, {"numeric", "key", "none"})
    return BibliographyStyle(name, title, include, sort, placement, label_style, templates)


def parse_template(call: CallUnit) -> tuple[str, tuple[str, ...]]:
    values = [raw_arg(arg) for arg in call.args]
    if not values or values[0] is None:
        raise MarkTeXError("bibliography template requires an entry type", call.origin)
    fields = tuple(value.lower() for value in values[1:] if value)
    if not fields:
        raise MarkTeXError("bibliography template requires at least one field", call.origin)
    return values[0].lower(), fields


def raw_arg(value: object) -> str | None:
    if isinstance(value, RawString):
        return value.text.strip()
    return None


def raw_kw(call: CallUnit, key: str, *, preserve_raw: bool = False) -> str | None:
    value = call.kwargs.get(key)
    if isinstance(value, RawString):
        if preserve_raw and value.force_raw:
            return value.text
        return value.text.strip()
    return None


def validate_choice(label: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise MarkTeXError(f"unsupported {label}: {value}; expected one of {expected}")
