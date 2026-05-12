from __future__ import annotations

from marktex.surface.assemble import assemble_surface
from marktex.surface.fallback_layer import parse_fallback_layer
from marktex.surface.marktex_layer import parse_marktex_layer
from marktex.surface.model import SurfaceDocument


def parse_surface(source: str, *, filename: str) -> SurfaceDocument:
    marktex_document = parse_marktex_layer(source, filename=filename)
    fallback_document = parse_fallback_layer(marktex_document, filename=filename, source=source)
    return assemble_surface(fallback_document)
