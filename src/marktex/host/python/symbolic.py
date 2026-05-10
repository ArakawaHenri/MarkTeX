from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marktex.source import MarkTeXError


@dataclass(frozen=True, eq=False)
class SymbolicExpr:
    op: str
    operands: tuple[Any, ...]

    def __bool__(self) -> bool:
        raise MarkTeXError("symbolic value cannot be coerced to a host boolean")

    def to_json(self) -> dict[str, object]:
        return {"kind": "symbolic_expr", "op": self.op, "operands": [symbolic_to_json(v) for v in self.operands]}

    def _binary(self, op: str, other: Any) -> "SymbolicExpr":
        return SymbolicExpr(op, (self, other))

    def _rbinary(self, op: str, other: Any) -> "SymbolicExpr":
        return SymbolicExpr(op, (other, self))

    def __add__(self, other: Any) -> "SymbolicExpr":
        return self._binary("add", other)

    def __radd__(self, other: Any) -> "SymbolicExpr":
        return self._rbinary("add", other)

    def __sub__(self, other: Any) -> "SymbolicExpr":
        return self._binary("sub", other)

    def __rsub__(self, other: Any) -> "SymbolicExpr":
        return self._rbinary("sub", other)

    def __mod__(self, other: Any) -> "SymbolicExpr":
        return self._binary("mod", other)

    def __rmod__(self, other: Any) -> "SymbolicExpr":
        return self._rbinary("mod", other)

    def __eq__(self, other: Any) -> "SymbolicExpr":  # type: ignore[override]
        return self._binary("eq", other)

    def __ne__(self, other: Any) -> "SymbolicExpr":  # type: ignore[override]
        return self._binary("ne", other)

    def __lt__(self, other: Any) -> "SymbolicExpr":
        return self._binary("lt", other)

    def __le__(self, other: Any) -> "SymbolicExpr":
        return self._binary("le", other)

    def __gt__(self, other: Any) -> "SymbolicExpr":
        return self._binary("gt", other)

    def __ge__(self, other: Any) -> "SymbolicExpr":
        return self._binary("ge", other)


@dataclass(frozen=True, eq=False)
class SymbolicValue(SymbolicExpr):
    owner: str = ""
    name: str = ""

    def __init__(self, owner: str, name: str) -> None:
        object.__setattr__(self, "op", "value")
        object.__setattr__(self, "operands", ())
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "name", name)

    def to_json(self) -> dict[str, object]:
        return {"kind": "symbolic_value", "owner": self.owner, "name": self.name}


class _Page:
    CURRENT = SymbolicValue("PAGE", "CURRENT")
    TOTAL = SymbolicValue("PAGE", "TOTAL")


PAGE = _Page()


def symbolic_to_json(value: Any) -> object:
    if hasattr(value, "to_json"):
        return value.to_json()
    return value
