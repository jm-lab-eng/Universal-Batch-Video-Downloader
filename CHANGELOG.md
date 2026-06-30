# Changelog

All notable changes to this project are documented in this file.

## [v1.0] — Current

### Added
- `app/core/command_builder.py` — builds complete yt-dlp command lines: format selection, output templates, archive support, subtitle/thumbnail/metadata embedding, aria2 integration, ffmpeg location, cookies, container/codec preferences, auto-numbering, playlist item ranges.
- `app/core/progress_parser.py` — parses yt-dlp `--newline --progress` stdout into structured `ProgressEvent` objects (percent, speed, ETA, filename, merge status, errors, warnings).
- `app/core/download_engine.py` — independent subprocess-based download engine with `DownloadJob` / `JobState` queue model (Pending → Analyzing → Waiting → Downloading → Completed / Failed / Cancelled), cancellation, automatic retries, bounded parallel downloads.
- `app/core/config.py` — `AppConfig` dataclass persisted to `config.json`: folders, quality defaults, embedding toggles, aria2 settings, container preference, parallelism, theme, last-used cookies path.
- `app/core/cookies_helper.py` — validates and saves cookies, supporting **both** input methods: pasted Netscape-format text and browsing to an existing `cookies.txt` file.
- `app/ui/cookies_dialog.py` — modal cookie-request dialog with tabbed Paste / Browse interface, shown automatically when authentication is required.
- `app/ui/quality_dialog.py` — modal quality-selection dialog showing human-readable options (resolution, fps, HDR, codec, estimated size) instead of raw format IDs; supports "remember as default."
- Single-URL vs. links.txt **auto-detection** (`analyzer.classify_input`) with live UI indicator.
- **Batch cookie pre-check**: every link in a links.txt file is analysed first; the app reports a single consolidated summary of how many are ready, how many need cookies, and how many are unavailable — before any cookie prompt or download begins.
- YouTube-specific quality detection: full list of available resolutions/codecs/HDR/audio bitrates surfaced via `VideoInfo.quality_options()`.
- Full tab-based UI: **Download / Queue / History / Settings / About**.
- Live per-item progress bars in the Queue tab (percent, speed, ETA, current filename).
- History tab logging completed downloads.
- Settings tab: embedding toggles, aria2 toggle + connections, archive toggle, auto-numbering, parallel download count, container preference — all persisted to `config.json`.
- `run.bat` Windows launcher.
- `LICENSE` (MIT, with third-party binary notice).

### Changed
- `app/core/analyzer.py` — added `classify_input()`, expanded auth-reason detection (private / members-only / age-restricted / login-required), added `reanalyze_with_cookies()` / `reanalyze_async()` for retry-after-cookies flow, added `AnalysisResult.needs_cookies`.
- `app/core/video_info.py` — added `QualityOption` dataclass and `VideoInfo.quality_options()` for the quality picker; added `is_youtube` property.
- `app/utils/tool_detector.py` — added `ffplay` detection.
- `main.py` — updated version banner to v1.0.

### Fixed
- Renamed `QualityDialog._options` → `_quality_options` to avoid shadowing CustomTkinter's internal `_options()` method, which caused a `TypeError: 'list' object is not callable` on dialog construction.

---

## [v0.2]
### Added
- `app/core/video_info.py` — `VideoInfo`, `FormatInfo`, `SubtitleInfo`, `ThumbnailInfo` dataclasses; `fetch_video_info()` running `yt-dlp -J`.
- `app/core/analyzer.py` — `Analyzer` class, sync + async analysis, `AnalysisResult` / `AnalyzedItem`, platform detection, auth detection from metadata and error messages.
- `app/utils/tool_detector.py` — binary detection for yt-dlp, ffmpeg, ffprobe, aria2, node.
- `app/utils/logger.py` — rotating file + console logging on three channels.
- Updated `app/ui/main_window.py` — live analysis log, metadata results panel.

## [v0.1]
### Added
- Initial CustomTkinter scaffold.
- Tool detection (yt-dlp, ffmpeg).
- Source and download-folder selection.
- Preliminary analyzer stub (platform detection only).