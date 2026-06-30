"""
cookies_helper.py
==================
Handles both supported cookie input methods:
1. User pastes the raw contents of a Netscape-format cookies.txt
2. User browses to an existing cookies.txt file on disk

Validates basic Netscape cookie file format and saves pasted content to
a file so it can be passed to yt-dlp via --cookies.

No GUI code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


class CookiesValidationError(Exception):
    """Raised when supplied cookie content/file does not look valid."""


def looks_like_netscape_cookies(text: str) -> bool:
    """
    Loose validation: a Netscape cookies.txt has either the standard
    header comment, or at least one tab-separated 7-field data line.
    """
    if NETSCAPE_HEADER in text:
        return True

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) == 7:
            return True
    return False


def save_pasted_cookies(
    text: str,
    destination_dir: str | Path = "temp",
    filename: str = "cookies.txt",
) -> Path:
    """
    Validate and save pasted cookie text to a file.

    Raises CookiesValidationError if the text doesn't look like a valid
    Netscape cookies.txt.

    Returns the path to the saved file.
    """
    text = text.strip()
    if not text:
        raise CookiesValidationError("Cookie text is empty.")

    if not looks_like_netscape_cookies(text):
        raise CookiesValidationError(
            "This doesn't look like a valid Netscape cookies.txt export. "
            "Use a browser extension (e.g. 'Get cookies.txt') to export cookies "
            "in Netscape format, then paste the full contents here."
        )

    dest_dir = Path(destination_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    # Ensure the file starts with the standard header for yt-dlp compatibility
    if NETSCAPE_HEADER not in text:
        text = NETSCAPE_HEADER + "\n" + text

    dest_path.write_text(text, encoding="utf-8")
    return dest_path


def validate_cookies_file(path: str | Path) -> Path:
    """
    Validate an existing cookies.txt file path.

    Raises CookiesValidationError if missing or invalid format.
    Returns the resolved Path on success.
    """
    p = Path(path)
    if not p.is_file():
        raise CookiesValidationError(f"File not found: {p}")

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CookiesValidationError(f"Could not read file: {exc}")

    if not looks_like_netscape_cookies(content):
        raise CookiesValidationError(
            "This file doesn't look like a valid Netscape cookies.txt export."
        )

    return p