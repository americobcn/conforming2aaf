from fractions import Fraction

import pytest

from conform2aaf.timecode import FrameRate, frames_to_samples, frames_to_tc, tc_to_frames


@pytest.mark.parametrize(
    "text,fps,nominal,drop",
    [
        ("23.976", Fraction(24000, 1001), 24, False),
        ("24", Fraction(24), 24, False),
        ("25", Fraction(25), 25, False),
        ("29.97", Fraction(30000, 1001), 30, False),
        ("29.97df", Fraction(30000, 1001), 30, True),
        ("30", Fraction(30), 30, False),
        ("50", Fraction(50), 50, False),
        ("59.94", Fraction(60000, 1001), 60, False),
        ("59.94DF", Fraction(60000, 1001), 60, True),
        ("60", Fraction(60), 60, False),
    ],
)
def test_parse_rates(text, fps, nominal, drop):
    r = FrameRate.parse(text)
    assert (r.fps, r.nominal, r.drop) == (fps, nominal, drop)


def test_invalid_rate():
    with pytest.raises(ValueError):
        FrameRate.parse("24df")


def test_ndf_roundtrip():
    r = FrameRate.parse("25")
    assert tc_to_frames("01:00:00:00", r) == 90000
    assert frames_to_tc(90001, r) == "01:00:00:01"


@pytest.mark.parametrize(
    "tc,frames",
    [
        ("00:00:59;29", 1799),
        ("00:01:00;02", 1800),
        ("00:10:00;00", 17982),
        ("01:00:00;00", 107892),
    ],
)
def test_drop_frame_2997(tc, frames):
    r = FrameRate.parse("29.97df")
    assert tc_to_frames(tc, r) == frames
    assert frames_to_tc(frames, r) == tc


def test_drop_frame_5994():
    r = FrameRate.parse("59.94df")
    assert tc_to_frames("00:10:00;00", r) == 35964
    assert frames_to_tc(3600, r) == "00:01:00;04"


def test_invalid_drop_frame_tc():
    with pytest.raises(ValueError):
        tc_to_frames("00:01:00;00", FrameRate.parse("29.97df"))


def test_frames_to_samples():
    assert frames_to_samples(1, FrameRate.parse("23.976"), 48000) == 2002
    assert frames_to_samples(1, FrameRate.parse("25"), 48000) == 1920
    # 29.97: 1601.6 samples/frame -> rounds to nearest sample
    assert frames_to_samples(5, FrameRate.parse("29.97"), 48000) == 8008
