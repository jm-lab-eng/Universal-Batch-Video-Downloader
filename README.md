# Universal Batch Video Downloader

**v1.0** — Professional Windows front-end for yt-dlp

A Python + CustomTkinter desktop application supporting YouTube, Vimeo,
direct M3U8 streams, and every site supported by yt-dlp. Built for
intelligent batch downloading with automatic quality selection, cookie
handling, and a live progress queue.

---

## Features

- **Analyze-before-download** — every URL is inspected first; nothing downloads until you review and confirm.
- **Single URL or batch links.txt** — auto-detected, no manual switch needed.
- **YouTube-aware quality picker** — plain-language choices (1080p60 HDR, 720p, Audio only…) instead of yt-dlp format codes; remembers your preference.
- **Automatic cookie handling** — if a video needs sign-in (private, age-restricted, members-only), the app detects it *before* downloading and asks for cookies via paste box or file browser.
- **Batch-wide cookie pre-check** — for links.txt files, every link is checked first; you get one consolidated cookie request instead of one per video.
- **aria2 multi-connection downloads**, ffmpeg muxing, embedded subtitles/thumbnail/metadata.
- **Live download queue** — per-item progress bar, speed, ETA; cancel individual items or all at once.
- **Download archive** — `archive.txt` prevents re-downloading the same video.
- **Auto-numbering** for batch downloads.
- **Persistent settings** in `config.json`.

---

## Project Status

| Milestone | Status |
|-----------|--------|
| v0.1 – UI scaffold, tool detection | ✅ |
| v0.2 – Metadata retrieval, analyzer | ✅ |
| **v1.0 – Full feature set (this release)** | ✅ |

See `CHANGELOG.md` for full details.

---

## Quick Start

### Prerequisites
- Python 3.10+
- `pip install -r requirements.txt`
- Place these binaries in `bin/` (NOT committed to Git):
  - `yt-dlp.exe`
  - `ffmpeg.exe`
  - `ffprobe.exe`
  - `ffplay.exe` *(optional)*
  - `aria2c.exe` *(optional, enables multi-connection downloads)*
  - `node.exe` *(optional, some extractors require it)*

### Run

```bash
python main.py
```

Or on Windows, double-click `run.bat`.

---

## Project Structure

```
Universal-Batch-Video-Downloader/
├── main.py                      # Entry point
├── run.bat                      # Windows launcher
├── requirements.txt
├── config.json                  # Generated on first run (gitignored)
├── .gitignore
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── app/
│   ├── core/
│   │   ├── video_info.py        # yt-dlp -J metadata retrieval
│   │   ├── analyzer.py          # Single/batch detection, auth/cookie pre-check
│   │   ├── config.py            # AppConfig load/save
│   │   ├── command_builder.py   # Builds full yt-dlp CLI commands
│   │   ├── download_engine.py   # Subprocess queue manager
│   │   ├── progress_parser.py   # Parses yt-dlp stdout into events
│   │   └── cookies_helper.py    # Validates/saves cookies (paste or file)
│   │
│   ├── ui/
│   │   ├── main_window.py       # Tab-based main window
│   │   ├── cookies_dialog.py    # Paste / Browse cookie modal
│   │   └── quality_dialog.py    # Human-readable quality picker
│   │
│   └── utils/
│       ├── tool_detector.py     # Locates bundled binaries
│       └── logger.py            # Rotating file + console logging
│
├── bin/                         # Bundled binaries — gitignored
├── docs/                        # Documentation
├── downloads/                   # Default output folder
├── logs/                        # app.log, download.log, errors.log
└── temp/                        # Pasted-cookie temp storage, scratch files
```

---

## How It Works

### 1. Source Detection
Paste a URL or browse to a `.txt` file. The app auto-detects which mode
you're in (`single_url` vs `batch_file`) and shows a live indicator.

### 2. Analysis
Clicking **Analyse** runs `yt-dlp -J` against every URL (one at a time for
batches), reporting live progress. No downloading happens at this stage.

### 3. Cookie Pre-Check
If any item requires sign-in, the app does **not** download the rest and
then fail on the locked ones — it finishes checking every link first, then
shows one summary: *"3 of 10 links require cookies (age-restricted, private)."*
You're prompted once, with two ways to supply cookies:
- **Paste tab** — paste the full Netscape-format cookies.txt contents.
- **Browse tab** — select an existing cookies.txt file on disk.

Once supplied, only the previously-blocked items are re-checked automatically.

### 4. Quality Selection
For each ready item, click **Select Quality** to see a plain-language list:
resolution, fps, HDR, codec, and estimated size. "Best available" is always
the top option. Your choice can be remembered as the default.

### 5. Download Queue
Click **Download All Ready** to build the queue and switch to the Queue tab.
Each item shows a live progress bar, speed, and ETA. Cancel individual items
or the whole queue at any time. Completed items move to the History tab.

---

## Fixing Git History (binaries accidentally committed)

If `bin/` binaries were committed before `.gitignore` excluded them, the
local history needs to be rebuilt before pushing. From the project root:

```powershell
# 1. Back up any uncommitted work first if unsure.

# 2. Remove the existing .git folder to start clean history
Remove-Item -Recurse -Force .git

# 3. Re-initialise
git init
git add .
git status        # confirm bin/ is NOT listed
git commit -m "v1.0 - full feature set, clean history"

# 4. Reconnect remote and force-push
git remote add origin https://github.com/jm-lab-eng/Universal-Batch-Video-Downloader.git
git branch -M main
git push -u origin main --force
```

`--force` is required because the remote's prior history (containing large
binaries) is being replaced. This is safe for a personal/solo project repo.

---

## Building a Portable EXE (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --noconsole --onedir --name "UniversalBatchVideoDownloader" main.py
```

Copy the `bin/` folder into the resulting `dist/UniversalBatchVideoDownloader/`
directory alongside the generated executable before distributing.

---

## License

MIT — see `LICENSE`. Bundled/referenced third-party binaries (yt-dlp, ffmpeg,
aria2, Node.js) are licensed separately and are not distributed in this repo.