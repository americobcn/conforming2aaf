"""Picture list -> sound tracks: one track per channel of each linked production file."""
from __future__ import annotations

from dataclasses import replace

from .model import Timeline, Track


def expand_to_channels(tl: Timeline) -> int:
    """Replace the picture tracks by one track per source channel (in place).

    Every matched picture clip becomes one clip per channel of its file, at the same
    position. Tracks are named "<n> <iXML name>" (just "<n>" when the file leaves the
    name empty); overlapping cuts spill into "<name> #2"... Returns the number of picture clips that had no file (left out).
    """
    names: dict[int, str] = {}
    by_channel: dict[int, Track] = {}
    skipped = 0
    for clip in tl.clips():
        if clip.match_status != "matched" or clip.media is None:
            skipped += 1
            continue
        for ch in range(1, clip.media.channels + 1):
            if ch - 1 < len(clip.media.track_names) and clip.media.track_names[ch - 1]:
                names.setdefault(ch, clip.media.track_names[ch - 1])
            by_channel.setdefault(ch, Track(str(ch))).clips.append(replace(clip, channel=ch))
    tracks: list[Track] = []
    for ch in sorted(by_channel):
        base = f"{ch} {names[ch]}" if ch in names else str(ch)
        # cuts that overlap in time (stacked video layers) go to extra tracks: nothing is trimmed away
        lanes: list[list] = []
        for clip in sorted(by_channel[ch].clips, key=lambda c: c.record_in):
            for lane in lanes:
                if lane[-1].record_out <= clip.record_in:
                    lane.append(clip)
                    break
            else:
                lanes.append([clip])
        tracks += [Track(base if i == 0 else f"{base} #{i + 1}", lane) for i, lane in enumerate(lanes)]
    tl.tracks = tracks
    return skipped
