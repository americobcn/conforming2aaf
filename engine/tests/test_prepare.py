import hashlib
import struct
from fractions import Fraction as F

import aaf2
import pytest

from conform2aaf.media.prepare import can_embed, prepare_media, split_wav
from conform2aaf.media.riff import read_chunks, read_wav
from conform2aaf.model import Clip, Timeline, Track
from conform2aaf.timecode import FrameRate
from conform2aaf.writers.aaf import write_aaf

SR = 48000


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _data(path):
    off, size = read_chunks(path)["data"]
    return path.read_bytes()[off : off + size]


def _clip(mf, channel=1, name="c", rec=0, dur=1, src=0):
    c = Clip(name=name, record_in=F(rec), duration=F(dur), source_in=F(src), channel=channel)
    c.media, c.match_status = mf, "matched"
    return c


def _timeline(*clips):
    return Timeline("T", FrameRate.parse("25"), tracks=[Track("A1", list(clips))])


@pytest.fixture
def poly(wav_factory):
    p = wav_factory(
        "poly.wav", seconds=0.01, channels=3, bits=24, time_reference=36000 * SR, fill=True,
        description="sSPEED=025", scene="12A", take="3", tape="D1",
        track_names=["Boom", "Lav1", "Lav2"], info={"INAM": "Take 3"},
    )
    return read_wav(p)


def test_split_wav_deinterleaves_and_keeps_metadata(tmp_path, poly):
    dest = tmp_path / "poly_2.wav"
    split_wav(poly, 2, dest)
    mono = read_wav(dest)
    assert (mono.channels, mono.bits, mono.sample_rate, mono.frames) == (1, 24, SR, poly.frames)
    expected = b"".join(bytes((2, f % 251, 7)) for f in range(poly.frames))
    assert _data(dest) == expected
    assert mono.time_reference == poly.time_reference and mono.start == poly.start
    assert (mono.description, mono.originator) == (poly.description, poly.originator)
    assert (mono.scene, mono.take, mono.tape) == ("12A", "3", "D1")
    assert mono.info == {"INAM": "Take 3"}
    assert mono.track_names == ["Lav1"]  # iXML keeps only this channel's track
    assert {"bext", "iXML", "LIST"} <= set(mono.chunks)


def test_split_wav_odd_data_size_is_padded(tmp_path, wav_factory):
    src = read_wav(wav_factory("odd3.wav", seconds=3.5 / SR, channels=2, bits=24, fill=True))
    assert src.frames == 3
    dest = tmp_path / "odd3_1.wav"
    split_wav(src, 1, dest)
    raw = dest.read_bytes()
    assert read_wav(dest).frames == 3
    assert len(raw) % 2 == 0
    assert struct.unpack("<I", raw[4:8])[0] == len(raw) - 8


def test_link_without_split_touches_nothing(tmp_path, poly):
    tl = _timeline(_clip(poly))
    out = tmp_path / "out" / "x.aaf"
    with prepare_media(tl, out, "link", split_mono=False) as res:
        assert res.media_dir is None and res.files == 0
    assert tl.tracks[0].clips[0].media is poly
    assert not (tmp_path / "out").exists()


def test_copy_is_bit_exact_and_dedupes_names(tmp_path, wav_factory):
    a = read_wav(wav_factory("d1/T001.wav", seconds=0.1, time_reference=SR))
    b = read_wav(wav_factory("d2/T001.wav", seconds=0.2, time_reference=2 * SR))
    tl = _timeline(_clip(a, name="a"), _clip(b, name="b", rec=1), _clip(a, name="a2", rec=2))
    out = tmp_path / "out" / "reel.aaf"
    with prepare_media(tl, out, "copy", split_mono=False) as res:
        assert res.media_dir == out.parent / "reel Media" and res.files == 2
        c1, c2, c3 = tl.tracks[0].clips
        assert c1.media.path.parent == res.media_dir
        assert sorted(p.name for p in res.media_dir.iterdir()) == ["T001 (2).wav", "T001.wav"]
        assert _sha(c1.media.path) == _sha(a.path) and _sha(c2.media.path) == _sha(b.path)
        assert c3.media.path == c1.media.path  # same source copied once
        assert c1.media.time_reference == SR


def test_split_only_used_channels(tmp_path, poly):
    tl = _timeline(_clip(poly, channel=1), _clip(poly, channel=3, rec=1))
    out = tmp_path / "reel.aaf"
    with prepare_media(tl, out, "link", split_mono=True) as res:
        assert sorted(p.name for p in res.media_dir.iterdir()) == ["poly_1.wav", "poly_3.wav"]
        c1, c3 = tl.tracks[0].clips
        assert (c1.channel, c3.channel) == (1, 1)
        assert c1.media.path.name == "poly_1.wav" and c3.media.track_names == ["Lav2"]
        assert res.files == 2 and res.bytes > 0


def test_mono_file_is_not_split(tmp_path, wav_factory):
    mono = read_wav(wav_factory("m.wav", seconds=0.1))
    tl = _timeline(_clip(mono))
    with prepare_media(tl, tmp_path / "r.aaf", "link", split_mono=True) as res:
        assert res.files == 0 and tl.tracks[0].clips[0].media is mono


def test_can_embed(wav_factory):
    assert can_embed(read_wav(wav_factory("a.wav", seconds=0.1, bits=24)))
    assert can_embed(read_wav(wav_factory("b.wav", seconds=0.1, bits=16)))
    assert not can_embed(read_wav(wav_factory("c.wav", seconds=0.1, bits=32)))
    assert not can_embed(read_wav(wav_factory("d.wav", seconds=0.1, rf64=True)))
    assert not can_embed(read_wav(wav_factory("e.wav", seconds=0.1, channels=2)))


def test_embed_uses_temp_dir_and_cleans_up(tmp_path, poly):
    tl = _timeline(_clip(poly, channel=2, dur=F(1, 200), src=36000))
    out = tmp_path / "out" / "reel.aaf"
    with prepare_media(tl, out, "embed", split_mono=True) as res:
        temp = tl.tracks[0].clips[0].media.path
        assert temp.exists() and res.media_dir != out.parent / "reel Media"
        write_aaf(tl, out, SR, embed=True)
    assert not temp.exists()
    assert not (out.parent / "reel Media").exists()
    with aaf2.open(str(out), "r") as f:
        (ed,) = list(f.content.essencedata)
        assert len(ed.open("r").read()) == poly.frames * 3
        (mm,) = list(f.content.mastermobs())
        assert mm.name == "poly_2" and mm.comments["Scene"] == "12A"
        file_mob = mm.slot_at(1).segment.components[0].mob
        assert type(file_mob.descriptor).__name__ == "PCMDescriptor"
        assert file_mob.descriptor["Channels"].value == 1
        tape_clip = file_mob.slot_at(1).segment
        assert tape_clip.start == 36000 * SR and tape_clip.mob.name == "poly_2.wav"  # BWF timecode survives


def test_embed_keeps_non_embeddable_linked(tmp_path, wav_factory):
    f32 = read_wav(wav_factory("w.wav", seconds=0.1, channels=2, bits=32, time_reference=0))
    tl = _timeline(_clip(f32, channel=2))
    out = tmp_path / "r.aaf"
    with prepare_media(tl, out, "embed", split_mono=True) as res:
        assert any("no se puede embeber" in w for w in res.warnings)
        assert tl.tracks[0].clips[0].media is f32 and tl.tracks[0].clips[0].channel == 2
        write_aaf(tl, out, SR, embed=True)
    with aaf2.open(str(out), "r") as f:
        assert list(f.content.essencedata) == []


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_warns_when_polyphonic_stays_multichannel(tmp_path, poly, mode):
    tl = _timeline(_clip(poly, channel=2), _clip(poly, channel=3, rec=1))
    with prepare_media(tl, tmp_path / "r.aaf", mode, split_mono=False) as res:
        (w,) = res.warnings  # once per file, not per clip
        assert "poly.wav" in w and "3 canales" in w and "mono" in w
    with prepare_media(tl, tmp_path / "r2.aaf", mode, split_mono=True) as res:
        assert res.warnings == []


# ---- every mono file needs its own identity: Pro Tools merges files that share a UMID ----
import re  # noqa: E402

UMID = bytes.fromhex("060a2b340101010501010f1013000000") + b"RXSL7648115335N\x06" + bytes(32)
REF = "AATON                 SL76480000"
UID = "AAT19BS0008202510111154056480001"


@pytest.fixture
def poly_id(wav_factory):
    return read_wav(wav_factory(
        "id.wav", seconds=0.01, channels=3, bits=24, time_reference=36000 * SR, fill=True,
        umid=UMID, originator_ref=REF, file_uid=UID, scene="12A", take="3", track_names=["L", "R", "Boom"],
        coding_history="A=PCM,F=48000,W=24,M=multi,R=48000,T=3 Ch\r\n",
    ))


def _bext(path):
    off, size = read_chunks(path)["bext"]
    b = path.read_bytes()[off : off + size]
    return {"ref": b[288:320], "umid": b[348:412], "tr": b[338:346], "hist": b[602:], "raw": b}


def _file_uid(path):
    off, size = read_chunks(path)["iXML"]
    return re.search(rb"<FILE_UID>([^<]*)<", path.read_bytes()[off : off + size]).group(1)


def test_split_files_get_distinct_identities(tmp_path, poly_id):
    outs = []
    for ch in (1, 2, 3):
        dest = tmp_path / f"id_{ch}.wav"
        split_wav(poly_id, ch, dest)
        outs.append(dest)
    fields = [_bext(p) for p in outs]
    assert len({f["umid"] for f in fields}) == 3 and UMID[:64] not in {f["umid"] for f in fields}
    assert len({f["ref"] for f in fields}) == 3
    assert len({_file_uid(p) for p in outs}) == 3
    assert [f["ref"].rstrip(b"\0")[-2:] for f in fields] == [b"01", b"02", b"03"]
    assert [_file_uid(p)[-2:] for p in outs] == [b"01", b"02", b"03"]
    for f in fields:  # the rest of the identity block and the timecode stay put
        assert f["umid"][:16] == UMID[:16] and f["umid"][32:] == UMID[32:]
        assert f["tr"] == struct.pack("<II", 36000 * SR, 0)
        assert f["ref"][:30] == REF.encode()[:30]
        assert b"M=mono" in f["hist"] and b"M=multi" not in f["hist"]


def test_split_identity_is_deterministic(tmp_path, poly_id):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    split_wav(poly_id, 2, a)
    split_wav(poly_id, 2, b)
    assert _bext(a)["raw"] == _bext(b)["raw"] and _file_uid(a) == _file_uid(b)


def test_split_leaves_zero_umid_and_version0_bext_alone(tmp_path, wav_factory):
    plain = read_wav(wav_factory("p.wav", seconds=0.01, channels=2, time_reference=5, fill=True))
    v0 = read_wav(wav_factory("v0.wav", seconds=0.01, channels=2, time_reference=5, fill=True,
                              umid=UMID, bext_version=0))
    for mf in (plain, v0):
        dest = tmp_path / f"{mf.stem}_1.wav"
        split_wav(mf, 1, dest)
        assert _bext(dest)["umid"] == _bext(mf.path)["umid"]
        assert _bext(dest)["tr"] == _bext(mf.path)["tr"]


# ---- 32-bit float sources: Pro Tools crashes on them, so they are converted to PCM 24 bit ----
def _float_samples(frames, channels):  # exactly representable in 24 bit: (c+1)*(1+f%3)/16
    return [(c + 1) * (1 + f % 3) / 16 for f in range(frames) for c in range(channels)]


def _expected24(frames, channel):  # channel is 1-based
    return [channel * (1 + f % 3) * 2**19 for f in range(frames)]


def _data_ints(path):
    off, size = read_chunks(path)["data"]
    raw = path.read_bytes()[off : off + size]
    return [int.from_bytes(raw[i : i + 3], "little", signed=True) for i in range(0, len(raw), 3)]


@pytest.fixture
def poly_f(wav_factory):
    return read_wav(wav_factory(
        "fp.wav", channels=3, float_data=_float_samples(300, 3), time_reference=36000 * SR,
        umid=UMID, originator_ref=REF, file_uid=UID, scene="12A", take="3", track_names=["L", "R", "Boom"],
        ixml_extra="<SPEED><AUDIO_BIT_DEPTH>32</AUDIO_BIT_DEPTH></SPEED>",
        coding_history="A=PCM,F=48000,W=32,M=multi,R=48000,T=3 Ch\r\n",
    ))


def test_split_float_converts_to_pcm24_and_updates_metadata(tmp_path, poly_f, audioconv_env):
    assert poly_f.format_tag == 3 and poly_f.bits == 32
    dest = tmp_path / "fp_2.wav"
    stats = split_wav(poly_f, 2, dest)
    mf = read_wav(dest)
    assert (mf.format_tag, mf.bits, mf.channels, mf.block_align, mf.frames) == (1, 24, 1, 3, 300)
    assert _data_ints(dest) == _expected24(300, 2)
    assert stats.clipped == 0
    off, size = read_chunks(dest)["iXML"]
    assert b"<AUDIO_BIT_DEPTH>24<" in dest.read_bytes()[off : off + size]
    assert b"W=24" in _bext(dest)["hist"] and b"W=32" not in _bext(dest)["hist"]
    assert _bext(dest)["umid"][:16] == UMID[:16] and _bext(dest)["umid"] != UMID[:64]  # identity per channel kept
    assert mf.scene == "12A" and mf.time_reference == poly_f.time_reference and mf.track_names == ["R"]


def test_split_pcm24_is_untouched_by_conversion(tmp_path, poly_id):
    stats = split_wav(poly_id, 1, tmp_path / "id_1.wav")
    assert stats is None  # no conversion needed: pure Python path


def test_copy_converts_a_mono_float_file(tmp_path, wav_factory, audioconv_env):
    mono = read_wav(wav_factory("m.wav", float_data=_float_samples(100, 1), time_reference=SR))
    tl = _timeline(_clip(mono, src=1, dur=F(1, 1000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False) as res:
        c = tl.tracks[0].clips[0]
        assert (c.media.format_tag, c.media.bits, c.media.channels) == (1, 24, 1)
        assert _data_ints(c.media.path) == _expected24(100, 1) and c.channel == 1
        assert res.files == 1 and res.warnings == []
        assert c.media.time_reference == SR


def test_link_with_split_still_rewrites_a_mono_float_file(tmp_path, wav_factory, audioconv_env):
    mono = read_wav(wav_factory("m.wav", float_data=_float_samples(100, 1), time_reference=SR))
    tl = _timeline(_clip(mono, src=1, dur=F(1, 1000)))
    with prepare_media(tl, tmp_path / "r.aaf", "link", split_mono=True) as res:
        assert res.media_dir is not None and tl.tracks[0].clips[0].media.bits == 24


def test_link_without_split_warns_about_float(tmp_path, wav_factory):
    mono = read_wav(wav_factory("m.wav", float_data=_float_samples(100, 1), time_reference=SR))
    tl = _timeline(_clip(mono, src=1, dur=F(1, 1000)))
    with prepare_media(tl, tmp_path / "r.aaf", "link", split_mono=False) as res:
        assert tl.tracks[0].clips[0].media is mono
        (w,) = res.warnings
        assert "coma flotante" in w and "Pro Tools" in w


def test_clipped_samples_are_reported_when_peak_control_is_off(tmp_path, wav_factory, audioconv_env):
    hot = read_wav(wav_factory("hot.wav", float_data=[0.1, 1.5, -2.0, 0.2], time_reference=0))
    tl = _timeline(_clip(hot, src=0, dur=F(1, 12000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False, peak_ceiling_db=None) as res:
        (w,) = res.warnings
        assert "2 muestras" in w and "recortad" in w and "hot.wav" in w


def test_hot_channel_is_lowered_so_it_does_not_clip(tmp_path, wav_factory, audioconv_env):
    import math

    hot = read_wav(wav_factory("hot.wav", float_data=[0.1, 4.0, -2.0, 0.2], time_reference=0, track_names=["X"]))
    tl = _timeline(_clip(hot, src=0, dur=F(1, 12000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False, max_reduction_db=None) as res:
        mf = tl.tracks[0].clips[0].media
        gain = -1.0 - 20 * math.log10(4.0)  # the peak lands on -1 dBFS
        assert mf.applied_gain_db == pytest.approx(gain, abs=1e-6)
        ints = _data_ints(mf.path)
        assert max(abs(v) for v in ints) == pytest.approx(10 ** (-1 / 20) * 8388608, abs=2)
        assert ints[0] == pytest.approx(0.1 * 10 ** (gain / 20) * 8388608, abs=2)  # the whole file is scaled
        (w,) = res.warnings
        assert "reducido 13.0 dB" in w and "+12.0 dBFS" in w and "hot.wav" in w
        off, size = read_chunks(mf.path)["iXML"]
        note = mf.path.read_bytes()[off : off + size]
        assert b"<GAIN_DB>-13.04<" in note and b"<SOURCE_PEAK_DBFS>12.04<" in note


def test_only_the_channels_that_clip_are_lowered(tmp_path, wav_factory, audioconv_env):
    # ch1 peaks at 0.5, ch2 at 3.0: only channel 2 must change
    two = read_wav(wav_factory("two.wav", channels=2, float_data=[0.5, 3.0, 0.25, -1.5] * 25, time_reference=0,
                               track_names=["A", "B"], ixml_extra="<SPEED><AUDIO_BIT_DEPTH>32</AUDIO_BIT_DEPTH></SPEED>"))
    tl = _timeline(_clip(two, channel=1, src=0, dur=F(1, 1000)), _clip(two, channel=2, name="b", rec=1, src=0, dur=F(1, 1000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=True, max_reduction_db=None) as res:
        c1, c2 = tl.tracks[0].clips
        assert c1.media.applied_gain_db == 0.0 and c2.media.applied_gain_db < -9
        assert _data_ints(c1.media.path)[0] == 4194304  # 0.5 untouched
        assert len(res.warnings) == 1 and "two_2.wav" in res.warnings[0]


def test_reduction_is_limited_to_6_db_and_the_rest_clips(tmp_path, wav_factory, audioconv_env):
    glitch = read_wav(wav_factory("glitch.wav", float_data=[0.2, 40.0, -0.3, 0.1], time_reference=0, track_names=["X"]))
    tl = _timeline(_clip(glitch, src=0, dur=F(1, 12000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False) as res:  # default limit: 6 dB
        mf = tl.tracks[0].clips[0].media
        assert mf.applied_gain_db == pytest.approx(-6.0)
        ints = _data_ints(mf.path)
        assert ints[0] == pytest.approx(0.2 * 10 ** (-6 / 20) * 8388608, abs=2)  # the music is only 6 dB lower
        assert ints[1] == 8388607  # the glitch clips
        (w,) = res.warnings
        assert "reducido 6.0 dB" in w and "límite" in w and "+32.0 dBFS" in w and "1 muestras recortadas" in w


def test_reduction_under_the_limit_is_applied_in_full(tmp_path, wav_factory, audioconv_env):
    mild = read_wav(wav_factory("mild.wav", float_data=[0.2, 1.5, -0.3, 0.1], time_reference=0, track_names=["X"]))
    tl = _timeline(_clip(mild, src=0, dur=F(1, 12000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False) as res:
        assert tl.tracks[0].clips[0].media.applied_gain_db == pytest.approx(-1.0 - 20 * __import__("math").log10(1.5))
        (w,) = res.warnings
        assert "límite" not in w and "recortad" not in w


def test_clean_float_file_is_not_touched(tmp_path, wav_factory, audioconv_env):
    ok = read_wav(wav_factory("ok.wav", float_data=[0.1, 0.5, -0.9, 0.2], time_reference=0))
    tl = _timeline(_clip(ok, src=0, dur=F(1, 12000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False) as res:
        assert tl.tracks[0].clips[0].media.applied_gain_db == 0.0 and res.warnings == []


def test_embed_converts_float_then_embeds(tmp_path, wav_factory, audioconv_env):
    mono = read_wav(wav_factory("e.wav", float_data=_float_samples(480, 1), time_reference=0))
    tl = _timeline(_clip(mono, src=0, dur=F(1, 100)))
    out = tmp_path / "e.aaf"
    with prepare_media(tl, out, "embed", split_mono=True) as res:
        assert res.warnings == []
        write_aaf(tl, out, SR, embed=True)
    with aaf2.open(str(out), "r") as f:
        assert len(list(f.content.essencedata)) == 1


def test_copy_of_polyphonic_float_without_split_keeps_all_channels(tmp_path, poly_f, audioconv_env):
    tl = _timeline(_clip(poly_f, channel=1, src=36000, dur=F(1, 1000)))
    with prepare_media(tl, tmp_path / "r.aaf", "copy", split_mono=False) as res:
        mf = tl.tracks[0].clips[0].media
        assert (mf.format_tag, mf.bits, mf.channels) == (1, 24, 3)
        assert len(_data_ints(mf.path)) == 300 * 3
