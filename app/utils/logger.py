"""
logger.py
=========
Centralised logging: ubvd.app, ubvd.download, ubvd.error.
Rotating file handlers (5 MB x 3 backups) plus console output.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


_LOGS_DIR: Path | None = None


def init_logging(logs_dir: str | Path = "logs") -> None:
    global _LOGS_DIR
    _LOGS_DIR = Path(logs_dir)
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    _setup_logger("ubvd.app",      _LOGS_DIR / "app.log")
    _setup_logger("ubvd.download", _LOGS_DIR / "download.log")
    _setup_logger("ubvd.error",    _LOGS_DIR / "errors.log", level=logging.WARNING)

    get_logger("app").info("Logging initialised — log dir: %s", _LOGS_DIR)


def get_logger(channel: str = "app") -> logging.Logger:
    mapping = {"app": "ubvd.app", "download": "ubvd.download", "error": "ubvd.error"}
    return logging.getLogger(mapping.get(channel, "ubvd.app"))


def _setup_logger(name: str, log_file: Path, level: int = logging.DEBUG) -> None:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(max(level, logging.INFO))
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.propagate = False