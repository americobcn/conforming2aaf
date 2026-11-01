import hashlib
import struct
from fractions import Fraction as F

import aaf2

from conform2aaf.media.riff import read_wav
from conform2aaf.model import Clip, Timeline, Track
from conform2aaf.timecode import FrameRate
from conform2aaf.writers.aaf import locator_url, write_aaf

SR = 48000


def _matched(mf, **kw):
    c = Clip(**kw)
    c.media, c.match_status = mf, "matched"
    return c


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_write_and_read_back(tmp_path, wav_factory):
    a_path = wav_factory("A.wav", seconds=10, channels=2, time_reference=36000 * SR, scene="12A", take="3")
    b_path = wav_factory("B.wav", seconds=10, time_reference=39600 * SR)
    before = (_sha(a_path), _sha(b_path))
    a, b = read_wav(a_path), read_wav(b_path)

    clips = [
        _matched(a, name="A", record_in=F(3600), duration=F(2), source_in=F(36001), channel=1, gain_db=-6.0),
        _matched(b, name="B", record_in=F(3602), duration=F(2), source_in=F(39601), channel=1,
                 crossfade_in=F(1, 2), crossfade_pre=F(1, 4)),
        _matched(a, name="A2", record_in=F(3605), duration=F(1), source_in=F(36005), channel=2,
                 fade_in=F(1, 5), fade_out=F(1, 10)),
        Clip(name="lost", record_in=F(3607), duration=F(1), match_status="missing"),
    ]
    tl = Timeline("Reel 1", FrameRate.parse("25"), start=F(3600), tracks=[Track("A1", clips)])
    out = tmp_path / "out" / "reel1.aaf"
    res = write_aaf(tl, out, SR)
    assert (res.clips_written, res.clips_skipped) == (3, 1)
    assert res.warnings == []
    assert (_sha(a_path), _sha(b_path)) == before  # media untouched

    with aaf2.open(str(out), "r") as f:
        (comp,) = list(f.content.compositionmobs())
        assert comp.name == "Reel 1"
        tc_slot = next(s for s in comp.slots if s.media_kind == "Timecode")
        assert tc_slot.segment.start == 3600 * 25 and tc_slot.segment.fps == 25
        (snd,) = [s for s in comp.slots if s.media_kind == "Sound"]
        assert snd.name == "A1" and snd.edit_rate == SR
        c = list(snd.segment.components)
        kinds = [type(x).__name__ for x in c]
        assert kinds == ["OperationGroup", "Transition", "SourceClip", "Filler",
                         "Transition", "SourceClip", "Transition", "Filler"]

        gain, xf, clip_b, fill, fin, clip_a2, fout, tail = c
        inner = gain.segments[0]
        assert (gain.length, inner.start, inner.length) == (108000, 48000, 108000)
        (param,) = list(gain.parameters)
        assert param.parameterdef.name == "Amplitude"
        amp = param.value
        assert abs(float(amp) - 0.501) < 0.001
        assert (xf.length, xf["CutPoint"].value) == (24000, 12000)
        assert (clip_b.start, clip_b.length, clip_b.mob.name) == (36000, 108000, "B")
        assert fill.length == 57600 and (fin.length, fin["CutPoint"].value) == (9600, 0)
        assert (clip_a2.start, clip_a2.length, clip_a2.slot_id) == (240000, 48000, 2)
        assert (fout.length, tail.length) == (4800, 4800)
        assert snd.segment.length == 288000

        mm = inner.mob
        assert mm.name == "A" and mm.comments["Scene"] == "12A" and mm.comments["Take"] == "3"
        file_clip = mm.slot_at(1).segment.components[0]
        file_mob = file_clip.mob
        url = file_mob.descriptor["Locator"][0]["URLString"].value
        assert url == locator_url(a_path.resolve())
        assert file_mob.descriptor["SampleRate"].value == SR
        tape_clip = file_mob.slot_at(1).segment.components[0]
        assert tape_clip.start == 36000 * SR  # original BWF timecode
    assert not (tmp_path / "out" / "reel1.aaf.partial").exists()


def test_out_of_range_and_bad_channel_are_reported(tmp_path, wav_factory):
    mf = read_wav(wav_factory("S.wav", seconds=1, time_reference=0))
    clips = [_matched(mf, name="S", record_in=F(0), duration=F(2), source_in=F(0), channel=3)]
    tl = Timeline("T", FrameRate.parse("24"), tracks=[Track("A1", clips)])
    res = write_aaf(tl, tmp_path / "t.aaf", SR)
    assert res.clips_written == 1
    assert any("excede" in w for w in res.warnings) and any("canal 3" in w for w in res.warnings)


def test_summary_is_plain_pcm_even_for_extensible_wav(tmp_path, wav_factory):
    """Pro Tools rejects 'AAF WAVE Data' when the Summary holds a WAVE_FORMAT_EXTENSIBLE fmt chunk."""
    mf = read_wav(wav_factory("ext.wav", seconds=1, channels=2, time_reference=0, extensible=True))
    assert mf.format_tag == 1 and mf.channels == 2
    clips = [_matched(mf, name="E", record_in=F(0), duration=F(1), source_in=F(0), channel=1)]
    tl = Timeline("T", FrameRate.parse("25"), tracks=[Track("A1", clips)])
    write_aaf(tl, tmp_path / "e.aaf", SR)
    with aaf2.open(str(tmp_path / "e.aaf"), "r") as f:
        (m,) = [m for m in f.content.sourcemobs() if type(m.descriptor).__name__ == "WAVEDescriptor"]
        summary = bytes(m.descriptor["Summary"].value)
    assert len(summary) == 36
    tag, channels, rate, avg, align, bits = struct.unpack("<HHIIHH", summary[20:36])
    assert (tag, channels, rate, avg, align, bits) == (1, 2, SR, SR * 6, 6, 24)
    assert struct.unpack("<I", summary[4:8])[0] == 28 and struct.unpack("<I", summary[16:20])[0] == 16


def test_locator_url_names_the_volume_first():
    """Pro Tools turns file:///Volumes/X/... into the HFS path 'Volumes:X:...' (a disk that
    does not exist) and drops the media offline; Avid-style URLs start with the volume name."""
    assert locator_url("/Volumes/MediaSSD/AAF EXP/Media/a_1.wav") == "file:///MediaSSD/AAF%20EXP/Media/a_1.wav"
    assert locator_url("/Users/me/Audio/a.wav", boot_volume="MacHD") == "file:///MacHD/Users/me/Audio/a.wav"
    assert locator_url("/Volumes/Data/é.wav") == "file:///Data/%C3%A9.wav"
