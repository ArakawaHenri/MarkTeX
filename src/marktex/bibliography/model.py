from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BibEntry:
    key: str
    entry_type: str
    fields: dict[str, str]
    source_path: Path
    order: int

    def field(self, *names: str) -> str:
        for name in names:
            value = self.fields.get(name.lower(), "")
            if value:
                return value
        return ""


@dataclass(frozen=True)
class CitationStyle:
    name: str
    mode: str = "numeric"
    form: str = "square"
    delimiter: str = "; "
    year_separator: str = ", "
    locator_prefix: str = ", "


@dataclass(frozen=True)
class BibliographyStyle:
    name: str
    title: str = "References"
    include: str = "cited"
    sort: str = "citation-order"
    placement: str = "new-page"
    label: str = "numeric"
    templates: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class BibliographyResources:
    entries: dict[str, BibEntry]
    ordered_keys: tuple[str, ...]

