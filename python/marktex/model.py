from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StyleScalar = str | float | bool | tuple[int, int, int]
StyleMap = dict[str, StyleScalar]


@dataclass(frozen=True)
class SourceSpan:
    line: int
    col_start: int
    col_end: int


@dataclass(frozen=True)
class BlockContext:
    kind: Literal["paragraph", "heading"]
    heading_level: int | None = None


@dataclass(frozen=True)
class DirectiveEvent:
    body: str
    span: SourceSpan


@dataclass(frozen=True)
class ScopeSetEvent:
    scope: str
    styles: StyleMap
    span: SourceSpan


@dataclass(frozen=True)
class ScopeUnsetEvent:
    scope: str | None
    all_scopes: bool
    span: SourceSpan


@dataclass(frozen=True)
class InlinePushEvent:
    styles: StyleMap
    span: SourceSpan


@dataclass(frozen=True)
class InlinePopEvent:
    span: SourceSpan


@dataclass(frozen=True)
class CitationEvent:
    key: str
    pages: str | None
    span: SourceSpan
    block: BlockContext
    line_no: int


@dataclass(frozen=True)
class BibEntryEvent:
    entry: str
    span: SourceSpan


@dataclass(frozen=True)
class TextEvent:
    text: str
    span: SourceSpan
    block: BlockContext
    line_no: int


@dataclass(frozen=True)
class LineBreakEvent:
    line_no: int
    block: BlockContext


Event = (
    DirectiveEvent
    | ScopeSetEvent
    | ScopeUnsetEvent
    | InlinePushEvent
    | InlinePopEvent
    | CitationEvent
    | BibEntryEvent
    | TextEvent
    | LineBreakEvent
)


@dataclass(frozen=True)
class StyledChunk:
    text: str
    styles: StyleMap
    block: BlockContext
    line_no: int
    raw_latex: bool = False


@dataclass(frozen=True)
class LineBreak:
    line_no: int
    block: BlockContext


ResolvedUnit = StyledChunk | LineBreak


@dataclass
class DocumentConfig:
    layout_name: str | None = None
    orientation: Literal["portrait", "landscape"] = "portrait"
    paper_size_mm: tuple[float, float] | None = None
    margins_mm: dict[str, float] = field(default_factory=dict)
    column_rules_raw: str | None = None
    column_margin_rules_raw: str | None = None
    header_footer: dict[str, str] = field(
        default_factory=lambda: {
            "header_left": "",
            "header_center": "",
            "header_right": "",
            "footer_left": "",
            "footer_center": "",
            "footer_right": "",
        }
    )
    bib_files: list[str] = field(default_factory=list)
    bibstyle: str | None = None
    citestyle: str | None = None
    raw_directives: list[str] = field(default_factory=list)


@dataclass
class ResolvedDocument:
    config: DocumentConfig
    units: list[ResolvedUnit]
    bib_entries: list[str]
