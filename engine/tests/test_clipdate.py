from datetime import date

import pytest

from conform2aaf.clipdate import date_from_name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("A001C012_261009_RNU8.mov", date(2026, 10, 9)),
        ("A006C009_261011_RNU8.mov - Merged", date(2026, 10, 11)),
        ("A007C052_261011_RNU8 - Merged.mov", date(2026, 10, 11)),
        ("20261009_cam_A.mov", date(2026, 10, 9)),
        ("take_2026-10-09_B", date(2026, 10, 9)),
        ("2/BRUTOS/DIA 01/A003C007_261009_RNU8.mov", date(2026, 10, 9)),
    ],
)
def test_date_from_name(name, expected):
    assert date_from_name(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "A001C012",  # no date at all
        "A001_999999_x",  # month 99
        "clip_123456",  # year 12 is not a plausible shooting year
        "A001_10091234_C001",  # Blackmagic MMDDHHMM: not a date we can trust
        "A001C012_261309_RNU8",  # month 13
        "",
    ],
)
def test_no_date(name):
    assert date_from_name(name) is None
