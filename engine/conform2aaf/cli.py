"""Command line entry point. Talks to the app through JSON lines on stdout.

    conform2aaf inspect INPUT --media DIR [--media DIR ...] [--fps 25]
    conform2aaf convert INPUT --media DIR --out OUT.aaf [--fps 25] [--start-tc 01:00:00:00]
                        [--sample-rate 48000] [--choose T:C=/path/file.wav ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

from .media.matcher import Matcher
from .media.riff import read_wav
from .media.scanner import scan
from .model import Timeline
from .readers import read_timeline
from .timecode import FrameRate, frames_to_tc, tc_to_frames
from .writers.aaf import write_aaf


def emit(kind: str, **data) -> None:
    print(json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)


def _tc(t: Fraction | None, rate: FrameRate) -> str | None:
    if t is None or t < 0:
        return None
    return frames_to_tc(int(t * rate.fps), rate)


def report(tl: Timeline, counts: dict) -> dict:
    clips = []
    for ti, track in enumerate(tl.tracks):
        for ci, c in enumerate(track.clips):
            clips.append({
                "id": f"{ti}:{ci}",
                "track": track.name,
                "name": c.name,
                "record_in": _tc(c.record_in, tl.rate),
                "record_out": _tc(c.record_out, tl.rate),
                "source_in": _tc(c.source_in, tl.rate),
                "channel": c.channel,
                "status": c.match_status,
                "note": c.match_note,
                "file": str(c.media.path) if c.media else None,
                "candidates": [str(m.path) for m in c.candidates],
            })
    return {
        "timeline": {
            "name": tl.name,
            "rate": str(tl.rate),
            "start_tc": _tc(tl.start, tl.rate),
            "tracks": [{"name": t.name, "clips": len(t.clips)} for t in tl.tracks],
        },
        "counts": counts,
        "clips": clips,
    }


def _prepare(args) -> tuple[Timeline, dict]:
    rate = FrameRate.parse(args.fps) if args.fps else None
    emit("progress", stage="read", message=f"Leyendo {Path(args.input).name}")
    tl = read_timeline(Path(args.input), rate)
    if args.start_tc:
        tl.start = Fraction(tc_to_frames(args.start_tc, tl.rate)) / tl.rate.fps
    for w in tl.warnings:
        emit("warning", message=w)

    emit("progress", stage="scan", message="Indexando medios")
    files, warnings = scan([Path(m) for m in args.media], recursive=not args.no_recursive)
    for w in warnings:
        emit("warning", message=w)
    n = sum(len(t.clips) for t in tl.tracks)
    emit("progress", stage="match", message=f"Enlazando {n} clips con {len(files)} ficheros")
    counts = Matcher(files).match_timeline(tl)

    for choice in args.choose or []:
        cid, _, path = choice.partition("=")
        ti, _, ci = cid.partition(":")
        clip = tl.tracks[int(ti)].clips[int(ci)]
        counts[clip.match_status] -= 1
        clip.media = read_wav(Path(path))
        clip.match_status, clip.match_note, clip.candidates = "matched", "Elegido manualmente", [clip.media]
        counts["matched"] += 1
    return tl, counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="conform2aaf")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "convert"):
        p = sub.add_parser(name)
        p.add_argument("input")
        p.add_argument("--media", action="append", default=[])
        p.add_argument("--no-recursive", action="store_true")
        p.add_argument("--fps")
        p.add_argument("--start-tc")
        p.add_argument("--choose", action="append")
        if name == "convert":
            p.add_argument("--out", required=True)
            p.add_argument("--sample-rate", type=int, default=48000)
    args = ap.parse_args(argv)

    try:
        tl, counts = _prepare(args)
        emit("report", **report(tl, counts))
        if args.cmd == "convert":
            emit("progress", stage="write", message="Escribiendo AAF")
            res = write_aaf(tl, Path(args.out), args.sample_rate)
            for w in res.warnings:
                emit("warning", message=w)
            emit("result", output=str(Path(args.out).resolve()),
                 clips_written=res.clips_written, clips_skipped=res.clips_skipped)
        return 0
    except Exception as e:  # report every failure to the app instead of a traceback
        emit("error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
