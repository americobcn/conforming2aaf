"""Final Cut Pro FCPXML (1.8-1.11) and .fcpxmld reader, audio only.

Each story element maps its local time to timeline time with
    record(t) = parent_record(offset + (t - start)).
Nested content (compound, multicam, sync clips) is trimmed to the window the
parent actually shows.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from ..model import Clip, Timeline, Track
from ..timecode import FrameRate

STORY = {"asset-clip", "clip", "audio", "video", "sync-clip", "ref-clip", "mc-clip", "gap", "spine", "title"}
MAX_DEPTH = 12
Window = tuple[Fraction, Fraction]


def _t(s: str | None) -> Fraction:
    if not s:
        return Fraction(0)
    return Fraction(s.strip().removesuffix("s"))


def _src(url: str) -> str:
    p = urlparse(url)
    return unquote(p.path) if p.scheme == "file" else unquote(url)


def _channels(s: str | None) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", s or "")]


def _db(s: str | None) -> float:
    m = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", s or "")
    return float(m.group(1)) if m else 0.0


class _Reader:
    def __init__(self, resources: dict[str, ET.Element], warnings: list[str]):
        self.res = resources
        self.warnings = warnings
        self.items: list[tuple[str, int, Clip]] = []  # (role, channel position, clip)

    # -- spines -----------------------------------------------------------
    def walk_spine(self, spine, P: Callable, window: Window, depth: int) -> list[Clip]:
        kids = [k for k in spine if k.tag in STORY or k.tag == "transition"]
        if spine.get("offset") is not None:
            o = _t(spine.get("offset"))
            first = next((k for k in kids if k.tag != "transition"), None)
            s = _t(spine.get("start")) if spine.get("start") else (_t(first.get("offset")) if first is not None else o)
            L = lambda t, o=o, s=s: P(o + (t - s))
        else:
            L = P
        emitted_all: list[Clip] = []
        prev: list[Clip] = []
        pending = None
        for k in kids:
            if k.tag == "transition":
                pending = k
                continue
            cur = self.walk_item(k, L, window, depth)
            if pending is not None:
                self._transition(pending, L, prev, cur, L(_t(k.get("offset"))))
                pending = None
            prev = cur
            emitted_all += cur
        if pending is not None:
            for c in prev:
                c.fade_out = _t(pending.get("duration"))
        return emitted_all

    @staticmethod
    def _transition(tr, L, prev: list[Clip], cur: list[Clip], cut: Fraction) -> None:
        d = _t(tr.get("duration"))
        pre = cut - L(_t(tr.get("offset")))
        incoming = [c for c in cur if c.record_in == cut]
        outgoing = [c for c in prev if c.record_out == cut]
        if incoming and outgoing:
            for c in incoming:
                c.crossfade_in, c.crossfade_pre = d, pre
        elif incoming:
            for c in incoming:
                c.fade_in = d
        else:
            for c in outgoing:
                c.fade_out = d

    # -- story elements ---------------------------------------------------
    def walk_item(self, e, P: Callable, window: Window, depth: int) -> list[Clip]:
        if depth > MAX_DEPTH:
            self.warnings.append(f"{e.get('name')}: anidamiento demasiado profundo; usa 'Break Apart' en Final Cut")
            return []
        name = e.get("name") or ""
        if e.get("enabled") == "0":
            if e.tag != "gap":
                self.warnings.append(f"{name or e.tag}: desactivado, omitido")
            return []
        if e.tag == "spine":
            return self.walk_spine(e, P, window, depth + 1)

        o, s, d = _t(e.get("offset")), _t(e.get("start")), _t(e.get("duration"))
        rec_in = P(o)
        L = lambda t, o=o, s=s: P(o + (t - s))
        w = (max(window[0], rec_in), min(window[1], rec_in + d))
        if e.find("timeMap") is not None:
            self.warnings.append(f"{name}: cambio de velocidad no soportado, se usa a velocidad normal")

        emitted: list[Clip] = []
        tag = e.tag
        if tag in ("asset-clip", "audio"):
            emitted += self._emit_asset(e, rec_in, s, d, w)
        elif tag in ("clip", "sync-clip", "video"):
            for c in e:
                if c.tag in STORY and c.get("lane") is None:
                    emitted += self.walk_item(c, L, w, depth + 1)
        elif tag == "ref-clip":
            media = self.res.get(e.get("ref"))
            seq = media.find("sequence") if media is not None else None
            if seq is not None and e.get("srcEnable", "all") in ("all", "audio"):
                emitted += self.walk_spine(seq.find("spine"), L, w, depth + 1)
        elif tag == "mc-clip":
            emitted += self._multicam(e, L, w, depth)

        # connected clips and storylines
        for c in e:
            if c.tag in STORY and c.get("lane") is not None:
                self.walk_item(c, L, window, depth + 1)

        self._apply_volume(e, emitted)
        return emitted

    def _multicam(self, e, L, w, depth) -> list[Clip]:
        media = self.res.get(e.get("ref"))
        mc = media.find("multicam") if media is not None else None
        if mc is None:
            self.warnings.append(f"{e.get('name')}: multicam sin recurso")
            return []
        out: list[Clip] = []
        sources = [s for s in e.findall("mc-source") if s.get("srcEnable", "all") in ("all", "audio")]
        if not sources:
            self.warnings.append(f"{e.get('name')}: multicam sin ángulo de audio activo")
        for src in sources:
            angle = next((a for a in mc.iter("mc-angle") if a.get("angleID") == src.get("angleID")), None)
            if angle is None:
                continue
            for c in angle:
                if c.tag in STORY:
                    out += self.walk_item(c, L, w, depth + 1)
        return out

    def _emit_asset(self, e, rec_in, s, d, w) -> list[Clip]:
        asset = self.res.get(e.get("ref"))
        if asset is None or asset.tag != "asset" or asset.get("hasAudio") == "0":
            return []
        a, b = max(rec_in, w[0]), min(rec_in + d, w[1])
        if b <= a:
            return []
        nch = int(asset.get("audioChannels") or 2)
        base_role = e.get("audioRole") or e.get("role") or "dialogue"
        rep = asset.find("media-rep")
        hint = _src(rep.get("src")) if rep is not None and rep.get("src") else _src(asset.get("src") or "")
        sources = e.findall("audio-channel-source")
        if sources:
            mapping = [(src.get("role") or base_role, _channels(src.get("srcCh")) or list(range(1, nch + 1)))
                       for src in sources if src.get("enabled") != "0"]
        else:
            mapping = [(base_role, _channels(e.get("srcCh")) or list(range(1, nch + 1)))]
        out: list[Clip] = []
        for role, chans in mapping:
            for idx, ch in enumerate(chans):
                c = Clip(
                    name=e.get("name") or asset.get("name") or "",
                    record_in=a,
                    duration=b - a,
                    source_in=s + (a - rec_in),
                    file_hint=hint or asset.get("name") or "",
                    channel=ch,
                )
                self.items.append((role, idx, c))
                out.append(c)
        return out

    @staticmethod
    def _apply_volume(e, clips: list[Clip]) -> None:
        adj = e.find("adjust-volume")
        if adj is None or not clips:
            return
        gain = _db(adj.get("amount"))
        fin = adj.find(".//fadeIn")
        fout = adj.find(".//fadeOut")
        for c in clips:
            c.gain_db += gain
            if fin is not None:
                c.fade_in = _t(fin.get("duration"))
            if fout is not None:
                c.fade_out = _t(fout.get("duration"))


def _build_tracks(items: list[tuple[str, int, Clip]]) -> list[Track]:
    groups: OrderedDict[tuple[str, int], list[Clip]] = OrderedDict()
    width: dict[str, int] = {}
    for role, idx, clip in items:
        groups.setdefault((role, idx), []).append(clip)
        width[role] = max(width.get(role, 0), idx + 1)
    roles = list(width)
    keys = sorted(groups, key=lambda k: (roles.index(k[0]), k[1]))
    tracks: list[Track] = []
    for role, idx in keys:
        base = role if width[role] == 1 else f"{role} {idx + 1}"
        subs: list[list[Clip]] = []
        for c in sorted(groups[(role, idx)], key=lambda c: c.record_in):
            for sub in subs:
                if sub[-1].record_out <= c.record_in:
                    sub.append(c)
                    break
            else:
                subs.append([c])
        tracks += [Track(base if k == 0 else f"{base} #{k + 1}", sub) for k, sub in enumerate(subs)]
    return tracks


def read_fcpxml(path: Path) -> Timeline:
    p = Path(path)
    if p.is_dir():
        p = p / "Info.fcpxml"
    root = ET.parse(p).getroot()
    res_el = root.find("resources")
    resources = {r.get("id"): r for r in res_el} if res_el is not None else {}
    project = root.find(".//project")
    seq = project.find("sequence") if project is not None else None
    if seq is None:
        raise ValueError("El FCPXML no contiene un proyecto. Exporta el proyecto (timeline), no clips sueltos del evento.")
    fmt = resources.get(seq.get("format"))
    fd = _t(fmt.get("frameDuration")) if fmt is not None and fmt.get("frameDuration") else Fraction(1, 25)
    fps = 1 / fd
    warnings: list[str] = []
    try:
        rate = FrameRate.from_fps(fps, seq.get("tcFormat") == "DF")
    except ValueError:
        if fps == 120:
            warnings.append("Proyecto a 120 fps: se usa 60 fps para el timecode")
            rate = FrameRate.parse("60")
        else:
            raise
    start = _t(seq.get("tcStart"))
    reader = _Reader(resources, warnings)
    reader.walk_spine(seq.find("spine"), lambda t: t, (Fraction(-(10**9)), Fraction(10**9)), 0)
    return Timeline(name=project.get("name") or p.stem, rate=rate, start=start,
                    tracks=_build_tracks(reader.items), warnings=warnings)
