from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from marktex.bibliography.model import BibEntry, BibliographyResources
from marktex.source import MarkTeXError


IGNORED_ENTRY_TYPES = {"comment", "preamble", "string"}


def load_bib_resources(paths: tuple[Path, ...]) -> BibliographyResources:
    entries: dict[str, BibEntry] = {}
    ordered_keys: list[str] = []
    order = 0
    for path in paths:
        for entry in parse_bibtex_file(path, start_order=order):
            if entry.key in entries:
                raise MarkTeXError(f"duplicate bibliography key: {entry.key}")
            entries[entry.key] = entry
            ordered_keys.append(entry.key)
            order += 1
    return BibliographyResources(entries, tuple(ordered_keys))


def parse_bibtex_file(path: Path, *, start_order: int = 0) -> tuple[BibEntry, ...]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkTeXError(f"bibliography file cannot be read: {path}") from exc
    return tuple(_BibTeXParser(source, path, start_order).parse())


class _BibTeXParser:
    def __init__(self, source: str, path: Path, start_order: int) -> None:
        self.source = source
        self.path = path
        self.index = 0
        self.next_order = start_order

    def parse(self) -> list[BibEntry]:
        entries: list[BibEntry] = []
        while not self.eof:
            self.skip_until_entry()
            if self.eof:
                break
            entry = self.parse_entry()
            if entry is not None:
                entries.append(entry)
        return entries

    def skip_until_entry(self) -> None:
        while not self.eof and self.peek != "@":
            self.index += 1

    def parse_entry(self) -> BibEntry | None:
        self.expect("@")
        entry_type = self.read_identifier().lower()
        self.skip_ws()
        opener = self.peek
        if opener not in {"{", "("}:
            self.error("malformed BibTeX entry: expected '{' or '('")
        closer = "}" if opener == "{" else ")"
        self.index += 1
        if entry_type in IGNORED_ENTRY_TYPES:
            self.skip_balanced(opener, closer)
            return None
        key = self.read_until({","}).strip()
        if not key:
            self.error("malformed BibTeX entry: missing key")
        self.expect(",")
        fields: dict[str, str] = {}
        while not self.eof:
            self.skip_ws_and_commas()
            if self.peek == closer:
                self.index += 1
                entry = BibEntry(key, entry_type, fields, self.path, self.next_order)
                self.next_order += 1
                return entry
            name = self.read_identifier().lower()
            if not name:
                self.error("malformed BibTeX field: missing field name")
            self.skip_ws()
            self.expect("=")
            self.skip_ws()
            fields[name] = clean_bibtex_value(self.read_value(closer))
            self.skip_ws()
            if self.peek == ",":
                self.index += 1
        self.error("unclosed BibTeX entry")

    def read_value(self, entry_closer: str) -> str:
        if self.peek == "{":
            return self.read_braced()
        if self.peek == '"':
            return self.read_quoted()
        return self.read_until({",", entry_closer}).strip()

    def read_braced(self) -> str:
        self.expect("{")
        depth = 1
        parts: list[str] = []
        while not self.eof:
            char = self.peek
            self.index += 1
            if char == "{":
                depth += 1
                parts.append(char)
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return "".join(parts)
                parts.append(char)
            else:
                parts.append(char)
        self.error("unclosed braced BibTeX value")

    def read_quoted(self) -> str:
        self.expect('"')
        parts: list[str] = []
        while not self.eof:
            char = self.peek
            self.index += 1
            if char == "\\" and not self.eof:
                parts.append(char)
                parts.append(self.peek)
                self.index += 1
            elif char == '"':
                return "".join(parts)
            else:
                parts.append(char)
        self.error("unclosed quoted BibTeX value")

    def read_identifier(self) -> str:
        start = self.index
        while not self.eof and (self.peek.isalnum() or self.peek in {"_", "-", ":"}):
            self.index += 1
        return self.source[start : self.index]

    def read_until(self, stops: set[str]) -> str:
        start = self.index
        while not self.eof and self.peek not in stops:
            self.index += 1
        return self.source[start : self.index]

    def skip_balanced(self, opener: str, closer: str) -> None:
        depth = 1
        while not self.eof and depth:
            char = self.peek
            self.index += 1
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
        if depth:
            self.error("unclosed BibTeX entry")

    def skip_ws(self) -> None:
        while not self.eof and self.peek.isspace():
            self.index += 1

    def skip_ws_and_commas(self) -> None:
        while not self.eof and (self.peek.isspace() or self.peek == ","):
            self.index += 1

    def expect(self, value: str) -> None:
        if self.peek != value:
            self.error(f"malformed BibTeX: expected {value!r}")
        self.index += 1

    @property
    def eof(self) -> bool:
        return self.index >= len(self.source)

    @property
    def peek(self) -> str:
        if self.eof:
            return ""
        return self.source[self.index]

    def error(self, message: str) -> NoReturn:
        raise MarkTeXError(f"{message} in {self.path}")


def clean_bibtex_value(value: str) -> str:
    text = value.replace("\n", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text.replace("{", "").replace("}", "")

