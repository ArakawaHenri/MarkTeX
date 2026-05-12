from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CookedText:
    text: str
    escaped: tuple[bool, ...]
    offsets: tuple[int, ...]

    @classmethod
    def from_raw(cls, raw: str, offsets: tuple[int, ...] | None = None) -> CookedText:
        source_offsets = offsets if offsets is not None else tuple(range(len(raw) + 1))
        chars: list[str] = []
        escaped: list[bool] = []
        cooked_offsets: list[int] = [source_offsets[0]]
        index = 0
        while index < len(raw):
            char = raw[index]
            if char == "\\":
                index += 1
                if index >= len(raw):
                    chars.append("\\")
                    escaped.append(True)
                    cooked_offsets.append(source_offsets[index])
                    continue
                if raw[index] == "\n":
                    index += 1
                    continue
                chars.append(raw[index])
                escaped.append(True)
                index += 1
                cooked_offsets.append(source_offsets[index])
                continue
            chars.append(char)
            escaped.append(False)
            index += 1
            cooked_offsets.append(source_offsets[index])
        return cls("".join(chars), tuple(escaped), tuple(cooked_offsets))

    def __len__(self) -> int:
        return len(self.text)

    def slice(self, start: int, end: int | None = None) -> CookedText:
        resolved_end = len(self.text) if end is None else end
        return CookedText(
            self.text[start:resolved_end],
            self.escaped[start:resolved_end],
            self.offsets[start : resolved_end + 1],
        )

    def is_unescaped(self, index: int) -> bool:
        return 0 <= index < len(self.escaped) and not self.escaped[index]

    def char_is(self, index: int, char: str, *, unescaped: bool = True) -> bool:
        if index < 0 or index >= len(self.text) or self.text[index] != char:
            return False
        return self.is_unescaped(index) if unescaped else True

    def startswith(self, prefix: str, index: int = 0, *, unescaped: bool = True) -> bool:
        if not self.text.startswith(prefix, index):
            return False
        if not unescaped:
            return True
        return all(self.is_unescaped(cursor) for cursor in range(index, index + len(prefix)))

    def find_unescaped(self, char: str, start: int = 0, end: int | None = None) -> int:
        resolved_end = len(self.text) if end is None else end
        cursor = start
        while cursor < resolved_end:
            if self.text[cursor] == char and self.is_unescaped(cursor):
                return cursor
            cursor += 1
        return -1

    def strip_ascii_padding(self) -> CookedText:
        start = 1 if self.text.startswith(" ") else 0
        end = len(self.text) - 1 if self.text.endswith(" ") and len(self.text) > start else len(self.text)
        return self.slice(start, end)


def cook_raw(raw: str, offsets: tuple[int, ...] | None = None) -> CookedText:
    return CookedText.from_raw(raw, offsets)
