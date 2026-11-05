"""Sample conversion with Apple's AudioToolbox, through the bundled `audioconv` tool.

The tool (tools/audioconv/main.swift) reads any file CoreAudio understands and streams raw
24-bit packed little-endian PCM. Chunks and the RIFF container stay in Python (media/prepare.py):
Apple's file writers do not preserve bext/iXML/axml.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

BLOCK = 1 << 20


class AudioToolMissing(RuntimeError):
    pass


@dataclass
class ConvertStats:
    frames: int
    channels: int
    clipped: int  # samples beyond +-1.0 (0 dBFS) that were clamped
    peak: float


def audioconv_path() -> Path:
    """CONFORM2AAF_AUDIOCONV, the app bundle (Resources/engine/bin) or the repo build folder."""
    env = os.environ.get("CONFORM2AAF_AUDIOCONV")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parents[3]
    for candidate in (root / "bin" / "audioconv", root / "build" / "engine" / "bin" / "audioconv"):
        if candidate.is_file():
            return candidate
    raise AudioToolMissing(
        "No se encuentra audioconv (conversión de audio con AudioToolbox). Compila el motor con scripts/build_engine.sh")


def measure_peak(path: Path, channel: int) -> ConvertStats:
    """Peak (before any gain) and clipped-sample count of a channel (0 = all), without writing audio."""
    return convert_pcm24(path, channel, None)


def convert_pcm24(path: Path, channel: int, sink: BinaryIO | None, gain_db: float = 0.0) -> ConvertStats:
    """Write the 24-bit PCM of `path` to `sink`: channel 1..N, or 0 for all channels interleaved.

    gain_db is applied before the conversion. With sink None nothing is written (measure only).
    """
    cmd = [str(audioconv_path()), "--in", str(path), "--channel", str(channel), "--out", "-" if sink else os.devnull]
    if gain_db:
        cmd += ["--gain-db", f"{gain_db:.10f}"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while block := proc.stdout.read(BLOCK):
            if sink:
                sink.write(block)
        err = proc.stderr.read().decode("utf-8", "replace").strip()
        code = proc.wait()
    finally:
        proc.stdout.close()
        proc.stderr.close()
    if code != 0:
        raise RuntimeError(f"audioconv falló con {path.name}: {err}")
    stats = json.loads(err.splitlines()[-1])
    return ConvertStats(stats["frames"], stats["channels"], stats["clipped"], stats["peak"])
