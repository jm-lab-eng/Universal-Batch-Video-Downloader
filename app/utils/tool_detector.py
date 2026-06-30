"""
tool_detector.py
================
Locates bundled binaries (yt-dlp, ffmpeg, ffprobe, ffplay, aria2c, node) by
checking the local bin/ directory first, then falling back to PATH.

No GUI code.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_TOOLS = {
    "ytdlp":   ["yt-dlp.exe", "yt-dlp"],
    "ffmpeg":  ["ffmpeg.exe", "ffmpeg"],
    "ffprobe": ["ffprobe.exe", "ffprobe"],
    "ffplay":  ["ffplay.exe", "ffplay"],
    "aria2":   ["aria2c.exe", "aria2c"],
    "node":    ["node.exe", "node"],
}


@dataclass
class ToolSet:
    ytdlp:   Optional[Path] = None
    ffmpeg:  Optional[Path] = None
    ffprobe: Optional[Path] = None
    ffplay:  Optional[Path] = None
    aria2:   Optional[Path] = None
    node:    Optional[Path] = None

    versions: dict[str, str] = field(default_factory=dict)

    @property
    def ytdlp_ready(self) -> bool:
        return self.ytdlp is not None

    @property
    def ffmpeg_ready(self) -> bool:
        return self.ffmpeg is not None

    @property
    def aria2_ready(self) -> bool:
        return self.aria2 is not None

    def summary(self) -> list[str]:
        lines = []
        for name in ("ytdlp", "ffmpeg", "ffprobe", "ffplay", "aria2", "node"):
            path = getattr(self, name)
            ver = self.versions.get(name, "")
            lines.append(f"✓ {name:<8} {ver}  ({path})" if path else f"✗ {name:<8} NOT FOUND")
        return lines


def detect_tools(bin_dir: Optional[str | Path] = None) -> ToolSet:
    if bin_dir is None:
        bin_dir = Path(__file__).resolve().parent.parent.parent / "bin"
    else:
        bin_dir = Path(bin_dir)

    ts = ToolSet()
    for attr, candidates in _TOOLS.items():
        path = _find_binary(candidates, bin_dir)
        if path:
            setattr(ts, attr, path)
            ver = _get_version(attr, path)
            if ver:
                ts.versions[attr] = ver
    return ts


def _find_binary(candidates: list[str], bin_dir: Path) -> Optional[Path]:
    for name in candidates:
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    for name in candidates:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _get_version(tool_name: str, path: Path) -> str:
    try:
        if tool_name == "ytdlp":
            r = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
            return r.stdout.strip()
        if tool_name in ("ffmpeg", "ffprobe", "ffplay"):
            r = subprocess.run([str(path), "-version"], capture_output=True, text=True, timeout=10)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            parts = first.split()
            return parts[2] if len(parts) > 2 else first
        if tool_name == "aria2":
            r = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            return first.replace("aria2 version", "").strip()
        if tool_name == "node":
            r = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
            return r.stdout.strip()
    except Exception:
        pass
    return ""