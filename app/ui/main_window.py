"""
main_window.py
==============
Primary CustomTkinter application window, v1.0.

Tab layout
----------
- Download : source input, analysis, per-item quality selection, start
- Queue    : live progress for active/pending downloads
- History  : completed download log
- Settings : folders, quality defaults, embedding options, aria2, theme
- About    : version info, links

Cookie + auth flow
------------------
1. analyze() runs without cookies.
2. If any items need auth, CookiesDialog is shown (paste OR browse).
3. On success, analyzer.reanalyze_with_cookies() retries only those items.
4. For batch files, ALL links are checked first before any cookie prompt,
   so the user sees one consolidated request rather than one per video.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from app.core.analyzer import AnalysisResult, Analyzer, AnalyzedItem
from app.core.command_builder import DownloadJobSpec
from app.core.config import AppConfig, load_config, save_config
from app.core.download_engine import DownloadEngine, DownloadJob, JobState
from app.utils.logger import get_logger
from app.utils.tool_detector import ToolSet, detect_tools
from app.ui.cookies_dialog import CookiesDialog
from app.ui.quality_dialog import QualityDialog

log = get_logger("app")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_APP_TITLE = "Universal Batch Video Downloader"
_VERSION = "v1.0"

STATUS_COLORS = {
    "ready":         ("#4caf50", "✓ Ready"),
    "auth_required": ("#ff9800", "⚠ Needs Cookies"),
    "unavailable":   ("#f44336", "✗ Unavailable"),
    "error":         ("#f44336", "✗ Error"),
}

JOB_STATE_COLORS = {
    JobState.PENDING:     "#888",
    JobState.ANALYZING:   "#64b5f6",
    JobState.WAITING:     "#ffb74d",
    JobState.DOWNLOADING: "#4fc3f7",
    JobState.COMPLETED:   "#4caf50",
    JobState.FAILED:      "#f44336",
    JobState.CANCELLED:   "#777",
}


class MainWindow(ctk.CTk):
    def __init__(self, tools: ToolSet):
        super().__init__()
        self.tools = tools
        self.config_obj: AppConfig = load_config()

        self._analyzer: Optional[Analyzer] = None
        self._result: Optional[AnalysisResult] = None
        self._cookies_file: Optional[Path] = None
        self._item_quality: dict[str, str] = {}   # url -> format_selector

        self._engine: Optional[DownloadEngine] = None
        self._job_rows: dict[str, dict] = {}        # job_id -> widget refs

        self.title(f"{_APP_TITLE}  {_VERSION}")
        self.geometry("1000x780")
        self.minsize(860, 640)

        self._build_ui()
        self._refresh_tool_status()
        log.info("MainWindow initialised (v1.0).")

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Tool status bar
        self._tool_bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        self._tool_bar.grid(row=0, column=0, sticky="ew")
        self._tool_label = ctk.CTkLabel(self._tool_bar, text="Checking tools …",
                                         font=ctk.CTkFont(size=12), anchor="w")
        self._tool_label.pack(side="left", padx=12, pady=4)

        # Tabs
        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        self._tab_download = self._tabs.add("Download")
        self._tab_queue = self._tabs.add("Queue")
        self._tab_history = self._tabs.add("History")
        self._tab_settings = self._tabs.add("Settings")
        self._tab_about = self._tabs.add("About")

        self._build_download_tab()
        self._build_queue_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self._build_about_tab()

    # ------------------------------------------------------------------
    # Download tab
    # ------------------------------------------------------------------

    def _build_download_tab(self) -> None:
        tab = self._tab_download
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        # Source
        src_frame = ctk.CTkFrame(tab)
        src_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=6)
        src_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(src_frame, text="Source:", width=80, anchor="w").grid(row=0, column=0, padx=(8, 4), pady=6)
        self._source_var = tk.StringVar()
        ctk.CTkEntry(
            src_frame, textvariable=self._source_var,
            placeholder_text="Paste a single video URL  —or—  select a links.txt file",
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(src_frame, text="Browse .txt", width=110,
                       command=self._browse_links_file).grid(row=0, column=2, padx=(4, 8), pady=6)

        # Detected input kind indicator
        self._input_kind_label = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(size=11), text_color="#999", anchor="w")
        self._input_kind_label.grid(row=1, column=0, sticky="ew", padx=12)
        self._source_var.trace_add("write", lambda *_: self._update_input_kind_label())

        # Download folder
        dl_frame = ctk.CTkFrame(tab)
        dl_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=6)
        dl_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dl_frame, text="Save to:", width=80, anchor="w").grid(row=0, column=0, padx=(8, 4), pady=6)
        default_folder = self.config_obj.download_folder or str(Path.home() / "Downloads")
        self._folder_var = tk.StringVar(value=default_folder)
        ctk.CTkEntry(dl_frame, textvariable=self._folder_var).grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(dl_frame, text="Browse", width=80,
                       command=self._browse_folder).grid(row=0, column=2, padx=(4, 8), pady=6)

        # Action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self._analyse_btn = ctk.CTkButton(btn_frame, text="Analyse", width=120, command=self._start_analysis)
        self._analyse_btn.pack(side="left", padx=(0, 8))
        self._cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#555",
                                          hover_color="#333", state="disabled", command=self._cancel_analysis)
        self._cancel_btn.pack(side="left", padx=(0, 8))
        self._download_all_btn = ctk.CTkButton(btn_frame, text="Download All Ready", width=160,
                                                 state="disabled", fg_color="#2e7d32", hover_color="#1b5e20",
                                                 command=self._start_downloads)
        self._download_all_btn.pack(side="left")
        self._status_label = ctk.CTkLabel(btn_frame, text="", font=ctk.CTkFont(size=12))
        self._status_label.pack(side="left", padx=12)

        # Log + results split
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        log_frame = ctk.CTkFrame(body)
        log_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(log_frame, text="Analysis Log", font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(6, 2))
        self._log_text = tk.Text(log_frame, state="disabled", wrap="word", height=8,
                                  bg="#1a1a1a", fg="#e0e0e0", font=("Consolas", 10), relief="flat", padx=6, pady=4)
        self._log_text.pack(fill="x", padx=8, pady=(0, 6))
        self._log_text.tag_config("info", foreground="#e0e0e0")
        self._log_text.tag_config("success", foreground="#4caf50")
        self._log_text.tag_config("warning", foreground="#ff9800")
        self._log_text.tag_config("error", foreground="#f44336")
        self._log_text.tag_config("header", foreground="#64b5f6", font=("Consolas", 10, "bold"))

        self._meta_frame = ctk.CTkScrollableFrame(body, label_text="Analysis Results")
        self._meta_frame.grid(row=1, column=0, sticky="nsew")
        self._meta_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Queue tab
    # ------------------------------------------------------------------

    def _build_queue_tab(self) -> None:
        tab = self._tab_queue
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(top, text="Cancel All", fg_color="#b71c1c", hover_color="#7f0000",
                       width=120, command=self._cancel_all_downloads).pack(side="left")

        self._queue_frame = ctk.CTkScrollableFrame(tab, label_text="Download Queue")
        self._queue_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self._queue_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------

    def _build_history_tab(self) -> None:
        tab = self._tab_history
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        self._history_frame = ctk.CTkScrollableFrame(tab, label_text="Completed Downloads")
        self._history_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=8)
        self._history_frame.grid_columnconfigure(0, weight=1)
        self._history_count = 0

    # ------------------------------------------------------------------
    # Settings tab
    # ------------------------------------------------------------------

    def _build_settings_tab(self) -> None:
        tab = self._tab_settings
        tab.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkScrollableFrame(tab, label_text="Settings")
        frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=8)
        frame.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        r = 0
        ctk.CTkLabel(frame, text="Embedding", font=ctk.CTkFont(weight="bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2)); r += 1

        self._subs_var = ctk.BooleanVar(value=self.config_obj.embed_subtitles)
        ctk.CTkCheckBox(frame, text="Embed subtitles", variable=self._subs_var).grid(
            row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        self._thumb_var = ctk.BooleanVar(value=self.config_obj.embed_thumbnail)
        ctk.CTkCheckBox(frame, text="Embed thumbnail", variable=self._thumb_var).grid(
            row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        self._meta_var = ctk.BooleanVar(value=self.config_obj.embed_metadata)
        ctk.CTkCheckBox(frame, text="Embed metadata", variable=self._meta_var).grid(
            row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        ctk.CTkLabel(frame, text="Engine", font=ctk.CTkFont(weight="bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(16, 2)); r += 1

        self._aria2_var = ctk.BooleanVar(value=self.config_obj.use_aria2)
        ctk.CTkCheckBox(frame, text="Use aria2 (multi-connection downloads)",
                         variable=self._aria2_var).grid(row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        self._archive_var = ctk.BooleanVar(value=self.config_obj.use_archive)
        ctk.CTkCheckBox(frame, text="Use download archive (skip duplicates)",
                         variable=self._archive_var).grid(row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        self._number_var = ctk.BooleanVar(value=self.config_obj.auto_number_batch)
        ctk.CTkCheckBox(frame, text="Auto-number batch downloads",
                         variable=self._number_var).grid(row=r, column=0, sticky="w", padx=16, pady=3); r += 1

        ctk.CTkLabel(frame, text="Parallel downloads:").grid(row=r, column=0, sticky="w", padx=16, pady=(8, 3))
        self._parallel_var = tk.StringVar(value=str(self.config_obj.max_parallel_downloads))
        ctk.CTkOptionMenu(frame, values=["1", "2", "3", "4", "5"],
                           variable=self._parallel_var, width=80).grid(row=r, column=1, sticky="w", pady=(8, 3)); r += 1

        ctk.CTkLabel(frame, text="Container:").grid(row=r, column=0, sticky="w", padx=16, pady=3)
        self._container_var = tk.StringVar(value=self.config_obj.preferred_container)
        ctk.CTkOptionMenu(frame, values=["mp4", "mkv", "webm"],
                           variable=self._container_var, width=100).grid(row=r, column=1, sticky="w", pady=3); r += 1

        ctk.CTkButton(frame, text="Save Settings", command=self._save_settings).grid(
            row=r, column=0, sticky="w", padx=16, pady=(20, 8))

    def _save_settings(self) -> None:
        self.config_obj.embed_subtitles = self._subs_var.get()
        self.config_obj.embed_thumbnail = self._thumb_var.get()
        self.config_obj.embed_metadata = self._meta_var.get()
        self.config_obj.use_aria2 = self._aria2_var.get()
        self.config_obj.use_archive = self._archive_var.get()
        self.config_obj.auto_number_batch = self._number_var.get()
        self.config_obj.preferred_container = self._container_var.get()
        try:
            self.config_obj.max_parallel_downloads = int(self._parallel_var.get())
        except ValueError:
            self.config_obj.max_parallel_downloads = 2
        self.config_obj.download_folder = self._folder_var.get()
        save_config(self.config_obj)
        self._append_log("✓  Settings saved.", "success")

    # ------------------------------------------------------------------
    # About tab
    # ------------------------------------------------------------------

    def _build_about_tab(self) -> None:
        tab = self._tab_about
        tab.grid_columnconfigure(0, weight=1)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="n", pady=40)

        ctk.CTkLabel(frame, text=_APP_TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(pady=4)
        ctk.CTkLabel(frame, text=_VERSION, font=ctk.CTkFont(size=14), text_color="#999").pack(pady=2)
        ctk.CTkLabel(
            frame,
            text="A professional front-end for yt-dlp.\nSupports YouTube, Vimeo, M3U8 and any\nsite supported by yt-dlp.",
            justify="center", font=ctk.CTkFont(size=12),
        ).pack(pady=12)
        ctk.CTkLabel(
            frame, text="github.com/jm-lab-eng/Universal-Batch-Video-Downloader",
            font=ctk.CTkFont(size=11), text_color="#64b5f6",
        ).pack(pady=4)

    # ==================================================================
    # Tool status
    # ==================================================================

    def _refresh_tool_status(self) -> None:
        parts = []
        for name, ready_attr, ver_key in (
            ("yt-dlp", "ytdlp_ready", "ytdlp"),
            ("ffmpeg", "ffmpeg_ready", "ffmpeg"),
            ("aria2", "aria2_ready", "aria2"),
        ):
            ready = getattr(self.tools, ready_attr)
            ver = self.tools.versions.get(ver_key, "")
            if ready:
                parts.append(f"{name} {ver}" if ver else f"{name} ✓")
            else:
                parts.append(f"{name} ✗")
        self._tool_label.configure(text="  |  ".join(parts))

    # ==================================================================
    # Source / folder browsing
    # ==================================================================

    def _browse_links_file(self) -> None:
        path = filedialog.askopenfilename(title="Select links file",
                                           filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self._source_var.set(path)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Select download folder")
        if path:
            self._folder_var.set(path)

    def _update_input_kind_label(self) -> None:
        from app.core.analyzer import classify_input
        source = self._source_var.get().strip()
        if not source:
            self._input_kind_label.configure(text="")
            return
        kind = classify_input(source)
        labels = {
            "single_url": "📄 Detected: single video URL",
            "batch_file": "📋 Detected: batch links.txt file",
            "invalid": "⚠ Not a recognised URL or file path",
        }
        colors = {"single_url": "#4caf50", "batch_file": "#64b5f6", "invalid": "#ff9800"}
        self._input_kind_label.configure(text=labels.get(kind, ""), text_color=colors.get(kind, "#999"))

    # ==================================================================
    # Analysis flow
    # ==================================================================

    def _start_analysis(self) -> None:
        source = self._source_var.get().strip()
        if not source:
            self._append_log("⚠  Please enter a URL or select a links.txt file.", "warning")
            return
        if not self.tools.ytdlp_ready:
            self._append_log("✗  yt-dlp not found. Place yt-dlp.exe inside the bin/ folder.", "error")
            return

        self._clear_log()
        self._clear_metadata_panel()
        self._cookies_file = None
        self._item_quality.clear()
        self._analyse_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._download_all_btn.configure(state="disabled")
        self._set_status("Analysing …")

        self._analyzer = Analyzer(ytdlp_path=self.tools.ytdlp)
        self._append_log(f"▶  Starting analysis: {source}", "header")

        def _on_progress(idx, total, msg):
            self._append_log(f"  [{idx}/{total}] {msg}", "info")
            self._set_status(f"Analysing {idx}/{total} …")

        def _on_complete(result: AnalysisResult):
            self.after(0, lambda: self._analysis_done(result))

        self._analyzer.analyze_async(source, on_progress=_on_progress, on_complete=_on_complete)

    def _cancel_analysis(self) -> None:
        if self._analyzer:
            self._analyzer.cancel()
            self._append_log("⚠  Analysis cancelled by user.", "warning")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._set_status("Cancelled")

    def _analysis_done(self, result: AnalysisResult) -> None:
        self._result = result
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")

        if result.cancelled:
            self._set_status("Analysis cancelled")
            return

        self._set_status(f"Done — {result.ready_count}/{result.total} ready")
        self._append_log("", "info")
        self._append_log("── Analysis Complete ──────────────────────", "header")
        for line in result.summary_lines():
            tag = "warning" if ("Require cookies" in line or "Unavailable" in line) else "info"
            self._append_log(f"  {line}", tag)

        log.info("Analysis: total=%d ready=%d auth=%d unavail=%d",
                  result.total, result.ready_count, result.auth_count, result.unavailable_count)

        self._populate_metadata_panel(result)

        if result.needs_cookies:
            self._prompt_for_cookies(result)
        elif result.ready_count:
            self._download_all_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Cookie flow
    # ------------------------------------------------------------------

    def _prompt_for_cookies(self, result: AnalysisResult) -> None:
        count = result.auth_count
        reasons = sorted(set(i.auth_reason_label for i in result.auth_required))
        reason_text = (
            f"{count} of {result.total} link(s) require sign-in to access "
            f"({', '.join(reasons)})."
        )
        self._append_log(f"⚠  {reason_text} Cookies needed.", "warning")

        def _on_success(cookies_path: Path):
            self._cookies_file = cookies_path
            self._append_log(f"✓  Cookies accepted: {cookies_path}", "success")
            self.config_obj.last_cookies_file = str(cookies_path)
            save_config(self.config_obj)
            self._retry_with_cookies(result, cookies_path)

        def _on_cancel():
            self._append_log("⚠  Skipped items requiring cookies.", "warning")
            if result.ready_count:
                self._download_all_btn.configure(state="normal")

        CookiesDialog(self, reason_text=reason_text, on_success=_on_success, on_cancel=_on_cancel)

    def _retry_with_cookies(self, result: AnalysisResult, cookies_path: Path) -> None:
        self._set_status("Re-checking items with cookies …")
        self._append_log("▶  Re-analysing items that required cookies …", "header")

        def _on_progress(idx, total, msg):
            self._append_log(f"  [{idx}/{total}] {msg}", "info")

        def _on_complete(new_result: AnalysisResult):
            self.after(0, lambda: self._cookie_retry_done(new_result))

        self._analyzer.reanalyze_async(result, cookies_path, on_progress=_on_progress, on_complete=_on_complete)

    def _cookie_retry_done(self, result: AnalysisResult) -> None:
        self._result = result
        self._clear_metadata_panel()
        self._populate_metadata_panel(result)

        self._append_log("── Re-check Complete ──────────────────────", "header")
        for line in result.summary_lines():
            tag = "warning" if ("Require cookies" in line or "Unavailable" in line) else "info"
            self._append_log(f"  {line}", tag)

        if result.needs_cookies:
            self._append_log("⚠  Some items still require valid cookies for that account/region.", "warning")
        if result.ready_count:
            self._download_all_btn.configure(state="normal")
        self._set_status(f"Done — {result.ready_count}/{result.total} ready")

    # ==================================================================
    # Metadata panel + quality selection
    # ==================================================================

    def _clear_metadata_panel(self) -> None:
        for w in self._meta_frame.winfo_children():
            w.destroy()

    def _populate_metadata_panel(self, result: AnalysisResult) -> None:
        for idx, item in enumerate(result.items):
            self._add_item_card(item, idx)

    def _add_item_card(self, item: AnalyzedItem, idx: int) -> None:
        card = ctk.CTkFrame(self._meta_frame, corner_radius=8)
        card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
        card.grid_columnconfigure(1, weight=1)

        color, label = STATUS_COLORS.get(item.status, ("#aaa", item.status))
        ctk.CTkLabel(card, text=label, text_color=color, font=ctk.CTkFont(weight="bold"),
                     width=140, anchor="w").grid(row=0, column=0, padx=(10, 4), pady=(8, 2), sticky="nw")

        if item.info:
            info = item.info
            ctk.CTkLabel(card, text=info.title, anchor="w", wraplength=480,
                         font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=1, sticky="ew", padx=4, pady=(8, 2))

            details = [f"Platform: {info.platform}", f"Duration: {info.duration_str}",
                       f"Uploader: {info.uploader or '—'}"]
            if info.max_resolution != "unknown":
                details.append(f"Max res: {info.max_resolution}")
            if info.has_hdr:
                details.append("HDR available")
            if info.is_live:
                details.append("LIVE STREAM")
            if info.is_playlist:
                details.append(f"Playlist: {info.playlist_count or '?'} videos")
            ctk.CTkLabel(card, text="  |  ".join(details), anchor="w", font=ctk.CTkFont(size=11),
                         text_color="#bbb", wraplength=500).grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 4))

            if item.status == "ready":
                chosen_key = self._item_quality.get(item.url)
                btn_text = f"Quality: {chosen_key}" if chosen_key else "Select Quality"
                ctk.CTkButton(card, text=btn_text, width=160, height=26,
                              command=lambda it=item: self._open_quality_dialog(it)).grid(
                    row=2, column=1, sticky="w", padx=4, pady=(0, 8))
        else:
            msg = item.auth_reason_label if item.status == "auth_required" else (item.error_message or "No details available")
            ctk.CTkLabel(card, text=msg, anchor="w", font=ctk.CTkFont(size=12),
                         text_color="#bbb", wraplength=520).grid(row=0, column=1, sticky="ew", padx=4, pady=(8, 8))

        ctk.CTkLabel(card, text=item.url, anchor="w", font=ctk.CTkFont(size=10),
                     text_color="#666", wraplength=680).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

    def _open_quality_dialog(self, item: AnalyzedItem) -> None:
        if not item.info:
            return

        def _on_select(option, remember):
            self._item_quality[item.url] = option.label
            self._item_quality[f"__selector__{item.url}"] = option.format_selector
            if remember:
                self.config_obj.preferred_quality_key = option.key
                save_config(self.config_obj)
            self._clear_metadata_panel()
            self._populate_metadata_panel(self._result)

        QualityDialog(self, info=item.info, default_key=self.config_obj.preferred_quality_key,
                      on_select=_on_select)

    # ==================================================================
    # Download flow
    # ==================================================================

    def _start_downloads(self) -> None:
        if not self._result:
            return

        folder = self._folder_var.get().strip()
        if not folder:
            self._append_log("⚠  Please choose a download folder.", "warning")
            return
        Path(folder).mkdir(parents=True, exist_ok=True)

        self.config_obj.download_folder = folder
        save_config(self.config_obj)

        ready_items = self._result.ready
        if not ready_items:
            self._append_log("⚠  No ready items to download.", "warning")
            return

        self._engine = DownloadEngine(
            self.config_obj,
            ytdlp_path=self.tools.ytdlp,
            ffmpeg_path=self.tools.ffmpeg.parent if self.tools.ffmpeg else None,
            aria2_path=self.tools.aria2,
        )

        for idx, item in enumerate(ready_items, start=1):
            selector = self._item_quality.get(f"__selector__{item.url}", "bestvideo+bestaudio/best")
            spec = DownloadJobSpec(
                url=item.url,
                download_folder=folder,
                format_selector=selector,
                batch_index=idx if self._result.is_batch else None,
                cookies_file=str(self._cookies_file) if self._cookies_file else None,
                is_playlist_item=bool(item.info and item.info.is_playlist),
            )
            job = self._engine.add_job(spec)
            self._add_queue_row(job, item)

        self._tabs.set("Queue")
        self._engine.start(on_update=lambda job: self.after(0, lambda j=job: self._update_queue_row(j)))
        self._append_log(f"▶  Started download queue: {len(ready_items)} item(s).", "header")

    def _cancel_all_downloads(self) -> None:
        if self._engine:
            self._engine.cancel_all()
            self._append_log("⚠  Cancelling all downloads …", "warning")

    # ------------------------------------------------------------------
    # Queue tab rows
    # ------------------------------------------------------------------

    def _add_queue_row(self, job: DownloadJob, item: AnalyzedItem) -> None:
        title = item.info.title if item.info else item.url
        row = ctk.CTkFrame(self._queue_frame, corner_radius=8)
        row.grid(row=len(self._job_rows), column=0, sticky="ew", padx=4, pady=4)
        row.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(row, text=title, anchor="w", wraplength=600,
                                  font=ctk.CTkFont(size=12, weight="bold"))
        title_lbl.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))

        state_lbl = ctk.CTkLabel(row, text=job.state.value, anchor="e", width=110,
                                  text_color=JOB_STATE_COLORS.get(job.state, "#aaa"))
        state_lbl.grid(row=0, column=1, sticky="e", padx=10, pady=(8, 2))

        progress = ctk.CTkProgressBar(row)
        progress.set(0)
        progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 4))

        detail_lbl = ctk.CTkLabel(row, text="", anchor="w", font=ctk.CTkFont(size=10), text_color="#999")
        detail_lbl.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))

        cancel_btn = ctk.CTkButton(row, text="Cancel", width=80, height=22, fg_color="#555",
                                    hover_color="#333", command=lambda: self._engine.cancel_job(job.job_id))
        cancel_btn.grid(row=0, column=2, padx=(0, 10))

        self._job_rows[job.job_id] = {
            "row": row, "title": title_lbl, "state": state_lbl,
            "progress": progress, "detail": detail_lbl, "cancel_btn": cancel_btn,
        }

    def _update_queue_row(self, job: DownloadJob) -> None:
        widgets = self._job_rows.get(job.job_id)
        if not widgets:
            return

        widgets["state"].configure(text=job.state.value, text_color=JOB_STATE_COLORS.get(job.state, "#aaa"))
        widgets["progress"].set(min(max(job.percent / 100.0, 0.0), 1.0))

        detail_parts = []
        if job.speed:
            detail_parts.append(f"Speed: {job.speed}")
        if job.eta:
            detail_parts.append(f"ETA: {job.eta}")
        if job.current_filename:
            detail_parts.append(Path(job.current_filename).name)
        if job.error_message and job.state == JobState.FAILED:
            detail_parts.append(f"Error: {job.error_message}")
        widgets["detail"].configure(text="  |  ".join(detail_parts))

        if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            widgets["cancel_btn"].configure(state="disabled")
        if job.state == JobState.COMPLETED:
            self._add_history_row(job)

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------

    def _add_history_row(self, job: DownloadJob) -> None:
        # Avoid duplicate entries if update fires multiple times at 100%
        key = f"hist_{job.job_id}"
        if key in self._job_rows.get("_history_seen", {}):
            return
        seen = self._job_rows.setdefault("_history_seen", {})
        seen[key] = True

        row = ctk.CTkFrame(self._history_frame, corner_radius=6)
        row.grid(row=self._history_count, column=0, sticky="ew", padx=4, pady=2)
        row.grid_columnconfigure(0, weight=1)
        self._history_count += 1

        name = Path(job.current_filename).name if job.current_filename else job.spec.url
        ctk.CTkLabel(row, text=f"✓ {name}", anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="ew", padx=10, pady=6)

    # ==================================================================
    # Log helpers
    # ==================================================================

    def _append_log(self, text: str, tag: str = "info") -> None:
        def _do():
            self._log_text.configure(state="normal")
            self._log_text.insert("end", text + "\n", tag)
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_label.configure(text=text))

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")