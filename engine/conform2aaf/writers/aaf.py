"""AAF writer: one composition linking external production WAV files.

Mob chain per file:  MasterMob -> file SourceMob (WAVEDescriptor + NetworkLocator)
                     -> import SourceMob (ImportDescriptor + timecode slot).
The WAV files are referenced, never copied or rewritten, so BWF/iXML/INFO
metadata stays intact. The composition runs at the session sample rate so
every edit is sample-accurate whatever the project frame rate.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import aaf2
from aaf2.ama import create_network_locator
from aaf2.auid import AUID
from aaf2.rational import AAFRational

from ..media.riff import read_chunks
from ..model import Clip, MediaFile, Timeline

OP_DISSOLVE = AUID("0c3bea41-fc05-11d2-8a29-0050040ef7d2")
OP_GAIN = AUID("9d2ea894-0968-11d3-8a38-0050040ef7d2")
PARAM_AMPLITUDE = AUID("e4962321-2267-11d3-8a4c-0050040ef7d2")
DAY_SECONDS = 24 * 3600


@dataclass
class WriteResult:
    clips_written: int = 0
    clips_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def _wave_summary(path: Path) -> bytes:
    """RIFF/WAVE header + fmt chunk, as a WAVEDescriptor Summary (RF64 safe)."""
    off, size = read_chunks(path)["fmt "]
    with open(path, "rb") as fh:
        fh.seek(off)
        fmt = fh.read(size)
    return b"RIFF" + struct.pack("<I", 4 + 8 + size) + b"WAVE" + b"fmt " + struct.pack("<I", size) + fmt


class _Defs:
    def __init__(self, f):
        self.amplitude = f.create.ParameterDef(PARAM_AMPLITUDE, "Amplitude", "Audio gain", "Rational")
        f.dictionary.register_def(self.amplitude)
        self.dissolve = self._op(f, OP_DISSOLVE, "Mono Audio Dissolve", 2)
        self.gain = self._op(f, OP_GAIN, "Mono Audio Gain", 1)
        self.gain["ParametersDefined"].append(self.amplitude)

    @staticmethod
    def _op(f, auid, name, inputs):
        op = f.create.OperationDef(auid, name, "")
        op.media_kind = "sound"
        op["NumberInputs"].value = inputs
        op["IsTimeWarp"].value = False
        f.dictionary.register_def(op)
        return op


class AAFWriter:
    def __init__(self, f, timeline: Timeline, sample_rate: int, result: WriteResult):
        self.f = f
        self.tl = timeline
        self.sr = sample_rate
        self.res = result
        self.defs = _Defs(f)
        self.masters: dict[Path, object] = {}

    # -- media mobs -------------------------------------------------------
    def master_for(self, mf: MediaFile):
        if mf.path in self.masters:
            return self.masters[mf.path]
        f = self.f
        rate = self.tl.rate
        tr = mf.time_reference or 0
        path = str(mf.path.resolve())

        imp = f.create.SourceMob()
        imp.name = mf.path.name
        imp.descriptor = f.create.ImportDescriptor()
        imp.descriptor["Locator"].append(create_network_locator(f, path))
        f.content.mobs.append(imp)
        for _ in range(mf.channels):
            s = imp.create_empty_slot(edit_rate=mf.sample_rate, media_kind="sound")
            s.segment.length = DAY_SECONDS * mf.sample_rate + mf.frames
        tc = imp.create_timecode_slot(rate.nominal, rate.nominal, rate.drop, length=DAY_SECONDS * rate.nominal)
        tc.segment.start = 0

        fm = f.create.SourceMob()
        fm.name = mf.path.name
        desc = f.create.WAVEDescriptor()
        desc["SampleRate"].value = mf.sample_rate
        desc["Length"].value = mf.frames
        desc["Summary"].value = bytearray(_wave_summary(mf.path))
        desc["ContainerFormat"].value = f.dictionary.lookup_containerdef("AAF")
        desc["Locator"].append(create_network_locator(f, path))
        fm.descriptor = desc
        f.content.mobs.append(fm)

        mm = f.create.MasterMob()
        mm.name = mf.stem
        f.content.mobs.append(mm)
        for ch in range(1, mf.channels + 1):
            fslot = fm.create_empty_sequence_slot(mf.sample_rate, media_kind="sound")
            fslot["PhysicalTrackNumber"].value = ch
            fslot.segment.components.append(imp.create_source_clip(ch, start=tr, length=mf.frames))
            fslot.segment.length = mf.frames
            mslot = mm.create_empty_sequence_slot(mf.sample_rate, media_kind="sound")
            mslot["PhysicalTrackNumber"].value = ch
            mslot.segment.components.append(fm.create_source_clip(fslot.slot_id, start=0, length=mf.frames))
            mslot.segment.length = mf.frames

        for key, val in (("Scene", mf.scene), ("Take", mf.take), ("Tape", mf.tape),
                         ("Project", mf.project), ("Description", mf.description)):
            if val:
                mm.comments[key] = val
        if mf.track_names:
            mm.comments["Tracks"] = ", ".join(mf.track_names)
        self.masters[mf.path] = mm
        return mm

    # -- composition ------------------------------------------------------
    def samples(self, t: Fraction) -> int:
        return round(t * self.sr)

    def source_offset(self, clip: Clip) -> int:
        if clip.source_in is None:
            return 0
        start = clip.media.start if clip.media.start is not None else Fraction(0)
        return self.samples(clip.source_in - start)

    def make_clip(self, clip: Clip, start: int, length: int):
        mm = self.master_for(clip.media)
        ch = clip.channel or 1
        if ch > clip.media.channels:
            self.res.warnings.append(f"{clip.name}: canal {ch} no existe en {clip.media.path.name}, se usa el 1")
            ch = 1
        sc = mm.create_source_clip(ch, start=start, length=length)
        if not clip.gain_db:
            return sc, sc
        og = self.f.create.OperationGroup(self.defs.gain, length=length, media_kind="sound")
        og.segments.append(sc)
        amp = Fraction(10 ** (clip.gain_db / 20)).limit_denominator(10000)
        og.parameters.append(self.f.create.ConstantValue(self.defs.amplitude, AAFRational(amp)))
        return og, sc

    def transition(self, length: int, cut: int):
        t = self.f.create.Transition(media_kind="sound", length=length)
        t["CutPoint"].value = cut
        t["OperationGroup"].value = self.f.create.OperationGroup(self.defs.dissolve, length=length, media_kind="sound")
        return t

    def write_track(self, comp, track) -> None:
        slot = comp.create_sound_slot(edit_rate=self.sr)
        slot.name = track.name
        seq = slot.segment
        comps = seq.components
        cursor = 0
        last = None  # (outer, inner, clip, src_start, length) of the previous source clip
        for clip in sorted(track.clips, key=lambda c: c.record_in):
            if clip.match_status != "matched" or clip.media is None:
                self.res.clips_skipped += 1
                continue
            if clip.media.sample_rate != self.sr:
                self.res.warnings.append(
                    f"{clip.media.path.name}: {clip.media.sample_rate} Hz en sesión de {self.sr} Hz (sin remuestreo)")
            rec = self.samples(clip.record_in - self.tl.start)
            length = self.samples(clip.record_out - self.tl.start) - rec
            src = self.source_offset(clip)
            if src < 0 or src + length > clip.media.frames:
                self.res.warnings.append(f"{clip.name}: el rango pedido excede el fichero, se recorta")
                head = max(0, -src)
                src, rec = src + head, rec + head
                length = min(length - head, clip.media.frames - src)
                if length <= 0:
                    self.res.clips_skipped += 1
                    continue
            if rec < cursor:
                self.res.warnings.append(f"{clip.name}: se solapa con el clip anterior en {track.name}, se recorta")
                trim = cursor - rec
                rec, src, length = cursor, src + trim, length - trim
                if length <= 0:
                    self.res.clips_skipped += 1
                    continue

            xf = self.samples(clip.crossfade_in)
            pre = self.samples(clip.crossfade_pre)
            if xf and last and rec == cursor and self._can_crossfade(last, src, xf, pre):
                outer_p, inner_p = last[0], last[1]
                ext = xf - pre
                outer_p.length += ext
                if inner_p is not outer_p:
                    inner_p.length += ext
                comps.append(self.transition(xf, pre))
                outer, inner = self.make_clip(clip, src - pre, length + pre)
                comps.append(outer)
            else:
                if xf:
                    self.res.warnings.append(f"{clip.name}: sin material para el crossfade, se deja en corte")
                gap = rec - cursor
                fin = self.samples(clip.fade_in)
                if fin and gap > 0:
                    comps.append(self.f.create.Filler("sound", gap + fin))
                    comps.append(self.transition(fin, 0))
                elif gap > 0:
                    comps.append(self.f.create.Filler("sound", gap))
                elif fin:
                    self.res.warnings.append(f"{clip.name}: fundido de entrada sin hueco previo, omitido")
                outer, inner = self.make_clip(clip, src, length)
                comps.append(outer)
            cursor = rec + length
            fout = self.samples(clip.fade_out)
            if fout:
                comps.append(self.transition(fout, fout))
                comps.append(self.f.create.Filler("sound", fout))
                last = None
            else:
                last = (outer, inner, clip, src, length)
            self.res.clips_written += 1
        seq.length = cursor

    @staticmethod
    def _can_crossfade(last, src: int, xf: int, pre: int) -> bool:
        _, _, clip_p, src_p, len_p = last
        ext = xf - pre
        return pre >= 0 and ext >= 0 and src - pre >= 0 and src_p + len_p + ext <= clip_p.media.frames

    def write(self) -> None:
        f, tl = self.f, self.tl
        comp = f.create.CompositionMob()
        comp.name = tl.name
        comp.usage = "Usage_TopLevel"
        f.content.mobs.append(comp)
        tc = comp.create_timeline_slot(tl.rate.nominal)
        tc.segment = f.create.Timecode(tl.rate.nominal, drop=tl.rate.drop)
        tc.segment.start = round(tl.start * tl.rate.fps)
        tc.name = "TC1"
        for track in tl.tracks:
            self.write_track(comp, track)
        total = max((s.segment.length for s in comp.slots if s.media_kind == "Sound"), default=0)
        tc.segment.length = max(1, round(Fraction(total, self.sr) * tl.rate.nominal))


def write_aaf(tl: Timeline, out: Path, sample_rate: int = 48000) -> WriteResult:
    result = WriteResult()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    with aaf2.open(str(tmp), "w") as f:
        AAFWriter(f, tl, sample_rate, result).write()
    tmp.replace(out)
    return result
