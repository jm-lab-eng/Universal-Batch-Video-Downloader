"""
config.py
=========
Loads and saves application settings to config.json in the project root.

No GUI code.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass
class AppConfig:
    # Folders
    download_folder: str = ""
    cookies_folder: str = ""

    # Quality preferences (per-session default; can be overridden per item)
    preferred_quality_key: str = "best"     # matches QualityOption.key
    preferred_audio_only: bool = False

    # yt-dlp feature toggles
    embed_subtitles: bool = True
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    subtitle_languages: list[str] = field(default_factory=lambda: ["en"])

    # Engine
    use_aria2: bool = True
    aria2_connections: int = 16
    use_archive: bool = True
    auto_number_batch: bool = True

    # Container / codec preference
    preferred_container: str = "mp4"        # mp4, mkv, webm

    # UI
    theme: str = "dark"

    # Cookies
    last_cookies_file: str = ""

    # Concurrency
    max_parallel_downloads: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        # Only accept known fields; ignore unknown keys for forward-compat
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load config.json, returning defaults if missing or invalid."""
    path = Path(path)
    if not path.is_file():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return AppConfig()


def save_config(config: AppConfig, path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    """Write config to config.json (pretty-printed)."""
    path = Path(path)
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")