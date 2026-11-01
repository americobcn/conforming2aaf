from fractions import Fraction

import pytest

from conform2aaf.media.riff import NotAWav, read_wav


def test_reads_bwf_ixml_and_info(wav_factory):
    tr = 10 * 3600 * 48000  # 10:00:00:00
    p = wav_factory(
        "12A_T3.wav",
        seconds=0.5,
        channels=2,
        time_reference=tr,
        description="sSPEED=023.976-ND",
        scene="12A",
        take="3",
        tape="DAY01",
        track_names=["Boom", "Lav1"],
        info={"INAM": "Take 3", "ICMT": "good"},
    )
    mf = read_wav(p)
    assert (mf.sample_rate, mf.channels, mf.bits, mf.frames) == (48000, 2, 24, 24000)
    assert mf.time_reference == tr
    assert mf.start == Fraction(36000)
    assert mf.description == "sSPEED=023.976-ND"
    assert mf.originator == "TestRecorder"
    assert (mf.scene, mf.take, mf.tape, mf.project) == ("12A", "3", "DAY01", "TestProj")
    assert mf.track_names == ["Boom", "Lav1"]
    assert mf.info == {"INAM": "Take 3", "ICMT": "good"}
    assert {"fmt ", "bext", "iXML", "LIST", "data"} <= set(mf.chunks)


def test_plain_wav_without_metadata(wav_factory):
    mf = read_wav(wav_factory("plain.wav", seconds=0.25, bits=16))
    assert mf.time_reference is None and mf.start is None
    assert mf.frames == 12000 and mf.bits == 16


def test_rf64(wav_factory):
    mf = read_wav(wav_factory("big.wav", seconds=0.1, rf64=True, time_reference=48000))
    assert mf.frames == 4800
    assert mf.time_reference == 48000


def test_not_a_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"hello world, not riff")
    with pytest.raises(NotAWav):
        read_wav(p)
