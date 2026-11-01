"""Test helpers: synthetic broadcast WAV files with metadata chunks."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest


def _chunk(cid: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) & 1 else b""
    return struct.pack("<4sI", cid, len(data)) + data + pad


def make_wav(
    path: Path,
    seconds: float = 1.0,
    sample_rate: int = 48000,
    channels: int = 1,
    bits: int = 24,
    time_reference: int | None = None,
    description: str = "",
    scene: str = "",
    take: str = "",
    tape: str = "",
    track_names: list[str] | None = None,
    info: dict[str, str] | None = None,
    rf64: bool = False,
    fill: bool = False,
    extensible: bool = False,
) -> Path:
    block = channels * bits // 8
    frames = int(seconds * sample_rate)
    fmt = struct.pack("<HHIIHH", 1, channels, sample_rate, sample_rate * block, block, bits)
    if extensible:  # WAVE_FORMAT_EXTENSIBLE: cbSize 22, valid bits, channel mask, PCM sub-format GUID
        fmt = struct.pack("<HHIIHH", 0xFFFE, channels, sample_rate, sample_rate * block, block, bits)
        fmt += struct.pack("<HHI", 22, bits, 3) + struct.pack("<H", 1) + bytes.fromhex("000000001000800000aa00389b71")
    body = _chunk(b"fmt ", fmt)
    if time_reference is not None or description:
        tr = time_reference or 0
        bext = (
            description.encode().ljust(256, b"\x00")
            + b"TestRecorder".ljust(32, b"\x00")
            + b"".ljust(32, b"\x00")
            + b"2026-11-01"
            + b"10:00:00"
            + struct.pack("<II", tr & 0xFFFFFFFF, tr >> 32)
            + struct.pack("<H", 1)
            + b"\x00" * 254
        )
        body += _chunk(b"bext", bext)
    if scene or take or tape or track_names:
        tracks = "".join(
            f"<TRACK><CHANNEL_INDEX>{i + 1}</CHANNEL_INDEX><NAME>{n}</NAME></TRACK>"
            for i, n in enumerate(track_names or [])
        )
        ixml = (
            f"<?xml version='1.0'?><BWFXML><PROJECT>TestProj</PROJECT><SCENE>{scene}</SCENE>"
            f"<TAKE>{take}</TAKE><TAPE>{tape}</TAPE><TRACK_LIST>{tracks}</TRACK_LIST></BWFXML>"
        )
        body += _chunk(b"iXML", ixml.encode())
    if info:
        sub = b"".join(_chunk(k.encode(), v.encode() + b"\x00") for k, v in info.items())
        body += _chunk(b"LIST", b"INFO" + sub)
    if fill:  # frame f, channel c -> bytes (c + 1, f % 251, 7, ...)
        w = bits // 8
        data = b"".join(
            bytes(((c + 1) % 256, f % 251) + (7,) * (w - 2)) for f in range(frames) for c in range(channels)
        )
    else:
        data = b"\x00" * (frames * block)
    if rf64:
        ds64 = _chunk(b"ds64", struct.pack("<QQQI", 0, len(data), frames, 0))
        out = b"RF64" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE" + ds64 + body
        out += struct.pack("<4sI", b"data", 0xFFFFFFFF) + data
    else:
        payload = b"WAVE" + body + _chunk(b"data", data)
        out = b"RIFF" + struct.pack("<I", len(payload)) + payload
    path.write_bytes(out)
    return path


@pytest.fixture
def wav_factory(tmp_path):
    def factory(name: str, **kw) -> Path:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return make_wav(p, **kw)

    return factory
