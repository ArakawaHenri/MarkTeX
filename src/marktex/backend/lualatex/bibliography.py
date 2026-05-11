from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from marktex.bibliography import (
    BibEntry,
    BibliographyResources,
    BibliographyStyle,
    CitationStyle,
    load_bib_resources,
    load_bibliography_style,
    load_citation_style,
)
from marktex.core import Citation, Document, DocumentPatch
from marktex.mos import RawString
from marktex.source import MarkTeXError, SourceSpan


Escaper = Callable[[str], str]


class LuaLaTeXBibliography:
    def __init__(
        self,
        document: Document,
        escape_text: Escaper,
        escape_url: Escaper,
        *,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        if snapshot is None:
            base_dir = document_base_dir(document)
            resource_paths, citation_style_name, bibliography_style_name = document_bibliography_config(
                document,
                base_dir,
            )
            self.resources = load_bib_resources(tuple(resource_paths))
            self.citation_style = load_citation_style(citation_style_name, base_dir)
            self.bibliography_style = load_bibliography_style(bibliography_style_name, base_dir)
        else:
            self.resources = resources_from_json(snapshot.get("resources"))
            self.citation_style = citation_style_from_json(snapshot.get("citation_style"))
            self.bibliography_style = bibliography_style_from_json(snapshot.get("bibliography_style"))
        self.escape_text = escape_text
        self.escape_url = escape_url
        self.cited_keys: list[str] = []
        self.citation_numbers: dict[str, int] = {}

    def cite(
        self,
        citation: Citation,
        context: str,
        deferred_footnotes: list[str] | None,
    ) -> str:
        entries = [self.entry_for_key(key, citation.origin) for key in citation.keys]
        for entry in entries:
            self.register_citation(entry.key)
        if self.citation_style.mode == "note":
            note = "; ".join(self.note_text(entry, citation) for entry in entries)
            if context == "table_cell":
                if deferred_footnotes is None:
                    raise MarkTeXError("table citation footnote queue is unavailable", citation.origin)
                deferred_footnotes.append(note)
                return r"\footnotemark"
            return r"\footnote{" + note + "}"
        text = self.inline_citation_text(entries, citation)
        return self.wrap_inline_citation(text)

    def entry_for_key(self, key: str, origin: SourceSpan | None) -> BibEntry:
        entry = self.resources.entries.get(key)
        if entry is None:
            raise MarkTeXError(f"undefined bibliography entry: {key}", origin)
        return entry

    def register_citation(self, key: str) -> None:
        if key not in self.citation_numbers:
            self.citation_numbers[key] = len(self.citation_numbers) + 1
            self.cited_keys.append(key)

    def inline_citation_text(self, entries: list[BibEntry], citation: Citation) -> str:
        if self.citation_style.mode == "numeric":
            return ",".join(str(self.citation_numbers[entry.key]) for entry in entries)
        return self.citation_style.delimiter.join(
            self.author_citation_text(entry, citation)
            for entry in entries
        )

    def author_citation_text(self, entry: BibEntry, citation: Citation) -> str:
        author = short_author(entry)
        locator = citation_locator(citation)
        if self.citation_style.mode == "author-page":
            if locator:
                return author + self.citation_style.locator_prefix + locator
            return author
        year = entry.field("year") or "n.d."
        text = author + self.citation_style.year_separator + year
        if locator:
            text += self.citation_style.locator_prefix + locator
        return text

    def wrap_inline_citation(self, text: str) -> str:
        escaped = self.escape_text(text)
        if self.citation_style.form == "superscript":
            return r"\textsuperscript{" + escaped + "}"
        if self.citation_style.form == "paren":
            return "(" + escaped + ")"
        if self.citation_style.form == "square":
            return "[" + escaped + "]"
        return escaped

    def note_text(self, entry: BibEntry, citation: Citation) -> str:
        parts = [reference_authors(entry), entry.field("title"), entry.field("year")]
        locator = citation_locator(citation)
        if locator:
            parts.append(locator)
        return sentence_join(self.escape_text(part) for part in parts if part)

    def reference_lines(self) -> list[str]:
        keys = self.reference_keys()
        if not keys:
            return []
        lines: list[str] = []
        if self.bibliography_style.placement == "new-page":
            lines.append(r"\clearpage")
        lines.append(r"\section*{" + self.escape_text(self.bibliography_style.title) + "}")
        if self.bibliography_style.label == "numeric":
            lines.append(r"\begin{enumerate}")
            for key in keys:
                lines.append(r"\item " + self.reference_text(self.resources.entries[key]))
            lines.append(r"\end{enumerate}")
            return lines
        for key in keys:
            label = ""
            if self.bibliography_style.label == "key":
                label = "[" + self.escape_text(key) + "] "
            lines.append(r"\noindent " + label + self.reference_text(self.resources.entries[key]) + r"\par")
        return lines

    def reference_keys(self) -> list[str]:
        if self.bibliography_style.include == "all":
            keys = list(self.resources.ordered_keys)
        else:
            keys = list(self.cited_keys)
        if self.bibliography_style.sort == "citation-order":
            return keys
        return sorted(keys, key=self.reference_sort_key)

    def reference_sort_key(self, key: str) -> tuple[str, str, str]:
        entry = self.resources.entries[key]
        author = short_author(entry).casefold()
        year = entry.field("year")
        title = entry.field("title").casefold()
        if self.bibliography_style.sort == "key":
            return (key.casefold(), "", "")
        if self.bibliography_style.sort == "author-title":
            return (author, title, year)
        return (author, year, title)

    def reference_text(self, entry: BibEntry) -> str:
        fields = self.bibliography_style.templates.get(
            entry.entry_type,
            self.bibliography_style.templates.get(
                "default",
                ("author", "year", "title", "container", "publisher", "pages", "doi", "url"),
            ),
        )
        pieces = [self.reference_field(entry, field) for field in fields]
        return sentence_join(piece for piece in pieces if piece)

    def reference_field(self, entry: BibEntry, field: str) -> str:
        if field == "author":
            return self.escape_text(reference_authors(entry))
        if field == "year":
            year = entry.field("year")
            if not year:
                return ""
            if self.bibliography_style.name == "apa":
                return "(" + self.escape_text(year) + ")"
            return self.escape_text(year)
        if field == "title":
            title = entry.field("title")
            if not title:
                return ""
            escaped = self.escape_text(title)
            if entry.entry_type in {"book", "thesis"}:
                return r"\emph{" + escaped + "}"
            return escaped
        if field == "container":
            return self.escape_text(entry.field("journal", "booktitle", "howpublished", "organization"))
        if field == "publisher":
            return self.escape_text(entry.field("publisher", "school", "institution"))
        if field == "pages":
            pages = entry.field("pages")
            return "pp. " + self.escape_text(pages) if pages else ""
        if field == "doi":
            doi = entry.field("doi")
            return r"\href{https://doi.org/" + self.escape_url(doi) + "}{" + self.escape_text(doi) + "}" if doi else ""
        if field == "url":
            url = entry.field("url")
            return r"\href{" + self.escape_url(url) + "}{" + self.escape_text(url) + "}" if url else ""
        return self.escape_text(entry.field(field))


def document_bibliography_config(
    document: Document,
    base_dir: Path,
) -> tuple[list[Path], str | None, str | None]:
    resources: list[Path] = []
    citation_style: str | None = None
    bibliography_style: str | None = None
    for event in document.events:
        if not isinstance(event, DocumentPatch):
            continue
        head = event.call.head
        if head == "bib":
            resources = [resolve_resource_path(raw, base_dir) for raw in raw_args(event.call.args)]
        elif head == "bib+":
            resources.extend(resolve_resource_path(raw, base_dir) for raw in raw_args(event.call.args))
        elif head == "bib-":
            removals = {normalize_path(resolve_resource_path(raw, base_dir)) for raw in raw_args(event.call.args)}
            resources = [path for path in resources if normalize_path(path) not in removals]
        elif head == "citestyle":
            citation_style = first_raw_arg(event.call.args) or citation_style
        elif head == "bibstyle":
            bibliography_style = first_raw_arg(event.call.args) or bibliography_style
    return resources, citation_style, bibliography_style


def document_base_dir(document: Document) -> Path:
    for event in document.events:
        if event.origin is not None and event.origin.filename:
            return Path(event.origin.filename).expanduser().parent
    for block in document.blocks:
        origin = getattr(block, "origin", None)
        if origin is not None and origin.filename:
            return Path(origin.filename).expanduser().parent
    return Path(".")


def raw_args(args: tuple[object, ...]) -> list[str]:
    return [arg.text.strip() for arg in args if isinstance(arg, RawString) and arg.text.strip()]


def first_raw_arg(args: tuple[object, ...]) -> str | None:
    values = raw_args(args)
    return values[0] if values else None


def resolve_resource_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def normalize_path(path: Path) -> str:
    return str(path.resolve(strict=False))


def citation_locator(citation: Citation) -> str:
    for key in ("pages", "page", "locator", "p"):
        value = citation.kwargs.get(key)
        if value:
            return value
    return ""


def short_author(entry: BibEntry) -> str:
    names = split_names(entry.field("author", "editor"))
    if not names:
        return entry.key
    surnames = [surname(name) for name in names]
    if len(surnames) == 1:
        return surnames[0]
    if len(surnames) == 2:
        return surnames[0] + " and " + surnames[1]
    return surnames[0] + " et al."


def reference_authors(entry: BibEntry) -> str:
    names = split_names(entry.field("author", "editor"))
    if not names:
        return entry.key
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", and " + names[-1]


def split_names(value: str) -> list[str]:
    return [part.strip() for part in value.split(" and ") if part.strip()]


def surname(name: str) -> str:
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    return parts[-1] if parts else name


def sentence_join(parts: Iterable[object]) -> str:
    values = [str(part).strip().rstrip(".") for part in parts if str(part).strip()]
    if not values:
        return ""
    return ". ".join(values) + "."


def bibliography_summary(document: Document) -> dict[str, object]:
    base_dir = document_base_dir(document)
    resources, citation_style, bibliography_style = document_bibliography_config(document, base_dir)
    return {
        "resources": [str(path) for path in resources],
        "citation_style": citation_style or "numeric",
        "bibliography_style": bibliography_style or "numeric",
    }


def bibliography_snapshot(document: Document) -> dict[str, object]:
    base_dir = document_base_dir(document)
    resource_paths, citation_style_name, bibliography_style_name = document_bibliography_config(
        document,
        base_dir,
    )
    resources = load_bib_resources(tuple(resource_paths))
    citation_style = load_citation_style(citation_style_name, base_dir)
    bibliography_style = load_bibliography_style(bibliography_style_name, base_dir)
    return {
        "config": {
            "resources": [str(path) for path in resource_paths],
            "citation_style": citation_style_name or "numeric",
            "bibliography_style": bibliography_style_name or "numeric",
        },
        "resources": resources_to_json(resources),
        "citation_style": citation_style_to_json(citation_style),
        "bibliography_style": bibliography_style_to_json(bibliography_style),
    }


def resources_to_json(resources: BibliographyResources) -> dict[str, object]:
    return {
        "ordered_keys": list(resources.ordered_keys),
        "entries": [
            entry_to_json(resources.entries[key])
            for key in resources.ordered_keys
            if key in resources.entries
        ],
    }


def entry_to_json(entry: BibEntry) -> dict[str, object]:
    return {
        "key": entry.key,
        "entry_type": entry.entry_type,
        "fields": dict(entry.fields),
        "source_path": str(entry.source_path),
        "order": entry.order,
    }


def citation_style_to_json(style: CitationStyle) -> dict[str, object]:
    return {
        "name": style.name,
        "mode": style.mode,
        "form": style.form,
        "delimiter": style.delimiter,
        "year_separator": style.year_separator,
        "locator_prefix": style.locator_prefix,
    }


def bibliography_style_to_json(style: BibliographyStyle) -> dict[str, object]:
    return {
        "name": style.name,
        "title": style.title,
        "include": style.include,
        "sort": style.sort,
        "placement": style.placement,
        "label": style.label,
        "templates": {key: list(value) for key, value in style.templates.items()},
    }


def resources_from_json(payload: object) -> BibliographyResources:
    if not isinstance(payload, dict):
        raise MarkTeXError("backend-ir bibliography resources are invalid")
    entries: dict[str, BibEntry] = {}
    for item in payload.get("entries", []):
        if not isinstance(item, dict):
            raise MarkTeXError("backend-ir bibliography entry is invalid")
        entry = BibEntry(
            str(item.get("key", "")),
            str(item.get("entry_type", "")),
            {str(key): str(value) for key, value in dict(item.get("fields", {})).items()},
            Path(str(item.get("source_path", ""))),
            int(item.get("order", 0)),
        )
        entries[entry.key] = entry
    ordered_keys = tuple(str(key) for key in payload.get("ordered_keys", []))
    return BibliographyResources(entries, ordered_keys)


def citation_style_from_json(payload: object) -> CitationStyle:
    if not isinstance(payload, dict):
        raise MarkTeXError("backend-ir citation style is invalid")
    return CitationStyle(
        str(payload.get("name", "numeric")),
        str(payload.get("mode", "numeric")),
        str(payload.get("form", "square")),
        str(payload.get("delimiter", "; ")),
        str(payload.get("year_separator", ", ")),
        str(payload.get("locator_prefix", ", ")),
    )


def bibliography_style_from_json(payload: object) -> BibliographyStyle:
    if not isinstance(payload, dict):
        raise MarkTeXError("backend-ir bibliography style is invalid")
    templates: dict[str, tuple[str, ...]] = {}
    raw_templates = payload.get("templates", {})
    if isinstance(raw_templates, dict):
        templates = {
            str(key): tuple(str(item) for item in value)
            for key, value in raw_templates.items()
            if isinstance(value, list)
        }
    return BibliographyStyle(
        str(payload.get("name", "numeric")),
        str(payload.get("title", "References")),
        str(payload.get("include", "cited")),
        str(payload.get("sort", "citation-order")),
        str(payload.get("placement", "new-page")),
        str(payload.get("label", "numeric")),
        templates,
    )
