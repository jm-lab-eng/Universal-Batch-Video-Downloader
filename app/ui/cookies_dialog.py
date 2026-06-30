"""
cookies_dialog.py
==================
Modal dialog requesting cookies from the user when authentication is
required. Offers BOTH supported input methods on the same screen:

  Tab 1 — Paste cookies.txt contents directly
  Tab 2 — Browse to an existing cookies.txt file on disk

Returns the resolved cookies file path via a callback once validated.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from app.core.cookies_helper import (
    CookiesValidationError,
    save_pasted_cookies,
    validate_cookies_file,
)


class CookiesDialog(ctk.CTkToplevel):
    """
    Modal cookie-input dialog.

    Usage
    -----
    ::

        CookiesDialog(
            parent,
            reason_text="Some videos require sign-in (age-restricted).",
            on_success=lambda path: print("Got cookies at", path),
        )
    """

    def __init__(
        self,
        parent,
        reason_text: str = "This content requires you to be signed in.",
        on_success: Optional[Callable[[Path], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.title("Cookies Required")
        self.geometry("620x520")
        self.minsize(560, 480)
        self.transient(parent)
        self.grab_set()

        self._on_success = on_success
        self._on_cancel = on_cancel

        self._build_ui(reason_text)

        self.protocol("WM_DELETE_WINDOW", self._handle_cancel)

    # ------------------------------------------------------------------

    def _build_ui(self, reason_text: str) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Explanation banner ──────────────────────────────────────
        banner = ctk.CTkFrame(self, fg_color="#3a2f1a", corner_radius=8)
        banner.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            banner,
            text=f"⚠  {reason_text}",
            wraplength=560, justify="left", anchor="w",
            font=ctk.CTkFont(size=13),
        ).pack(padx=12, pady=10, fill="x")

        instructions = (
            "To continue, supply your browser cookies for the site. "
            "Use a browser extension such as 'Get cookies.txt LOCALLY' "
            "(Chrome/Firefox) to export cookies in Netscape format, "
            "then either paste them below or select the saved file."
        )
        ctk.CTkLabel(
            self, text=instructions, wraplength=580, justify="left",
            anchor="w", font=ctk.CTkFont(size=11), text_color="#999",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # ── Tabs: Paste / Browse ────────────────────────────────────
        tabs = ctk.CTkTabview(self)
        tabs.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        tab_paste = tabs.add("Paste cookies.txt")
        tab_browse = tabs.add("Browse for file")

        # --- Paste tab ---
        tab_paste.grid_columnconfigure(0, weight=1)
        tab_paste.grid_rowconfigure(0, weight=1)

        self._paste_text = ctk.CTkTextbox(tab_paste, wrap="none", font=("Consolas", 10))
        self._paste_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._paste_text.insert(
            "1.0",
            "# Netscape HTTP Cookie File\n"
            "# Paste the full exported cookies.txt content here…\n",
        )

        ctk.CTkButton(
            tab_paste, text="Use Pasted Cookies", command=self._handle_paste_submit,
        ).grid(row=1, column=0, sticky="e", padx=8, pady=(0, 8))

        # --- Browse tab ---
        tab_browse.grid_columnconfigure(0, weight=1)

        browse_inner = ctk.CTkFrame(tab_browse, fg_color="transparent")
        browse_inner.pack(expand=True, fill="both", padx=8, pady=20)

        self._file_var = tk.StringVar()
        file_row = ctk.CTkFrame(browse_inner, fg_color="transparent")
        file_row.pack(fill="x", pady=8)
        ctk.CTkEntry(
            file_row, textvariable=self._file_var,
            placeholder_text="Path to cookies.txt …",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            file_row, text="Browse…", width=100, command=self._browse_file,
        ).pack(side="left")

        ctk.CTkButton(
            browse_inner, text="Use Selected File", command=self._handle_browse_submit,
        ).pack(anchor="e", pady=(12, 0))

        # ── Status / error label ────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self, text="", text_color="#f44336", wraplength=580,
            justify="left", anchor="w",
        )
        self._status_label.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))

        # ── Bottom buttons ───────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="e", padx=16, pady=(0, 16))
        ctk.CTkButton(
            bottom, text="Skip these items", fg_color="#555", hover_color="#333",
            command=self._handle_cancel,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._file_var.set(path)

    def _handle_paste_submit(self) -> None:
        text = self._paste_text.get("1.0", "end").strip()
        try:
            saved_path = save_pasted_cookies(text, destination_dir="temp")
        except CookiesValidationError as exc:
            self._show_error(str(exc))
            return
        self._finish_success(saved_path)

    def _handle_browse_submit(self) -> None:
        path_str = self._file_var.get().strip()
        if not path_str:
            self._show_error("Please select a cookies.txt file first.")
            return
        try:
            validated = validate_cookies_file(path_str)
        except CookiesValidationError as exc:
            self._show_error(str(exc))
            return
        self._finish_success(validated)

    def _show_error(self, message: str) -> None:
        self._status_label.configure(text=message)

    def _finish_success(self, path: Path) -> None:
        self._status_label.configure(text="")
        if self._on_success:
            self._on_success(path)
        self.destroy()

    def _handle_cancel(self) -> None:
        if self._on_cancel:
            self._on_cancel()
        self.destroy()