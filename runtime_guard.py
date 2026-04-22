from __future__ import annotations

"""运行期界面守卫层。

解决的问题：
1. 自动点击时客户端卡顿，可能误点到错误窗口 / 弹窗 / 其他界面。
2. 即使动作链本身没错，界面失真后如果继续点击，也会把状态机带偏。
3. 需要把“自我监测 / 自我检测 / 自我修复”独立成一层，避免和调度状态机强耦合。

设计原则：
- 先检测，再恢复，最后才允许继续点击。
- 对“同进程弹窗 / 相关窗口”可以自动 ESC / Alt+F4 尝试关闭。
- 对“外部前台窗口漂移”只尝试回焦，不乱关别的程序。
- 对“错误界面 / 错误窗口 / 错误点击结果”统一返回结构化事件，便于日志、自测、UI 提示复用。
"""

import time
from dataclasses import dataclass, field
from typing import Any

from common import Rect, RuntimeGuardConfig, VisualViewState, WindowInfo, WindowSnapshot, resolve_output_path


@dataclass(frozen=True)
class GuardEvent:
    ok: bool
    issue: str = "ok"
    reason: str = ""
    severity: str = "info"
    details: dict[str, Any] = field(default_factory=dict)


class RuntimeGuard:
    def __init__(self, config: RuntimeGuardConfig, window_manager, detector, controller, logger, config_path):
        self._config = config
        self._window_manager = window_manager
        self._detector = detector
        self._controller = controller
        self._logger = logger
        self._config_path = config_path

    def check(
        self,
        *,
        stage: str,
        target_window: WindowInfo | None,
        preview_rect: Rect | None,
        active_cell_rect: Rect | None,
        expected_view: VisualViewState | None,
        grid_probe=None,
        zoom_probe=None,
    ) -> GuardEvent:
        if not self._config.enabled:
            return GuardEvent(ok=True)
        if target_window is None:
            return GuardEvent(ok=False, issue="missing_target_window", reason="target_window_is_none", severity="error")

        foreground_event = self._check_foreground(stage=stage, target_window=target_window)
        if foreground_event and not foreground_event.ok:
            return foreground_event

        popup_event = self._check_related_popups(stage=stage, target_window=target_window)
        if popup_event and not popup_event.ok:
            return popup_event

        if preview_rect is not None and active_cell_rect is not None:
            runtime_result = self._detector.inspect_runtime_interface(
                preview_rect,
                active_cell_rect,
                expected_view=expected_view,
                grid_probe=grid_probe,
                zoom_probe=zoom_probe,
            )
            if runtime_result.status != "ok":
                details = dict(runtime_result.metrics)
                details["stage"] = stage
                return GuardEvent(
                    ok=False,
                    issue=runtime_result.status,
                    reason=runtime_result.reason,
                    severity="warning",
                    details=details,
                )

        return GuardEvent(ok=True, issue="ok", reason="guard_ok", severity="info", details={"stage": stage})

    def try_auto_heal(self, *, event: GuardEvent, target_window: WindowInfo | None) -> bool:
        if event.ok or not self._config.enabled or target_window is None:
            return event.ok

        issue = event.issue
        self._logger.warning("RUNTIME_GUARD healing issue=%s reason=%s details=%s", issue, event.reason, event.details)

        if issue in {"unexpected_related_window", "related_popup_visible"}:
            # 关键修复：当前台只是 VSClient 这类同进程辅窗漂移时，不能先发 ESC。
            # 在全屏场景里 ESC 会直接退出全屏，把“用户已经切好的全屏宫格”打回非全屏。
            # 这种情况先只做回焦；只有标题像真弹窗时，才允许走 ESC / Alt+F4。
            if issue == "unexpected_related_window" and event.reason == "foreground_window_drift":
                relation = str(event.details.get("relation", "") or "")
                title = str(event.details.get("foreground_title", "") or "")
                if relation in {"same_process", "owned_by_target"} and not self._title_matches_popup_keyword(title):
                    if not self._window_manager.focus_window(target_window.hwnd):
                        return False
                    time.sleep(self._config.settle_after_recover_ms / 1000.0)
                    return True
            if not self._config.auto_close_related_popups:
                return False
            self._controller.emergency_recover(hwnd=None)
            time.sleep(self._config.post_action_wait_ms / 1000.0)
            if self._is_same_issue_present(event, target_window):
                try:
                    self._controller.close_foreground_window()
                except Exception as exc:  # pragma: no cover - 运行期兜底
                    self._logger.warning("RUNTIME_GUARD close_foreground_window failed: %s", exc)
            if not self._window_manager.focus_window(target_window.hwnd):
                return False
            time.sleep(self._config.settle_after_recover_ms / 1000.0)
            return True

        if issue == "unexpected_foreground_window":
            if not self._config.auto_refocus_external_window:
                return False
            if not self._window_manager.focus_window(target_window.hwnd):
                return False
            time.sleep(self._config.settle_after_recover_ms / 1000.0)
            return True

        if issue in {"unexpected_interface", "view_unknown", "view_mismatch", "missing_target_window"}:
            if not self._window_manager.focus_window(target_window.hwnd):
                return False
            time.sleep(0.1)
            self._controller.recover_to_grid(hwnd=target_window.hwnd)
            time.sleep(self._config.settle_after_recover_ms / 1000.0)
            return True

        return False

    def save_guard_snapshot(self, *, tag: str, detector, rect: Rect | None) -> str | None:
        if rect is None:
            return None
        try:
            output_dir = resolve_output_path(self._config_path, self._config.screenshot_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / f"{tag}_{int(time.time())}.png"
            detector.save_cell_snapshot(rect, destination)
            return str(destination)
        except Exception as exc:  # pragma: no cover - 运行期兜底
            self._logger.warning("RUNTIME_GUARD snapshot failed tag=%s error=%s", tag, exc)
            return None

    def _check_foreground(self, *, stage: str, target_window: WindowInfo) -> GuardEvent | None:
        if not self._config.verify_foreground_window:
            return None
        getter = getattr(self._window_manager, "get_foreground_window_snapshot", None)
        if getter is None:
            return None
        snapshot = getter()
        if snapshot is None or snapshot.hwnd == target_window.hwnd:
            return None
        if self._is_ignored_auxiliary_foreground(snapshot):
            self._logger.info(
                "RUNTIME_GUARD ignoring auxiliary foreground window stage=%s hwnd=%s title=%s process=%s",
                stage,
                snapshot.hwnd,
                snapshot.title,
                snapshot.process_name,
            )
            return None

        relation = self._classify_relation(snapshot, target_window)
        if self._looks_like_attached_surface(snapshot, target_window):
            self._logger.info(
                "RUNTIME_GUARD allowing attached foreground surface stage=%s hwnd=%s owner=%s title=%s",
                stage,
                snapshot.hwnd,
                snapshot.owner_hwnd,
                snapshot.title,
            )
            return None
        if self._looks_like_keywordless_same_process_aux_foreground(snapshot, relation):
            self._logger.info(
                "RUNTIME_GUARD allowing keywordless related foreground surface stage=%s hwnd=%s relation=%s title=%s",
                stage,
                snapshot.hwnd,
                relation,
                snapshot.title,
            )
            return None
        issue = "unexpected_related_window" if relation in {"same_process", "owned_by_target"} else "unexpected_foreground_window"
        return GuardEvent(
            ok=False,
            issue=issue,
            reason="foreground_window_drift",
            severity="warning",
            details={
                "stage": stage,
                "foreground_hwnd": snapshot.hwnd,
                "foreground_title": snapshot.title,
                "foreground_process": snapshot.process_name,
                "relation": relation,
                "target_hwnd": target_window.hwnd,
            },
        )

    def _check_related_popups(self, *, stage: str, target_window: WindowInfo) -> GuardEvent | None:
        if not self._config.detect_related_popups:
            return None
        getter = getattr(self._window_manager, "list_related_visible_windows", None)
        if getter is None:
            return None
        windows = getter(target_window)
        if not windows:
            return None

        keyword_hits = []
        lowered_keywords = [item.casefold() for item in self._config.popup_title_keywords]
        popup_titles: list[str] = []
        popup_hwnds: list[int] = []
        for item in windows:
            title = (item.title or "").strip()
            popup_titles.append(title)
            popup_hwnds.append(item.hwnd)
            if title and any(keyword in title.casefold() for keyword in lowered_keywords):
                keyword_hits.append(title)

        if not popup_titles:
            return None
        if not keyword_hits:
            # 关键修复：不能把所有“同进程可见窗口”都当成弹窗。
            # 全屏场景里客户端可能带有 VSClient 这类同进程辅窗；如果这里直接告警，
            # auto-heal 会误发 Alt+F4，把目标客户端主窗口关掉。
            self._logger.info(
                "RUNTIME_GUARD ignoring related same-process windows without popup keywords stage=%s titles=%s",
                stage,
                popup_titles,
            )
            return None

        return GuardEvent(
            ok=False,
            issue="related_popup_visible",
            reason="same_process_popup_detected",
            severity="warning",
            details={
                "stage": stage,
                "popup_hwnds": popup_hwnds,
                "popup_titles": popup_titles,
                "keyword_hits": keyword_hits,
                "target_hwnd": target_window.hwnd,
            },
        )

    def _is_same_issue_present(self, event: GuardEvent, target_window: WindowInfo) -> bool:
        if event.issue not in {"unexpected_related_window", "related_popup_visible"}:
            return False
        refreshed = self._check_related_popups(stage="heal_verify", target_window=target_window)
        return refreshed is not None and not refreshed.ok

    def _title_matches_popup_keyword(self, title: str) -> bool:
        lowered = (title or "").strip().casefold()
        if not lowered:
            return False
        return any(keyword.casefold() in lowered for keyword in self._config.popup_title_keywords)

    def _is_ignored_auxiliary_foreground(self, snapshot: WindowSnapshot) -> bool:
        title = (snapshot.title or "").strip()
        process_name = (snapshot.process_name or "").strip().casefold()
        # 关键修复：状态浮窗是本程序自己的透明提示层，不能再被误判成“前台窗口漂移”。
        if title == "Video Polling Status" and process_name in {"pythonw.exe", "python.exe"}:
            return True
        if self._looks_like_automation_console_foreground(snapshot):
            return True
        return False

    def _looks_like_automation_console_foreground(self, snapshot: WindowSnapshot) -> bool:
        process_name = (snapshot.process_name or "").strip().casefold()
        title = str(snapshot.title or "").strip()
        lowered_title = title.casefold()

        # 关键修复：Codex / GPT CLI 常驻在 Windows Terminal 的 Ubuntu 标签页里。
        # 它不是业务弹窗，也不应该把运行中的固定程序误打成“前台漂移异常”。
        if process_name in {"windowsterminal.exe", "wt.exe"} and lowered_title.startswith("ubuntu"):
            return True

        if process_name not in {"python.exe", "pythonw.exe"}:
            return False

        normalized_title = title.replace("\\", "/").casefold()
        if not normalized_title.endswith("/python.exe") or "/.venv/" not in normalized_title:
            return False

        config_path = str(self._config_path or "").replace("\\", "/").rstrip("/")
        config_parts = [segment.casefold() for segment in config_path.split("/") if segment]
        project_marker = config_parts[-2] if len(config_parts) >= 2 else ""
        if not project_marker:
            return False

        candidate_markers = {project_marker}
        if project_marker.endswith("_windows_runtime"):
            candidate_markers.add(project_marker[: -len("_windows_runtime")])
        return any(marker and marker in normalized_title for marker in candidate_markers)

    def _looks_like_attached_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:
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
        intersection_area = intersection_width * intersection_height
        target_area = max(1, target_rect.width * target_rect.height)
        coverage_ratio = intersection_area / target_area

        if coverage_ratio < 0.9:
            return False

        left_gap = abs(candidate_rect.left - target_rect.left)
        top_gap = abs(candidate_rect.top - target_rect.top)
        if left_gap > 8 or top_gap > 8:
            return False

        if snapshot.owner_hwnd == target_window.hwnd:
            return True

        # 关键修复：全屏切回宫格后，客户端有时会把 VSClient 渲染面重新挂成“无 owner 的顶层窗”，
        # 但它仍然和主窗口完全重叠，前台也仍然属于同一个客户端渲染链。
        # 这种窗口不能再被当成外部前台漂移，否则 GRID_DWELL 会被错误打回重跑。
        process_name = str(snapshot.process_name or "").strip().casefold()
        title = str(snapshot.title or "").strip().casefold()
        return process_name == "vsclient.exe" and title == "vsclient"

    def _looks_like_keywordless_same_process_aux_foreground(
        self,
        snapshot: WindowSnapshot,
        relation: str,
    ) -> bool:
        title = str(snapshot.title or "").strip()
        if self._title_matches_popup_keyword(title):
            return False
        process_name = str(snapshot.process_name or "").strip().casefold()
        if process_name != "vsclient.exe":
            return False
        lowered_title = title.casefold()
        if lowered_title == "vsclient":
            return relation in {"same_process", "owned_by_target"}
        if not lowered_title.startswith("0x") or len(lowered_title) <= 2:
            return False
        try:
            int(lowered_title[2:], 16)
        except ValueError:
            return False
        # 关键修复：全屏 12 实机里，渲染链会短暂把一个 0x... 标题的 VSClient 辅窗顶到前台，
        # 但它未必能稳定被 relation classifier 判成 same_process/owned_by_target。
        # 这类窗口属于客户端自己的前台辅窗，不能再当成外部 foreground drift。
        return True

    def _classify_relation(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> str:
        classifier = getattr(self._window_manager, "classify_window_relation", None)
        if classifier is not None:
            try:
                return classifier(snapshot, target_window)
            except Exception:  # pragma: no cover - 运行期兜底
                pass
        if snapshot.process_id == target_window.process_id:
            return "same_process"
        if getattr(snapshot, "owner_hwnd", 0) == target_window.hwnd:
            return "owned_by_target"
        return "other"
