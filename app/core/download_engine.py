"""
download_engine.py
===================
Independent download engine. Responsible ONLY for launching yt-dlp via
subprocess, monitoring stdout/stderr, handling cancellation and retries,
and exposing queue-style job states.

No GUI code. Command construction is delegated to command_builder.py.
Progress text parsing is delegated to progress_parser.py.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from app.core.command_builder import DownloadJobSpec, build_ytdlp_command
from app.core.config import AppConfig
from app.core.progress_parser import ProgressEvent, parse_line


class JobState(str, Enum):
    PENDING = "Pending"
    ANALYZING = "Analyzing"
    WAITING = "Waiting"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class DownloadJob:
    """One item in the download queue."""
    job_id: str
    spec: DownloadJobSpec
    state: JobState = JobState.PENDING
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    current_filename: str = ""
    error_message: str = ""
    retries: int = 0
    max_retries: int = 3
    log_lines: list[str] = field(default_factory=list)

    def append_log(self, line: str, limit: int = 500) -> None:
        self.log_lines.append(line)
        if len(self.log_lines) > limit:
            self.log_lines = self.log_lines[-limit:]


JobCallback = Callable[[DownloadJob], None]


class DownloadEngine:
    """
    Manages a queue of DownloadJob objects, running them sequentially or
    in parallel (bounded by config.max_parallel_downloads).

    Usage
    -----
    ::

        engine = DownloadEngine(config, ytdlp_path=..., ffmpeg_path=..., aria2_path=...)
        engine.add_job(spec)
        engine.start(on_update=lambda job: print(job.state, job.percent))
    """

    def __init__(
        self,
        config: AppConfig,
        ytdlp_path: str | Path = "yt-dlp",
        ffmpeg_path: Optional[str | Path] = None,
        aria2_path: Optional[str | Path] = None,
    ):
        self.config = config
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_path = ffmpeg_path
        self.aria2_path = aria2_path

        self._jobs: dict[str, DownloadJob] = {}
        self._job_order: list[str] = []
        self._cancel_flags: dict[str, threading.Event] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._active_count = 0
        self._stop_all = threading.Event()

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def add_job(self, spec: DownloadJobSpec, job_id: Optional[str] = None) -> DownloadJob:
        job_id = job_id or f"job_{len(self._job_order) + 1}_{int(time.time() * 1000)}"
        job = DownloadJob(job_id=job_id, spec=spec)
        with self._lock:
            self._jobs[job_id] = job
            self._job_order.append(job_id)
            self._cancel_flags[job_id] = threading.Event()
        return job

    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def all_jobs(self) -> list[DownloadJob]:
        return [self._jobs[jid] for jid in self._job_order]

    def cancel_job(self, job_id: str) -> None:
        flag = self._cancel_flags.get(job_id)
        if flag:
            flag.set()
        proc = self._processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()

    def cancel_all(self) -> None:
        self._stop_all.set()
        for job_id in list(self._cancel_flags.keys()):
            self.cancel_job(job_id)

    def skip_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job and job.state in (JobState.PENDING, JobState.WAITING):
            job.state = JobState.CANCELLED

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def start(self, on_update: Optional[JobCallback] = None) -> threading.Thread:
        """
        Start processing the queue in a background thread, respecting
        config.max_parallel_downloads. Returns the controller thread.
        """
        self._stop_all.clear()
        t = threading.Thread(target=self._run_queue, args=(on_update,), daemon=True)
        t.start()
        return t

    def _run_queue(self, on_update: Optional[JobCallback]) -> None:
        max_parallel = max(1, self.config.max_parallel_downloads)
        threads: list[threading.Thread] = []

        for job_id in self._job_order:
            if self._stop_all.is_set():
                break

            job = self._jobs[job_id]
            if job.state == JobState.CANCELLED:
                continue

            # Bound parallelism
            while self._active_count >= max_parallel and not self._stop_all.is_set():
                time.sleep(0.2)

            if self._stop_all.is_set():
                break

            job.state = JobState.WAITING
            if on_update:
                on_update(job)

            t = threading.Thread(target=self._run_single_job, args=(job, on_update), daemon=True)
            threads.append(t)
            with self._lock:
                self._active_count += 1
            t.start()

        for t in threads:
            t.join()

    def _run_single_job(self, job: DownloadJob, on_update: Optional[JobCallback]) -> None:
        try:
            job.state = JobState.DOWNLOADING
            if on_update:
                on_update(job)

            while True:
                success = self._execute_job(job, on_update)
                if success or job.state == JobState.CANCELLED:
                    break
                if job.retries >= job.max_retries:
                    job.state = JobState.FAILED
                    break
                job.retries += 1
                job.append_log(f"Retrying ({job.retries}/{job.max_retries}) …")
                job.state = JobState.WAITING
                if on_update:
                    on_update(job)
                time.sleep(2)
                job.state = JobState.DOWNLOADING

            if job.state == JobState.DOWNLOADING:
                job.state = JobState.COMPLETED
            if on_update:
                on_update(job)

        finally:
            with self._lock:
                self._active_count -= 1

    def _execute_job(self, job: DownloadJob, on_update: Optional[JobCallback]) -> bool:
        """Run yt-dlp once for *job*. Returns True on success."""
        cmd = build_ytdlp_command(
            job.spec, self.config,
            ytdlp_path=self.ytdlp_path,
            ffmpeg_location=self.ffmpeg_path,
            aria2_path=self.aria2_path if self.config.use_aria2 else None,
        )

        cancel_flag = self._cancel_flags.get(job.job_id, threading.Event())

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            job.error_message = f"yt-dlp not found at '{self.ytdlp_path}'"
            job.state = JobState.FAILED
            return False

        self._processes[job.job_id] = proc

        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_flag.is_set():
                proc.terminate()
                job.state = JobState.CANCELLED
                job.append_log("Cancelled by user.")
                if on_update:
                    on_update(job)
                return True   # treat as terminal, not a retry-able failure

            event = parse_line(line)
            self._apply_event(job, event)
            if on_update:
                on_update(job)

        proc.wait()
        self._processes.pop(job.job_id, None)

        if proc.returncode == 0:
            job.percent = 100.0
            return True

        job.error_message = job.error_message or f"yt-dlp exited with code {proc.returncode}"
        return False

    def _apply_event(self, job: DownloadJob, event: ProgressEvent) -> None:
        job.append_log(event.raw_line)

        if event.kind == "progress":
            if event.percent is not None:
                job.percent = event.percent
            if event.speed:
                job.speed = event.speed
            if event.eta:
                job.eta = event.eta

        elif event.kind == "destination":
            job.current_filename = event.filename or job.current_filename

        elif event.kind == "merging":
            job.current_filename = event.filename or job.current_filename

        elif event.kind == "finished":
            job.percent = 100.0
            if event.filename:
                job.current_filename = event.filename

        elif event.kind == "error":
            job.error_message = event.message or job.error_message

        elif event.kind == "postprocessing":
            pass  # logged only; could set a "Processing" sub-state in future