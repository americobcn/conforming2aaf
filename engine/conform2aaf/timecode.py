"""Frame rates and SMPTE timecode, including drop-frame."""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

_RATES = {
    "23.976": (Fraction(24000, 1001), 24),
    "23.98": (Fraction(24000, 1001), 24),
    "24": (Fraction(24), 24),
    "25": (Fraction(25), 25),
    "29.97": (Fraction(30000, 1001), 30),
    "30": (Fraction(30), 30),
    "50": (Fraction(50), 50),
    "59.94": (Fraction(60000, 1001), 60),
    "60": (Fraction(60), 60),
}

_TC_RE = re.compile(r"^(\d{1,2})[:;.](\d{2})[:;.](\d{2})[:;.,](\d{2,3})$")


@dataclass(frozen=True)
class FrameRate:
    fps: Fraction
    nominal: int
    drop: bool = False

    @classmethod
    def parse(cls, text: str) -> "FrameRate":
        t = text.strip().lower().replace(" ", "")
        drop = t.endswith("df") and not t.endswith("ndf")
        t = t.removesuffix("ndf").removesuffix("df")
        if t not in _RATES:
            raise ValueError(f"Unsupported frame rate: {text}")
        fps, nominal = _RATES[t]
        if drop and fps.denominator != 1001:
            raise ValueError(f"Drop-frame is only valid for 29.97/59.94: {text}")
        return cls(fps, nominal, drop)

    @classmethod
    def from_fps(cls, fps: Fraction, drop: bool = False) -> "FrameRate":
        for f, nominal in _RATES.values():
            if f == fps:
                return cls(f, nominal, drop and f.denominator == 1001)
        raise ValueError(f"Unsupported frame rate: {float(fps):.3f}")

    @property
    def dropped_per_minute(self) -> int:
        return self.nominal // 15 if self.drop else 0  # 2 @29.97, 4 @59.94

    def __str__(self) -> str:
        label = next(k for k, (f, _) in _RATES.items() if f == self.fps)
        return label + ("DF" if self.drop else "")


def tc_to_frames(tc: str, rate: FrameRate) -> int:
    m = _TC_RE.match(tc.strip())
    if not m:
        raise ValueError(f"Invalid timecode: {tc}")
    h, mi, s, f = (int(g) for g in m.groups())
    if f >= rate.nominal or mi > 59 or s > 59:
        raise ValueError(f"Invalid timecode for {rate}: {tc}")
    total_minutes = h * 60 + mi
    frames = (total_minutes * 60 + s) * rate.nominal + f
    d = rate.dropped_per_minute
    if d:
        if s == 0 and f < d and mi % 10 != 0:
            raise ValueError(f"Timecode does not exist in drop-frame: {tc}")
        frames -= d * (total_minutes - total_minutes // 10)
    return frames


def frames_to_tc(frames: int, rate: FrameRate) -> str:
    if frames < 0:
        raise ValueError("Negative frame count")
    d = rate.dropped_per_minute
    if d:
        per_10min = rate.nominal * 600 - d * 9
        per_min = rate.nominal * 60 - d
        tens, rem = divmod(frames, per_10min)
        extra = 0 if rem < d else d * ((rem - d) // per_min)
        frames += d * 9 * tens + extra
    n = rate.nominal
    f = frames % n
    s = frames // n % 60
    mi = frames // (n * 60) % 60
    h = frames // (n * 3600) % 24
    sep = ";" if rate.drop else ":"
    return f"{h:02d}:{mi:02d}:{s:02d}{sep}{f:02d}"


def frames_to_samples(frames: int | Fraction, rate: FrameRate, sample_rate: int) -> int:
    """Nearest audio sample for a frame position (exact for integer-sample rates)."""
    return round(Fraction(frames) * sample_rate / rate.fps)


def samples_to_frames(samples: int, rate: FrameRate, sample_rate: int) -> Fraction:
    return Fraction(samples) * rate.fps / sample_rate
