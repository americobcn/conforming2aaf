from fractions import Fraction as F

from conform2aaf.media.matcher import Matcher
from conform2aaf.media.scanner import scan
from conform2aaf.model import Clip

SR = 48000
H10 = 10 * 3600


def clip(name="", source_in=None, dur=F(1, 2), reel="", hint=""):
    return Clip(name=name, record_in=F(0), duration=dur, source_in=source_in, reel=reel, file_hint=hint)


def test_scan_recursive_and_skips_junk(tmp_path, wav_factory):
    wav_factory("day1/a.wav")
    wav_factory("day1/sub/b.WAV")
    (tmp_path / "day1/notes.txt").write_text("x")
    (tmp_path / "day1/._a.wav").write_bytes(b"junk")
    (tmp_path / "day1/broken.wav").write_bytes(b"junk")
    files, warnings = scan([tmp_path / "day1", tmp_path / "missing"])
    assert sorted(f.stem for f in files) == ["a", "b"]
    assert any("broken.wav" in w for w in warnings)
    assert any("missing" in w for w in warnings)
    flat, _ = scan([tmp_path / "day1"], recursive=False)
    assert [f.stem for f in flat] == ["a"]


def test_name_and_tc(tmp_path, wav_factory):
    wav_factory("12A_T3.wav", seconds=10, time_reference=H10 * SR)
    files, _ = scan([tmp_path])
    c = clip(hint="C:\\media\\12A_T3.WAV", source_in=F(H10 + 2))
    Matcher(files).match_clip(c)
    assert c.match_status == "matched" and c.media.stem == "12A_T3" and c.match_note == ""


def test_name_only_without_camera_tc(tmp_path, wav_factory):
    wav_factory("wild.wav", seconds=2)
    files, _ = scan([tmp_path])
    c = clip(name="WILD")
    Matcher(files).match_clip(c)
    assert c.match_status == "matched" and "sin TC" in c.match_note


def test_duplicate_names_resolved_by_tc(tmp_path, wav_factory):
    wav_factory("day1/T001.wav", seconds=10, time_reference=H10 * SR)
    wav_factory("day2/T001.wav", seconds=10, time_reference=(H10 + 3600) * SR)
    files, _ = scan([tmp_path])
    c = clip(name="T001", source_in=F(H10 + 3600 + 5))
    Matcher(files).match_clip(c)
    assert c.match_status == "matched" and c.media.path.parent.name == "day2"


def test_duplicate_names_without_tc_is_ambiguous(tmp_path, wav_factory):
    wav_factory("day1/T001.wav")
    wav_factory("day2/T001.wav")
    files, _ = scan([tmp_path])
    c = clip(name="T001")
    Matcher(files).match_clip(c)
    assert c.match_status == "ambiguous" and len(c.candidates) == 2 and c.media is None


def test_tc_only_with_tape_tiebreak(tmp_path, wav_factory):
    wav_factory("x1.wav", seconds=10, time_reference=H10 * SR, tape="DAY01")
    wav_factory("x2.wav", seconds=10, time_reference=H10 * SR, tape="DAY02")
    files, _ = scan([tmp_path])
    c = clip(name="unknown", reel="DAY02", source_in=F(H10 + 1))
    Matcher(files).match_clip(c)
    assert c.match_status == "matched" and c.media.stem == "x2"
    c2 = clip(name="unknown", source_in=F(H10 + 1))
    Matcher(files).match_clip(c2)
    assert c2.match_status == "ambiguous"


def test_name_match_tc_out_of_range(tmp_path, wav_factory):
    wav_factory("A.wav", seconds=1, time_reference=H10 * SR)
    files, _ = scan([tmp_path])
    c = clip(name="A", source_in=F(H10 + 50))
    Matcher(files).match_clip(c)
    assert c.match_status == "ambiguous"


def test_missing(tmp_path, wav_factory):
    wav_factory("A.wav")
    files, _ = scan([tmp_path])
    c = clip(name="nothing", source_in=F(5))
    Matcher(files).match_clip(c)
    assert c.match_status == "missing"
