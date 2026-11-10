"""Premiere Pro / Final Cut Pro 7 XML (xmeml) reader: audio tracks, or picture cuts.

In picture mode a cut may be a nested sequence (Premiere synced clip: camera clip + production
WAV). The WAV inside it gives the cut its source TC and file; the camera clip is the fallback."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..model import Clip, Timeline, Track
from ..timecode import FrameRate, tc_to_frames


def _int(el, path, default=None):
    v = el.findtext(path) if el is not None else None
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _rate(el) -> Fraction | None:
    if el is None or el.findtext("timebase") is None:
        return None
    tb = int(el.findtext("timebase"))
    ntsc = (el.findtext("ntsc") or "").upper() == "TRUE"
    return Fraction(tb * 1000, 1001) if ntsc else Fraction(tb)


def _tc_seconds(tc_el, fallback_fps: Fraction) -> Fraction | None:
    if tc_el is None:
        return None
    fps = _rate(tc_el.find("rate")) or fallback_fps
    frame = _int(tc_el, "frame")
    if frame is None and tc_el.findtext("string"):
        drop = (tc_el.findtext("displayformat") or "").upper() == "DF"
        frame = tc_to_frames(tc_el.findtext("string"), FrameRate.from_fps(fps, drop))
    return None if frame is None else Fraction(frame) / fps


def _path_from_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url)
    return unquote(p.path) if p.scheme == "file" else unquote(url)


def _gain_db(item, warnings: list[str], name: str) -> float:
    for eff in item.iterfind("filter/effect"):
        if (eff.findtext("effectid") or "").lower() != "audiolevels":
            continue
        for par in eff.iterfind("parameter"):
            if (par.findtext("parameterid") or "").lower() != "level":
                continue
            if par.find("keyframe") is not None:
                warnings.append(f"{name}: automatización de volumen no soportada, se usa el valor fijo")
            try:
                v = float(par.findtext("value") or par.findtext("keyframe/value"))
            except (TypeError, ValueError):
                continue
            return 20 * math.log10(v) if v > 0 else -144.0
    return 0.0


def read_xmeml(path: Path, picture: bool = False) -> Timeline:
    root = ET.parse(path).getroot()
    seq = root.find(".//sequence")
    if seq is None:
        raise ValueError("El XML no contiene ninguna secuencia")
    fps = _rate(seq.find("rate")) or Fraction(25)
    tc = seq.find("timecode")
    drop = tc is not None and (tc.findtext("displayformat") or "").upper() == "DF"
    rate = FrameRate.from_fps(fps, drop)
    start = _tc_seconds(tc, fps) or Fraction(0)
    warnings: list[str] = []

    files = {f.get("id"): f for f in root.iter("file") if f.get("id") and len(f)}
    if picture:
        return _read_picture(root, seq, files, fps, rate, start, warnings, path)

    tracks: list[Track] = []
    for ti, tr in enumerate(seq.findall("media/audio/track"), 1):
        if (tr.findtext("enabled") or "TRUE").upper() == "FALSE":
            warnings.append(f"Pista A{ti} desactivada: omitida")
            continue
        stereo = (tr.get("premiereTrackType") or "").lower() == "stereo"
        names = [f"A{ti}.L", f"A{ti}.R"] if stereo else [f"A{ti}"]
        out = [Track(n) for n in names]

        # clips and transitions in track order
        seqitems: list[dict] = []
        for el in tr:
            if el.tag == "transitionitem":
                seqitems.append({
                    "kind": "t",
                    "start": _int(el, "start", 0),
                    "end": _int(el, "end", 0),
                    "align": (el.findtext("alignment") or "center").lower(),
                })
            elif el.tag == "clipitem":
                if (el.findtext("enabled") or "TRUE").upper() == "FALSE":
                    warnings.append(f"{el.findtext('name')}: clip desactivado, omitido")
                    continue
                seqitems.append({"kind": "c", "el": el, "start": _int(el, "start", -1),
                                 "end": _int(el, "end", -1), "in": _int(el, "in", 0),
                                 "xf": None, "fade_in": 0, "fade_out": 0})

        for i, it in enumerate(seqitems):
            if it["kind"] != "t":
                continue
            prev = seqitems[i - 1] if i and seqitems[i - 1]["kind"] == "c" else None
            nxt = seqitems[i + 1] if i + 1 < len(seqitems) and seqitems[i + 1]["kind"] == "c" else None
            prev = prev if prev and (prev["end"] == -1 or prev["end"] > it["start"]) else None
            nxt = nxt if nxt and (nxt["start"] == -1 or nxt["start"] < it["end"]) else None
            d = it["end"] - it["start"]
            if prev and nxt:
                cut = {"start": it["start"], "end": it["end"]}.get(it["align"], it["start"] + Fraction(d, 2))
                # in/out of a clip that starts under a transition refer to the transition start
                nxt["in"] += cut - it["start"]
                prev["end"], nxt["start"] = cut, cut
                nxt["xf"] = (Fraction(d), cut - it["start"])
            elif nxt:
                if nxt["start"] == -1:
                    nxt["start"] = it["start"]
                nxt["fade_in"] = d
            elif prev:
                if prev["end"] == -1:
                    prev["end"] = it["end"]
                prev["fade_out"] = d

        for it in seqitems:
            if it["kind"] != "c":
                continue
            el = it["el"]
            name = el.findtext("name") or ""
            f = el.find("file")
            if f is not None and f.get("id") in files:
                f = files[f.get("id")]
            item_fps = _rate(el.find("rate")) or fps
            file_tc = _tc_seconds(f.find("timecode") if f is not None else None, item_fps)
            hint = _path_from_url(f.findtext("pathurl") or "") if f is not None else ""
            hint = hint or (f.findtext("name") if f is not None else "") or ""
            src_ch = _int(el, "sourcetrack/trackindex", 1)
            chans = [1, 2] if stereo else [src_ch]
            if it["start"] < 0 or it["end"] < 0 or it["end"] <= it["start"]:
                warnings.append(f"{name}: posición no válida, omitido")
                continue
            gain = _gain_db(el, warnings, name)
            for t, ch in zip(out, chans):
                c = Clip(
                    name=name,
                    record_in=start + Fraction(it["start"]) / fps,
                    duration=Fraction(it["end"] - it["start"]) / fps,
                    source_in=(file_tc + Fraction(it["in"]) / item_fps) if file_tc is not None else None,
                    file_hint=hint,
                    channel=ch,
                    gain_db=gain,
                    fade_in=Fraction(it["fade_in"]) / fps,
                    fade_out=Fraction(it["fade_out"]) / fps,
                )
                if it["xf"]:
                    c.crossfade_in, c.crossfade_pre = (v / fps for v in it["xf"])
                t.clips.append(c)
        tracks += out

    return Timeline(name=seq.findtext("name") or Path(path).stem, rate=rate, start=start,
                    tracks=tracks, warnings=warnings)


AUDIO_FILE_EXTS = (".wav", ".bwf")


def _resolve_file(el, files):
    f = el.find("file")
    return files.get(f.get("id"), f) if f is not None else None


def _file_hint(f) -> str:
    if f is None:
        return ""
    return _path_from_url(f.findtext("pathurl") or "") or f.findtext("name") or ""


def _position(items, i) -> tuple[int, int, int]:
    """start/end/in of clipitem i; -1 means "under a transition": cut at the transition centre."""
    el = items[i]
    s_, e_, in_ = _int(el, "start", -1), _int(el, "end", -1), _int(el, "in", 0)
    if s_ < 0 and i and items[i - 1].tag == "transitionitem":
        t = items[i - 1]
        cut = (_int(t, "start", 0) + _int(t, "end", 0)) // 2
        in_ += cut - _int(t, "start", 0)
        s_ = cut
    if e_ < 0 and i + 1 < len(items) and items[i + 1].tag == "transitionitem":
        t = items[i + 1]
        e_ = (_int(t, "start", 0) + _int(t, "end", 0)) // 2
    return s_, e_, in_


def _nested_sources(body, files, a: Fraction, b: Fraction, fps: Fraction) -> list[tuple]:
    """What plays in the nested-sequence range [a, b) (seconds): (offset, length, source TC, file, reel).

    The production WAVs come first; the camera clip fills what no WAV covers."""
    nfps = _rate(body.find("rate")) or fps

    def spans(kind: str, want_wav: bool):
        seen = set()
        for tr in body.findall(f"media/{kind}/track"):
            for it in tr.findall("clipitem"):
                if (it.findtext("enabled") or "TRUE").upper() == "FALSE":
                    continue
                f = _resolve_file(it, files)
                hint = _file_hint(f)
                if f is None or hint.lower().endswith(AUDIO_FILE_EXTS) != want_wav:
                    continue
                st, en = _int(it, "start", -1), _int(it, "end", -1)
                key = (f.get("id"), st)
                if st < 0 or en <= st or key in seen:
                    continue
                seen.add(key)
                ifps = _rate(it.find("rate")) or nfps
                tc = _tc_seconds(f.find("timecode"), ifps)
                if tc is None:
                    continue
                reel = (f.findtext("timecode/reel/name") or "").strip()
                yield Fraction(st) / nfps, Fraction(en) / nfps, tc + Fraction(_int(it, "in", 0)) / ifps, hint, reel

    out: list[tuple] = []
    for ws, we, src, hint, reel in spans("audio", True):
        lo, hi = max(a, ws), min(b, we)
        if hi > lo:
            out.append((lo - a, hi - lo, src + lo - ws, hint, reel))
    # gaps no WAV covers: the camera clip's own TC
    covered = sorted((o, o + d) for o, d, *_ in out)
    gaps, pos = [], Fraction(0)
    for lo, hi in covered:
        if lo > pos:
            gaps.append((pos, lo))
        pos = max(pos, hi)
    if pos < b - a:
        gaps.append((pos, b - a))
    for g0, g1 in gaps:
        for vs, ve, src, hint, reel in spans("video", False):
            lo, hi = max(a + g0, vs), min(a + g1, ve)
            if hi > lo:
                out.append((lo - a, hi - lo, src + lo - vs, hint, reel))
                break
    return sorted(out, key=lambda x: x[0])


def _read_picture(root, seq, files, fps: Fraction, rate: FrameRate, start: Fraction, warnings: list[str], path: Path) -> Timeline:
    """One clip per picture cut (no channel), with scene/take/reel from the list's metadata.

    Cuts are the video clipitems plus the nested sequences on any track (Premiere places synced
    clips on the audio tracks too). The list's own audio clips (music, effects) are not cuts."""
    nested = {s.get("id"): s for s in root.iter("sequence") if s.get("id") and s.find("media") is not None}
    seen: set[tuple] = set()
    tracks: list[Track] = []
    groups = [("V", seq.findall("media/video/track")), ("A", seq.findall("media/audio/track"))]
    for prefix, trs in groups:
        for ti, tr in enumerate(trs, 1):
            items = [el for el in tr if el.tag in ("clipitem", "transitionitem")]
            cuts = [el for el in items if el.tag == "clipitem" and (prefix == "V" or el.find("sequence") is not None)]
            if not cuts:
                continue
            if (tr.findtext("enabled") or "TRUE").upper() == "FALSE":
                warnings.append(f"Pista {prefix}{ti} desactivada: omitida")
                continue
            track = Track(f"{prefix}{ti}")
            for i, el in enumerate(items):
                if el not in cuts:
                    continue
                name = el.findtext("name") or ""
                if (el.findtext("enabled") or "TRUE").upper() == "FALSE":
                    warnings.append(f"{name}: clip desactivado, omitido")
                    continue
                s_, e_, in_ = _position(items, i)
                if s_ < 0 or e_ <= s_:
                    warnings.append(f"{name}: posición no válida, omitido")
                    continue
                item_fps = _rate(el.find("rate")) or fps
                rec, length = start + Fraction(s_) / fps, Fraction(e_ - s_) / fps
                li = el.find("logginginfo")
                meta = dict(
                    scene=((li.findtext("scene") if li is not None else None) or "").strip(),
                    take=((li.findtext("shottake") if li is not None else None) or "").strip(),
                )
                ns = el.find("sequence")
                if ns is not None:
                    body = nested.get(ns.get("id"))
                    a = Fraction(in_) / item_fps
                    sources = _nested_sources(body, files, a, a + length, fps) if body is not None else []
                    if not sources:
                        warnings.append(f"{name}: la secuencia anidada no tiene medios con TC, omitido")
                        continue
                    parts = [Clip(name=name, record_in=rec + off, duration=d, source_in=src,
                                  reel=reel, file_hint=hint, **meta)
                             for off, d, src, hint, reel in sources]
                else:
                    f = _resolve_file(el, files)
                    file_tc = _tc_seconds(f.find("timecode") if f is not None else None, item_fps)
                    parts = [Clip(
                        name=name, record_in=rec, duration=length,
                        source_in=(file_tc + Fraction(in_) / item_fps) if file_tc is not None else None,
                        reel=((f.findtext("timecode/reel/name") if f is not None else None) or "").strip(),
                        file_hint=_file_hint(f), **meta)]
                for c in parts:
                    # the same nested clip sits on several tracks at once: one cut is enough
                    key = (c.record_in, c.duration, c.source_in, c.file_hint)
                    if key not in seen:
                        seen.add(key)
                        track.clips.append(c)
            if track.clips:
                tracks.append(track)
    return Timeline(name=seq.findtext("name") or Path(path).stem, rate=rate, start=start,
                    tracks=tracks, warnings=list(dict.fromkeys(warnings)), picture=True)
