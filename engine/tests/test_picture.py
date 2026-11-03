from fractions import Fraction as F

from conform2aaf.media.riff import read_wav
from conform2aaf.model import Clip, Timeline, Track
from conform2aaf.picture import expand_to_channels
from conform2aaf.timecode import FrameRate

SR = 48000


def _clip(mf, name, rec, dur=F(2), src=F(36000)):
    c = Clip(name=name, record_in=F(rec), duration=dur, source_in=src)
    if mf is not None:
        c.media, c.match_status = mf, "matched"
    else:
        c.match_status = "missing"
    return c


def test_expand_makes_one_track_per_channel_named_from_ixml(wav_factory):
    poly = read_wav(wav_factory("poly.wav", seconds=3, channels=3, time_reference=36000 * SR,
                                track_names=["MIXDOWN L", "", "Boom 1"]))
    mono = read_wav(wav_factory("mono.wav", seconds=3, time_reference=36000 * SR))
    tl = Timeline("P", FrameRate.parse("25"), start=F(3600), picture=True, tracks=[Track("V", [
        _clip(poly, "cam1", 3600), _clip(mono, "cam2", 3602), _clip(None, "lost", 3604)])])
    skipped = expand_to_channels(tl)
    assert skipped == 1
    assert [t.name for t in tl.tracks] == ["1 MIXDOWN L", "2", "3 Boom 1"]
    ch1, ch2, ch3 = tl.tracks
    assert [(c.name, c.channel, c.record_in) for c in ch1.clips] == [("cam1", 1, F(3600)), ("cam2", 1, F(3602))]
    assert [(c.name, c.channel) for c in ch2.clips] == [("cam1", 2)]  # the mono file has no channel 2
    assert [(c.name, c.channel) for c in ch3.clips] == [("cam1", 3)]
    assert all(c.match_status == "matched" and c.media is not None for t in tl.tracks for c in t.clips)
    assert ch1.clips[0].duration == F(2) and ch1.clips[0].source_in == F(36000)


def test_expand_with_nothing_matched_leaves_no_tracks(wav_factory):
    tl = Timeline("P", FrameRate.parse("25"), picture=True, tracks=[Track("V", [_clip(None, "a", 0)])])
    assert expand_to_channels(tl) == 1 and tl.tracks == []


def test_overlapping_cuts_go_to_extra_tracks_instead_of_being_trimmed(wav_factory):
    mf = read_wav(wav_factory("two.wav", seconds=30, channels=2, time_reference=36000 * SR,
                              track_names=["MIXDOWN L", "MIXDOWN R"]))
    clips = [_clip(mf, "a", 3600, F(5)), _clip(mf, "b", 3602, F(5)), _clip(mf, "c", 3610, F(1))]  # b overlaps a
    tl = Timeline("P", FrameRate.parse("25"), picture=True, tracks=[Track("V1", clips)])
    assert expand_to_channels(tl) == 0
    assert [t.name for t in tl.tracks] == ["1 MIXDOWN L", "1 MIXDOWN L #2", "2 MIXDOWN R", "2 MIXDOWN R #2"]
    assert [c.name for c in tl.tracks[0].clips] == ["a", "c"] and [c.name for c in tl.tracks[1].clips] == ["b"]
    for t in tl.tracks:  # no overlaps inside any track
        assert all(x.record_out <= y.record_in for x, y in zip(t.clips, t.clips[1:]))
