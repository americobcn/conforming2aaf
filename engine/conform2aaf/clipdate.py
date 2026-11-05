"""Shooting date and start time carried by a camera clip name.

A001C012_261009_RNU8.mov                    -> 2026-10-09
A_0002C012_251111_115104_h1D2K.mov - Merged -> 2025-11-11 at 11:51:04
"""
from __future__ import annotations

import re
from datetime import date, time

_ISO = re.compile(r"(?<!\d)(20\d{2})[-./](\d{2})[-./](\d{2})(?!\d)")
_YYYYMMDD = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
_YYMMDD = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")  # RED / ARRI style: _261009_
_TIME_AFTER_DATE = re.compile(r"[_\-. T]?(\d{2})(\d{2})(\d{2})(?!\d)")  # _115104 right after the date


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _find_date(text: str) -> tuple[date | None, int]:
    """First plausible date in `text` and where its token ends. Years are 2020-2039."""
    for pattern in (_ISO, _YYYYMMDD):
        for m in pattern.finditer(text):
            if d := _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3))):
                return d, m.end()
    for m in _YYMMDD.finditer(text):
        yy = int(m.group(1))
        if 20 <= yy <= 39 and (d := _valid_date(2000 + yy, int(m.group(2)), int(m.group(3)))):
            return d, m.end()
    return None, 0


def date_from_name(text: str) -> date | None:
    return _find_date(text)[0]


def time_from_name(text: str) -> time | None:
    """HHMMSS token that follows the date (a time, never a second date), if it is a valid time."""
    d, end = _find_date(text)
    if d is None:
        return None
    m = _TIME_AFTER_DATE.match(text, end)
    if not m:
        return None
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return time(hh, mm, ss) if hh < 24 and mm < 60 and ss < 60 else None
