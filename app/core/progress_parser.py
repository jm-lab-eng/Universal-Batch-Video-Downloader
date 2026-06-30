"""
progress_parser.py
===================
Parses yt-dlp stdout (run with --newline --progress) line by line and
extracts structured progress events: percentage, speed, ETA, filename,
merge status, and completion.

No GUI code. No subprocess management — pure text parsing, fed lines by
download_engine.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Typical yt-dlp progress line:
# [download]  45.2% of   123.45MiB at    2.34MiB/s ETA 00:42
_PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>[\d.]+)%\s+of\s+(?:~\s*)?(?P<size>[\d.]+\w+)"
    r"(?:\s+at\s+(?P<speed>[\d.]+\w+/s|Unknown speed))?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+|Unknown ETA))?"
)

_DESTINATION_RE = re.compile(r"\[download\]\s+Destination:\s+(?P<filename>.+)")
_ALREADY_RE = re.compile(r"\[download\]\s+(?P<filename>.+)\s+has already been downloaded")
_MERGING_RE = re.compile(r"\[Merger\]\s+Merging formats into\s+\"(?P<filename>.+)\"")
_EXTRACTING_RE = re.compile(r"\[(?:ExtractAudio|VideoConvertor|EmbedThumbnail|FFmpeg)\]")
_FINISHED_RE = re.compile(r"\[download\]\s+100%")
_ERROR_RE = re.compile(r"ERROR:\s*(?P<message>.+)")
_WARNING_RE = re.compile(r"WARNING:\s*(?P<message>.+)")


@dataclass
class ProgressEvent:
    """One parsed event from a single line of yt-dlp output."""
    kind: str                       # "progress", "destination", "merging",
                                     # "postprocessing", "finished",
                                     # "error", "warning", "other"
    percent: Optional[float] = None
    speed: Optional[str] = None
    eta: Optional[str] = None
    size: Optional[str] = None
    filename: Optional[str] = None
    message: Optional[str] = None
    raw_line: str = ""


def parse_line(line: str) -> ProgressEvent:
    """Parse a single line of yt-dlp stdout/stderr into a ProgressEvent."""
    line = line.rstrip("\n").rstrip("\r")

    m = _PROGRESS_RE.search(line)
    if m:
        return ProgressEvent(
            kind="progress",
            percent=_safe_float(m.group("percent")),
            speed=m.group("speed"),
            eta=m.group("eta"),
            size=m.group("size"),
            raw_line=line,
        )

    m = _DESTINATION_RE.search(line)
    if m:
        return ProgressEvent(kind="destination", filename=m.group("filename"), raw_line=line)

    m = _ALREADY_RE.search(line)
    if m:
        return ProgressEvent(kind="finished", filename=m.group("filename"),
                              message="Already downloaded", raw_line=line)

    m = _MERGING_RE.search(line)
    if m:
        return ProgressEvent(kind="merging", filename=m.group("filename"), raw_line=line)

    if _EXTRACTING_RE.search(line):
        return ProgressEvent(kind="postprocessing", message=line.strip(), raw_line=line)

    if _FINISHED_RE.search(line):
        return ProgressEvent(kind="finished", percent=100.0, raw_line=line)

    m = _ERROR_RE.search(line)
    if m:
        return ProgressEvent(kind="error", message=m.group("message"), raw_line=line)

    m = _WARNING_RE.search(line)
    if m:
        return ProgressEvent(kind="warning", message=m.group("message"), raw_line=line)

    return ProgressEvent(kind="other", raw_line=line)


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None