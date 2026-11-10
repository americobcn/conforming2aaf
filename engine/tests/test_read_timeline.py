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


def test_auto_reads_a_picture_only_list_as_picture_cuts(tmp_path):
    p = tmp_path / "pic.edl"
    p.write_text(PICTURE_ONLY)
    tl = read_timeline(p, R25)
    assert tl.picture and len(list(tl.clips())) == 1


AUDIO_ONLY = """TITLE: SND
FCM: NON-DROP FRAME

001  12A_T3   AA    C        10:00:01:00 10:00:03:00 01:00:00:00 01:00:02:00
"""


def test_auto_conforms_production_sound_to_the_picture_even_when_the_list_has_audio(tmp_path):
    p = tmp_path / "av.edl"
    p.write_text(WITH_AUDIO)
    tl = read_timeline(p, R25)
    assert tl.picture and len(list(tl.clips())) == 2  # the V and AA/V events


def test_auto_reads_the_audio_tracks_when_there_are_no_picture_cuts(tmp_path):
    p = tmp_path / "snd.edl"
    p.write_text(AUDIO_ONLY)
    tl = read_timeline(p, R25)
    assert not tl.picture and len(list(tl.clips())) == 2  # AA -> A1 and A2
    assert any("sin cortes de imagen" in w for w in tl.warnings)


def test_forced_modes(tmp_path):
    p = tmp_path / "av.edl"
    p.write_text(WITH_AUDIO)
    assert read_timeline(p, R25, picture=True).picture
    assert not read_timeline(p, R25, picture=False).picture
    only = tmp_path / "pic.edl"
    only.write_text(PICTURE_ONLY)
    off = read_timeline(only, R25, picture=False)
    assert not off.picture and list(off.clips()) == []
