from __future__ import annotations

import json
import platform
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from common import WindowSearchConfig


class NativeRuntimeClientError(RuntimeError):
    pass


class NativeRuntimeClient:
    """Long-lived .NET sidecar for Windows-native window/input automation."""

    def __init__(self, repo_root: Path, config: WindowSearchConfig, logger):
        self._repo_root = self._resolve_repo_root(Path(repo_root).resolve(), config)
        self._config = config
        self._logger = logger
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._stderr_thread: threading.Thread | None = None
        self._stdout_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._config.native_runtime_enabled)

    def start(self) -> None:
        if not self.enabled:
            return
        if platform.system() != "Windows":
            raise NativeRuntimeClientError("Native runtime sidecar requires a Windows desktop session.")
        if self._process is not None and self._process.poll() is None:
            return

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = self._resolve_sidecar_command()
        self._logger.info("Starting native automation sidecar: %s", command)
        self._process = subprocess.Popen(
            command,
            cwd=self._repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        self._stdout_queue = queue.Queue()
        self._stdout_thread = threading.Thread(target=self._pump_stdout, name="native-runtime-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._pump_stderr, name="native-runtime-stderr", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        with self._lock:
            self._request_locked("ping", timeout=self._config.native_runtime_startup_timeout_seconds)

    def _resolve_sidecar_command(self) -> list[str]:
        published_binary = self._resolve_published_sidecar_binary()
        if published_binary is not None:
            return [
                str(published_binary),
                "serve",
                "--repo-root",
                str(self._repo_root),
                "--tree-depth",
                str(max(1, int(self._config.native_runtime_tree_depth))),
            ]

        dotnet = shutil.which("dotnet.exe") or shutil.which("dotnet")
        if not dotnet:
            raise NativeRuntimeClientError(
                "Neither a packaged native automation sidecar nor dotnet runtime was found for the native automation sidecar."
            )

        project_path = (self._repo_root / self._config.native_runtime_project).resolve()
        if not project_path.exists():
            raise NativeRuntimeClientError(f"Native runtime project was not found: {project_path}")

        return [
            dotnet,
            "run",
            "--project",
            str(project_path),
            "--framework",
            "net8.0-windows",
            "--",
            "serve",
            "--repo-root",
            str(self._repo_root),
            "--tree-depth",
            str(max(1, int(self._config.native_runtime_tree_depth))),
        ]

    def _resolve_published_sidecar_binary(self) -> Path | None:
        binary_name = "VideoPlatform.NativeProbe.exe"
        candidate_paths = [
            self._repo_root / "runtime" / "native_runtime" / binary_name,
            self._repo_root / "native_runtime" / "VideoPlatform.NativeProbe" / "publish" / "win-x64" / binary_name,
            self._repo_root / "native_runtime" / "publish" / "win-x64" / binary_name,
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                return candidate.resolve()
        return None

    @staticmethod
    def _resolve_repo_root(candidate_root: Path, config: WindowSearchConfig) -> Path:
        project_rel = Path(config.native_runtime_project)
        for root in (candidate_root, *candidate_root.parents):
            if (root / project_rel).exists():
                return root
        return candidate_root

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    self.request("shutdown", timeout=1.0)
                except Exception:
                    pass
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
        finally:
            self._process = None

    def request(
        self,
        command: str,
        *,
        timeout: float | None = None,
        startup_timeout: float | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise NativeRuntimeClientError("Native runtime sidecar is disabled in config.")

        if self._process is None or self._process.poll() is not None:
            self.start()
        with self._lock:
            effective_timeout = startup_timeout if startup_timeout is not None else timeout
            return self._request_locked(command, timeout=effective_timeout, **payload)

    def _request_locked(
        self,
        command: str,
        *,
        timeout: float | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None:
            raise NativeRuntimeClientError("Native runtime sidecar stdin is unavailable.")

        request_id = uuid.uuid4().hex
        message = {"id": request_id, "command": command, **payload}
        serialized = json.dumps(message, ensure_ascii=False) + "\n"
        try:
            process.stdin.write(serialized)
            process.stdin.flush()
        except Exception as exc:
            raise NativeRuntimeClientError(f"Failed to write request to native runtime sidecar: {exc}") from exc

        effective_timeout = timeout or self._config.native_runtime_command_timeout_seconds
        started = time.monotonic()
        stale_response_count = 0
        while True:
            remaining = max(0.1, effective_timeout - (time.monotonic() - started))
            try:
                raw = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise NativeRuntimeClientError(
                    f"Timed out waiting for native runtime response command={command!r} timeout={effective_timeout}"
                ) from exc
            if raw is None:
                stderr = ""
                try:
                    if process.stderr is not None:
                        stderr = process.stderr.read()
                except Exception:
                    stderr = ""
                raise NativeRuntimeClientError(
                    f"Native runtime sidecar exited unexpectedly while handling {command!r}. stderr={stderr.strip()}"
                )

            try:
                response = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise NativeRuntimeClientError(f"Invalid JSON from native runtime sidecar: {raw!r}") from exc
            if response.get("id") != request_id:
                stale_response_count += 1
                self._logger.warning(
                    "Native runtime sidecar response id mismatch expected=%s actual=%s command=%s stale_count=%s; discarding stale response",
                    request_id,
                    response.get("id"),
                    command,
                    stale_response_count,
                )
                continue
            if not response.get("ok", False):
                raise NativeRuntimeClientError(
                    f"Native runtime command failed command={command!r}: {response.get('error', 'unknown error')}"
                )
            result = response.get("result")
            if not isinstance(result, dict):
                return {}
            return result

    def find_target_window(self) -> dict[str, Any]:
        return self.request(
            "findTargetWindow",
            titleKeywords=self._config.title_keywords,
            processNames=self._config.process_names,
        )

    def get_window_info(self, hwnd: int) -> dict[str, Any]:
        return self.request("getWindowInfo", hwnd=int(hwnd))

    def focus_window(self, hwnd: int) -> dict[str, Any]:
        return self.request("focusWindow", hwnd=int(hwnd))

    def list_related_windows(self, hwnd: int, process_id: int, render_process_names: list[str]) -> dict[str, Any]:
        return self.request(
            "listRelatedWindows",
            hwnd=int(hwnd),
            processId=int(process_id),
            renderProcessNames=render_process_names,
        )

    def detect_windowed_visual_shell(self, hwnd: int) -> dict[str, Any]:
        return self.request("detectWindowedVisualShell", hwnd=int(hwnd))

    def detect_runtime_signals(
        self,
        hwnd: int,
        process_id: int,
        render_process_names: list[str],
        *,
        open_layout_panel: bool = False,
    ) -> dict[str, Any]:
        return self.request(
            "detectRuntimeSignals",
            hwnd=int(hwnd),
            processId=int(process_id),
            renderProcessNames=render_process_names,
            treeDepth=max(1, int(self._config.native_runtime_tree_depth)),
            openLayoutPanel=bool(open_layout_panel),
        )

    def get_runtime_layout_state(
        self,
        hwnd: int,
        process_id: int,
        render_process_names: list[str],
        *,
        open_layout_panel: bool = True,
        close_panel: bool = False,
    ) -> dict[str, Any]:
        return self.request(
            "getRuntimeLayoutState",
            hwnd=int(hwnd),
            processId=int(process_id),
            renderProcessNames=render_process_names,
            treeDepth=max(1, int(self._config.native_runtime_tree_depth)),
            openLayoutPanel=bool(open_layout_panel),
            closePanel=bool(close_panel),
        )

    def select_runtime_layout(
        self,
        hwnd: int,
        process_id: int,
        render_process_names: list[str],
        *,
        section: str,
        label: str,
        close_panel: bool = False,
    ) -> dict[str, Any]:
        return self.request(
            "selectRuntimeLayout",
            hwnd=int(hwnd),
            processId=int(process_id),
            renderProcessNames=render_process_names,
            treeDepth=max(1, int(self._config.native_runtime_tree_depth)),
            section=str(section),
            label=str(label),
            closePanel=bool(close_panel),
        )

    def invoke_named_control(
        self,
        hwnd: int,
        process_id: int,
        render_process_names: list[str],
        control_name: str,
    ) -> dict[str, Any]:
        return self.request(
            "invokeNamedControl",
            hwnd=int(hwnd),
            processId=int(process_id),
            renderProcessNames=render_process_names,
            treeDepth=max(1, int(self._config.native_runtime_tree_depth)),
            controlName=str(control_name),
        )

    def pointer_action(self, x: int, y: int, *, double: bool, restore_cursor: bool = True) -> dict[str, Any]:
        return self.request(
            "pointerAction",
            x=int(x),
            y=int(y),
            double=bool(double),
            restoreCursor=bool(restore_cursor),
        )

    def send_key(self, key: str) -> dict[str, Any]:
        return self.request("sendKey", key=str(key))

    def _pump_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._stdout_queue.put(None)
            return
        try:
            for line in process.stdout:
                text = line.strip()
                if text:
                    self._stdout_queue.put(text)
        finally:
            self._stdout_queue.put(None)

    def _pump_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            text = line.strip()
            if text:
                self._logger.warning("native-runtime stderr: %s", text)
