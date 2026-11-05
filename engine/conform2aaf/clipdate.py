"""Shooting date carried by a camera clip name, e.g. A001C012_261009_RNU8.mov -> 2026-10-09."""
from __future__ import annotations

import re
from datetime import date

_ISO = re.compile(r"(?<!\d)(20\d{2})[-./](\d{2})[-./](\d{2})(?!\d)")
_YYYYMMDD = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
_YYMMDD = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")  # RED / ARRI style: _261009_


def _valid(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_from_name(text: str) -> date | None:
    """First plausible date in `text` (a clip name or path), or None. Years are 2020-2039."""
    for pattern in (_ISO, _YYYYMMDD):
        for m in pattern.finditer(text):
            if d := _valid(int(m.group(1)), int(m.group(2)), int(m.group(3))):
                return d
    for m in _YYMMDD.finditer(text):
        yy = int(m.group(1))
        if 20 <= yy <= 39 and (d := _valid(2000 + yy, int(m.group(2)), int(m.group(3)))):
            return d
    return None
