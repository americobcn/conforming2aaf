"""Read-only RIFF/RF64 WAV metadata parser (fmt, bext, iXML, LIST/INFO, axml, XMP)."""
from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import MediaFile

WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class NotAWav(ValueError):
    pass


def _text(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()


def read_chunks(path: Path) -> dict[str, tuple[int, int]]:
    """Map chunk id -> (offset of payload, payload size). First occurrence wins."""
    chunks: dict[str, tuple[int, int]] = {}
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[8:12] != b"WAVE" or head[:4] not in (b"RIFF", b"RF64", b"BW64"):
            raise NotAWav(str(path))
        rf64 = head[:4] != b"RIFF"
        file_size = path.stat().st_size
        data64 = None
        pos = 12
        while pos + 8 <= file_size:
            f.seek(pos)
            cid_raw, size = struct.unpack("<4sI", f.read(8))
            cid = cid_raw.decode("latin-1")
            if rf64 and cid == "ds64":
                _, data64 = struct.unpack("<QQ", f.read(16))
            if cid == "data" and size == 0xFFFFFFFF and data64 is not None:
                size = data64
            chunks.setdefault(cid, (pos + 8, size))
            pos += 8 + size + (size & 1)
    return chunks


def head_is_rf64(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) in (b"RF64", b"BW64")


_BEXT_KEY = re.compile(r"^[A-Za-z]?(SCENE|TAKE|TAPE)\s*=\s*(.*)$", re.I)


def parse_bext_description(text: str) -> dict:
    """Scene/take/tape from `key=value` lines of a bext description (`aSCENE=20 54`, `sTAKE=3`)."""
    out: dict = {}
    for line in text.splitlines():
        m = _BEXT_KEY.match(line.strip())
        if m and m.group(2).strip():
            out.setdefault(m.group(1).lower(), m.group(2).strip())
    return out


def parse_ixml(xml_text: str) -> dict:
    out: dict = {"track_names": []}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for key in ("PROJECT", "SCENE", "TAKE", "TAPE"):
        el = root.find(key)
        if el is not None and el.text:
            out[key.lower()] = el.text.strip()
    for tr in root.iterfind("TRACK_LIST/TRACK"):
        out["track_names"].append((tr.findtext("NAME") or "").strip())
    return out


def read_wav(path: Path) -> MediaFile:
    path = Path(path)
    chunks = read_chunks(path)
    if "fmt " not in chunks or "data" not in chunks:
        raise NotAWav(f"{path}: missing fmt/data chunk")
    with open(path, "rb") as f:
        def payload(cid: str) -> bytes:
            off, size = chunks[cid]
            f.seek(off)
            return f.read(size)

        fmt = payload("fmt ")
        tag, channels, sample_rate, _, block_align, bits = struct.unpack("<HHIIHH", fmt[:16])
        if tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 26:
            tag = struct.unpack("<H", fmt[24:26])[0]
        frames = chunks["data"][1] // block_align if block_align else 0
        mf = MediaFile(path, sample_rate, channels, bits, frames, chunks=list(chunks),
                       format_tag=tag, block_align=block_align, rf64=head_is_rf64(path))

        if "bext" in chunks:
            b = payload("bext")
            if len(b) >= 346:
                mf.description = _text(b[0:256])
                mf.originator = _text(b[256:288])
                lo, hi = struct.unpack("<II", b[338:346])
                mf.time_reference = (hi << 32) | lo
        if "iXML" in chunks:
            ix = parse_ixml(_text(payload("iXML")))
            mf.project = ix.get("project", "")
            mf.scene = ix.get("scene", "")
            mf.take = ix.get("take", "")
            mf.tape = ix.get("tape", "")
            mf.track_names = ix["track_names"]
        for key, value in parse_bext_description(mf.description).items():
            if not getattr(mf, key):  # iXML wins; the bext description only fills gaps
                setattr(mf, key, value)
        if "LIST" in chunks:
            lst = payload("LIST")
            if lst[:4] == b"INFO":
                p = 4
                while p + 8 <= len(lst):
                    sid, ssize = struct.unpack("<4sI", lst[p : p + 8])
                    mf.info[sid.decode("latin-1")] = _text(lst[p + 8 : p + 8 + ssize])
                    p += 8 + ssize + (ssize & 1)
    return mf
