from conform2aaf.readers import read_timeline
from conform2aaf.timecode import FrameRate

R25 = FrameRate.parse("25")

PICTURE_ONLY = """TITLE: PIC
FCM: NON-DROP FRAME

001  A001C002 V     C        10:00:01:00 10:00:03:00 01:00:00:00 01:00:02:00
"""

WITH_AUDIO = PICTURE_ONLY + """
002  A001C002 AA/V  C        10:00:03:00 10:00:04:00 01:00:02:00 01:00:03:00
"""


def test_auto_switches_to_picture_mode_when_there_is_no_audio(tmp_path):
    p = tmp_path / "pic.edl"
    p.write_text(PICTURE_ONLY)
    tl = read_timeline(p, R25)
    assert tl.picture and len(list(tl.clips())) == 1
    assert any("Lista de imagen" in w for w in tl.warnings)


def test_auto_keeps_audio_mode_when_the_list_has_audio(tmp_path):
    p = tmp_path / "av.edl"
    p.write_text(WITH_AUDIO)
    tl = read_timeline(p, R25)
    assert not tl.picture and len(list(tl.clips())) == 2  # AA/V -> A1 and A2


def test_forced_modes(tmp_path):
    p = tmp_path / "av.edl"
    p.write_text(WITH_AUDIO)
    assert read_timeline(p, R25, picture=True).picture
    only = tmp_path / "pic.edl"
    only.write_text(PICTURE_ONLY)
    off = read_timeline(only, R25, picture=False)
    assert not off.picture and list(off.clips()) == []
