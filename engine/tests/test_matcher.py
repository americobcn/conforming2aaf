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


# ---- picture lists: camera names never match production names -> TC and metadata decide ----
from conform2aaf.media.matcher import normalize_id  # noqa: E402
from conform2aaf.timecode import FrameRate  # noqa: E402

R25 = FrameRate.parse("25")


def pclip(source_in, dur=F(2), scene="", take="", tape="", reel="", name="A001C002"):
    return Clip(name=name, record_in=F(0), duration=dur, source_in=source_in, reel=reel,
                scene=scene, take=take, tape=tape)


def test_normalize_id():
    assert normalize_id("5 12") == normalize_id("5/12") == normalize_id("05-12") == "5-12"
    assert normalize_id("12A") == normalize_id("012a")
    assert normalize_id("1 12") != normalize_id("11 2")
    assert normalize_id("  ") == ""


def test_picture_clip_matches_by_tc_only(tmp_path, wav_factory):
    wav_factory("SL1.wav", seconds=10, time_reference=H10 * SR)
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 3))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "SL1" and c.match_note == "Enlazado por TC"


def test_scene_take_breaks_a_tc_tie(tmp_path, wav_factory):
    wav_factory("t1.wav", seconds=10, time_reference=H10 * SR, scene="5 12", take="3")
    wav_factory("t2.wav", seconds=10, time_reference=H10 * SR, scene="5 12", take="4")
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 1), scene="05/12", take="4")
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "t2"
    assert "escena/toma" in c.match_note


def test_tape_breaks_a_tc_tie_scene_take_still_ambiguous_without_metadata(tmp_path, wav_factory):
    wav_factory("a.wav", seconds=10, time_reference=H10 * SR, tape="1111")
    wav_factory("b.wav", seconds=10, time_reference=H10 * SR, tape="1113")
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 1), tape="1113")
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "b"
    c2 = pclip(F(H10 + 1))
    Matcher(files).match_clip(c2, R25)
    assert c2.match_status == "ambiguous" and len(c2.candidates) == 2


def test_tc_matches_but_scene_take_differ_is_ambiguous(tmp_path, wav_factory):
    wav_factory("only.wav", seconds=10, time_reference=H10 * SR, scene="5", take="3")
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 1), scene="5", take="2")
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "ambiguous" and c.media is None
    assert "escena/toma" in c.match_note and "5/2" in c.match_note and "5/3" in c.match_note
    assert [f.stem for f in c.candidates] == ["only"]


def test_camera_reel_never_conflicts_with_sound_tape(tmp_path, wav_factory):
    wav_factory("only.wav", seconds=10, time_reference=H10 * SR, tape="1113")
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 1), reel="A001")
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched"


def test_partial_overlap_matches_and_reports_missing_frames(tmp_path, wav_factory):
    wav_factory("late.wav", seconds=4, time_reference=(H10 + 5) * SR)  # sound starts 5 s .. 9 s
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 4), dur=F(3))  # clip 4 s .. 7 s: 1 s (25 frames) missing at the start
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and "faltan 25 fotogramas al principio" in c.match_note
    d = pclip(F(H10 + 8), dur=F(3))  # 8 s .. 11 s: 2 s (50 frames) missing at the end
    Matcher(files).match_clip(d, R25)
    assert d.match_status == "matched" and "faltan 50 fotogramas al final" in d.match_note


def test_no_overlap_is_missing(tmp_path, wav_factory):
    wav_factory("x.wav", seconds=2, time_reference=H10 * SR)
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 100))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "missing"


def test_full_coverage_preferred_over_partial(tmp_path, wav_factory):
    wav_factory("full.wav", seconds=10, time_reference=H10 * SR)
    wav_factory("tail.wav", seconds=10, time_reference=(H10 + 9) * SR)
    files, _ = scan([tmp_path])
    c = pclip(F(H10 + 8), dur=F(2))  # 8..10 s: inside full.wav, 1 s inside tail.wav
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "full"


def test_without_tc_scene_take_matches(tmp_path, wav_factory):
    wav_factory("a.wav", seconds=1, scene="7", take="1")
    wav_factory("b.wav", seconds=1, scene="7", take="2")
    files, _ = scan([tmp_path])
    c = Clip(name="CAM", record_in=F(0), duration=F(1), scene="07", take="2")
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "b" and "escena/toma" in c.match_note
    c2 = Clip(name="CAM", record_in=F(0), duration=F(1), scene="7")
    Matcher(files).match_clip(c2, R25)
    assert c2.match_status == "ambiguous" and len(c2.candidates) == 2


# ---- the clip name carries the shooting date (A001C012_261009_RNU8): it separates days with the same TC ----
def dclip(name, source_in, dur=F(2)):
    return Clip(name=name, record_in=F(0), duration=dur, source_in=source_in)


def test_date_in_the_clip_name_separates_two_days_with_the_same_tc(tmp_path, wav_factory):
    wav_factory("d1/1-007.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-09")
    wav_factory("d3/3-003.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-11")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.media.stem == "1-007" and c.match_note == "Enlazado por TC y fecha"
    c2 = dclip("A006C009_261011_RNU8.mov - Merged", F(H10 + 1))
    Matcher(files).match_clip(c2, R25)
    assert c2.match_status == "matched" and c2.media.stem == "3-003"


def test_same_day_candidates_stay_ambiguous(tmp_path, wav_factory):
    wav_factory("a.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-09")
    wav_factory("b.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-09")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "ambiguous" and len(c.candidates) == 2


def test_candidates_from_other_days_are_discarded(tmp_path, wav_factory):
    wav_factory("a.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-11")
    wav_factory("b.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-12")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "missing" and c.media is None and c.candidates == []
    assert "otra fecha" in c.match_note and "2026-10-09" in c.match_note and "2026-10-11" in c.match_note


def test_a_single_tc_candidate_from_another_day_is_discarded_not_linked(tmp_path, wav_factory):
    wav_factory("only.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-15")
    files, _ = scan([tmp_path])
    c = dclip("A003C026_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "missing" and "otra fecha" in c.match_note


def test_one_day_off_is_discarded_too(tmp_path, wav_factory):
    wav_factory("only.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-10")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "missing" and c.media is None and c.candidates == []
    assert "otra fecha" in c.match_note and "2026-10-09" in c.match_note and "2026-10-10" in c.match_note


def test_same_name_on_another_day_is_ambiguous_not_discarded(tmp_path, wav_factory):
    wav_factory("A001C012_261009_RNU8.wav", seconds=10, time_reference=H10 * SR, origination_date="2026-10-15")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8", F(H10 + 1))  # same stem as the file: matched by name
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "ambiguous" and "fecha difiere" in c.match_note  # the name equals: the user decides


def test_missing_date_on_either_side_changes_nothing(tmp_path, wav_factory):
    wav_factory("nodate.wav", seconds=10, time_reference=H10 * SR, origination_date="")
    files, _ = scan([tmp_path])
    c = dclip("A001C012_261009_RNU8.mov", F(H10 + 1))
    Matcher(files).match_clip(c, R25)
    assert c.match_status == "matched" and c.match_note == "Enlazado por TC"
    d = dclip("CAM_WITHOUT_DATE", F(H10 + 1))
    Matcher(files).match_clip(d, R25)
    assert d.match_status == "matched"
