from __future__ import annotations

from datetime import datetime
import ast
from types import MappingProxyType
from typing import Any

import marktex.runtime as runtime
from marktex.host.python.symbolic import PAGE
from marktex.source import MarkTeXError, SourceSpan


SAFE_BUILTINS = MappingProxyType(
    {
        "True": True,
        "False": False,
        "None": None,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "len": len,
        "list": list,
        "tuple": tuple,
        "dict": dict,
        "min": min,
        "max": max,
        "sum": sum,
        "range": range,
    }
)


class PythonHost:
    """Small controlled Python host environment for the 0.1 compiler."""

    def __init__(
        self,
        *,
        no_host: bool = False,
        runtime_session: runtime.RuntimeSession | None = None,
    ) -> None:
        self.no_host = no_host
        self.runtime = runtime_session or runtime.RuntimeSession()
        self.executed_blocks: list[str] = []
        self.globals: dict[str, Any] = {
            "__builtins__": SAFE_BUILTINS,
            "marktex": self.runtime,
            "PAGE": PAGE,
            "TIME": datetime.now(),
            "BIB": [],
        }

    def execute_block(self, body: str, origin: SourceSpan | None = None) -> None:
        if self.no_host:
            raise MarkTeXError("host blocks are disabled by --no-host", origin)
        try:
            exec(compile(body, origin.filename if origin else "<mtx-host>", "exec"), self.globals)
            self.executed_blocks.append(body)
        except MarkTeXError:
            raise
        except Exception as exc:  # pragma: no cover - exact host exceptions vary
            raise MarkTeXError(f"host block failed: {exc}", origin) from exc

    def eval_expr(self, expr: str, origin: SourceSpan | None = None) -> Any:
        if self.no_host:
            return self.eval_no_host(expr, origin)
        try:
            return eval(compile(expr, origin.filename if origin else "<mtx-expr>", "eval"), self.globals)
        except MarkTeXError:
            raise
        except Exception as exc:
            raise MarkTeXError(f"host expression failed: {expr}: {exc}", origin) from exc

    def eval_no_host(self, expr: str, origin: SourceSpan | None = None) -> Any:
        normalized = expr.strip()
        if normalized == "PAGE.CURRENT":
            return PAGE.CURRENT
        if normalized == "PAGE.TOTAL":
            return PAGE.TOTAL
        try:
            return ast.literal_eval(normalized)
        except Exception as exc:
            raise MarkTeXError(
                f"host expression is disabled by --no-host: {expr}",
                origin,
            ) from exc

    def drain_runtime_events(self) -> tuple[runtime.RuntimeEvent, ...]:
        return self.runtime.drain()
