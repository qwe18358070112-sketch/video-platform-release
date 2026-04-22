from __future__ import annotations

import argparse
import json
import time
import tkinter as tk
from contextlib import suppress
from pathlib import Path
from tkinter import font as tkfont

import win32con
import win32gui


COLORS = {
    "info": {
        "window": "#08111f",
        "panel": "#0f1b2f",
        "title": "#dbeafe",
        "message": "#f8fafc",
        "detail": "#cbd5e1",
        "meta": "#93c5fd",
        "accent": "#38bdf8",
        "badge_bg": "#082f49",
    },
    "warning": {
        "window": "#1a1208",
        "panel": "#24170b",
        "title": "#ffedd5",
        "message": "#fff7ed",
        "detail": "#fed7aa",
        "meta": "#fdba74",
        "accent": "#fb923c",
        "badge_bg": "#431407",
    },
    "error": {
        "window": "#220f18",
        "panel": "#32121f",
        "title": "#ffe4e6",
        "message": "#fff1f2",
        "detail": "#fecdd3",
        "meta": "#fda4af",
        "accent": "#fb7185",
        "badge_bg": "#4c0519",
    },
    "success": {
        "window": "#071a12",
        "panel": "#0d241a",
        "title": "#dcfce7",
        "message": "#f0fdf4",
        "detail": "#bbf7d0",
        "meta": "#86efac",
        "accent": "#34d399",
        "badge_bg": "#052e16",
    },
}
HOTKEY_HINT = "F1 自动/手动  F2 启停  F7 模式  F8 宫格  F9 步进  F10 停止  F11 恢复"
SAFE_STRIP_HEIGHT = 96
SAFE_STRIP_MARGIN = 8
DEFAULT_STALE_HIDE_MS = 4800


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Click-through runtime status overlay for the automation helper.")
    parser.add_argument("--status-file", required=True, help="Path to the JSON status file.")
    return parser.parse_args()


class OverlayApp:
    def __init__(self, status_file: Path):
        self._status_file = status_file
        self._pid_file = status_file.with_suffix(".overlay.pid")
        self._debug_file = status_file.with_suffix(".overlay.log")
        self._last_timestamp = None
        self._close_after_id = None
        self._hide_after_id = None

        self.root = tk.Tk()
        self.root.title("Video Polling Status")
        self.root.overrideredirect(True)
        self.root.resizable(False, False)
        self.root.withdraw()
        self.root.configure(bg="#04070c")
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.96)

        self._height = SAFE_STRIP_HEIGHT
        self._width = 880
        self._content_width = 0
        self._title_font = tkfont.Font(family="Microsoft YaHei UI", size=8, weight="bold")
        self._message_font = tkfont.Font(family="Microsoft YaHei UI", size=13, weight="bold")
        self._detail_font = tkfont.Font(family="Microsoft YaHei UI", size=9)
        self._meta_font = tkfont.Font(family="Microsoft YaHei UI", size=8, weight="bold")
        self._hotkey_font = tkfont.Font(family="Microsoft YaHei UI", size=8)

        self.container = tk.Frame(
            self.root,
            bg="#0f1b2f",
            highlightthickness=1,
            bd=0,
            padx=14,
            pady=8,
        )
        self.container.pack(fill="both", expand=True)

        self.accent_bar = tk.Frame(self.container, bg="#38bdf8", width=6)
        self.accent_bar.pack(side="left", fill="y", padx=(0, 10))

        self.content = tk.Frame(self.container, bg="#0f1b2f")
        self.content.pack(side="left", fill="both", expand=True)

        self.header = tk.Frame(self.content, bg="#0f1b2f")
        self.header.pack(fill="x", pady=(0, 2))

        self.badge_label = tk.Label(
            self.header,
            text="INFO",
            font=self._title_font,
            padx=8,
            pady=1,
            anchor="center",
        )
        self.badge_label.pack(side="left")

        self.title_label = tk.Label(
            self.header,
            text="视频轮巡助手",
            font=self._title_font,
            anchor="w",
            justify="left",
            padx=8,
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        self.message_label = tk.Label(
            self.content,
            text="等待状态更新...",
            font=self._message_font,
            anchor="w",
            justify="left",
        )
        self.message_label.pack(fill="x")

        self.detail_label = tk.Label(
            self.content,
            text="提示词会随运行状态实时同步。",
            font=self._detail_font,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.detail_label.pack(fill="x", pady=(2, 3))

        self.footer = tk.Frame(self.content, bg="#0f1b2f")
        self.footer.pack(fill="x")

        self.meta_label = tk.Label(
            self.footer,
            text="控制: 自动识别 | 实际: 等待识别 | 目标: 现场自动识别",
            font=self._meta_font,
            anchor="w",
            justify="left",
        )
        self.meta_label.pack(side="left", fill="x", expand=True)

        self.hotkey_label = tk.Label(
            self.footer,
            text=HOTKEY_HINT,
            font=self._hotkey_font,
            anchor="e",
            justify="right",
        )
        self.hotkey_label.pack(side="right", padx=(10, 0))

        self._apply_style("info")
        self.root.update_idletasks()
        self._apply_window_styles()
        self._debug("overlay initialized")
        self._poll()

    def _update_layout_metrics(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        self._width = min(max(720, int(screen_w * 0.62)), 980)
        self._content_width = max(420, self._width - 82)

    def _apply_style(self, level: str) -> None:
        palette = COLORS.get(level, COLORS["info"])
        self.root.configure(bg=palette["window"])
        self.container.configure(
            bg=palette["panel"],
            highlightbackground=palette["accent"],
            highlightcolor=palette["accent"],
        )
        self.content.configure(bg=palette["panel"])
        self.header.configure(bg=palette["panel"])
        self.footer.configure(bg=palette["panel"])
        self.accent_bar.configure(bg=palette["accent"])
        self.badge_label.configure(bg=palette["badge_bg"], fg=palette["title"])
        self.title_label.configure(bg=palette["panel"], fg=palette["title"])
        self.message_label.configure(bg=palette["panel"], fg=palette["message"])
        self.detail_label.configure(bg=palette["panel"], fg=palette["detail"])
        self.meta_label.configure(bg=palette["panel"], fg=palette["meta"])
        self.hotkey_label.configure(bg=palette["panel"], fg=palette["detail"])

    def _poll(self) -> None:
        try:
            if self._status_file.exists():
                payload = json.loads(self._status_file.read_text(encoding="utf-8"))
                timestamp = payload.get("timestamp")
                if timestamp != self._last_timestamp:
                    self._last_timestamp = timestamp
                    level = str(payload.get("level", "info"))
                    self._apply_style(level)
                    self._update_layout_metrics()
                    self.badge_label.configure(text=level.upper())
                    self.title_label.configure(
                        text=self._fit_text(
                            str(payload.get("title", "视频轮巡助手")),
                            self._content_width,
                            fallback="视频轮巡助手",
                            font=self._title_font,
                        )
                    )
                    self.message_label.configure(
                        text=self._fit_text(
                            str(payload.get("message", "")),
                            self._content_width,
                            font=self._message_font,
                        )
                    )
                    self.detail_label.configure(
                        text=self._fit_text(
                            str(payload.get("details", "")),
                            max(self._content_width * 2, self._content_width),
                            fallback="提示词会随运行状态实时同步。",
                            font=self._detail_font,
                        ),
                        wraplength=max(360, self._content_width),
                    )
                    self.meta_label.configure(
                        text=self._fit_text(
                            str(payload.get("meta", "")),
                            self._content_width,
                            fallback="",
                            font=self._meta_font,
                        )
                    )
                    self.hotkey_label.configure(
                        text=self._fit_text(
                            str(payload.get("hotkey_hint", HOTKEY_HINT)),
                            max(260, self._content_width // 2),
                            fallback=HOTKEY_HINT,
                            font=self._hotkey_font,
                        )
                    )

                    if self._close_after_id is not None:
                        self.root.after_cancel(self._close_after_id)
                        self._close_after_id = None
                    if self._hide_after_id is not None:
                        self.root.after_cancel(self._hide_after_id)
                        self._hide_after_id = None

                    if payload.get("close_requested"):
                        delay = int(payload.get("close_delay_ms", 2600))
                        self._close_after_id = self.root.after(delay, self.root.destroy)
                    else:
                        auto_hide_ms = int(payload.get("auto_hide_ms", 2200))
                        if auto_hide_ms > 0:
                            delay = max(300, auto_hide_ms)
                            if level in {"warning", "error"}:
                                delay = max(delay, 2600)
                            self._hide_after_id = self.root.after(delay, self._hide_card)
                    self._show_card()
                self._hide_if_stale(payload)
            else:
                self._hide_card()
        except Exception as exc:
            self._debug(f"poll error: {exc!r}")

        self.root.after(50, self._poll)

    def _hide_if_stale(self, payload: dict) -> None:
        timestamp = float(payload.get("timestamp", 0.0) or 0.0)
        if timestamp <= 0.0:
            return
        stale_hide_ms = int(payload.get("stale_hide_ms", DEFAULT_STALE_HIDE_MS))
        if stale_hide_ms <= 0:
            return
        stale_hide_ms = max(600, stale_hide_ms)
        age_ms = max(0.0, (time.time() - timestamp) * 1000.0)
        if payload.get("close_requested"):
            close_delay_ms = max(300, int(payload.get("close_delay_ms", 2600)))
            destroy_after_ms = max(stale_hide_ms, close_delay_ms + 1200)
            if age_ms >= destroy_after_ms:
                self._debug(
                    f"destroy stale close card age_ms={age_ms:.1f} destroy_after_ms={destroy_after_ms}"
                )
                try:
                    self.root.destroy()
                except Exception as exc:
                    self._debug(f"destroy failed: {exc!r}")
            return
        if age_ms >= stale_hide_ms:
            self._debug(f"hide stale card age_ms={age_ms:.1f} stale_hide_ms={stale_hide_ms}")
            self._hide_card()

    def _show_card(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self._update_layout_metrics()
        self.root.update_idletasks()
        requested_height = self.container.winfo_reqheight() + 2
        max_height = max(SAFE_STRIP_HEIGHT, screen_h - SAFE_STRIP_MARGIN * 2)
        self._height = min(max(SAFE_STRIP_HEIGHT, requested_height), max_height)
        x = max(12, (screen_w - self._width) // 2)
        y = max(0, screen_h - self._height - SAFE_STRIP_MARGIN)
        self.root.geometry(f"{self._width}x{self._height}+{x}+{y}")
        self.root.deiconify()
        self.root.state("normal")
        self.root.update_idletasks()
        hwnd = self.root.winfo_id()
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            x,
            y,
            self._width,
            self._height,
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )
        self._debug(
            f"show card hwnd={hwnd} rect=({x},{y},{self._width},{self._height}) "
            f"visible={win32gui.IsWindowVisible(hwnd)}"
        )

    def _hide_card(self) -> None:
        self._hide_after_id = None
        try:
            if not self.root.winfo_viewable():
                return
            self.root.withdraw()
            self._debug("hide card")
        except Exception as exc:
            self._debug(f"hide failed: {exc!r}")

    def _apply_window_styles(self) -> None:
        hwnd = self.root.winfo_id()
        try:
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= (
                win32con.WS_EX_TOOLWINDOW
                | win32con.WS_EX_NOACTIVATE
                | win32con.WS_EX_TOPMOST
                | win32con.WS_EX_LAYERED
                | win32con.WS_EX_TRANSPARENT
            )
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, 244, win32con.LWA_ALPHA)
            self._debug(f"overlay styles applied hwnd={hwnd} ex_style={ex_style}")
        except Exception as exc:
            self._debug(f"style apply failed: {exc!r}")

    def _fit_text(
        self,
        text: str,
        max_width_px: int,
        *,
        fallback: str = "等待状态更新...",
        font=None,
    ) -> str:
        text = text.strip() or fallback
        active_font = font or self._message_font
        if max_width_px <= 0:
            return text
        if active_font.measure(text) <= max_width_px:
            return text

        ellipsis = "..."
        clipped = text
        while clipped and active_font.measure(clipped + ellipsis) > max_width_px:
            clipped = clipped[:-1]
        return (clipped.rstrip() + ellipsis) if clipped else ellipsis

    def _debug(self, message: str) -> None:
        try:
            self._debug_file.parent.mkdir(parents=True, exist_ok=True)
            with self._debug_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.time():.3f} {message}\n")
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    app = OverlayApp(Path(args.status_file))
    app.root.mainloop()
    with suppress(Exception):
        app._pid_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
