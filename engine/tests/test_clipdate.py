from datetime import date, time

import pytest

from conform2aaf.clipdate import date_from_name, time_from_name


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


@pytest.mark.parametrize(
    "name,day,at",
    [
        ("A_0002C012_251111_115104_h1D2K.mov - Merged", date(2025, 11, 11), time(11, 51, 4)),
        ("A_0002C012_251111_115104_h1D2K.mov", date(2025, 11, 11), time(11, 51, 4)),
        ("20251111_115104_cam", date(2025, 11, 11), time(11, 51, 4)),
        # the time token looks like a date (23-11-02) but follows the real date: it is the time
        ("A001C001_251111_231102_x.mov", date(2025, 11, 11), time(23, 11, 2)),
    ],
)
def test_date_and_time_from_name(name, day, at):
    assert date_from_name(name) == day
    assert time_from_name(name) == at


@pytest.mark.parametrize(
    "name",
    [
        "A001C012_261009_RNU8.mov",  # date only
        "A001C012_261009_996104_x",  # 99 is not an hour
        "A001C012_261009_115960_x",  # 60 seconds
        "A001C012",
        "",
    ],
)
def test_no_time(name):
    assert time_from_name(name) is None


@pytest.mark.parametrize(
    "tape,expected",
    [
        ("26Y10M30", date(2026, 10, 30)),  # sound recorders that write the date as the tape
        ("26y10m28", date(2026, 10, 28)),
        ("261030", date(2026, 10, 30)),
    ],
)
def test_date_written_as_a_tape(tape, expected):
    assert date_from_name(tape) == expected
    assert time_from_name(tape) is None
