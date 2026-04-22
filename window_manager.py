from __future__ import annotations

import ctypes
import time
from contextlib import suppress
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path

import win32api
import win32con
import win32gui
import win32process
from PIL import ImageGrab
from pywinauto import Desktop

from admin_utils import PROCESS_QUERY_LIMITED_INFORMATION, integrity_level_for_pid
from common import Rect, WindowInfo, WindowSearchConfig, WindowSnapshot
from native_runtime_client import NativeRuntimeClient, NativeRuntimeClientError
from visual_shell_detector import analyze_windowed_shell_image, looks_like_windowed_shell


WINDOWED_UI_MARKERS = (
    "收藏夹",
    "打开文件夹",
    "搜索",
    "全部收藏",
    "快捷入口",
    "视频中心",
    "视频监控配置",
)
DEFAULT_RENDER_PROCESS_NAMES = ["VSClient.exe"]


@dataclass(frozen=True)
class WindowCandidate:
    hwnd: int
    title: str
    process_name: str
    area: int
    is_foreground: bool
    is_iconic: bool
    title_match: bool
    process_match: bool


class WindowManager:
    def __init__(self, config: WindowSearchConfig, logger, *, native_client: NativeRuntimeClient | None = None):
        self._config = config
        self._logger = logger
        self._native_client = native_client
        self._user32 = ctypes.windll.user32
        self._uia_desktop = Desktop(backend="uia")
        self._windowed_marker_cache_key: tuple[int, int, int, int, int, str] | None = None
        self._windowed_marker_cache_hits: list[str] = []
        self._windowed_marker_cache_at = 0.0
        self._windowed_marker_cache_ttl_seconds = 0.35
        self._native_signal_cache_key: tuple[int, int, int, int, int, str] | None = None
        self._native_signal_cache_payload: dict[str, object] = {}
        self._native_signal_cache_at = 0.0
        self._native_signal_cache_ttl_seconds = 0.35
        self._windowed_visual_cache_key: tuple[int, int, int, int, int, str] | None = None
        self._windowed_visual_cache_result = False
        self._windowed_visual_cache_metrics: dict[str, float] = {}
        self._windowed_visual_cache_at = 0.0
        self._windowed_visual_cache_ttl_seconds = 0.45

    def invalidate_windowed_marker_cache(self, *, reason: str = "manual_invalidate") -> None:
        self._windowed_marker_cache_key = None
        self._windowed_marker_cache_hits = []
        self._windowed_marker_cache_at = 0.0
        self._native_signal_cache_key = None
        self._native_signal_cache_payload = {}
        self._native_signal_cache_at = 0.0
        self._windowed_visual_cache_key = None
        self._windowed_visual_cache_result = False
        self._windowed_visual_cache_metrics = {}
        self._windowed_visual_cache_at = 0.0
        self._logger.info("WINDOWED_MARKER cache invalidated reason=%s", reason)

    def find_target_window(self) -> WindowInfo:
        if self._native_runtime_available():
            try:
                return self._find_target_window_native()
            except Exception as exc:
                self._logger.warning("Native target-window discovery failed; falling back to Python path: %s", exc)
        deadline = time.monotonic() + self._config.match_timeout_seconds
        last_error: RuntimeError | None = None
        while time.monotonic() < deadline:
            try:
                candidates = self._select_candidates()
            except RuntimeError as exc:
                last_error = exc
                self._logger.debug("No target window matched yet: %s", exc)
                time.sleep(0.5)
                continue
            for candidate in candidates:
                try:
                    if candidate.is_iconic:
                        self._logger.warning(
                            "Matched window hwnd=%s is minimized; attempting restore",
                            candidate.hwnd,
                        )
                        self._logger.warning(
                            "window_restore_pending hwnd=%s title=%s",
                            candidate.hwnd,
                            candidate.title,
                        )
                        self.focus_window(candidate.hwnd)
                        time.sleep(0.25)
                    stable_samples = 3 if candidate.is_iconic else 1
                    return self._wait_for_stable_window_info(
                        candidate.hwnd,
                        candidate.title,
                        candidate.process_name,
                        required_samples=stable_samples,
                        deadline=deadline,
                    )
                except RuntimeError as exc:
                    last_error = exc
                    self._logger.warning(
                        "Skipping candidate hwnd=%s title=%s because window info is invalid: %s",
                        candidate.hwnd,
                        candidate.title,
                        exc,
                    )
                    continue
            time.sleep(0.5)
        raise last_error or RuntimeError("Could not find target window.")

    def focus_window(self, hwnd: int) -> bool:
        if self._native_runtime_available():
            try:
                result = self._native_client.focus_window(hwnd)
                return bool(result.get("focused", False))
            except Exception as exc:
                self._logger.warning("Native focus failed for hwnd=%s; falling back to Python path: %s", hwnd, exc)
        try:
            self._activate_window(hwnd)
            return True
        except Exception as exc:
            self._logger.warning("Failed to focus window %s: %s", hwnd, exc)
            return False

    def refresh_target_window(self, current: WindowInfo) -> WindowInfo:
        if self._native_runtime_available():
            try:
                payload = self._native_client.get_window_info(current.hwnd)
                window_payload = payload.get("window")
                if isinstance(window_payload, dict):
                    return self._window_info_from_native_payload(window_payload)
            except Exception as exc:
                self._logger.warning("Native refresh failed for hwnd=%s; falling back to Python path: %s", current.hwnd, exc)
        if not win32gui.IsWindow(current.hwnd):
            raise RuntimeError(f"Target window hwnd={current.hwnd} is no longer valid")
        title = (win32gui.GetWindowText(current.hwnd) or current.title).strip() or current.title
        process_name = self._process_name_from_hwnd(current.hwnd).lower() or current.process_name
        return self._window_info(current.hwnd, title, process_name)

    def detect_mode(self, window_info: WindowInfo, requested_mode: str) -> str:
        # requested_mode 只表示调度器的目标约束，真实模式始终要靠现场窗口检测。
        # 否则一旦人工用 F7 锁了模式，后续所有“当前模式”都会被请求值污染，闭环就断了。
        coverage_w = window_info.client_rect.width / max(1, window_info.monitor_rect.width)
        coverage_h = window_info.client_rect.height / max(1, window_info.monitor_rect.height)
        aligned_left = abs(window_info.client_rect.left - window_info.monitor_rect.left) <= self._config.client_margin_tolerance_px
        aligned_top = abs(window_info.client_rect.top - window_info.monitor_rect.top) <= self._config.client_margin_tolerance_px
        fullscreen_geometry_candidate = (
            coverage_w >= self._config.fullscreen_coverage_ratio
            and coverage_h >= self._config.fullscreen_coverage_ratio
            and aligned_left
            and aligned_top
        )
        if not fullscreen_geometry_candidate:
            # 关键修复：普通非全屏窗口不需要先做慢速 UIA 深扫。
            # 只要几何上明显没铺满屏，就直接判成 windowed，避免启动和回焦时卡 3 秒。
            self._logger.info(
                "Auto mode resolved to windowed via geometry fast-path hwnd=%s coverage_w=%.4f coverage_h=%.4f",
                window_info.hwnd,
                coverage_w,
                coverage_h,
            )
            return "windowed"

        windowed_hits = self._detect_windowed_ui_markers_cached(window_info)
        if windowed_hits:
            self._logger.info(
                "Auto mode resolved to windowed via UI markers hwnd=%s hits=%s",
                window_info.hwnd,
                windowed_hits,
            )
            return "windowed"

        visual_shell_match, visual_shell_metrics = self._detect_windowed_visual_shell_cached(window_info)
        if visual_shell_match:
            self._logger.info(
                "Auto mode resolved to windowed via visual shell hwnd=%s metrics=%s",
                window_info.hwnd,
                visual_shell_metrics,
            )
            return "windowed"

        attached_surface = self.find_visual_render_surface(window_info)
        if attached_surface is not None and fullscreen_geometry_candidate:
            # 关键修复：真全屏时，ClientFrame 宿主窗口仍可能保留“收藏夹/打开文件夹”等
            # UIA 控件，但真正可见的 12 宫格已经渲染在 VSClient 这类附属窗体上。
            # 只要没有更强的“非全屏壳层”证据，才优先认定为 fullscreen。
            self._logger.info(
                "Auto mode resolved to fullscreen via attached render surface hwnd=%s attached_hwnd=%s title=%s process=%s",
                window_info.hwnd,
                attached_surface.hwnd,
                attached_surface.title,
                attached_surface.process_name,
            )
            return "fullscreen"

        fullscreen_toggle_checked = self._detect_fullscreen_toggle_checked(window_info.hwnd)
        if fullscreen_toggle_checked:
            # 关键修复：全屏开关已勾选并不等于“当前真实界面已经进入全屏”。
            # 只要收藏夹/搜索/打开文件夹等非全屏控件仍然可见，就必须优先判定为 windowed。
            self._logger.info(
                "Auto mode resolved to fullscreen via fullscreen toggle hwnd=%s",
                window_info.hwnd,
            )
            return "fullscreen"

        # 兜底才看几何：有些现场会把客户端窗口最大化，但界面仍然是“非全屏宫格”。
        # 如果只看覆盖率，就会把“最大化的非全屏界面”误判成 fullscreen。
        if fullscreen_geometry_candidate:
            self._logger.info(
                "Auto mode resolved to fullscreen via geometry hwnd=%s coverage_w=%.4f coverage_h=%.4f",
                window_info.hwnd,
                coverage_w,
                coverage_h,
            )
            return "fullscreen"
        self._logger.info(
            "Auto mode resolved to windowed via geometry fallback hwnd=%s coverage_w=%.4f coverage_h=%.4f",
            window_info.hwnd,
            coverage_w,
            coverage_h,
        )
        return "windowed"

    def _detect_windowed_ui_markers_cached(self, window_info: WindowInfo) -> list[str]:
        cache_key = (
            window_info.hwnd,
            window_info.client_rect.left,
            window_info.client_rect.top,
            window_info.client_rect.right,
            window_info.client_rect.bottom,
            window_info.title.strip().lower(),
        )
        now = time.monotonic()
        if (
            self._windowed_marker_cache_key == cache_key
            and (now - self._windowed_marker_cache_at) <= self._windowed_marker_cache_ttl_seconds
        ):
            return list(self._windowed_marker_cache_hits)

        hits = self._detect_windowed_ui_markers(window_info.hwnd, client_rect=window_info.client_rect)
        self._windowed_marker_cache_key = cache_key
        self._windowed_marker_cache_hits = list(hits)
        self._windowed_marker_cache_at = now
        return hits

    def _detect_windowed_visual_shell_cached(self, window_info: WindowInfo) -> tuple[bool, dict[str, float]]:
        window_info = self._ensure_window_observable_for_visual_probe(window_info)
        foreground_hwnd = win32gui.GetForegroundWindow()
        is_foreground = foreground_hwnd == window_info.hwnd
        is_iconic = win32gui.IsIconic(window_info.hwnd)
        cache_key = (
            window_info.hwnd,
            window_info.client_rect.left,
            window_info.client_rect.top,
            window_info.client_rect.right,
            window_info.client_rect.bottom,
            window_info.title.strip().lower(),
            int(is_foreground),
            int(is_iconic),
        )
        now = time.monotonic()
        if (
            self._windowed_visual_cache_key == cache_key
            and (now - self._windowed_visual_cache_at) <= self._windowed_visual_cache_ttl_seconds
        ):
            return self._windowed_visual_cache_result, dict(self._windowed_visual_cache_metrics)

        matched = False
        metrics: dict[str, float] = {}
        if is_iconic or not is_foreground:
            self._logger.info(
                "Windowed visual shell probe skipped because target is not observable hwnd=%s foreground=%s iconic=%s",
                window_info.hwnd,
                is_foreground,
                is_iconic,
            )
            self._windowed_visual_cache_key = cache_key
            self._windowed_visual_cache_result = False
            self._windowed_visual_cache_metrics = {}
            self._windowed_visual_cache_at = now
            return False, {}
        if self._native_runtime_available():
            try:
                signal_payload = self._native_client.detect_windowed_visual_shell(window_info.hwnd)
                native_metrics = self._normalize_native_windowed_visual_metrics(
                    signal_payload.get("windowedVisualShellMetrics")
                )
                if native_metrics.get("windowed_shell_probe_succeeded", 0.0) >= 1.0:
                    metrics = native_metrics
                    matched = bool(signal_payload.get("windowedVisualShellLikely", False))
            except Exception as exc:
                self._logger.debug("Native windowed visual shell probe failed for hwnd=%s: %s", window_info.hwnd, exc)

        try:
            if not metrics:
                image = ImageGrab.grab(bbox=window_info.client_rect.to_bbox()).convert("RGB")
                metrics = analyze_windowed_shell_image(image)
                matched = looks_like_windowed_shell(metrics)
        except Exception as exc:
            self._logger.debug("Windowed visual shell probe failed for hwnd=%s: %s", window_info.hwnd, exc)

        self._windowed_visual_cache_key = cache_key
        self._windowed_visual_cache_result = matched
        self._windowed_visual_cache_metrics = dict(metrics)
        self._windowed_visual_cache_at = now
        return matched, dict(metrics)

    def _ensure_window_observable_for_visual_probe(self, window_info: WindowInfo) -> WindowInfo:
        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd == window_info.hwnd and not win32gui.IsIconic(window_info.hwnd):
            return window_info

        try:
            focused = self.focus_window(window_info.hwnd)
            if not focused:
                return window_info
            time.sleep(0.2)
            refreshed = self.refresh_target_window(window_info)
            self._logger.info(
                "Prepared target window for visual probe hwnd=%s foreground=%s iconic=%s",
                refreshed.hwnd,
                win32gui.GetForegroundWindow() == refreshed.hwnd,
                win32gui.IsIconic(refreshed.hwnd),
            )
            return refreshed
        except Exception as exc:
            self._logger.warning("Failed to prepare target window for visual probe hwnd=%s: %s", window_info.hwnd, exc)
            return window_info

    @staticmethod
    def _normalize_native_windowed_visual_metrics(raw_metrics: object) -> dict[str, float]:
        if not isinstance(raw_metrics, dict):
            return {}

        mapping = {
            "probeSucceeded": "windowed_shell_probe_succeeded",
            "windowedShellLike": "windowed_shell_like",
            "windowedShellScore": "windowed_shell_score",
            "windowedShellLeftMean": "windowed_shell_left_mean",
            "windowedShellLeftStd": "windowed_shell_left_std",
            "windowedShellLeftBrightRatio": "windowed_shell_left_bright_ratio",
            "windowedShellLeftDarkRatio": "windowed_shell_left_dark_ratio",
            "windowedShellTopMean": "windowed_shell_top_mean",
            "windowedShellTopStd": "windowed_shell_top_std",
            "windowedShellTopBrightRatio": "windowed_shell_top_bright_ratio",
            "windowedShellTopDarkRatio": "windowed_shell_top_dark_ratio",
            "windowedShellPreviewMean": "windowed_shell_preview_mean",
            "windowedShellPreviewStd": "windowed_shell_preview_std",
            "windowedShellPreviewBrightRatio": "windowed_shell_preview_bright_ratio",
            "windowedShellPreviewDarkRatio": "windowed_shell_preview_dark_ratio",
        }
        normalized: dict[str, float] = {}
        for source_key, target_key in mapping.items():
            value = raw_metrics.get(source_key)
            if isinstance(value, bool):
                normalized[target_key] = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                normalized[target_key] = float(value)
        return normalized

    def _detect_fullscreen_toggle_checked(self, hwnd: int) -> bool:
        if self._native_runtime_available():
            try:
                signal_payload = self._get_native_runtime_signals_cached(hwnd=hwnd, process_id=0, title="")
                if bool(signal_payload.get("fullscreenToggleChecked", False)):
                    return True
            except Exception as exc:
                self._logger.debug("Native fullscreen toggle probe failed for hwnd=%s: %s", hwnd, exc)
        try:
            root = self._uia_desktop.window(handle=hwnd)
            for title in ("全屏", "退出全屏"):
                ctrl = root.child_window(title=title, control_type="CheckBox")
                if ctrl.exists(timeout=0.1):
                    return bool(ctrl.get_toggle_state())
        except Exception as exc:
            self._logger.debug("Fullscreen toggle probe failed for hwnd=%s: %s", hwnd, exc)
        return False

    def _detect_windowed_ui_markers(self, hwnd: int, *, client_rect: Rect | None = None) -> list[str]:
        if self._native_runtime_available():
            try:
                signal_payload = self._get_native_runtime_signals_cached(hwnd=hwnd, process_id=0, title="")
                markers = signal_payload.get("windowedMarkers")
                if isinstance(markers, list):
                    native_hits = [str(item) for item in markers[:4] if str(item).strip()]
                    if native_hits:
                        return native_hits
            except Exception as exc:
                self._logger.debug("Native UI marker probe failed for hwnd=%s: %s", hwnd, exc)
        try:
            root = self._uia_desktop.window(handle=hwnd)
            hits: list[str] = []
            seen: set[str] = set()
            for marker in WINDOWED_UI_MARKERS:
                # 关键修复：对固定中文控件文案优先做定点 child_window 查询，
                # 不再先枚举整棵 UIA 树，减少 windowed 模式识别的整体延迟。
                ctrl = root.child_window(title=marker)
                if not ctrl.exists(timeout=0.1):
                    continue
                if not self._control_is_effectively_visible(ctrl, client_rect=client_rect):
                    continue
                if marker in seen:
                    continue
                seen.add(marker)
                hits.append(marker)
                # 至少命中两个“非全屏宫格特征控件”再认定为 windowed，避免偶发单点误判。
                if len(hits) >= 2:
                    return hits
        except Exception as exc:
            self._logger.debug("UI marker probe failed for hwnd=%s: %s", hwnd, exc)
        return []

    def _control_is_effectively_visible(self, ctrl, *, client_rect: Rect | None) -> bool:
        try:
            if hasattr(ctrl, "is_visible") and not bool(ctrl.is_visible()):
                return False
            rect = ctrl.rectangle()
            left = int(getattr(rect, "left", 0))
            top = int(getattr(rect, "top", 0))
            right = int(getattr(rect, "right", 0))
            bottom = int(getattr(rect, "bottom", 0))
            width = max(0, right - left)
            height = max(0, bottom - top)
            if width < 6 or height < 6:
                return False
            if client_rect is not None:
                center_x = left + width // 2
                center_y = top + height // 2
                if not client_rect.contains_point((center_x, center_y)):
                    return False
        except Exception:
            return False
        return True

    def find_visual_render_surface(self, target_window: WindowInfo) -> WindowSnapshot | None:
        for snapshot in self.list_related_visible_windows(target_window):
            if self._looks_like_visual_render_surface(snapshot, target_window):
                return snapshot
        return None

    def _find_attached_render_surface(self, target_window: WindowInfo) -> WindowSnapshot | None:
        for snapshot in self.list_related_visible_windows(target_window):
            if self._looks_like_attached_render_surface(snapshot, target_window):
                return snapshot
        return None

    def is_visual_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
        return self._looks_like_visual_render_surface(snapshot, target_window)

    def _looks_like_visual_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
        return self._looks_like_attached_render_surface(snapshot, target_window) or self._looks_like_detached_render_surface(
            snapshot,
            target_window,
        )

    def _looks_like_attached_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
        if snapshot.owner_hwnd != target_window.hwnd:
            return False
        return self._matches_render_surface_geometry(snapshot, target_window)

    def _looks_like_detached_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
        if snapshot.owner_hwnd == target_window.hwnd:
            return False
        if not self._matches_render_surface_geometry(snapshot, target_window):
            return False
        # 关键修复：真全屏下客户端有时会把 VSClient 渲染面切成“无 owner 的顶层窗”。
        # 只要它仍与主窗口近乎完全重叠，就应该继续把它当成真实视觉目标，而不是外部漂移窗口。
        process_name = str(snapshot.process_name or "").strip().casefold()
        title = str(snapshot.title or "").strip().casefold()
        return process_name == "vsclient.exe" and title == "vsclient"

    def _looks_like_detached_render_surface_prefilter(self, *, title: str, rect: Rect, target_window: WindowInfo) -> bool:
        normalized_title = str(title or "").strip().casefold()
        if normalized_title != "vsclient":
            return False
        target_rect = target_window.window_rect
        if target_rect.width <= 0 or target_rect.height <= 0:
            return False

        intersection_left = max(target_rect.left, rect.left)
        intersection_top = max(target_rect.top, rect.top)
        intersection_right = min(target_rect.right, rect.right)
        intersection_bottom = min(target_rect.bottom, rect.bottom)
        intersection_width = max(0, intersection_right - intersection_left)
        intersection_height = max(0, intersection_bottom - intersection_top)
        coverage_ratio = (intersection_width * intersection_height) / max(1, target_rect.width * target_rect.height)
        if coverage_ratio < 0.9:
            return False

        left_gap = abs(rect.left - target_rect.left)
        top_gap = abs(rect.top - target_rect.top)
        return left_gap <= 8 and top_gap <= 8

    def _matches_render_surface_geometry(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
        target_rect = target_window.window_rect
        candidate_rect = snapshot.rect
        if target_rect.width <= 0 or target_rect.height <= 0:
            return False

        intersection_left = max(target_rect.left, candidate_rect.left)
        intersection_top = max(target_rect.top, candidate_rect.top)
        intersection_right = min(target_rect.right, candidate_rect.right)
        intersection_bottom = min(target_rect.bottom, candidate_rect.bottom)
        intersection_width = max(0, intersection_right - intersection_left)
        intersection_height = max(0, intersection_bottom - intersection_top)
        coverage_ratio = (intersection_width * intersection_height) / max(1, target_rect.width * target_rect.height)
        if coverage_ratio < 0.9:
            return False

        left_gap = abs(candidate_rect.left - target_rect.left)
        top_gap = abs(candidate_rect.top - target_rect.top)
        return left_gap <= 8 and top_gap <= 8

    def _select_candidates(self) -> list[WindowCandidate]:
        matches: list[WindowCandidate] = []
        foreground = win32gui.GetForegroundWindow()

        def callback(hwnd: int, _: int) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return

            title = win32gui.GetWindowText(hwnd).strip()
            process_name = self._process_name_from_hwnd(hwnd).lower()
            title_match = any(keyword.lower() in title.lower() for keyword in self._config.title_keywords)
            process_match = any(name.lower() == process_name for name in self._config.process_names)
            if not title_match and not process_match:
                return

            try:
                rect = win32gui.GetWindowRect(hwnd)
            except win32gui.error:
                return
            area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
            matches.append(
                WindowCandidate(
                    hwnd=hwnd,
                    title=title,
                    process_name=process_name,
                    area=area,
                    is_foreground=hwnd == foreground,
                    is_iconic=bool(win32gui.IsIconic(hwnd)),
                    title_match=title_match,
                    process_match=process_match,
                )
            )

        win32gui.EnumWindows(callback, 0)
        if not matches:
            raise RuntimeError(
                f"No matching window found for titles {self._config.title_keywords} and processes {self._config.process_names}."
            )

        process_matches = [item for item in matches if item.process_match]
        exact_matches = [item for item in matches if item.process_match and item.title_match]
        if exact_matches:
            # 关键修复：同进程可能同时挂着主窗、壳窗和辅窗。
            # 只要存在“标题和进程都命中”的候选，就优先选它，避免把壳窗误当主目标。
            matches = exact_matches
        elif process_matches:
            matches = process_matches
        else:
            self._logger.warning(
                "No process-name match found; falling back to title-only window matches for titles=%s",
                self._config.title_keywords,
            )

        titled_matches = [item for item in matches if item.title]
        if titled_matches:
            matches = titled_matches

        matches.sort(
            key=lambda item: (item.process_match and item.title_match, item.title_match, not item.is_iconic, item.is_foreground, item.area),
            reverse=True,
        )
        self._logger.debug(
            "Candidate windows: %s",
            [
                (
                    item.hwnd,
                    item.title,
                    item.process_name,
                    item.title_match,
                    item.process_match,
                    item.is_iconic,
                    item.area,
                )
                for item in matches
            ],
        )
        return matches

    def _find_target_window_native(self) -> WindowInfo:
        deadline = time.monotonic() + self._config.match_timeout_seconds
        last_error: RuntimeError | None = None
        while time.monotonic() < deadline:
            try:
                payload = self._native_client.find_target_window()
                window_payload = payload.get("window")
                if not isinstance(window_payload, dict):
                    raise RuntimeError("Native runtime did not return a target window payload.")
                latest_info = self._window_info_from_native_payload(window_payload)
                if bool(window_payload.get("isIconic", False)):
                    self._logger.warning(
                        "Matched window hwnd=%s is minimized; attempting restore",
                        latest_info.hwnd,
                    )
                    self._logger.warning(
                        "window_restore_pending hwnd=%s title=%s",
                        latest_info.hwnd,
                        latest_info.title,
                    )
                    self.focus_window(latest_info.hwnd)
                    time.sleep(0.25)
                    latest_info = self._wait_for_stable_window_info_native(
                        latest_info.hwnd,
                        required_samples=3,
                        deadline=deadline,
                    )
                return latest_info
            except Exception as exc:
                last_error = RuntimeError(str(exc))
                time.sleep(0.3)
        raise last_error or RuntimeError("Could not find target window via native runtime.")

    def _window_info(self, hwnd: int, title: str, process_name: str) -> WindowInfo:
        window_rect_raw = win32gui.GetWindowRect(hwnd)
        client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
        client_rect_raw = win32gui.GetClientRect(hwnd)
        monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))
        monitor_rect_raw = monitor_info["Monitor"]
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
        integrity = integrity_level_for_pid(process_id)

        client_rect = Rect(
            client_origin[0],
            client_origin[1],
            client_origin[0] + client_rect_raw[2],
            client_origin[1] + client_rect_raw[3],
        )
        if (
            client_rect.left <= -30000
            or client_rect.top <= -30000
            or client_rect.width <= 200
            or client_rect.height <= 200
        ):
            raise RuntimeError(f"Target client rect is invalid: {client_rect}")

        return WindowInfo(
            hwnd=hwnd,
            process_id=process_id,
            title=title,
            process_name=process_name,
            integrity_rid=integrity.rid,
            integrity_label=integrity.label,
            window_rect=Rect(*window_rect_raw),
            client_rect=client_rect,
            monitor_rect=Rect(*monitor_rect_raw),
        )

    def _window_info_from_native_payload(self, payload: dict[str, object]) -> WindowInfo:
        hwnd = int(payload.get("hwnd", 0))
        process_id = int(payload.get("processId", 0))
        title = str(payload.get("title", "") or "")
        process_name = str(payload.get("processName", "") or "").lower()
        integrity = integrity_level_for_pid(process_id)
        return WindowInfo(
            hwnd=hwnd,
            process_id=process_id,
            title=title,
            process_name=process_name,
            integrity_rid=integrity.rid,
            integrity_label=integrity.label,
            window_rect=self._rect_from_native_payload(payload.get("windowRect")),
            client_rect=self._rect_from_native_payload(payload.get("clientRect")),
            monitor_rect=self._rect_from_native_payload(payload.get("monitorRect")),
        )

    @staticmethod
    def _rect_from_native_payload(raw_rect: object) -> Rect:
        if not isinstance(raw_rect, dict):
            raise RuntimeError(f"Invalid native rect payload: {raw_rect!r}")
        return Rect(
            int(raw_rect.get("left", 0)),
            int(raw_rect.get("top", 0)),
            int(raw_rect.get("right", 0)),
            int(raw_rect.get("bottom", 0)),
        )

    def _wait_for_stable_window_info(
        self,
        hwnd: int,
        title: str,
        process_name: str,
        *,
        required_samples: int,
        deadline: float,
    ) -> WindowInfo:
        stable_samples = 0
        last_error: RuntimeError | None = None
        latest_info: WindowInfo | None = None

        while time.monotonic() < deadline:
            try:
                latest_info = self._window_info(hwnd, title, process_name)
                stable_samples += 1
                if required_samples > 1:
                    self._logger.info(
                        "client_rect_stable_samples hwnd=%s samples=%s/%s client_rect=%s",
                        hwnd,
                        stable_samples,
                        required_samples,
                        latest_info.client_rect,
                    )
                if stable_samples >= required_samples:
                    return latest_info
                time.sleep(0.12)
            except RuntimeError as exc:
                last_error = exc
                stable_samples = 0
                if self._should_retry_window_activation(hwnd, exc):
                    self._logger.warning(
                        "Window activation retry hwnd=%s title=%s because window info is still invalid: %s",
                        hwnd,
                        title,
                        exc,
                    )
                    with suppress(Exception):
                        self._activate_window(hwnd)
                    time.sleep(0.18)
                    continue
                time.sleep(0.12)

        raise last_error or RuntimeError(
            f"Timed out waiting for a stable client rect on hwnd={hwnd} title={title!r}"
        )

    def _wait_for_stable_window_info_native(
        self,
        hwnd: int,
        *,
        required_samples: int,
        deadline: float,
    ) -> WindowInfo:
        stable_samples = 0
        last_error: RuntimeError | None = None
        latest_info: WindowInfo | None = None
        while time.monotonic() < deadline:
            try:
                payload = self._native_client.get_window_info(hwnd)
                window_payload = payload.get("window")
                if not isinstance(window_payload, dict):
                    raise RuntimeError(f"Missing native window payload for hwnd={hwnd}")
                latest_info = self._window_info_from_native_payload(window_payload)
                stable_samples += 1
                if required_samples > 1:
                    self._logger.info(
                        "client_rect_stable_samples hwnd=%s samples=%s/%s client_rect=%s",
                        hwnd,
                        stable_samples,
                        required_samples,
                        latest_info.client_rect,
                    )
                if stable_samples >= required_samples:
                    return latest_info
                time.sleep(0.12)
            except Exception as exc:
                last_error = RuntimeError(str(exc))
                stable_samples = 0
                time.sleep(0.12)
        raise last_error or RuntimeError(f"Timed out waiting for a stable native client rect on hwnd={hwnd}")

    def _process_name_from_hwnd(self, hwnd: int) -> str:
        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
            try:
                buffer_size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(buffer_size.value)
                ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                    int(handle),
                    0,
                    buffer,
                    ctypes.byref(buffer_size),
                )
                if not ok:
                    return ""
                path = buffer.value
            finally:
                win32api.CloseHandle(handle)
            return Path(path).name
        except Exception:
            return ""

    def get_foreground_window_snapshot(self) -> WindowSnapshot | None:
        if self._native_runtime_available():
            try:
                payload = self._native_client.request("getForegroundWindow")
                window_payload = payload.get("window")
                if isinstance(window_payload, dict) and int(window_payload.get("hwnd", 0)):
                    return self._window_snapshot_from_native_payload(window_payload)
                return None
            except Exception as exc:
                self._logger.warning("Native foreground-window probe failed; falling back to Python path: %s", exc)
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        return self._window_snapshot(hwnd)

    def list_related_visible_windows(self, target_window: WindowInfo) -> list[WindowSnapshot]:
        if self._native_runtime_available():
            try:
                payload = self._native_client.list_related_windows(
                    target_window.hwnd,
                    target_window.process_id,
                    DEFAULT_RENDER_PROCESS_NAMES,
                )
                windows = payload.get("windows")
                if isinstance(windows, list):
                    related = [
                        self._window_snapshot_from_native_payload(item)
                        for item in windows
                        if isinstance(item, dict)
                    ]
                    related.sort(
                        key=lambda item: (item.owner_hwnd == target_window.hwnd, item.rect.width * item.rect.height),
                        reverse=True,
                    )
                    return related
            except Exception as exc:
                self._logger.warning("Native related-window scan failed; falling back to Python path: %s", exc)
        related: list[WindowSnapshot] = []
        target_pid = target_window.process_id
        target_hwnd = target_window.hwnd

        def callback(hwnd: int, _: int) -> None:
            if hwnd == target_hwnd:
                return
            if not win32gui.IsWindowVisible(hwnd):
                return
            try:
                rect_raw = win32gui.GetWindowRect(hwnd)
                owner_hwnd = int(win32gui.GetWindow(hwnd, win32con.GW_OWNER) or 0)
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            # 关键修复：运行期只关心“同 pid / owner”的相关窗口。
            # 先做廉价预筛，避免为桌面上所有可见窗口都取进程名和完整快照。
            detached_prefilter = self._looks_like_detached_render_surface_prefilter(
                title=title,
                rect=Rect(*rect_raw),
                target_window=target_window,
            )
            if process_id != target_pid and owner_hwnd != target_hwnd and not detached_prefilter:
                return
            try:
                snapshot = self._window_snapshot(hwnd)
            except Exception:
                return
            if (
                snapshot.process_id == target_pid
                or snapshot.owner_hwnd == target_hwnd
                or self._looks_like_detached_render_surface(snapshot, target_window)
            ):
                related.append(snapshot)

        win32gui.EnumWindows(callback, 0)
        related.sort(key=lambda item: (item.owner_hwnd == target_hwnd, item.rect.width * item.rect.height), reverse=True)
        return related

    def classify_window_relation(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> str:
        if snapshot.hwnd == target_window.hwnd:
            return "target"
        if snapshot.process_id == target_window.process_id:
            return "same_process"
        if snapshot.owner_hwnd == target_window.hwnd:
            return "owned_by_target"
        return "other"

    def _window_snapshot(self, hwnd: int) -> WindowSnapshot:
        rect_raw = win32gui.GetWindowRect(hwnd)
        owner_hwnd = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        title = win32gui.GetWindowText(hwnd).strip()
        process_name = self._process_name_from_hwnd(hwnd).lower()
        return WindowSnapshot(
            hwnd=hwnd,
            process_id=process_id,
            title=title,
            process_name=process_name,
            rect=Rect(*rect_raw),
            owner_hwnd=int(owner_hwnd or 0),
            is_visible=bool(win32gui.IsWindowVisible(hwnd)),
            is_foreground=hwnd == win32gui.GetForegroundWindow(),
        )

    def _window_snapshot_from_native_payload(self, payload: dict[str, object]) -> WindowSnapshot:
        return WindowSnapshot(
            hwnd=int(payload.get("hwnd", 0)),
            process_id=int(payload.get("processId", 0)),
            title=str(payload.get("title", "") or ""),
            process_name=str(payload.get("processName", "") or "").lower(),
            rect=self._rect_from_native_payload(payload.get("windowRect") or payload.get("bounds")),
            owner_hwnd=int(payload.get("ownerHwnd", 0)),
            is_visible=bool(payload.get("isVisible", True)),
            is_foreground=bool(payload.get("isForeground", False)),
        )

    def _native_runtime_available(self) -> bool:
        return bool(self._native_client is not None and self._native_client.enabled)

    def _get_native_runtime_signals_cached(self, *, hwnd: int, process_id: int, title: str) -> dict[str, object]:
        cache_key = (
            hwnd,
            process_id,
            0,
            0,
            0,
            str(title or "").strip().lower(),
        )
        now = time.monotonic()
        if (
            self._native_signal_cache_key == cache_key
            and (now - self._native_signal_cache_at) <= self._native_signal_cache_ttl_seconds
        ):
            return dict(self._native_signal_cache_payload)
        payload = self._native_client.detect_runtime_signals(
            hwnd,
            process_id,
            DEFAULT_RENDER_PROCESS_NAMES,
        )
        self._native_signal_cache_key = cache_key
        self._native_signal_cache_payload = dict(payload)
        self._native_signal_cache_at = now
        return dict(payload)

    def _activate_window(self, hwnd: int) -> None:
        if not win32gui.IsWindow(hwnd):
            raise RuntimeError(f"Cannot activate invalid hwnd={hwnd}")

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

            for _attempt in range(1, 5):
                if win32gui.IsIconic(hwnd):
                    with suppress(Exception):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    with suppress(Exception):
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
                else:
                    with suppress(Exception):
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

                with suppress(Exception):
                    win32gui.BringWindowToTop(hwnd)
                with suppress(Exception):
                    win32gui.SetForegroundWindow(hwnd)
                with suppress(Exception):
                    self._user32.SetActiveWindow(hwnd)
                with suppress(Exception):
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOPMOST,
                        0,
                        0,
                        0,
                        0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                    )
                with suppress(Exception):
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_NOTOPMOST,
                        0,
                        0,
                        0,
                        0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                    )
                time.sleep(0.08)
                if win32gui.GetForegroundWindow() == hwnd:
                    return
        finally:
            if attached_target:
                self._user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            if attached_foreground:
                self._user32.AttachThreadInput(current_thread_id, foreground_thread_id, False)

        if win32gui.IsIconic(hwnd):
            raise RuntimeError(f"Window hwnd={hwnd} stayed minimized after repeated restore attempts")
        raise RuntimeError(f"Window hwnd={hwnd} did not become the foreground window after repeated activation attempts")

    @staticmethod
    def _should_retry_window_activation(hwnd: int, exc: RuntimeError) -> bool:
        message = str(exc)
        return win32gui.IsIconic(hwnd) or "Target client rect is invalid" in message
