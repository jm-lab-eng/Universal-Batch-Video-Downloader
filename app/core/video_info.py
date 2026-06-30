"""
video_info.py
=============
Retrieves complete video metadata from yt-dlp using the -J flag (no download).
Returns a structured VideoInfo dataclass used throughout the application for
quality selection, playlist detection, subtitle detection, metadata display,
authentication detection, and download estimation.

No GUI code. No download logic.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FormatInfo:
    """Represents one available format/stream from yt-dlp."""
    format_id: str
    ext: str
    resolution: str
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    vcodec: str
    acodec: str
    abr: Optional[float]
    tbr: Optional[float]
    filesize: Optional[int]
    filesize_approx: Optional[int]
    dynamic_range: Optional[str]
    note: str
    protocol: str

    @property
    def is_video_only(self) -> bool:
        return self.vcodec != "none" and self.acodec == "none"

    @property
    def is_audio_only(self) -> bool:
        return self.vcodec == "none" and self.acodec != "none"

    @property
    def is_combined(self) -> bool:
        return self.vcodec != "none" and self.acodec != "none"

    @property
    def is_hdr(self) -> bool:
        dr = (self.dynamic_range or "").upper()
        return dr not in ("", "SDR")

    @property
    def size_bytes(self) -> Optional[int]:
        return self.filesize or self.filesize_approx

    @property
    def display_size(self) -> str:
        size = self.size_bytes
        if size is None:
            return "unknown"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def label(self) -> str:
        """Friendly one-line label for the quality picker UI."""
        if self.is_audio_only:
            codec = self.acodec.split(".")[0] if self.acodec else "audio"
            abr = f"{self.abr:.0f}kbps" if self.abr else ""
            return f"Audio only — {codec} {abr} ({self.display_size})".replace("  ", " ")

        parts = []
        if self.height:
            parts.append(f"{self.height}p")
        if self.fps and self.fps > 30:
            parts.append(f"{self.fps:.0f}fps")
        if self.is_hdr:
            parts.append(self.dynamic_range)
        codec = self.vcodec.split(".")[0] if self.vcodec else ""
        if codec:
            parts.append(f"[{codec}]")
        kind = "video+audio" if self.is_combined else "video only"
        parts.append(f"({kind}, {self.display_size})")
        return " ".join(parts) if parts else self.format_id


@dataclass
class SubtitleInfo:
    language: str
    name: str
    formats: list[str]


@dataclass
class ThumbnailInfo:
    url: str
    width: Optional[int]
    height: Optional[int]


@dataclass
class VideoInfo:
    """Complete metadata for a single video / audio item."""
    url: str
    video_id: str
    title: str
    uploader: str
    uploader_url: Optional[str]
    webpage_url: str
    extractor: str

    is_live: bool
    is_playlist: bool
    playlist_count: Optional[int]

    duration: Optional[float]
    upload_date: Optional[str]
    description: Optional[str]
    view_count: Optional[int]
    like_count: Optional[int]
    age_limit: Optional[int]

    formats: list[FormatInfo] = field(default_factory=list)
    subtitles: list[SubtitleInfo] = field(default_factory=list)
    automatic_captions: list[SubtitleInfo] = field(default_factory=list)
    thumbnail: Optional[ThumbnailInfo] = None

    raw: dict = field(default_factory=dict, repr=False)

    # Set by Analyzer
    requires_auth: bool = False
    auth_reason: str = ""   # "age_restricted", "private", "members_only", "login_required", ""

    @property
    def duration_str(self) -> str:
        if self.duration is None:
            return "unknown"
        total = int(self.duration)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    @property
    def platform(self) -> str:
        mapping = {
            "youtube": "YouTube",
            "vimeo": "Vimeo",
            "twitter": "X / Twitter",
            "twitch:stream": "Twitch",
            "twitch:vod": "Twitch",
            "instagram": "Instagram",
            "tiktok": "TikTok",
            "facebook": "Facebook",
            "soundcloud": "SoundCloud",
            "generic": "Generic",
        }
        return mapping.get(self.extractor.lower(), self.extractor.title())

    @property
    def is_youtube(self) -> bool:
        return "youtube" in self.extractor.lower()

    @property
    def best_video_formats(self) -> list[FormatInfo]:
        vids = [f for f in self.formats if f.vcodec != "none"]
        return sorted(vids, key=lambda f: (f.height or 0, f.fps or 0), reverse=True)

    @property
    def best_audio_formats(self) -> list[FormatInfo]:
        auds = [f for f in self.formats if f.is_audio_only]
        return sorted(auds, key=lambda f: f.abr or 0, reverse=True)

    @property
    def combined_formats(self) -> list[FormatInfo]:
        return [f for f in self.formats if f.is_combined]

    @property
    def has_hdr(self) -> bool:
        return any(f.is_hdr for f in self.formats)

    @property
    def max_resolution(self) -> str:
        heights = [f.height for f in self.formats if f.height]
        if not heights:
            return "unknown"
        h = max(heights)
        labels = {2160: "4K", 1440: "1440p", 1080: "1080p", 720: "720p", 480: "480p", 360: "360p"}
        return labels.get(h, f"{h}p")

    @property
    def subtitle_languages(self) -> list[str]:
        return sorted(set(s.language for s in self.subtitles))

    def quality_options(self) -> list["QualityOption"]:
        """
        Build a deduplicated, human-friendly list of quality choices
        for the quality-selector UI. Always includes a 'Best available'
        option first.
        """
        options = [QualityOption(
            key="best",
            label="Best available (auto)",
            format_selector="bestvideo+bestaudio/best",
            height=None, fps=None, hdr=False, size_bytes=None,
        )]

        seen_heights: set[int] = set()
        for f in self.best_video_formats:
            if not f.height or f.height in seen_heights:
                continue
            seen_heights.add(f.height)
            # Pair this video-only stream with best audio at download time
            selector = f"{f.format_id}+bestaudio/best" if f.is_video_only else f.format_id
            size = f.size_bytes
            if size and self.best_audio_formats:
                best_a = self.best_audio_formats[0].size_bytes
                if best_a and f.is_video_only:
                    size = size + best_a
            options.append(QualityOption(
                key=f.format_id,
                label=f.label,
                format_selector=selector,
                height=f.height,
                fps=f.fps,
                hdr=f.is_hdr,
                size_bytes=size,
            ))

        # Audio-only option (for "extract audio" use case)
        if self.best_audio_formats:
            a = self.best_audio_formats[0]
            options.append(QualityOption(
                key="audio_only",
                label=f"Audio only — best ({a.display_size})",
                format_selector="bestaudio/best",
                height=None, fps=None, hdr=False,
                size_bytes=a.size_bytes,
            ))

        return options


@dataclass
class QualityOption:
    """One selectable entry in the quality-picker dropdown."""
    key: str
    label: str
    format_selector: str        # yt-dlp -f value
    height: Optional[int]
    fps: Optional[float]
    hdr: bool
    size_bytes: Optional[int]


# ---------------------------------------------------------------------------
# Fetch function
# ---------------------------------------------------------------------------

class VideoInfoError(Exception):
    """Raised when yt-dlp fails or returns unexpected output."""
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


def fetch_video_info(
    url: str,
    ytdlp_path: str | Path = "yt-dlp",
    cookies_file: Optional[str | Path] = None,
    extra_args: Optional[list[str]] = None,
    timeout: int = 60,
) -> VideoInfo:
    """
    Run ``yt-dlp -J <url>`` and return a populated VideoInfo.
    Raises VideoInfoError on failure (caller inspects message for auth cues).
    """
    cmd = [str(ytdlp_path), "--no-warnings", "-J"]

    if cookies_file:
        cmd += ["--cookies", str(cookies_file)]
    if extra_args:
        cmd += extra_args
    cmd.append(url)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise VideoInfoError(f"yt-dlp timed out after {timeout}s for URL: {url}")
    except FileNotFoundError:
        raise VideoInfoError(
            f"yt-dlp binary not found at '{ytdlp_path}'. "
            "Check that it is present in bin/ or on PATH."
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        reason = _extract_ytdlp_error(stderr)
        raise VideoInfoError(f"yt-dlp returned exit code {result.returncode}: {reason}", stderr=stderr)

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoInfoError(f"yt-dlp returned invalid JSON: {exc}", stderr=result.stderr)

    return _parse_raw(url, raw)


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _extract_ytdlp_error(stderr: str) -> str:
    for line in reversed(stderr.splitlines()):
        line = line.strip()
        if line.startswith("ERROR:"):
            return line[len("ERROR:"):].strip()
    return stderr[:200] if stderr else "unknown error"


def _parse_raw(original_url: str, raw: dict) -> VideoInfo:
    entry_type = raw.get("_type", "video")
    is_playlist = entry_type == "playlist"
    entries = raw.get("entries") or []
    data = raw if not is_playlist else (entries[0] if entries else raw)

    formats = _parse_formats(data.get("formats") or [])
    subtitles = _parse_subtitles(data.get("subtitles") or {})
    auto_caps = _parse_subtitles(data.get("automatic_captions") or {})
    thumbnail = _parse_thumbnail(data.get("thumbnails") or [], data.get("thumbnail"))

    return VideoInfo(
        url=original_url,
        video_id=data.get("id") or raw.get("id") or "",
        title=data.get("title") or raw.get("title") or "(untitled)",
        uploader=data.get("uploader") or data.get("channel") or raw.get("uploader") or "",
        uploader_url=data.get("uploader_url") or data.get("channel_url"),
        webpage_url=data.get("webpage_url") or raw.get("webpage_url") or original_url,
        extractor=data.get("extractor_key") or raw.get("extractor_key") or "generic",
        is_live=bool(data.get("is_live") or data.get("was_live")),
        is_playlist=is_playlist,
        playlist_count=raw.get("playlist_count") if is_playlist else None,
        duration=data.get("duration"),
        upload_date=data.get("upload_date"),
        description=data.get("description"),
        view_count=data.get("view_count"),
        like_count=data.get("like_count"),
        age_limit=data.get("age_limit"),
        formats=formats,
        subtitles=subtitles,
        automatic_captions=auto_caps,
        thumbnail=thumbnail,
        raw=raw,
    )


def _parse_formats(raw_formats: list[dict]) -> list[FormatInfo]:
    result = []
    for f in raw_formats:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        width = f.get("width")
        height = f.get("height")
        if width and height:
            resolution = f"{width}x{height}"
        elif vcodec == "none":
            resolution = "audio only"
        else:
            resolution = "unknown"

        result.append(FormatInfo(
            format_id=f.get("format_id", ""),
            ext=f.get("ext", ""),
            resolution=resolution,
            width=width, height=height, fps=f.get("fps"),
            vcodec=vcodec, acodec=acodec,
            abr=f.get("abr"), tbr=f.get("tbr"),
            filesize=f.get("filesize"), filesize_approx=f.get("filesize_approx"),
            dynamic_range=f.get("dynamic_range"),
            note=f.get("format_note") or "",
            protocol=f.get("protocol") or "",
        ))
    return result


def _parse_subtitles(subs_dict: dict) -> list[SubtitleInfo]:
    result = []
    for lang, tracks in subs_dict.items():
        if not isinstance(tracks, list):
            continue
        name = tracks[0].get("name", lang) if tracks else lang
        formats = [t.get("ext", "") for t in tracks if t.get("ext")]
        result.append(SubtitleInfo(language=lang, name=name, formats=formats))
    return result


def _parse_thumbnail(thumbnails: list[dict], fallback_url: Optional[str]) -> Optional[ThumbnailInfo]:
    if thumbnails:
        best = thumbnails[-1]
        return ThumbnailInfo(url=best.get("url") or fallback_url or "",
                              width=best.get("width"), height=best.get("height"))
    if fallback_url:
        return ThumbnailInfo(url=fallback_url, width=None, height=None)
    return None