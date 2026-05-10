"""MarkTeX V0 compiler package."""

from __future__ import annotations

from marktex._version import __version__
from marktex.driver import ArtifactKind, CompileResult, compile_file

__all__ = ["ArtifactKind", "CompileResult", "compile_file", "__version__"]
