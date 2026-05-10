from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """A compact origin span in a source file."""

    filename: str
    start: int
    end: int
    line: int = 1
    column: int = 1

    def to_json(self) -> dict[str, int | str]:
        return {
            "filename": self.filename,
            "start": self.start,
            "end": self.end,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True)
class Diagnostic:
    message: str
    span: SourceSpan | None = None

    def format(self) -> str:
        if self.span is None:
            return self.message
        return f"{self.span.filename}:{self.span.line}:{self.span.column}: {self.message}"

    def to_json(self) -> dict[str, object]:
        return {
            "message": self.message,
            "span": self.span.to_json() if self.span else None,
        }


class MarkTeXError(Exception):
    """User-facing compiler error with optional source origin."""

    def __init__(self, message: str, span: SourceSpan | None = None) -> None:
        self.diagnostic = Diagnostic(message, span)
        super().__init__(self.diagnostic.format())
