"""Premiere Pro / Final Cut Pro 7 XML (xmeml) reader, audio tracks only."""
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
        return _read_picture(seq, files, fps, rate, start, warnings, path)

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


def _read_picture(seq, files, fps: Fraction, rate: FrameRate, start: Fraction, warnings: list[str], path: Path) -> Timeline:
    """One clip per video clipitem (no channel), with scene/take/reel from the list's metadata."""
    tracks: list[Track] = []
    for ti, tr in enumerate(seq.findall("media/video/track"), 1):
        if (tr.findtext("enabled") or "TRUE").upper() == "FALSE":
            warnings.append(f"Pista V{ti} desactivada: omitida")
            continue
        items = [el for el in tr if el.tag in ("clipitem", "transitionitem")]
        track = Track(f"V{ti}")
        for i, el in enumerate(items):
            if el.tag != "clipitem":
                continue
            name = el.findtext("name") or ""
            if (el.findtext("enabled") or "TRUE").upper() == "FALSE":
                warnings.append(f"{name}: clip desactivado, omitido")
                continue
            s_, e_, in_ = _int(el, "start", -1), _int(el, "end", -1), _int(el, "in", 0)
            # start/end of -1 mean "under a transition": use the centre of the neighbouring transition
            if s_ < 0 and i and items[i - 1].tag == "transitionitem":
                t = items[i - 1]
                cut = (_int(t, "start", 0) + _int(t, "end", 0)) // 2
                in_ += cut - _int(t, "start", 0)
                s_ = cut
            if e_ < 0 and i + 1 < len(items) and items[i + 1].tag == "transitionitem":
                t = items[i + 1]
                e_ = (_int(t, "start", 0) + _int(t, "end", 0)) // 2
            if s_ < 0 or e_ <= s_:
                warnings.append(f"{name}: posición no válida, omitido")
                continue
            f = el.find("file")
            if f is not None and f.get("id") in files:
                f = files[f.get("id")]
            item_fps = _rate(el.find("rate")) or fps
            file_tc = _tc_seconds(f.find("timecode") if f is not None else None, item_fps)
            hint = _path_from_url(f.findtext("pathurl") or "") if f is not None else ""
            hint = hint or (f.findtext("name") if f is not None else "") or ""
            li = el.find("logginginfo")
            track.clips.append(Clip(
                name=name,
                record_in=start + Fraction(s_) / fps,
                duration=Fraction(e_ - s_) / fps,
                source_in=(file_tc + Fraction(in_) / item_fps) if file_tc is not None else None,
                reel=((f.findtext("timecode/reel/name") if f is not None else None) or "").strip(),
                file_hint=hint,
                scene=((li.findtext("scene") if li is not None else None) or "").strip(),
                take=((li.findtext("shottake") if li is not None else None) or "").strip(),
            ))
        if track.clips:
            tracks.append(track)
    return Timeline(name=seq.findtext("name") or Path(path).stem, rate=rate, start=start,
                    tracks=tracks, warnings=warnings, picture=True)
