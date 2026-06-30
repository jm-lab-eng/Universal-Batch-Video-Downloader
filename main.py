"""
main.py
=======
Entry point for Universal Batch Video Downloader.

Run with:
    python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.logger import init_logging, get_logger
from app.utils.tool_detector import detect_tools
from app.ui.main_window import MainWindow


def main() -> None:
    init_logging(ROOT / "logs")
    log = get_logger("app")
    log.info("=== Universal Batch Video Downloader v1.0 starting ===")

    bin_dir = ROOT / "bin"
    log.info("Detecting tools in: %s", bin_dir)
    tools = detect_tools(bin_dir)
    for line in tools.summary():
        log.info(line)

    if not tools.ytdlp_ready:
        log.warning("yt-dlp not found. Place yt-dlp.exe in %s or ensure it is on PATH.", bin_dir)

    app = MainWindow(tools=tools)
    app.mainloop()
    log.info("Application closed.")


if __name__ == "__main__":
    main()