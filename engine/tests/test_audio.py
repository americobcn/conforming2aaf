import io
import struct

import pytest

from conform2aaf.media.audio import convert_pcm24, measure_peak

SR = 48000


def _ints(raw: bytes) -> list[int]:
    return [int.from_bytes(raw[i : i + 3], "little", signed=True) for i in range(0, len(raw), 3)]


def test_float_to_pcm24_uses_the_24_bit_range_and_counts_clipping(wav_factory, audioconv_env):
    samples = [0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 0.25]
    p = wav_factory("f.wav", float_data=samples, time_reference=0)
    out = io.BytesIO()
    stats = convert_pcm24(p, 1, out)
    assert _ints(out.getvalue()) == [0, 4194304, -4194304, 8388607, -8388608, 8388607, -8388608, 2097152]
    assert (stats.frames, stats.channels, stats.clipped) == (8, 1, 2) and stats.peak == pytest.approx(1.5)


def test_channel_selection_and_interleaved_output(wav_factory, audioconv_env):
    # two channels, 3 frames: ch1 = 0.5, 0.25, 0.125 ; ch2 = -0.5, -0.25, -0.125
    p = wav_factory("s.wav", channels=2, float_data=[0.5, -0.5, 0.25, -0.25, 0.125, -0.125], time_reference=0)
    ch2 = io.BytesIO()
    assert convert_pcm24(p, 2, ch2).channels == 1
    assert _ints(ch2.getvalue()) == [-4194304, -2097152, -1048576]
    both = io.BytesIO()
    stats = convert_pcm24(p, 0, both)
    assert stats.channels == 2 and _ints(both.getvalue()) == [4194304, -4194304, 2097152, -2097152, 1048576, -1048576]


def test_converts_24_bit_pcm_sources_too(wav_factory, audioconv_env):
    p = wav_factory("pcm.wav", seconds=0.001, bits=24, fill=True, time_reference=0)
    out = io.BytesIO()
    convert_pcm24(p, 1, out)
    expected = b"".join(bytes((1, f % 251, 7)) for f in range(48))
    assert out.getvalue() == expected  # same bytes: 24-bit in, 24-bit out


def test_errors_are_reported(tmp_path, audioconv_env):
    with pytest.raises(RuntimeError, match="audioconv"):
        convert_pcm24(tmp_path / "missing.wav", 1, io.BytesIO())


def test_gain_is_applied_before_the_conversion(wav_factory, audioconv_env):
    p = wav_factory("g.wav", float_data=[1.0, -1.0, 5.0, 0.5], time_reference=0)
    out = io.BytesIO()
    stats = convert_pcm24(p, 1, out, gain_db=-20.0)  # x0.1
    expected = [round(v * 0.1 * 8388608) for v in (1.0, -1.0, 5.0, 0.5)]
    assert all(abs(a - b) <= 1 for a, b in zip(_ints(out.getvalue()), expected))
    assert stats.peak == pytest.approx(5.0) and stats.clipped == 0  # peak is the source's; nothing clips after -20 dB
    assert convert_pcm24(p, 1, io.BytesIO()).clipped == 1  # without gain the 5.0 clips


def test_measure_peak_does_not_need_an_output(wav_factory, audioconv_env):
    p = wav_factory("m.wav", channels=2, float_data=[0.25, -3.0, 0.5, 0.1], time_reference=0)
    assert measure_peak(p, 1).peak == pytest.approx(0.5)
    assert measure_peak(p, 2).peak == pytest.approx(3.0)
    assert measure_peak(p, 0).peak == pytest.approx(3.0)  # all channels: the overall peak
