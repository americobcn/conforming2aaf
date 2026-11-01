"""Prepare production media for export: copy next to the AAF, split polyphonic
files into mono, or stage mono files for embedding.

Clips are updated in place to point at the prepared files. Source files are
never modified. Split files keep every original chunk (bext with its
TimeReference, iXML, LIST/INFO, axml, XMP...); only fmt and data change, and the
iXML track list is reduced to the channel that was extracted.
"""
from __future__ import annotations

import shutil
import struct
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterator

from ..model import MediaFile, Timeline
from .riff import read_chunks, read_wav

CHUNK_FRAMES = 1 << 18
RF64_LIMIT = 0xFFFF0000  # use RF64 when the RIFF size would not fit in 32 bits
MODES = ("link", "copy", "embed")


@dataclass
class PrepareResult:
    media_dir: Path | None = None
    files: int = 0
    bytes: int = 0
    warnings: list[str] = field(default_factory=list)


def _embeddable_format(mf: MediaFile) -> bool:
    """pyaaf2 reads embedded essence with the stdlib wave module: PCM 16/24 bit, plain RIFF."""
    return mf.format_tag == 1 and mf.bits in (16, 24) and not mf.rf64


def can_embed(mf: MediaFile) -> bool:
    return mf.channels == 1 and _embeddable_format(mf)


def _mono_ixml(raw: bytes, channel: int) -> bytes:
    """Keep only the TRACK of `channel` in an iXML track list, renumbered to 1."""
    try:
        root = ET.fromstring(raw.rstrip(b"\x00").decode("utf-8"))
    except (ET.ParseError, UnicodeDecodeError):
        return raw
    track_list = root.find("TRACK_LIST")
    tracks = track_list.findall("TRACK") if track_list is not None else []
    if len(tracks) < channel:
        return raw
    keep = next((t for t in tracks if (t.findtext("CHANNEL_INDEX") or "").strip() == str(channel)),
                tracks[channel - 1])
    for t in tracks:
        if t is not keep:
            track_list.remove(t)
    for tag in ("CHANNEL_INDEX", "INTERLEAVE_INDEX"):
        el = keep.find(tag)
        if el is not None:
            el.text = "1"
    count = track_list.find("TRACK_COUNT")
    if count is not None:
        count.text = "1"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def split_wav(src: MediaFile, channel: int, dest: Path) -> None:
    """Write channel `channel` (1-based) of `src` as a mono WAV with all other chunks preserved."""
    chunks = read_chunks(src.path)
    w = src.block_align // src.channels
    data_size = src.frames * w
    fmt = struct.pack("<HHIIHH", src.format_tag, 1, src.sample_rate, src.sample_rate * w, w, src.bits)

    with open(src.path, "rb") as fin:
        parts: list[tuple[bytes, bytes | None]] = []  # (chunk id, payload or None for data)
        for cid, (off, size) in chunks.items():
            if cid == "ds64":
                continue
            if cid == "fmt ":
                parts.append((b"fmt ", fmt))
            elif cid == "data":
                parts.append((b"data", None))
            else:
                fin.seek(off)
                payload = fin.read(size)
                if cid == "iXML":
                    payload = _mono_ixml(payload, channel)
                parts.append((cid.encode("latin-1"), payload))

        def padded(n: int) -> int:
            return n + (n & 1)

        body = sum(8 + padded(data_size if p is None else len(p)) for _, p in parts)
        rf64 = 4 + body > RF64_LIMIT
        if rf64:
            body += 8 + 28  # ds64 chunk

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        with open(tmp, "wb") as out:
            if rf64:
                out.write(b"RF64" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE")
                out.write(b"ds64" + struct.pack("<IQQQI", 28, 4 + body, data_size, src.frames, 0))
            else:
                out.write(b"RIFF" + struct.pack("<I", 4 + body) + b"WAVE")
            for cid, payload in parts:
                if payload is not None:
                    out.write(cid + struct.pack("<I", len(payload)) + payload)
                    if len(payload) & 1:
                        out.write(b"\x00")
                    continue
                out.write(b"data" + struct.pack("<I", 0xFFFFFFFF if rf64 else data_size))
                fin.seek(chunks["data"][0])
                remaining = src.frames
                first = (channel - 1) * w
                while remaining:
                    n = min(CHUNK_FRAMES, remaining)
                    block = fin.read(n * src.block_align)
                    mono = bytearray(n * w)
                    for i in range(w):
                        mono[i::w] = block[first + i :: src.block_align]
                    out.write(mono)
                    remaining -= n
                if data_size & 1:
                    out.write(b"\x00")
    tmp.replace(dest)


@contextmanager
def prepare_media(
    tl: Timeline,
    out: Path,
    mode: str,
    split_mono: bool,
    progress: Callable[[str], None] | None = None,
) -> Iterator[PrepareResult]:
    """Prepare media for the matched clips of `tl`; yields while the files must exist.

    link   : original files; polyphonic ones are split only if `split_mono`.
    copy   : used files are copied (or split) into '<out stem> Media' next to `out`.
    embed  : mono files are staged in a temporary folder removed on exit
             (polyphonic files are always split). Files that cannot be
             embedded stay linked, with a warning.
    """
    if mode not in MODES:
        raise ValueError(f"Modo de medios desconocido: {mode}")
    res = PrepareResult()
    split = split_mono or mode == "embed"
    final_dir = Path(out).parent / f"{Path(out).stem} Media"
    tmp: tempfile.TemporaryDirectory | None = None
    taken: dict[str, object] = {}
    cache: dict[tuple[Path, int], tuple[MediaFile, int | None]] = {}
    warned: set[Path] = set()
    poly_warned: set[Path] = set()

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    def alloc(name: str, owner: object) -> Path:
        nonlocal tmp
        if res.media_dir is None:
            if mode == "embed":
                tmp = tempfile.TemporaryDirectory(prefix="conform2aaf-")
                res.media_dir = Path(tmp.name)
            else:
                res.media_dir = final_dir
            res.media_dir.mkdir(parents=True, exist_ok=True)
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, n = name, 1
        while candidate in taken and taken[candidate] != owner:
            n += 1
            candidate = f"{stem} ({n}){suffix}"
        taken[candidate] = owner
        return res.media_dir / candidate

    def finished(dest: Path) -> None:
        res.files += 1
        res.bytes += dest.stat().st_size

    try:
        clips = [c for c in tl.clips() if c.match_status == "matched" and c.media is not None]
        for i, clip in enumerate(clips, 1):
            mf, ch = clip.media, clip.channel or 1
            if mode == "embed" and not _embeddable_format(mf):
                if mf.path not in warned:
                    warned.add(mf.path)
                    res.warnings.append(
                        f"{mf.path.name}: no se puede embeber (solo PCM de 16/24 bits en WAV estándar), se enlaza")
                continue
            if not split and mf.channels > 1 and mf.path not in poly_warned:
                poly_warned.add(mf.path)
                res.warnings.append(
                    f"{mf.path.name}: {mf.channels} canales. Pro Tools no admite ficheros multicanal en un AAF "
                    "y enlazaría siempre el canal 1; activa «Partir polifónicos a mono»")
            if split and mf.channels > 1 and ch <= mf.channels:
                key = (mf.path, ch)
                if key not in cache:
                    dest = alloc(f"{mf.stem}_{ch}.wav", key)
                    say(f"Partiendo {mf.path.name} canal {ch} ({i}/{len(clips)})")
                    split_wav(mf, ch, dest)
                    cache[key] = (read_wav(dest), 1)
                    finished(dest)
                clip.media, clip.channel = cache[key]
            elif mode == "copy":
                key = (mf.path, 0)
                if key not in cache:
                    dest = alloc(mf.path.name, key)
                    say(f"Copiando {mf.path.name} ({i}/{len(clips)})")
                    shutil.copy2(mf.path, dest)
                    cache[key] = (replace(mf, path=dest), None)
                    finished(dest)
                clip.media = cache[key][0]
        yield res
    finally:
        if tmp is not None:
            tmp.cleanup()
