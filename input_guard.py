from __future__ import annotations

import math
import threading
import time
from typing import Iterable

import keyboard
import win32api

from common import InputGuardConfig


class InputGuard:
    def __init__(self, config: InputGuardConfig, logger, ignored_hotkeys: Iterable[str] | None = None):
        self._config = config
        self._logger = logger
        self._ignored_keys = self._normalize_ignored_keys(ignored_hotkeys or [])
        self._last_manual_input_at = 0.0
        self._last_manual_input_kind = ""
        self._suppressed_until = 0.0
        self._cursor_pos_warning_active = False
        self._last_mouse_pos = self._safe_get_cursor_pos()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._mouse_thread: threading.Thread | None = None
        self._keyboard_hook = None

    def start(self) -> None:
        if not self._config.enabled:
            return
        self._stop_event.clear()
        self._keyboard_hook = keyboard.hook(self._on_keyboard_event, suppress=False)
        self._mouse_thread = threading.Thread(target=self._watch_mouse, name="input-guard-mouse", daemon=True)
        self._mouse_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._keyboard_hook is not None:
            keyboard.unhook(self._keyboard_hook)
            self._keyboard_hook = None
        if self._mouse_thread and self._mouse_thread.is_alive():
            self._mouse_thread.join(timeout=1.0)

    def mark_programmatic_action(self) -> None:
        if not self._config.enabled:
            return
        self.suppress_manual_detection()

    def suppress_manual_detection(self, duration_ms: int | None = None) -> None:
        if not self._config.enabled:
            return
        duration = (duration_ms if duration_ms is not None else self._config.suppress_after_programmatic_input_ms) / 1000.0
        with self._lock:
            self._suppressed_until = max(self._suppressed_until, time.monotonic() + duration)
            self._last_manual_input_at = 0.0
            self._last_manual_input_kind = ""
            self._last_mouse_pos = self._safe_get_cursor_pos()

    def clear_manual_activity(self) -> None:
        with self._lock:
            self._last_manual_input_at = 0.0
            self._last_manual_input_kind = ""
            self._last_mouse_pos = self._safe_get_cursor_pos()

    def has_recent_manual_input(self) -> bool:
        if not self._config.enabled:
            return False
        with self._lock:
            last_input = self._last_manual_input_at
        return last_input > 0 and (time.monotonic() - last_input) < self._config.idle_resume_seconds

    def ready_to_auto_resume(self) -> bool:
        if not self._config.enabled:
            return True
        return not self.has_recent_manual_input()

    def last_manual_input_kind(self) -> str:
        with self._lock:
            return self._last_manual_input_kind

    def _watch_mouse(self) -> None:
        poll_interval = self._config.poll_interval_ms / 1000.0
        while not self._stop_event.wait(poll_interval):
            current_pos = self._safe_get_cursor_pos()
            with self._lock:
                suppressed = time.monotonic() < self._suppressed_until
                distance = math.dist(current_pos, self._last_mouse_pos)
                self._last_mouse_pos = current_pos
                if not suppressed and distance >= self._config.mouse_move_threshold:
                    self._last_manual_input_at = time.monotonic()
                    self._last_manual_input_kind = "mouse_move"

    def _on_keyboard_event(self, event) -> None:
        if event.event_type != "down":
            return
        event_name = str(event.name).lower()
        if event_name in {
            "shift",
            "left shift",
            "right shift",
            "ctrl",
            "left ctrl",
            "right ctrl",
            "alt",
            "left alt",
            "right alt",
        }:
            return
        if event_name in self._ignored_keys:
            return
        with self._lock:
            if time.monotonic() < self._suppressed_until:
                return
            self._last_manual_input_at = time.monotonic()
            self._last_manual_input_kind = "keyboard"

    @staticmethod
    def _normalize_ignored_keys(hotkeys: Iterable[str]) -> set[str]:
        ignored: set[str] = set()
        for hotkey in hotkeys:
            parts = [part.strip().lower() for part in str(hotkey).split("+") if part.strip()]
            if parts:
                ignored.add(parts[-1])
        return ignored

    def _safe_get_cursor_pos(self) -> tuple[int, int]:
        # 中文注释：有些高完整性桌面态下 GetCursorPos 会返回“拒绝访问”。
        # 这里退化为沿用上一帧坐标，只关闭鼠标位移探测，不允许把整个调度器启动打崩。
        fallback = getattr(self, "_last_mouse_pos", (0, 0))
        try:
            position = win32api.GetCursorPos()
        except Exception as exc:
            if not self._cursor_pos_warning_active:
                self._logger.warning("INPUT_GUARD cursor probe unavailable; mouse-move detection degraded: %s", exc)
                self._cursor_pos_warning_active = True
            return fallback
        if self._cursor_pos_warning_active:
            self._logger.info("INPUT_GUARD cursor probe recovered")
            self._cursor_pos_warning_active = False
        return position
