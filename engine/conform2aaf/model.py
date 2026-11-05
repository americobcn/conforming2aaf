"""Format-neutral timeline model. All times are exact rational seconds."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .timecode import FrameRate


@dataclass
class MediaFile:
    path: Path
    sample_rate: int
    channels: int
    bits: int
    frames: int  # audio sample frames
    time_reference: int | None = None  # bext: samples since midnight
    description: str = ""
    originator: str = ""
    scene: str = ""
    take: str = ""
    tape: str = ""
    project: str = ""
    track_names: list[str] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    format_tag: int = 1  # 1 = PCM, 3 = IEEE float
    block_align: int = 0
    rf64: bool = False
    applied_gain_db: float = 0.0  # level lowered when converting float to 24 bit so it does not clip

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def start(self) -> Fraction | None:
        """Source timecode of the first sample, in seconds since midnight."""
        if self.time_reference is None:
            return None
        return Fraction(self.time_reference, self.sample_rate)

    @property
    def duration(self) -> Fraction:
        return Fraction(self.frames, self.sample_rate)


@dataclass
class Clip:
    name: str
    record_in: Fraction  # timeline position, seconds (absolute record TC)
    duration: Fraction
    source_in: Fraction | None = None  # absolute source TC, seconds since midnight
    reel: str = ""
    file_hint: str = ""  # path or file name from the edit list, if any
    channel: int | None = None  # 1-based source channel
    gain_db: float = 0.0
    fade_in: Fraction = Fraction(0)
    fade_out: Fraction = Fraction(0)
    # Crossfade from the previous clip on the track. record_in is the cut point;
    # crossfade_pre is how much of the crossfade lies before the cut.
    crossfade_in: Fraction = Fraction(0)
    crossfade_pre: Fraction = Fraction(0)
    scene: str = ""  # from the edit list (picture metadata), used to match production audio
    take: str = ""
    tape: str = ""
    media: MediaFile | None = None
    match_status: str = "unmatched"  # matched | ambiguous | missing
    match_note: str = ""
    candidates: list[MediaFile] = field(default_factory=list)

    @property
    def record_out(self) -> Fraction:
        return self.record_in + self.duration


@dataclass
class Track:
    name: str
    clips: list[Clip] = field(default_factory=list)


@dataclass
class Timeline:
    name: str
    rate: FrameRate
    start: Fraction = Fraction(0)  # record TC of the timeline start, seconds
    tracks: list[Track] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    picture: bool = False  # clips are picture cuts: production sound is conformed to them

    def clips(self):
        for t in self.tracks:
            yield from t.clips
