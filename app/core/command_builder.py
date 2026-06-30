"""
command_builder.py
===================
Constructs every yt-dlp command line based on user selections: quality,
output template, archive, subtitle/thumbnail/metadata embedding, aria2
integration, ffmpeg options, codec/container preferences, cookies, and
custom arguments.

Separating command generation from execution (download_engine.py) keeps
both pieces independently testable.

No GUI code. No subprocess execution — only builds argument lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.config import AppConfig


@dataclass
class DownloadJobSpec:
    """
    Everything needed to build a yt-dlp command for ONE download.
    Produced by the UI after analysis + quality selection.
    """
    url: str
    download_folder: str
    format_selector: str = "bestvideo+bestaudio/best"   # from QualityOption
    output_filename: Optional[str] = None       # None = yt-dlp default template
    batch_index: Optional[int] = None           # for auto-numbering
    cookies_file: Optional[str] = None
    is_playlist_item: bool = False
    playlist_items: Optional[str] = None        # e.g. "1-5" for partial playlist


def build_ytdlp_command(
    spec: DownloadJobSpec,
    config: AppConfig,
    ytdlp_path: str | Path = "yt-dlp",
    ffmpeg_location: Optional[str | Path] = None,
    aria2_path: Optional[str | Path] = None,
    extra_args: Optional[list[str]] = None,
) -> list[str]:
    """
    Build the full yt-dlp command-line argument list for *spec*.

    Returns a list suitable for ``subprocess.run`` / ``subprocess.Popen``
    (no shell=True needed).
    """
    cmd: list[str] = [str(ytdlp_path)]

    # ── Format selection ────────────────────────────────────────────
    cmd += ["-f", spec.format_selector]

    # Merge output container preference
    if config.preferred_container:
        cmd += ["--merge-output-format", config.preferred_container]

    # ── Output template ─────────────────────────────────────────────
    cmd += ["-o", _build_output_template(spec, config)]

    # ── Embedding features ──────────────────────────────────────────
    if config.embed_subtitles:
        cmd += ["--write-subs", "--embed-subs"]
        if config.subtitle_languages:
            cmd += ["--sub-langs", ",".join(config.subtitle_languages)]
    if config.embed_thumbnail:
        cmd += ["--embed-thumbnail"]
    if config.embed_metadata:
        cmd += ["--embed-metadata"]

    # ── Archive (no duplicate downloads) ────────────────────────────
    if config.use_archive:
        archive_path = Path(spec.download_folder) / "archive.txt"
        cmd += ["--download-archive", str(archive_path)]

    # ── Playlist handling ───────────────────────────────────────────
    if spec.playlist_items:
        cmd += ["--playlist-items", spec.playlist_items]

    # ── FFmpeg location ─────────────────────────────────────────────
    if ffmpeg_location:
        cmd += ["--ffmpeg-location", str(ffmpeg_location)]

    # ── aria2 external downloader ───────────────────────────────────
    if config.use_aria2 and aria2_path:
        cmd += ["--downloader", str(aria2_path)]
        cmd += [
            "--downloader-args",
            f"aria2c:-x {config.aria2_connections} -s {config.aria2_connections} -k 1M",
        ]

    # ── Cookies ──────────────────────────────────────────────────────
    cookies = spec.cookies_file or config.last_cookies_file
    if cookies:
        cmd += ["--cookies", str(cookies)]

    # ── Progress reporting friendliness ─────────────────────────────
    cmd += ["--newline", "--no-warnings", "--no-colors"]
    cmd += ["--progress"]

    # ── Custom / future args ────────────────────────────────────────
    if extra_args:
        cmd += extra_args

    # ── Target URL ───────────────────────────────────────────────────
    cmd.append(spec.url)

    return cmd


def _build_output_template(spec: DownloadJobSpec, config: AppConfig) -> str:
    """
    Decide the -o output template.

    - Single download: "%(title)s.%(ext)s"
    - Batch with auto-numbering enabled: "001 - %(title)s.%(ext)s"
    - Playlist item: "%(playlist_index)s - %(title)s.%(ext)s"
    """
    folder = str(Path(spec.download_folder))

    if spec.output_filename:
        template = spec.output_filename
    elif spec.is_playlist_item:
        template = "%(playlist_index)03d - %(title)s.%(ext)s"
    elif config.auto_number_batch and spec.batch_index is not None:
        template = f"{spec.batch_index:03d} - %(title)s.%(ext)s"
    else:
        template = "%(title)s.%(ext)s"

    return str(Path(folder) / template)


def build_analysis_command(
    url: str,
    ytdlp_path: str | Path = "yt-dlp",
    cookies_file: Optional[str | Path] = None,
) -> list[str]:
    """Build the metadata-only command (mirrors video_info.fetch_video_info)."""
    cmd = [str(ytdlp_path), "--no-warnings", "-J"]
    if cookies_file:
        cmd += ["--cookies", str(cookies_file)]
    cmd.append(url)
    return cmd