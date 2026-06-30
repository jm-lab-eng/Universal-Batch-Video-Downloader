"""
analyzer.py
===========
Central intelligence of the application.

Responsibilities
----------------
- Detect whether the input is a single URL or a links.txt batch file.
- Identify the platform (YouTube, Vimeo, M3U8, Generic) per URL.
- Call video_info.fetch_video_info() for every URL.
- Detect authentication / cookie requirements BEFORE any download starts.
- For batches: check every link first, then summarise how many are ready,
  how many need cookies, and how many are unavailable.
- Re-run analysis automatically once cookies are supplied.

No GUI code. No download logic.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.core.video_info import VideoInfo, VideoInfoError, fetch_video_info


# ---------------------------------------------------------------------------
# Source type detection
# ---------------------------------------------------------------------------

_YOUTUBE_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/",
    r"(?:https?://)?(?:www\.)?youtu\.be/",
    r"(?:https?://)?(?:m\.)?youtube\.com/",
]
_VIMEO_PATTERNS = [r"(?:https?://)?(?:www\.)?vimeo\.com/"]
_M3U8_PATTERNS = [r"\.m3u8(\?|$)", r"/m3u8"]
_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def detect_source_type(url: str) -> str:
    """Return 'YouTube', 'Vimeo', 'M3U8', or 'Generic' for a URL."""
    u = url.lower()
    for pat in _YOUTUBE_PATTERNS:
        if re.search(pat, u):
            return "YouTube"
    for pat in _VIMEO_PATTERNS:
        if re.search(pat, u):
            return "Vimeo"
    for pat in _M3U8_PATTERNS:
        if re.search(pat, u):
            return "M3U8"
    return "Generic"


def classify_input(source: str) -> str:
    """
    Determine how to treat the user's input.

    Returns one of:
    - "single_url"   — a single http(s) URL was pasted
    - "batch_file"    — an existing .txt (or other) file path was given
    - "invalid"       — neither a valid URL nor an existing file
    """
    stripped = source.strip()
    if not stripped:
        return "invalid"

    path = Path(stripped)
    if path.is_file():
        return "batch_file"

    if _URL_PATTERN.match(stripped):
        return "single_url"

    # Edge case: user pasted a bare domain without scheme, or a non-existent
    # file path. Treat anything containing a path separator AND ending in
    # .txt as an (missing) batch file attempt; otherwise assume URL typo.
    if stripped.lower().endswith(".txt"):
        return "batch_file"

    return "invalid"


_AUTH_PHRASES = {
    "private": ("private video", "this is a private video"),
    "members_only": ("members only", "membership required", "join this channel"),
    "age_restricted": ("age-restricted", "age restricted", "confirm your age", "sign in to confirm your age"),
    "login_required": ("sign in", "log in", "login required"),
}


def _detect_auth_from_error(error_message: str) -> tuple[bool, str]:
    """Inspect a yt-dlp error string and decide if auth/cookies are the cause."""
    msg = error_message.lower()
    for reason, phrases in _AUTH_PHRASES.items():
        if any(p in msg for p in phrases):
            return True, reason
    if "not available" in msg and ("country" not in msg):
        return True, "login_required"
    return False, ""


def _detect_auth_from_info(info: VideoInfo) -> tuple[bool, str]:
    """Inspect successfully-retrieved metadata for implicit auth signals."""
    age = info.age_limit or 0
    if age >= 18:
        return True, "age_restricted"
    return False, ""


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

AUTH_REASON_LABELS = {
    "private": "Private video",
    "members_only": "Members-only content",
    "age_restricted": "Age-restricted (sign-in required)",
    "login_required": "Sign-in required",
}


@dataclass
class AnalyzedItem:
    url: str
    source_type: str
    status: str             # "ready", "auth_required", "unavailable", "error"
    info: Optional[VideoInfo] = None
    error_message: str = ""
    auth_reason: str = ""

    @property
    def auth_reason_label(self) -> str:
        return AUTH_REASON_LABELS.get(self.auth_reason, self.auth_reason or "Authentication required")


@dataclass
class AnalysisResult:
    source_url: str
    is_batch: bool
    input_kind: str = "single_url"     # "single_url" | "batch_file"

    items: list[AnalyzedItem] = field(default_factory=list)
    is_complete: bool = False
    cancelled: bool = False

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def ready(self) -> list[AnalyzedItem]:
        return [i for i in self.items if i.status == "ready"]

    @property
    def auth_required(self) -> list[AnalyzedItem]:
        return [i for i in self.items if i.status == "auth_required"]

    @property
    def unavailable(self) -> list[AnalyzedItem]:
        return [i for i in self.items if i.status in ("unavailable", "error")]

    @property
    def ready_count(self) -> int:
        return len(self.ready)

    @property
    def auth_count(self) -> int:
        return len(self.auth_required)

    @property
    def unavailable_count(self) -> int:
        return len(self.unavailable)

    @property
    def needs_cookies(self) -> bool:
        return self.auth_count > 0

    @property
    def playlist_count(self) -> int:
        return sum(1 for i in self.items if i.info and i.info.is_playlist)

    @property
    def estimated_total_bytes(self) -> Optional[int]:
        total = 0
        has_any = False
        for item in self.items:
            if not item.info:
                continue
            for fmt in item.info.formats:
                size = fmt.filesize or fmt.filesize_approx
                if size:
                    total += size
                    has_any = True
                    break
        return total if has_any else None

    @property
    def estimated_size_str(self) -> str:
        size = self.estimated_total_bytes
        if size is None:
            return "unknown"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def summary_lines(self) -> list[str]:
        lines = [
            f"Total URLs analysed : {self.total}",
            f"Ready to download   : {self.ready_count}",
        ]
        if self.auth_count:
            lines.append(f"Require cookies     : {self.auth_count}")
        if self.unavailable_count:
            lines.append(f"Unavailable / error : {self.unavailable_count}")
        if self.playlist_count:
            lines.append(f"Playlists detected  : {self.playlist_count}")
        lines.append(f"Est. total size     : {self.estimated_size_str}")
        return lines


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str], None]


class Analyzer:
    """
    Runs analysis on a single URL or a links.txt batch file.

    Cookie workflow
    ----------------
    1. analyze() runs without cookies first.
    2. If result.needs_cookies is True, the UI should prompt for cookies
       (paste box or file browse) and call reanalyze_with_cookies().
    3. reanalyze_with_cookies() re-runs ONLY the items that previously
       required auth, using the supplied cookies file.
    """

    def __init__(
        self,
        ytdlp_path: str | Path = "yt-dlp",
        cookies_file: Optional[str | Path] = None,
        timeout: int = 60,
    ):
        self.ytdlp_path = Path(ytdlp_path)
        self.cookies_file = Path(cookies_file) if cookies_file else None
        self.timeout = timeout
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def analyze(
        self,
        source: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AnalysisResult:
        """Analyse a single URL or every line of a links.txt file."""
        self._cancel_event.clear()

        kind = classify_input(source)
        if kind == "invalid":
            result = AnalysisResult(source_url=source, is_batch=False, input_kind="invalid")
            result.items.append(AnalyzedItem(
                url=source, source_type="Generic", status="error",
                error_message="Input is neither a valid URL nor an existing links.txt file.",
            ))
            result.is_complete = True
            return result

        if kind == "batch_file":
            urls = self._read_links_file(Path(source))
            result = AnalysisResult(source_url=source, is_batch=True, input_kind="batch_file")
        else:
            urls = [source.strip()]
            result = AnalysisResult(source_url=source, is_batch=False, input_kind="single_url")

        total = len(urls)
        for idx, url in enumerate(urls, start=1):
            if self._cancel_event.is_set():
                result.cancelled = True
                break
            if progress_callback:
                progress_callback(idx, total, f"Analysing [{idx}/{total}]: {url[:80]}")
            result.items.append(self._analyze_single(url))

        result.is_complete = not result.cancelled
        return result

    def reanalyze_with_cookies(
        self,
        result: AnalysisResult,
        cookies_file: str | Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AnalysisResult:
        """
        Re-run analysis only for items that previously required auth,
        using the supplied cookies file. Returns a NEW AnalysisResult
        with updated statuses; items that were already ready/unavailable
        are carried over unchanged.
        """
        self.cookies_file = Path(cookies_file)
        self._cancel_event.clear()

        to_retry = [i for i in result.items if i.status == "auth_required"]
        carried = [i for i in result.items if i.status != "auth_required"]

        new_result = AnalysisResult(
            source_url=result.source_url,
            is_batch=result.is_batch,
            input_kind=result.input_kind,
        )
        new_result.items.extend(carried)

        total = len(to_retry)
        for idx, item in enumerate(to_retry, start=1):
            if self._cancel_event.is_set():
                new_result.cancelled = True
                break
            if progress_callback:
                progress_callback(idx, total, f"Retrying with cookies [{idx}/{total}]: {item.url[:80]}")
            new_result.items.append(self._analyze_single(item.url))

        new_result.is_complete = not new_result.cancelled
        return new_result

    def analyze_async(
        self,
        source: str,
        on_progress: Optional[ProgressCallback] = None,
        on_complete: Optional[Callable[[AnalysisResult], None]] = None,
    ) -> threading.Thread:
        def _run():
            result = self.analyze(source, progress_callback=on_progress)
            if on_complete:
                on_complete(result)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def reanalyze_async(
        self,
        result: AnalysisResult,
        cookies_file: str | Path,
        on_progress: Optional[ProgressCallback] = None,
        on_complete: Optional[Callable[[AnalysisResult], None]] = None,
    ) -> threading.Thread:
        def _run():
            new_result = self.reanalyze_with_cookies(result, cookies_file, progress_callback=on_progress)
            if on_complete:
                on_complete(new_result)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_links_file(self, path: Path) -> list[str]:
        lines = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        return lines

    def _analyze_single(self, url: str) -> AnalyzedItem:
        source_type = detect_source_type(url)
        try:
            info = fetch_video_info(
                url=url, ytdlp_path=self.ytdlp_path,
                cookies_file=self.cookies_file, timeout=self.timeout,
            )
            requires_auth, auth_reason = _detect_auth_from_info(info)
            info.requires_auth = requires_auth
            info.auth_reason = auth_reason
            status = "auth_required" if requires_auth else "ready"
            return AnalyzedItem(url=url, source_type=source_type, status=status,
                                 info=info, auth_reason=auth_reason)

        except VideoInfoError as exc:
            requires_auth, auth_reason = _detect_auth_from_error(str(exc) + " " + exc.stderr)
            if requires_auth:
                return AnalyzedItem(url=url, source_type=source_type, status="auth_required",
                                     error_message=str(exc), auth_reason=auth_reason)

            err_lower = str(exc).lower()
            unavailable_signals = (
                "video unavailable", "has been removed",
                "account has been terminated", "content not available", "404",
            )
            if any(s in err_lower for s in unavailable_signals):
                return AnalyzedItem(url=url, source_type=source_type, status="unavailable",
                                     error_message=str(exc))

            return AnalyzedItem(url=url, source_type=source_type, status="error",
                                 error_message=str(exc))