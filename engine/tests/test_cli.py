import json
import subprocess
import sys

import aaf2

from conform2aaf.writers.aaf import locator_url

SR = 48000

EDL = """TITLE: CLI TEST
FCM: NON-DROP FRAME

001  12A_T3   A     C        10:00:01:00 10:00:03:00 01:00:00:00 01:00:02:00
* FROM CLIP NAME: 12A_T3
002  T001     A     C        11:00:01:00 11:00:02:00 01:00:02:00 01:00:03:00
003  NOPE     A     C        00:00:00:00 00:00:01:00 01:00:03:00 01:00:04:00
"""


def run(*args):
    p = subprocess.run([sys.executable, "-m", "conform2aaf", *map(str, args)],
                       capture_output=True, text=True)
    events = [json.loads(line) for line in p.stdout.splitlines()]
    return p.returncode, events


def _setup(tmp_path, wav_factory):
    wav_factory("media/12A_T3.wav", seconds=5, time_reference=36000 * SR, scene="12A")
    wav_factory("media/d1/T001.wav", seconds=5, time_reference=39600 * SR)
    wav_factory("media/d2/T001.wav", seconds=5, time_reference=39600 * SR)
    edl = tmp_path / "r1.edl"
    edl.write_text(EDL)
    return edl, tmp_path / "media"


def test_inspect_reports_matches(tmp_path, wav_factory):
    edl, media = _setup(tmp_path, wav_factory)
    code, events = run("inspect", edl, "--media", media, "--fps", "25")
    assert code == 0
    assert [e["stage"] for e in events if e["type"] == "progress"] == ["read", "scan", "match"]
    (rep,) = [e for e in events if e["type"] == "report"]
    assert rep["timeline"]["start_tc"] == "01:00:00:00" and rep["timeline"]["rate"] == "25"
    assert rep["counts"] == {"matched": 1, "ambiguous": 1, "missing": 1}
    first = rep["clips"][0]
    assert first["id"] == "0:0" and first["source_in"] == "10:00:01:00" and first["status"] == "matched"
    assert len(rep["clips"][1]["candidates"]) == 2


def test_convert_with_manual_choice(tmp_path, wav_factory):
    edl, media = _setup(tmp_path, wav_factory)
    out = tmp_path / "r1.aaf"
    code, events = run("convert", edl, "--media", media, "--fps", "25", "--out", out,
                       "--choose", f"0:1={media / 'd2' / 'T001.wav'}")
    assert code == 0, events
    (res,) = [e for e in events if e["type"] == "result"]
    assert (res["clips_written"], res["clips_skipped"]) == (2, 1)
    with aaf2.open(str(out), "r") as f:
        names = sorted(m.name for m in f.content.mastermobs())
        assert names == ["12A_T3", "T001"]


def test_errors_are_json(tmp_path):
    bad = tmp_path / "x.edl"
    bad.write_text("TITLE: X\n")
    code, events = run("inspect", bad)
    assert code == 1 and events[-1]["type"] == "error" and "frecuencia" in events[-1]["message"]


def _poly_setup(tmp_path, wav_factory):
    wav_factory("media/poly.wav", seconds=5, channels=2, time_reference=36000 * SR, scene="12A",
                track_names=["Boom", "Lav"])
    edl = tmp_path / "p.edl"
    edl.write_text(
        "TITLE: POLY\nFCM: NON-DROP FRAME\n"
        "001  poly  A1  C  10:00:01:00 10:00:02:00 01:00:00:00 01:00:01:00\n"
        "002  poly  A2  C  10:00:01:00 10:00:02:00 01:00:00:00 01:00:01:00\n"
    )
    return edl, tmp_path / "media"


def test_convert_copy_and_split_mono(tmp_path, wav_factory):
    edl, media = _poly_setup(tmp_path, wav_factory)
    out = tmp_path / "out" / "poly.aaf"
    code, events = run("convert", edl, "--media", media, "--fps", "25", "--out", out,
                       "--media-mode", "copy", "--split-mono")
    assert code == 0, events
    (res,) = [e for e in events if e["type"] == "result"]
    folder = tmp_path / "out" / "poly Media"
    assert res["media_dir"] == str(folder) and res["media_files"] == 2 and res["media_bytes"] > 0
    assert sorted(p.name for p in folder.iterdir()) == ["poly_1.wav", "poly_2.wav"]
    with aaf2.open(str(out), "r") as f:
        urls = sorted(m.descriptor["Locator"][0]["URLString"].value
                      for m in f.content.sourcemobs() if type(m.descriptor).__name__ == "WAVEDescriptor")
    assert urls == sorted(locator_url((folder / n).resolve()) for n in ("poly_1.wav", "poly_2.wav"))


def test_convert_embed(tmp_path, wav_factory):
    edl, media = _poly_setup(tmp_path, wav_factory)
    out = tmp_path / "poly.aaf"
    code, events = run("convert", edl, "--media", media, "--fps", "25", "--out", out, "--media-mode", "embed")
    assert code == 0, events
    (res,) = [e for e in events if e["type"] == "result"]
    assert res["media_dir"] is None and res["media_files"] == 2 and res["media_bytes"] > 0
    assert not (tmp_path / "poly Media").exists()
    with aaf2.open(str(out), "r") as f:
        assert len(list(f.content.essencedata)) == 2


def _picture_setup(tmp_path, wav_factory):
    names = ["MIXDOWN L", "MIXDOWN R", "Boom 1"]
    wav_factory("media/SL1.wav", seconds=6, channels=3, time_reference=36000 * SR, scene="5 12", take="3", track_names=names)
    wav_factory("media/SL2.wav", seconds=6, channels=3, time_reference=36000 * SR, scene="5 12", take="4", track_names=names)
    edl = tmp_path / "pic.edl"
    edl.write_text(
        "TITLE: PIC\nFCM: NON-DROP FRAME\n\n"
        "001  A001C002  V  C  10:00:01:00 10:00:03:00 01:00:00:00 01:00:02:00\n"
        "* FROM CLIP NAME: A001_C002.mov\n* SCENE: 05/12\n* TAKE: 4\n\n"
        "002  A001C009  V  C  15:00:00:00 15:00:01:00 01:00:02:00 01:00:03:00\n"
    )
    return edl, tmp_path / "media"


def test_picture_list_is_detected_and_matched_by_tc_and_take(tmp_path, wav_factory):
    edl, media = _picture_setup(tmp_path, wav_factory)
    code, events = run("inspect", edl, "--media", media, "--fps", "25")
    assert code == 0, events
    (rep,) = [e for e in events if e["type"] == "report"]
    assert rep["timeline"]["picture"] is True
    assert rep["counts"] == {"matched": 1, "ambiguous": 0, "missing": 1}
    first = rep["clips"][0]
    assert first["file"].endswith("SL2.wav") and (first["scene"], first["take"]) == ("05/12", "4")
    assert any("Lista de imagen" in e["message"] for e in events if e["type"] == "warning")


def test_picture_off_reads_no_clips(tmp_path, wav_factory):
    edl, media = _picture_setup(tmp_path, wav_factory)
    code, events = run("inspect", edl, "--media", media, "--fps", "25", "--picture", "off")
    (rep,) = [e for e in events if e["type"] == "report"]
    assert rep["timeline"]["picture"] is False and rep["clips"] == []


def test_convert_picture_list_writes_one_track_per_channel(tmp_path, wav_factory):
    edl, media = _picture_setup(tmp_path, wav_factory)
    out = tmp_path / "out" / "pic.aaf"
    code, events = run("convert", edl, "--media", media, "--fps", "25", "--out", out,
                       "--media-mode", "copy", "--split-mono")
    assert code == 0, events
    (res,) = [e for e in events if e["type"] == "result"]
    assert (res["clips_written"], res["clips_skipped"]) == (3, 1)  # 3 channels; the unmatched cut is counted
    assert res["media_files"] == 3
    with aaf2.open(str(out), "r") as f:
        comp = next(f.content.compositionmobs())
        assert [s.name for s in comp.slots if s.media_kind == "Sound"] == ["1 MIXDOWN L", "2 MIXDOWN R", "3 Boom 1"]
        assert sorted(m.name for m in f.content.mastermobs()) == ["SL2_1", "SL2_2", "SL2_3"]


def test_convert_float_lowers_hot_channels_unless_peak_control_is_off(tmp_path, wav_factory, audioconv_env):
    samples = [0.1, 4.0] * 24000  # 1 s mono float, peak 4.0 (+12 dBFS)
    wav_factory("media/hot.wav", float_data=samples, time_reference=36000 * SR, track_names=["MixL"])
    edl = tmp_path / "h.edl"
    edl.write_text("TITLE: H\nFCM: NON-DROP FRAME\n001  hot  A  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n")
    base = ["convert", edl, "--media", tmp_path / "media", "--fps", "25", "--media-mode", "copy"]
    code, events = run(*base, "--out", tmp_path / "a" / "h.aaf")
    assert code == 0, events
    assert any("nivel reducido" in e["message"] for e in events if e["type"] == "warning")
    with aaf2.open(str(tmp_path / "a" / "h.aaf"), "r") as f:
        (mm,) = list(f.content.mastermobs())
        assert mm.comments["GainReduction"].endswith("dB") and float(mm.comments["GainReduction"][:-3]) < -12
    code, events = run(*base, "--out", tmp_path / "b" / "h.aaf", "--peak-ceiling-db", "off")
    assert code == 0 and any("recortado" in e["message"] for e in events if e["type"] == "warning")
