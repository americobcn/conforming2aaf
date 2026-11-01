from fractions import Fraction as F

from conform2aaf.readers.edl import read_edl
from conform2aaf.timecode import FrameRate

EDL = """TITLE: REEL 1 AUDIO
FCM: NON-DROP FRAME

001  12A_T3   AA/V  C        10:00:02:00 10:00:04:00 01:00:00:00 01:00:02:00
* FROM CLIP NAME: 12A_T3
* SOURCE FILE: 12A_T3.WAV
* AUDIO LEVEL AT 01:00:00:00 IS -3.00 DB  (REEL 12A_T3 A2)

002  14B_T1   A     C        11:00:00:00 11:00:00:00 01:00:02:00 01:00:02:00
002  14B_T2   A     D    012 11:30:00:00 11:30:03:00 01:00:02:00 01:00:05:00
* FROM CLIP NAME: 14B_T1
* TO CLIP NAME: 14B_T2

003  WILD     A3    C        00:00:00:00 00:00:01:00 01:00:05:00 01:00:06:00
AUD  4
M2   WILD     050.0          00:00:00:00

004  BL       V     C        00:00:00:00 00:00:01:00 01:00:06:00 01:00:07:00
005  X        A     W001     00:00:00:00 00:00:01:00 01:00:07:00 01:00:08:00
"""


def test_reads_events(tmp_path):
    p = tmp_path / "r1.edl"
    p.write_text(EDL)
    tl = read_edl(p, FrameRate.parse("25"))
    assert tl.name == "REEL 1 AUDIO"
    assert tl.start == F(3600)
    assert [t.name for t in tl.tracks] == ["A1", "A2", "A3", "A4"]

    a1 = tl.tracks[0].clips
    assert [c.name for c in a1] == ["12A_T3", "14B_T2", "X"]
    first = a1[0]
    assert first.record_in == F(3600) and first.duration == F(2)
    assert first.source_in == F(36002) and first.file_hint == "12A_T3.WAV"
    assert first.channel == 1 and first.gain_db == 0.0
    assert tl.tracks[1].clips[0].gain_db == -3.0

    xfade = a1[1]
    assert xfade.crossfade_in == F(12, 25) and xfade.crossfade_pre == 0
    assert xfade.source_in == F(11 * 3600 + 30 * 60)

    assert [c.channel for c in tl.tracks[2].clips + tl.tracks[3].clips] == [1, 2]  # simultaneous events -> source channels 1, 2
    assert any("velocidad" in w for w in tl.warnings)
    assert any("W001" in w for w in tl.warnings)


def test_fade_from_and_to_black(tmp_path):
    p = tmp_path / "f.edl"
    p.write_text(
        "TITLE: F\nFCM: NON-DROP FRAME\n"
        "001  BL  A  C       00:00:00:00 00:00:00:00 01:00:00:00 01:00:00:00\n"
        "001  T1  A  D  010  10:00:00:00 10:00:02:00 01:00:00:00 01:00:02:00\n"
        "002  T1  A  C       10:00:02:00 10:00:02:00 01:00:02:00 01:00:02:00\n"
        "002  BL  A  D  005  00:00:00:00 00:00:01:00 01:00:02:00 01:00:03:00\n"
    )
    tl = read_edl(p, FrameRate.parse("25"))
    (c,) = tl.tracks[0].clips
    assert c.fade_in == F(10, 25) and c.crossfade_in == 0 and c.fade_out == F(5, 25)


def test_drop_frame_from_fcm(tmp_path):
    p = tmp_path / "df.edl"
    p.write_text(
        "TITLE: DF\nFCM: DROP FRAME\n"
        "001  A  A  C  00:10:00;00 00:10:01;00 01:00:00;00 01:00:01;00\n"
    )
    tl = read_edl(p, FrameRate.parse("29.97"))
    assert tl.rate.drop
    c = tl.tracks[0].clips[0]
    assert c.source_in == F(17982) / F(30000, 1001)


def test_simultaneous_events_take_source_channels_in_track_order(tmp_path):
    """An EDL only names the destination track (A3..A6), never the source channel."""
    p = tmp_path / "poly.edl"
    p.write_text(
        "TITLE: P\nFCM: NON-DROP FRAME\n"
        + "".join(
            f"{i:03d}  AX  {t}  C  09:23:49:20 09:24:07:07 01:01:39:05 01:01:56:16\n"
            f"* FROM CLIP NAME: SL7787.WAV\n\n"
            for i, t in enumerate(["A3", "A4", "A5", "A6"], 11)
        )
        + "020  AX  A2  C  10:00:00:00 10:00:01:00 01:02:00:00 01:02:01:00\n* FROM CLIP NAME: LONE.WAV\n"
    )
    tl = read_edl(p, FrameRate.parse("25"))
    assert [t.name for t in tl.tracks] == ["A2", "A3", "A4", "A5", "A6"]
    by_track = {t.name: [c.channel for c in t.clips] for t in tl.tracks}
    assert by_track == {"A2": [1], "A3": [1], "A4": [2], "A5": [3], "A6": [4]}
