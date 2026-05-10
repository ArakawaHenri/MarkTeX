from __future__ import annotations

import re

FOOTNOTE_LABEL_PATTERN = r"[A-Za-z0-9_.:-]+"
FOOTNOTE_DEFINITION_RE = re.compile(rf"^\[\^({FOOTNOTE_LABEL_PATTERN})\]:\s*(.*)$")


def is_footnote_label(value: str) -> bool:
    return re.fullmatch(FOOTNOTE_LABEL_PATTERN, value) is not None
