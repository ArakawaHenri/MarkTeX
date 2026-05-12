from __future__ import annotations

from marktex.source.model import SourceSpan


def span_from_range(filename: str, start: int, end: int, source: str) -> SourceSpan:
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start + 1 if last_newline == -1 else start - last_newline
    return SourceSpan(filename, start, end, line, column)


def span_from_offsets(filename: str, offsets: tuple[int, ...], source: str) -> SourceSpan:
    return span_from_range(filename, offsets[0], offsets[-1], source)


def offset_span(origin: SourceSpan, start_delta: int, end_delta: int, source: str) -> SourceSpan:
    return span_from_range(
        origin.filename,
        origin.start + start_delta,
        origin.start + end_delta,
        source,
    )


def remap_span_to_offsets(
    origin: SourceSpan | None,
    offsets: tuple[int, ...],
    filename: str,
    source: str,
) -> SourceSpan | None:
    if origin is None:
        return None
    start_index = min(max(origin.start, 0), len(offsets) - 1)
    end_index = min(max(origin.end, 0), len(offsets) - 1)
    return span_from_range(filename, offsets[start_index], offsets[end_index], source)
