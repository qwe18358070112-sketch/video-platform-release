from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

import psutil

from common import StatusOverlayConfig, resolve_output_path


class StatusPublisher:
    def __init__(self, config: StatusOverlayConfig, config_path: Path, logger):
        self._config = config
        self._config_path = config_path
        self._logger = logger
        self._status_file = resolve_output_path(config_path, config.status_file)
        self._pid_file = self._status_file.with_suffix(".overlay.pid")
        self._overlay_script = Path(__file__).resolve().with_name("status_overlay.py")
        self._preferred_pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not self._preferred_pythonw.exists():
            self._preferred_pythonw = Path(sys.executable)
        self._expected_overlay_executables = {
            self._normalize_path(Path(sys.executable)),
            self._normalize_path(self._preferred_pythonw),
        }
        self._expected_overlay_process_names = {"python.exe", "pythonw.exe"}
        self._expected_overlay_script = self._normalize_path(self._overlay_script)
        self._expected_status_file = self._normalize_path(self._status_file)
        self._overlay_process_started = False
        self._overlay_process: subprocess.Popen[str] | None = None
        self._last_signature: tuple[str, str, str, str, str, str, bool] | None = None
        self._last_publish_at = 0.0
        self._dedupe_window_seconds = 0.12
        self._overlay_ensure_thread: threading.Thread | None = None
        self._overlay_ensure_lock = threading.Lock()
        self._overlay_ensure_min_interval_seconds = 0.6
        self._overlay_ensure_last_requested_at = 0.0

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def start(self) -> None:
        if not self._config.enabled:
            return
        self._status_file.parent.mkdir(parents=True, exist_ok=True)
        signature = (
            "视频轮巡助手",
            "准备启动",
            "等待下一条状态更新。",
            "info",
            "",
            "状态初始化中",
            False,
        )
        payload = self._build_payload(
            title="视频轮巡助手",
            message="准备启动",
            details="状态栏会跟随程序动作实时同步。",
            level="info",
            hotkey_hint="状态初始化中",
        )
        # 关键修复：启动时先落一份非关闭态 payload。
        # 这样即使复用到的是上一轮刚停机的 overlay，它也会先看到新的“准备启动”状态，
        # 不会因为上一轮残留的 close_requested 而在本轮启动中途自杀。
        self._persist_payload(payload, signature=signature)
        self._overlay_process_started = False
        self._overlay_process = None
        self._ensure_overlay_process_for_start()
        self._wait_for_overlay_ready(timeout_seconds=0.8)

    def _terminate_overlay_process(self) -> None:
        matching_processes = self._matching_overlay_processes()
        if not matching_processes:
            existing_pid = self._read_overlay_pid()
            if existing_pid:
                self._logger.warning(
                    "Ignoring stale overlay pid=%s because it does not match the expected overlay process",
                    existing_pid,
                )
            self._overlay_process_started = False
            self._overlay_process = None
            self._clear_overlay_pid_file()
            return

        for process in matching_processes:
            with suppress(Exception):
                process.terminate()
        for _ in range(10):
            if not any(self._is_process_alive(process.pid) for process in matching_processes):
                break
            time.sleep(0.05)
        self._overlay_process_started = False
        self._overlay_process = None
        self._clear_overlay_pid_file()

    def _ensure_overlay_process(self) -> None:
        if self._overlay_process_started:
            existing_pid = self._read_overlay_pid()
            if existing_pid and self._is_process_alive(existing_pid):
                return
            self._overlay_process_started = False

        existing_pid = self._read_overlay_pid()
        verified_process = self._verified_overlay_process(existing_pid)
        if verified_process is not None:
            blocked_reason = self._overlay_reuse_blocked_reason()
            if blocked_reason is not None:
                self._logger.info(
                    "Skipping status overlay reuse pid=%s reason=%s",
                    verified_process.pid,
                    blocked_reason,
                )
                with suppress(Exception):
                    verified_process.terminate()
                self._clear_overlay_pid_file()
                existing_pid = None
            else:
                self._terminate_duplicate_overlay_processes(keep_pid=verified_process.pid)
                if psutil.pid_exists(verified_process.pid):
                    self._write_overlay_pid(verified_process.pid)
                    self._overlay_process_started = True
                    self._overlay_process = None
                    self._logger.info("Reusing status overlay pid=%s via pid_file", verified_process.pid)
                    return
                self._logger.warning(
                    "Discarding unstable overlay pid=%s because it disappeared during reuse validation",
                    verified_process.pid,
                )
                self._clear_overlay_pid_file()
                existing_pid = None
        if existing_pid:
            self._logger.warning(
                "Discarding stale overlay pid=%s because it does not match the expected overlay process",
                existing_pid,
            )
            self._clear_overlay_pid_file()

        matching_processes = self._matching_overlay_processes()
        if matching_processes:
            matching_processes.sort(key=lambda process: process.pid)
            verified_process = matching_processes[0]
            for duplicate in matching_processes[1:]:
                # 关键修复：同一个 status_file 只能保留一个浮窗进程。
                # 否则会出现提示词叠层、卡屏和“明明已经关闭还留在桌面上”的错觉。
                with suppress(Exception):
                    duplicate.terminate()
            self._write_overlay_pid(verified_process.pid)
            self._overlay_process_started = True
            self._overlay_process = None
            self._logger.info("Reusing status overlay pid=%s", verified_process.pid)
            return

        self._launch_overlay_process()

    def _ensure_overlay_process_for_start(self) -> None:
        existing_pid = self._read_overlay_pid()
        verified_process = self._verified_overlay_process(existing_pid)
        if verified_process is not None:
            blocked_reason = self._overlay_reuse_blocked_reason()
            if blocked_reason is None:
                self._write_overlay_pid(verified_process.pid)
                self._overlay_process_started = True
                self._overlay_process = None
                self._logger.info("Reusing status overlay pid=%s via startup pid_file", verified_process.pid)
                return
            self._logger.info(
                "Skipping status overlay startup reuse pid=%s reason=%s",
                verified_process.pid,
                blocked_reason,
            )
            with suppress(Exception):
                verified_process.terminate()
            for _ in range(6):
                if not self._is_process_alive(verified_process.pid):
                    break
                time.sleep(0.05)
            self._clear_overlay_pid_file()
        elif existing_pid:
            self._logger.warning(
                "Discarding stale startup overlay pid=%s because it does not match the expected overlay process",
                existing_pid,
            )
            self._clear_overlay_pid_file()

        self._launch_overlay_process()

    def _launch_overlay_process(self) -> None:
        try:
            process = subprocess.Popen(
                [str(self._preferred_pythonw), str(self._overlay_script), "--status-file", str(self._status_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            time.sleep(0.2)
            if process.poll() is None:
                self._write_overlay_pid(process.pid)
                self._overlay_process_started = True
                self._overlay_process = process
                self._logger.info("Started status overlay pid=%s via pythonw", process.pid)
                return
            fallback = subprocess.Popen(
                [str(Path(sys.executable)), str(self._overlay_script), "--status-file", str(self._status_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            self._write_overlay_pid(fallback.pid)
            self._overlay_process_started = fallback.poll() is None
            self._overlay_process = fallback if self._overlay_process_started else None
            if self._overlay_process_started:
                self._logger.info("Started status overlay pid=%s via python fallback", fallback.pid)
            else:
                self._clear_overlay_pid_file()
        except Exception as exc:
            self._logger.warning("Failed to launch status overlay: %s", exc)

    def publish(
        self,
        title: str,
        message: str,
        details: str = "",
        level: str = "info",
        *,
        meta: str = "",
        hotkey_hint: str = "",
        close_requested: bool = False,
    ) -> None:
        if not self._config.enabled:
            return
        # 关键修复：overlay 进程探测 / 复用 / 拉起不能阻塞自动化主线程。
        # 否则固定程序会卡在 startup warmup，只留下 “STARTUP_WARMUP begin”。
        self._request_overlay_process_async(reason="publish")
        signature = (title, message, details, level, meta, hotkey_hint, close_requested)
        now = time.monotonic()
        if not close_requested and signature == self._last_signature and (now - self._last_publish_at) < self._dedupe_window_seconds:
            return

        payload = self._build_payload(
            title=title,
            message=message,
            details=details,
            level=level,
            meta=meta,
            hotkey_hint=hotkey_hint,
            close_requested=close_requested,
        )
        self._persist_payload(payload, signature=signature, published_at=now)

    def stop(self, message: str = "程序已停止") -> None:
        if not self._config.enabled:
            return
        self.publish(
            title="视频轮巡助手",
            message=message,
            details="状态栏会自动关闭。",
            level="success",
            close_requested=True,
        )

    def _request_overlay_process_async(self, *, reason: str) -> None:
        if not self._config.enabled:
            return
        with self._overlay_ensure_lock:
            current_thread = self._overlay_ensure_thread
            if current_thread is not None and current_thread.is_alive():
                return
            now = time.monotonic()
            if (now - self._overlay_ensure_last_requested_at) < self._overlay_ensure_min_interval_seconds:
                return
            self._overlay_ensure_last_requested_at = now
            thread = threading.Thread(
                target=self._ensure_overlay_process_async_worker,
                args=(reason,),
                name="status-overlay-ensure",
                daemon=True,
            )
            self._overlay_ensure_thread = thread
            thread.start()

    def _wait_for_overlay_ready(self, timeout_seconds: float) -> None:
        if not self._config.enabled:
            return
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            existing_pid = self._read_overlay_pid()
            verified = self._verified_overlay_process(existing_pid)
            if verified is not None:
                return
            time.sleep(0.05)

    def _ensure_overlay_process_async_worker(self, reason: str) -> None:
        try:
            self._ensure_overlay_process()
        except Exception as exc:
            self._logger.warning("Status overlay async ensure failed reason=%s error=%s", reason, exc)
        finally:
            with self._overlay_ensure_lock:
                current_thread = threading.current_thread()
                if self._overlay_ensure_thread is current_thread:
                    self._overlay_ensure_thread = None

    def _read_overlay_pid(self) -> int | None:
        try:
            return int(self._pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _write_overlay_pid(self, pid: int) -> None:
        self._pid_file.write_text(str(pid), encoding="utf-8")

    def _clear_overlay_pid_file(self) -> None:
        with suppress(Exception):
            self._pid_file.unlink(missing_ok=True)

    def _read_status_payload(self) -> dict[str, object] | None:
        try:
            raw = json.loads(self._status_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    def _overlay_reuse_blocked_reason(self) -> str | None:
        payload = self._read_status_payload()
        if not payload:
            return None
        if payload.get("close_requested"):
            return "close_requested"
        return None

    def _build_payload(
        self,
        *,
        title: str,
        message: str,
        details: str = "",
        level: str = "info",
        meta: str = "",
        hotkey_hint: str = "",
        close_requested: bool = False,
    ) -> dict[str, object]:
        return {
            "timestamp": time.time(),
            "title": title,
            "message": message,
            "details": details,
            "level": level,
            "meta": meta,
            "hotkey_hint": hotkey_hint,
            "close_requested": close_requested,
            "close_delay_ms": self._config.close_delay_ms,
            "auto_hide_ms": self._config.auto_hide_ms,
            "stale_hide_ms": self._config.stale_hide_ms,
        }

    def _persist_payload(
        self,
        payload: dict[str, object],
        *,
        signature: tuple[str, str, str, str, str, str, bool] | None = None,
        published_at: float | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        temp_file = self._status_file.with_suffix(".tmp")

        for _ in range(3):
            try:
                temp_file.write_text(body, encoding="utf-8")
                temp_file.replace(self._status_file)
                if signature is not None:
                    self._last_signature = signature
                if published_at is not None:
                    self._last_publish_at = published_at
                return
            except PermissionError:
                time.sleep(0.05)
            except Exception as exc:
                self._logger.warning("Status overlay publish failed: %s", exc)
                return

        try:
            self._status_file.write_text(body, encoding="utf-8")
            if signature is not None:
                self._last_signature = signature
            if published_at is not None:
                self._last_publish_at = published_at
        except Exception as exc:
            self._logger.warning("Status overlay fallback write failed: %s", exc)
        finally:
            with suppress(Exception):
                temp_file.unlink(missing_ok=True)

    def _is_process_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if self._overlay_process is not None and self._overlay_process.pid == pid:
                return self._overlay_process.poll() is None
            return self._verified_overlay_process(pid) is not None
        except Exception as exc:
            self._logger.warning("Status overlay alive-check failed for pid=%s: %s", pid, exc)
            return False

    def _verified_overlay_process(self, pid: int | None) -> psutil.Process | None:
        if pid is None or pid <= 0:
            return None
        try:
            process = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.Error):
            return None
        return process if self._matches_overlay_process(process) else None

    def _matching_overlay_processes(self) -> list[psutil.Process]:
        matches: list[psutil.Process] = []
        for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            if self._matches_overlay_process(process):
                matches.append(process)
        return matches

    def _matches_overlay_process(self, process: psutil.Process) -> bool:
        try:
            process_name = str(process.name()).strip().lower()
            executable = self._normalize_path(process.exe())
            cmdline = process.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.Error):
            return False

        if (
            executable not in self._expected_overlay_executables
            and process_name not in self._expected_overlay_process_names
        ):
            return False

        normalized_args = [str(arg).strip().lower() for arg in cmdline]
        normalized_paths = {self._normalize_path(arg) for arg in cmdline if str(arg).strip()}
        if self._expected_overlay_script not in normalized_paths:
            return False

        status_arg_index = next((index for index, arg in enumerate(normalized_args) if arg == "--status-file"), -1)
        if status_arg_index < 0 or status_arg_index + 1 >= len(cmdline):
            return False
        if self._normalize_path(cmdline[status_arg_index + 1]) != self._expected_status_file:
            return False
        return True

    def _terminate_duplicate_overlay_processes(self, *, keep_pid: int) -> None:
        if keep_pid <= 0:
            return
        for process in self._matching_overlay_processes():
            if process.pid == keep_pid:
                continue
            with suppress(Exception):
                process.terminate()

    @staticmethod
    def _normalize_path(value: str | Path) -> str:
        return str(Path(value).resolve()).lower()
