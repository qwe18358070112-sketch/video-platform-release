from __future__ import annotations

import ctypes
import sys
import threading
from contextlib import suppress
from ctypes import wintypes
from queue import Empty, Queue
from typing import Callable


if sys.platform.startswith("win"):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WM_HOTKEY = 0x0312
    WM_APP_TASK = 0x8001
    PM_NOREMOVE = 0x0000
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
else:
    user32 = None
    kernel32 = None
    WM_HOTKEY = 0
    WM_APP_TASK = 0
    PM_NOREMOVE = 0
    MOD_ALT = 0
    MOD_CONTROL = 0
    MOD_SHIFT = 0
    MOD_WIN = 0
    MOD_NOREPEAT = 0


_MODIFIER_TOKENS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}

_VK_ALIASES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
}


def native_hotkeys_supported() -> bool:
    return sys.platform.startswith("win") and user32 is not None and kernel32 is not None


def parse_hotkey_spec(spec: str | None) -> tuple[int, int, str] | None:
    if not native_hotkeys_supported() or spec is None:
        return None
    raw = str(spec).strip().lower()
    if raw in {"", "disabled", "none", "off"}:
        return None
    tokens = [part.strip() for part in raw.split("+") if part.strip()]
    if not tokens:
        return None

    modifiers = 0
    key_token = ""
    for token in tokens:
        if token in _MODIFIER_TOKENS:
            modifiers |= _MODIFIER_TOKENS[token]
            continue
        if key_token:
            return None
        key_token = token
    if not key_token:
        return None

    vk = _vk_from_token(key_token)
    if vk is None:
        return None
    normalized = "+".join([token for token in tokens if token in _MODIFIER_TOKENS] + [key_token])
    return modifiers | MOD_NOREPEAT, vk, normalized


def _vk_from_token(token: str) -> int | None:
    if token in _VK_ALIASES:
        return _VK_ALIASES[token]
    if len(token) == 1 and token.isalpha():
        return ord(token.upper())
    if len(token) == 1 and token.isdigit():
        return ord(token)
    if token.startswith("f") and token[1:].isdigit():
        index = int(token[1:])
        if 1 <= index <= 24:
            return 0x70 + index - 1
    return None


class NativeHotkeyManager:
    def __init__(self, logger=None):
        self._logger = logger
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._tasks: Queue[Callable[[], None]] = Queue()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered_ids: set[int] = set()
        self._next_hotkey_id = 1
        self._lock = threading.Lock()
        self._startup_error: str | None = None

    def start(self) -> bool:
        if not native_hotkeys_supported():
            return False
        if self._thread is not None:
            return self._startup_error is None
        self._thread = threading.Thread(target=self._message_loop, name="native-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._startup_error is None and self._thread_id is not None

    def register(self, spec: str, callback: Callable[[], None]) -> int | None:
        parsed = parse_hotkey_spec(spec)
        if parsed is None:
            return None
        if not self.start():
            return None

        with self._lock:
            hotkey_id = self._next_hotkey_id
            self._next_hotkey_id += 1

        modifiers, vk, normalized = parsed
        result_ready = threading.Event()
        result: dict[str, object] = {}

        def task() -> None:
            ctypes.set_last_error(0)
            success = bool(user32.RegisterHotKey(None, hotkey_id, modifiers, vk))
            if success:
                self._callbacks[hotkey_id] = callback
                self._registered_ids.add(hotkey_id)
                result["registered"] = True
                return
            error_code = ctypes.get_last_error()
            result["error_code"] = error_code
            result["registered"] = False
            if self._logger is not None:
                self._logger.warning(
                    "Native hotkey registration failed spec=%s normalized=%s error=%s; falling back to keyboard hooks",
                    spec,
                    normalized,
                    error_code,
                )

        self._post_task(task, result_ready)
        if not result_ready.wait(timeout=2.0):
            return None
        if not bool(result.get("registered")):
            return None
        return hotkey_id

    def unregister(self, hotkey_id: int) -> None:
        if not native_hotkeys_supported():
            return
        if hotkey_id not in self._registered_ids or self._thread_id is None:
            return
        done = threading.Event()

        def task() -> None:
            with suppress(Exception):
                user32.UnregisterHotKey(None, hotkey_id)
            self._registered_ids.discard(hotkey_id)
            self._callbacks.pop(hotkey_id, None)

        self._post_task(task, done)
        done.wait(timeout=1.0)

    def stop(self) -> None:
        if self._thread is None or self._thread_id is None:
            return
        done = threading.Event()

        def task() -> None:
            for hotkey_id in list(self._registered_ids):
                with suppress(Exception):
                    user32.UnregisterHotKey(None, hotkey_id)
            self._registered_ids.clear()
            self._callbacks.clear()
            user32.PostQuitMessage(0)

        self._post_task(task, done)
        done.wait(timeout=1.0)
        self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None
        self._stopped.set()

    def _post_task(self, callback: Callable[[], None], done: threading.Event | None = None) -> None:
        def wrapped() -> None:
            try:
                callback()
            finally:
                if done is not None:
                    done.set()

        self._tasks.put(wrapped)
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_APP_TASK, 0, 0)
        elif done is not None:
            done.set()

    def _message_loop(self) -> None:
        try:
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
            self._thread_id = int(kernel32.GetCurrentThreadId())
        except Exception as exc:
            self._startup_error = str(exc)
            self._ready.set()
            return

        self._ready.set()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == -1:
                self._startup_error = f"GetMessageW failed: {ctypes.get_last_error()}"
                return
            if result == 0:
                return
            if msg.message == WM_APP_TASK:
                while True:
                    try:
                        task = self._tasks.get_nowait()
                    except Empty:
                        break
                    with suppress(Exception):
                        task()
                continue
            if msg.message != WM_HOTKEY:
                continue
            callback = self._callbacks.get(int(msg.wParam))
            if callback is None:
                continue
            with suppress(Exception):
                callback()
