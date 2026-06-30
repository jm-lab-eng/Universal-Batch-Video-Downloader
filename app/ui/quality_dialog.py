"""
quality_dialog.py
==================
Modal dialog presenting available quality options for a single video in
plain language (resolution, fps, HDR, codec, estimated size) rather than
raw yt-dlp format IDs. Returns the chosen QualityOption via callback.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from app.core.video_info import QualityOption, VideoInfo


class QualityDialog(ctk.CTkToplevel):
    """
    Usage
    -----
    ::

        QualityDialog(
            parent,
            info=video_info,
            default_key=config.preferred_quality_key,
            on_select=lambda option, remember: print(option.format_selector, remember),
        )
    """

    def __init__(
        self,
        parent,
        info: VideoInfo,
        default_key: str = "best",
        on_select: Optional[Callable[[QualityOption, bool], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        remember_choice_default: bool = True,
    ):
        super().__init__(parent)
        self.title("Select Quality")
        self.geometry("560x520")
        self.minsize(480, 420)
        self.transient(parent)
        self.grab_set()

        self.info = info
        self._quality_options = info.quality_options()
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._selected_key = default_key
        self._remember_var = ctk.BooleanVar(value=remember_choice_default)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._handle_cancel)

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title
        ctk.CTkLabel(
            self, text=self.info.title, font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=520, anchor="w", justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))

        subtitle = f"{self.info.platform}  •  {self.info.duration_str}"
        if self.info.has_hdr:
            subtitle += "  •  HDR available"
        ctk.CTkLabel(
            self, text=subtitle, font=ctk.CTkFont(size=11), text_color="#999",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Scrollable option list
        scroll = ctk.CTkScrollableFrame(self, label_text="Available Qualities")
        scroll.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)

        self._radio_var = ctk.StringVar(value=self._selected_key)

        for idx, opt in enumerate(self._quality_options):
            row = ctk.CTkFrame(scroll, corner_radius=6)
            row.grid(row=idx, column=0, sticky="ew", padx=4, pady=3)
            row.grid_columnconfigure(1, weight=1)

            radio = ctk.CTkRadioButton(
                row, text="", variable=self._radio_var, value=opt.key, width=20,
            )
            radio.grid(row=0, column=0, padx=(10, 4), pady=8)

            label_color = "#4caf50" if opt.key == "best" else None
            ctk.CTkLabel(
                row, text=opt.label, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold" if opt.key == "best" else "normal"),
                text_color=label_color,
            ).grid(row=0, column=1, sticky="ew", padx=4, pady=8)

            # Clicking anywhere on the row selects it
            row.bind("<Button-1>", lambda e, k=opt.key: self._radio_var.set(k))

        # Remember choice checkbox
        ctk.CTkCheckBox(
            self, text="Remember this quality as my default",
            variable=self._remember_var,
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(0, 8))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="e", padx=16, pady=(0, 16))

        ctk.CTkButton(
            btn_row, text="Cancel", fg_color="#555", hover_color="#333",
            width=100, command=self._handle_cancel,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_row, text="Download", width=120, command=self._handle_confirm,
        ).pack(side="right")

    # ------------------------------------------------------------------

    def _handle_confirm(self) -> None:
        key = self._radio_var.get()
        chosen = next((o for o in self._quality_options if o.key == key), self._quality_options[0])
        if self._on_select:
            self._on_select(chosen, self._remember_var.get())
        self.destroy()

    def _handle_cancel(self) -> None:
        if self._on_cancel:
            self._on_cancel()
        self.destroy()