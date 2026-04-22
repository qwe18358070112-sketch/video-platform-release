from __future__ import annotations

import ctypes
import subprocess
import tempfile
import time
from pathlib import Path

import win32api
import win32con
import win32gui
import win32process

from common import TimingConfig
from native_runtime_client import NativeRuntimeClient


class ControllerActionError(RuntimeError):
    pass


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _InputUnion)]


class Controller:
    def __init__(
        self,
        timing: TimingConfig,
        logger,
        *,
        backend: str = "sendmessage",
        autohotkey_path: str | None = None,
        native_client: NativeRuntimeClient | None = None,
    ):
        self._timing = timing
        self._logger = logger
        self._user32 = ctypes.windll.user32
        self._backend = backend
        self._autohotkey_path = self._resolve_autohotkey_path(autohotkey_path)
        self._native_client = native_client
        self._script_dir = Path(tempfile.gettempdir()) / "infovision_auto_ahk"
        self._script_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_autohotkey_path(self, raw_path: str | None) -> Path | None:
        # 为跨电脑部署做兜底：即使 config 未写死路径，也尝试搜索常见安装位置。
        candidates: list[Path] = []
        if raw_path:
            candidates.append(Path(raw_path))
        candidates.extend(
            [
                Path(r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"),
                Path(r"C:\Program Files\AutoHotkey\AutoHotkey64.exe"),
                Path(r"C:\Program Files\AutoHotkey\v2\AutoHotkey.exe"),
                Path.home() / r"AppData/Local/Programs/AutoHotkey/v2/AutoHotkey64.exe",
                Path.home() / r"AppData/Local/Programs/AutoHotkey/AutoHotkey64.exe",
            ]
        )
        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate.resolve()
            except OSError:
                continue
        return Path(raw_path).resolve() if raw_path else None

    def select_and_zoom(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
    ) -> None:
        self.click_once(point, hwnd=hwnd, client_origin=client_origin, action_type="select")
        time.sleep(self._timing.click_after_select_ms / 1000.0)
        self.double_click(point, hwnd=hwnd, client_origin=client_origin, action_type="zoom_in")
        time.sleep(max(0.2, self._timing.double_click_interval_ms / 1000.0))

    def select_cell(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
    ) -> None:
        self.click_once(point, hwnd=hwnd, client_origin=client_origin, action_type="select")

    def restore_zoom(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
    ) -> None:
        self.double_click(point, hwnd=hwnd, client_origin=client_origin, action_type="zoom_out")
        time.sleep(max(0.15, self._timing.double_click_interval_ms / 1000.0))

    def emergency_recover(self, hwnd: int | None = None) -> None:
        if self._backend == "native_engine" and self._native_client is not None and self._native_client.enabled:
            try:
                if hwnd is not None:
                    self._focus_window_for_keyboard_input(hwnd)
                self._logger.warning("Sending ESC for emergency recovery via native engine")
                self._native_client.send_key("escape")
                return
            except Exception as exc:
                self._logger.warning("Native emergency recover failed; falling back to Win32 keybd_event: %s", exc)
        if hwnd is not None:
            self._focus_window_for_keyboard_input(hwnd)
        self._logger.warning("Sending ESC for emergency recovery")
        win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

    def recover_to_grid(self, hwnd: int | None = None) -> None:
        self.emergency_recover(hwnd=hwnd)

    def close_foreground_window(self) -> None:
        if self._backend == "native_engine" and self._native_client is not None and self._native_client.enabled:
            try:
                self._logger.warning("Sending Alt+F4 via native engine to close the foreground window")
                self._native_client.send_key("alt_f4")
                return
            except Exception as exc:
                self._logger.warning("Native close-foreground failed; falling back to keybd_event: %s", exc)
        self._logger.warning("Sending Alt+F4 to close the foreground window")
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(win32con.VK_F4, 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(win32con.VK_F4, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

    def click_once(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
        *,
        action_type: str = "click_once",
    ) -> None:
        self._logger.info(
            "CONTROL action_type=%s point=%s backend=%s hwnd=%s",
            action_type,
            point,
            self._backend,
            hwnd,
        )
        if self._backend == "real_mouse":
            self._click_with_real_mouse(point, action_type=action_type, double=False)
            return
        if self._backend == "native_engine" and self._native_client is not None and self._native_client.enabled:
            try:
                self._native_client.pointer_action(point[0], point[1], double=False)
                return
            except Exception as exc:
                self._logger.warning("Native single-click failed; falling back to real_mouse: %s", exc)
                self._click_with_real_mouse(point, action_type=action_type, double=False)
                return
        if self._backend == "ahk_controlclick":
            if hwnd is None:
                raise RuntimeError("ahk_controlclick backend requires hwnd")
            self._send_ahk_controlclick(hwnd, point, click_count=1)
            return
        if hwnd is not None and client_origin is not None:
            self._send_window_click(hwnd, point, client_origin, double=False)
            return
        self._click_with_sendinput_cursor_restore(point, double=False)

    def single_click(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
    ) -> None:
        self.click_once(point, hwnd=hwnd, client_origin=client_origin, action_type="single_click")

    def double_click(
        self,
        point: tuple[int, int],
        hwnd: int | None = None,
        client_origin: tuple[int, int] | None = None,
        *,
        action_type: str = "double_click",
    ) -> None:
        self._logger.info(
            "CONTROL action_type=%s point=%s backend=%s hwnd=%s interval_ms=%s",
            action_type,
            point,
            self._backend,
            hwnd,
            self._timing.double_click_interval_ms,
        )
        if self._backend == "real_mouse":
            self._click_with_real_mouse(point, action_type=action_type, double=True)
            return
        if self._backend == "native_engine" and self._native_client is not None and self._native_client.enabled:
            try:
                self._native_client.pointer_action(point[0], point[1], double=True)
                return
            except Exception as exc:
                self._logger.warning("Native double-click failed; falling back to real_mouse: %s", exc)
                self._click_with_real_mouse(point, action_type=action_type, double=True)
                return
        if self._backend == "ahk_controlclick":
            if hwnd is None:
                raise RuntimeError("ahk_controlclick backend requires hwnd")
            self._send_ahk_controlclick(hwnd, point, click_count=2)
            return
        if hwnd is not None and client_origin is not None:
            self._send_window_click(hwnd, point, client_origin, double=True)
            return
        self._click_with_sendinput_cursor_restore(point, double=True)

    def _move_cursor(self, point: tuple[int, int]) -> None:
        self._ensure_screen_point(point)
        self._send_input_move(point)

    def _mouse_click(self) -> None:
        self._send_input_flags(win32con.MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.02)
        self._send_input_flags(win32con.MOUSEEVENTF_LEFTUP)

    def _move_cursor_real(self, point: tuple[int, int]) -> None:
        self._ensure_screen_point(point)
        win32api.SetCursorPos(point)

    def _current_cursor_pos(self) -> tuple[int, int] | None:
        try:
            return tuple(int(value) for value in win32api.GetCursorPos())
        except Exception:
            return None

    def _restore_cursor_after_pointer_action(
        self,
        original_point: tuple[int, int] | None,
        target_point: tuple[int, int],
        *,
        backend: str,
    ) -> None:
        if original_point is None or original_point == target_point:
            return
        try:
            win32api.SetCursorPos(original_point)
        except Exception as exc:
            self._logger.debug(
                "CONTROL cursor restore skipped backend=%s target=%s original=%s error=%s",
                backend,
                target_point,
                original_point,
                exc,
            )

    def _mouse_click_real(self) -> None:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _send_window_click(
        self,
        hwnd: int,
        point: tuple[int, int],
        client_origin: tuple[int, int],
        *,
        double: bool,
    ) -> None:
        rel_x = max(0, point[0] - client_origin[0])
        rel_y = max(0, point[1] - client_origin[1])
        lparam = win32api.MAKELONG(rel_x, rel_y)
        win32gui.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
        if double:
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            time.sleep(self._timing.double_click_interval_ms / 1000.0)
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lparam)
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        else:
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)

    def _send_ahk_controlclick(self, hwnd: int, point: tuple[int, int], click_count: int) -> None:
        if not self._autohotkey_path or not self._autohotkey_path.exists():
            raise RuntimeError(
                f"AutoHotkey executable was not found. Configure window.autohotkey_path. Current: {self._autohotkey_path}"
            )

        window_rect = win32gui.GetWindowRect(hwnd)
        rel_x = max(0, point[0] - window_rect[0])
        rel_y = max(0, point[1] - window_rect[1])
        script_path = self._script_dir / f"controlclick_{hwnd}_{rel_x}_{rel_y}_{click_count}.ahk"
        script_path.write_text(
            "\n".join(
                [
                    "#Requires AutoHotkey v2.0",
                    'SetTitleMatchMode 2',
                    f'WinActivate "ahk_id {hwnd}"',
                    f'WinWaitActive "ahk_id {hwnd}",, 2',
                    "Sleep 120",
                    f'ControlClick "x{rel_x} y{rel_y}", "ahk_id {hwnd}",,,, "NA"',
                    *(["Sleep 80", f'ControlClick "x{rel_x} y{rel_y}", "ahk_id {hwnd}",,,, "NA"'] if click_count == 2 else []),
                    "Sleep 120",
                ]
            ),
            encoding="utf-8",
        )
        self._logger.debug(
            "AHK control click backend hwnd=%s rel=(%s,%s) click_count=%s script=%s",
            hwnd,
            rel_x,
            rel_y,
            click_count,
            script_path,
        )
        completed = subprocess.run(
            [str(self._autohotkey_path), str(script_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"AutoHotkey control click failed with exit code {completed.returncode}: {completed.stderr or completed.stdout}"
            )

    def _send_input_move(self, point: tuple[int, int]) -> None:
        screen_w = max(1, self._user32.GetSystemMetrics(0) - 1)
        screen_h = max(1, self._user32.GetSystemMetrics(1) - 1)
        abs_x = int(point[0] * 65535 / screen_w)
        abs_y = int(point[1] * 65535 / screen_h)
        extra = ctypes.c_ulong(0)
        union = _InputUnion()
        union.mi = _MouseInput(
            dx=abs_x,
            dy=abs_y,
            mouseData=0,
            dwFlags=win32con.MOUSEEVENTF_MOVE | win32con.MOUSEEVENTF_ABSOLUTE,
            time=0,
            dwExtraInfo=ctypes.pointer(extra),
        )
        command = _Input(type=0, ii=union)
        sent = self._user32.SendInput(1, ctypes.byref(command), ctypes.sizeof(command))
        if sent != 1:
            raise ControllerActionError(f"SendInput move failed for point={point}")

    def _send_input_flags(self, flags: int) -> None:
        extra = ctypes.c_ulong(0)
        union = _InputUnion()
        union.mi = _MouseInput(
            dx=0,
            dy=0,
            mouseData=0,
            dwFlags=flags,
            time=0,
            dwExtraInfo=ctypes.pointer(extra),
        )
        command = _Input(type=0, ii=union)
        sent = self._user32.SendInput(1, ctypes.byref(command), ctypes.sizeof(command))
        if sent != 1:
            raise ControllerActionError(f"SendInput click flags failed flags={flags}")

    def _click_with_sendinput_cursor_restore(self, point: tuple[int, int], *, double: bool) -> None:
        original_point = self._current_cursor_pos()
        try:
            self._move_cursor(point)
            self._mouse_click()
            if double:
                time.sleep(self._timing.double_click_interval_ms / 1000.0)
                self._mouse_click()
        finally:
            self._restore_cursor_after_pointer_action(original_point, point, backend="sendinput")

    def _click_with_real_mouse(self, point: tuple[int, int], *, action_type: str, double: bool) -> None:
        primary_error: Exception | None = None
        original_point = self._current_cursor_pos()
        try:
            self._move_cursor_real(point)
            self._mouse_click_real()
            if double:
                time.sleep(self._timing.double_click_interval_ms / 1000.0)
                self._mouse_click_real()
            return
        except Exception as exc:
            primary_error = exc
            self._logger.warning(
                "CONTROL real_mouse %s fallback to sendinput action_type=%s point=%s error=%s",
                "double-click" if double else "single-click",
                action_type,
                point,
                exc,
            )
        finally:
            self._restore_cursor_after_pointer_action(original_point, point, backend="real_mouse")

        try:
            self._click_with_sendinput_cursor_restore(point, double=double)
            return
        except Exception as exc:
            raise ControllerActionError(
                f"Both real_mouse and sendinput failed for action_type={action_type} point={point}: "
                f"real_mouse={primary_error!r} sendinput={exc!r}"
            ) from exc

    def _focus_window_for_keyboard_input(self, hwnd: int) -> None:
        if not win32gui.IsWindow(hwnd):
            raise ControllerActionError(f"Cannot focus invalid hwnd={hwnd} before keyboard recovery")

        foreground_hwnd = win32gui.GetForegroundWindow()
        current_thread_id = win32api.GetCurrentThreadId()
        foreground_thread_id = 0
        target_thread_id = 0
        attached_foreground = False
        attached_target = False

        try:
            if foreground_hwnd:
                foreground_thread_id, _ = win32process.GetWindowThreadProcessId(foreground_hwnd)
                if foreground_thread_id and foreground_thread_id != current_thread_id:
                    if self._user32.AttachThreadInput(current_thread_id, foreground_thread_id, True):
                        attached_foreground = True

            target_thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)
            if target_thread_id and target_thread_id != current_thread_id:
                if self._user32.AttachThreadInput(current_thread_id, target_thread_id, True):
                    attached_target = True

            for attempt in range(1, 4):
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                else:
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

                win32gui.BringWindowToTop(hwnd)
                if win32gui.GetForegroundWindow() != hwnd:
                    win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.06)

                if win32gui.GetForegroundWindow() == hwnd:
                    self._logger.info(
                        "Focused target window hwnd=%s before keyboard recovery on attempt=%s",
                        hwnd,
                        attempt,
                    )
                    return
        except Exception as exc:
            raise ControllerActionError(f"Failed to focus hwnd={hwnd} before keyboard recovery: {exc}") from exc
        finally:
            if attached_target:
                self._user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            if attached_foreground:
                self._user32.AttachThreadInput(current_thread_id, foreground_thread_id, False)

        raise ControllerActionError(f"Refusing to send ESC because hwnd={hwnd} could not be focused safely")

    def _ensure_screen_point(self, point: tuple[int, int]) -> None:
        screen_w = max(1, self._user32.GetSystemMetrics(0))
        screen_h = max(1, self._user32.GetSystemMetrics(1))
        x, y = point
        if not (0 <= x < screen_w and 0 <= y < screen_h):
            raise ControllerActionError(
                f"Point {point} is outside the current screen bounds {(screen_w, screen_h)}"
            )
