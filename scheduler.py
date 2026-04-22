from __future__ import annotations

import json
import sys
import time
from contextlib import suppress
from pathlib import Path
from queue import Empty, SimpleQueue

import keyboard
from PIL import ImageGrab

from common import (
    DEFAULT_LAYOUT_SPECS,
    ConfirmState,
    HotkeyCommand,
    Rect,
    SUPPORTED_LAYOUTS,
    SchedulerState,
    VisualViewState,
    resolve_output_path,
)
from controller import ControllerActionError
from win_hotkeys import NativeHotkeyManager, parse_hotkey_spec


class PollingScheduler:
    def __init__(
        self,
        config,
        window_manager,
        grid_mapper,
        detector,
        controller,
        input_guard,
        logger,
        requested_mode: str,
        requested_layout: int | None = None,
        status_publisher=None,
        favorites_reader=None,
        runtime_guard=None,
        layout_switcher=None,
    ):
        self._config = config
        self._window_manager = window_manager
        self._grid_mapper = grid_mapper
        self._detector = detector
        self._controller = controller
        self._input_guard = input_guard
        self._logger = logger
        self._requested_mode = requested_mode
        self._requested_layout = int(requested_layout) if requested_layout is not None else None
        self._lock_runtime_layout_to_requested = bool(
            self._config.controls.lock_runtime_layout_to_requested and self._requested_layout in SUPPORTED_LAYOUTS
        )
        self._profile_control_manual = requested_mode in {"windowed", "fullscreen"} or requested_layout is not None
        self._status = status_publisher
        self._favorites_reader = favorites_reader
        self._runtime_guard = runtime_guard
        self._layout_switcher = layout_switcher
        self._runtime_grid_order = self._normalize_runtime_grid_order(self._config.grid.order)
        self._runtime_favorite_labels: list[str] = []
        self._runtime_layout = int(self._requested_layout or self._config.grid.layout)
        self._observed_mode = "unknown"
        self._observed_layout = int(self._runtime_layout)
        self._effective_mode = "unknown"
        self._effective_layout = int(self._runtime_layout)
        self._manual_mode_cycle_anchor: str | None = (
            self._requested_mode if self._requested_mode in {"windowed", "fullscreen"} else None
        )
        self._manual_layout_cycle_anchor: int | None = (
            int(self._requested_layout) if self._requested_layout is not None else None
        )
        # 关键修复：现场布局刚通过 UIA 读数确认后，短时间内不要反复再拉“窗口分割”面板。
        # 否则一旦进入恢复/重试链，界面会来回抖动，甚至把用户的 F10 热键也打断。
        self._runtime_layout_uia_confirmed_layout: int | None = None
        self._runtime_layout_uia_confirmed_at = 0.0
        self._runtime_layout_uia_confirm_cooldown_seconds = 8.0
        # 关键修复：运行时布局一旦刚刚完成同步，PREPARE_TARGET 不要立刻再做同帧重判。
        # 全屏 4 宫格在 UIA 读数偶发超时时，视觉回退会短暂把 4 错翻成 6，导致动作路径抖动。
        self._runtime_layout_recent_sync_at = 0.0
        self._runtime_layout_recent_sync_cooldown_seconds = 30.0
        self._windowed_runtime_layout_sync_needed = True

        self._state = SchedulerState.IDLE
        self._current_index = 0
        self._cells = []
        self._window_info = None
        self._preview_rect = None
        self._current_mode = "unknown"
        self._active_cell = None
        self._is_zoomed = False
        self._cycle_id = 0
        self._active_cycle_id = 0
        self._zoom_confirmed = False
        self._zoom_confirmed_cycle_id = 0
        self._zoom_retry_count = 0
        self._select_confirmed = False
        self._grid_confirmed = False
        self._zoom_before_preview_probe = None
        self._zoom_before_cell_probe = None
        self._grid_confirm_esc_used = False
        self._last_grid_probe = None
        self._last_zoom_probe = None
        self._zoom_partial_signal_seen = False
        self._current_cycle_zoom_confirm_poll_count = 1
        self._zoom_confirm_poll_boost_cycles_remaining = 0
        self._startup_warmup_done = False
        self._cycle_soft_issue_hint = ""

        self._user_paused = False
        self._guard_paused = False
        self._stop_requested = False
        self._recovery_requested = False
        self._resume_requires_recovery = False

        self._hotkeys: list[tuple[str, object]] = []
        self._native_hotkeys = NativeHotkeyManager(logger=self._logger) if sys.platform.startswith("win") else None
        self._hotkey_last_trigger_at: dict[str, float] = {}
        self._hotkey_press_latched: dict[str, bool] = {}
        self._hotkey_plain_only: dict[str, bool] = {}
        self._start_pause_toggle_lock_until = 0.0
        self._last_pause_reason = ""
        self._post_recovery_state = SchedulerState.PREPARE_TARGET
        self._recovery_in_progress = False
        self._recovery_reason = ""
        self._next_transition_reason = "startup"
        self._pause_barrier_latched = False
        self._pause_barrier_source = ""
        self._pause_barrier_state = ""
        self._command_queue: SimpleQueue[HotkeyCommand] = SimpleQueue()
        self._pause_acknowledged = False
        self._pause_ack_view = VisualViewState.UNKNOWN
        self._paused_index: int | None = None
        self._paused_stage: str = ""
        self._grid_order_changed_during_pause = False
        self._manual_next_target_index: int | None = None
        self._manual_next_queue_depth = 0
        self._manual_next_used_during_pause = False
        self._pending_pause_ack_next_requests = 0
        self._resume_request_pending = False
        self._resume_clear_cooldown_bypass_index: int | None = None
        self._path_retry_count = 0
        self._issue_registry: dict[tuple[int, str], dict[str, int]] = {}
        self._issue_failure_streak = 0
        self._guard_failure_streak = 0
        self._prepare_target_context_reason = ""
        self._runtime_layout_cache_path = resolve_output_path(self._config.path, "tmp/runtime_profile_cache.json")
        self._runtime_status_path = resolve_output_path(self._config.path, self._config.status_overlay.status_file)
        self._runtime_control_path = self._runtime_status_path.with_suffix(".control.json")
        with suppress(Exception):
            self._runtime_control_path.unlink(missing_ok=True)
        self._runtime_layout_cache_ttl_seconds = 10.0 * 60.0
        self._startup_cached_layout_verify_pending = False
        self._last_published_status_key: tuple[str, str, str, str, str] | None = None

    def run(self) -> None:
        self._logger.info("Starting polling scheduler")
        self._input_guard.start()
        # 关键修复：启动首轮进入主循环前就要先压住 input_guard。
        # 否则 pythonw/状态浮层刚拉起时，_refresh_pause_state() 会先于 startup_warmup 执行，
        # 直接把调度器在 IDLE 段误暂停，后续根本跑不到第二行第一列的真实路径。
        self._suppress_input_guard(duration_ms=12000)
        self._register_hotkeys()
        self._logger.info(
            "Runtime hotkeys: %s=auto/manual, %s=mode cycle, %s=layout cycle, %s=order cycle, %s=run/pause/continue, %s=next while paused, %s=stop+exit, %s=emergency return to grid and restart current",
            self._config.hotkeys.profile_source_toggle,
            self._config.hotkeys.mode_cycle,
            self._config.hotkeys.layout_cycle,
            self._config.hotkeys.grid_order_cycle,
            self._config.hotkeys.start_pause,
            self._config.hotkeys.next_cell,
            self._config.hotkeys.stop,
            self._config.hotkeys.emergency_recover,
        )
        self._publish_status(
            message="启动预热中...",
            details=self._hotkey_summary(prefix="waiting_for_startup_warmup"),
            level="info",
        )

        try:
            while self._state != SchedulerState.STOPPED:
                self._consume_commands()
                self._refresh_pause_state()

                if self._recovery_requested and not self._recovery_in_progress:
                    self._state = SchedulerState.ERROR_RECOVERY

                if self._stop_requested:
                    self._stop_with_recovery()
                    continue

                if self._state == SchedulerState.PAUSED:
                    self._handle_paused_state()
                    continue

                if not self._startup_warmup_done:
                    self._startup_warmup()
                    if self._stop_requested:
                        self._stop_with_recovery()
                        continue
                    if self._state == SchedulerState.PAUSED or not self._startup_warmup_done:
                        continue
                    self._state = SchedulerState.PREPARE_TARGET
                    continue

                if self._state == SchedulerState.PREPARE_TARGET:
                    self._prepare_iteration()
                elif self._state == SchedulerState.SELECT_TARGET:
                    self._select_target()
                elif self._state == SchedulerState.SELECT_CONFIRM:
                    self._confirm_selected_target()
                elif self._state == SchedulerState.ZOOM_IN:
                    self._zoom_in_active_cell()
                elif self._state == SchedulerState.ZOOM_CONFIRM:
                    self._confirm_zoom_in()
                elif self._state == SchedulerState.ZOOM_DWELL:
                    self._dwell()
                elif self._state == SchedulerState.ZOOM_OUT:
                    self._zoom_out_active_cell()
                elif self._state == SchedulerState.GRID_CONFIRM:
                    self._confirm_grid_restore()
                elif self._state == SchedulerState.GRID_DWELL:
                    self._grid_dwell()
                elif self._state == SchedulerState.NEXT:
                    self._advance_to_next_cell()
                elif self._state == SchedulerState.ERROR_RECOVERY:
                    self._recover_from_error()
                elif self._state == SchedulerState.IDLE:
                    self._state = SchedulerState.PREPARE_TARGET
                else:
                    raise RuntimeError(f"Unexpected scheduler state {self._state}")
        finally:
            self._cleanup()

    def _startup_warmup(self) -> None:
        self._logger.info("STARTUP_WARMUP begin")
        self._publish_status(
            message="启动预热中...",
            details=self._hotkey_summary(prefix="STARTUP_WARMUP"),
            level="info",
        )
        locked_fast_path = self._use_locked_runtime_profile_fast_path()
        stable_samples = 0
        required_samples = 1 if locked_fast_path else 2

        while stable_samples < required_samples:
            self._consume_commands()
            self._refresh_pause_state()
            if self._state == SchedulerState.PAUSED or self._stop_requested:
                return
            # 关键修复：startup warmup 的第二个稳定样本只需要确认窗口矩形仍然稳定，
            # 不需要再跑一遍完整的 auto 模式识别，否则固定程序会在预热期白白多卡一轮。
            self._refresh_window_context(
                fast=(stable_samples > 0 or locked_fast_path) and self._window_info is not None,
            )
            stable_samples += 1
            self._logger.info(
                "client_rect_stable_samples hwnd=%s samples=%s/%s client_rect=%s",
                self._window_info.hwnd,
                stable_samples,
                required_samples,
                self._window_info.client_rect,
            )
            if stable_samples < required_samples and not self._wait_interruptible(0.12 if locked_fast_path else 0.18, allow_pause=True):
                return

        if not self._wait_interruptible(0.12 if locked_fast_path else 0.35, allow_pause=True):
            return

        self._clear_runtime_context_for_restart(reason="startup_warmup")
        self._bootstrap_windowed_runtime_layout_from_cache()
        clear_manual_activity = getattr(self._input_guard, "clear_manual_activity", None)
        if callable(clear_manual_activity):
            with suppress(Exception):
                clear_manual_activity()
        # 关键修复：管理员提权/UAC 接受、切回客户端、状态浮层拉起这些动作都会在预热阶段留下
        # “最近有人工输入”的痕迹。若只保留原来的 3 秒保护窗，固定程序经常在 STARTUP_WARMUP end
        # 之后立刻被 input_guard 误暂停，看起来像“预热完成后不再自动执行”。
        self._suppress_input_guard(duration_ms=max(8000, self._config.input_guard.resume_settle_ms + 2000))
        self._set_zoom_confirm_poll_boost_cycles(2)
        self._startup_warmup_done = True
        self._logger.info("STARTUP_WARMUP end")

    def _prepare_iteration(self) -> None:
        if self._pause_before_transition(SchedulerState.PREPARE_TARGET, SchedulerState.SELECT_TARGET):
            return
        self._begin_cycle()
        self._refresh_window_context(
            fast=self._use_locked_runtime_profile_fast_path() and self._window_info is not None,
        )
        self._verify_startup_cached_layout_before_actions()
        if self._maybe_skip_for_issue_cooldown():
            return
        if not self._ensure_prepare_target_grid():
            return
        if not self._pause_for_runtime_profile_mismatch(reason="prepare_target_profile_check"):
            return

        # 关键修复：进入 PREPARE_TARGET 时必须先建立“当前宫格”的新 probe。
        # 否则在首轮、恢复后或上下文刚清空时，runtime_guard / detector 只能面对
        # 一个低纹理画面却没有可对比的宫格基线，容易把合法宫格误判成 unexpected_interface。
        self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
        if not self._guard_stage_view("PREPARE_TARGET", VisualViewState.GRID, refresh_context=False):
            return
        if self._config.window.focus_before_action:
            # 关键修复：进入动作前也要复用“真实可见目标前台”判断，
            # 避免真全屏附属渲染窗未激活时，仍然只对宿主 hwnd 做一次无效聚焦。
            if not self._ensure_visual_target_foreground(reason="prepare_target_action"):
                return

        self._logger.info(
            "Prepared cell=%s row=%s col=%s mode=%s preview_rect=%s cell_rect=%s select_point=%s zoom_point=%s zoom_out_point=%s cycle=%s",
            self._active_cell.index,
            self._active_cell.row,
            self._active_cell.col,
            self._current_mode,
            self._preview_rect,
            self._active_cell.cell_rect,
            self._active_cell.select_point,
            self._active_cell.zoom_point,
            self._current_zoom_out_point(),
            self._active_cycle_id,
        )
        self._publish_current_state(level="info")
        self._transition_state(SchedulerState.SELECT_TARGET, from_state=SchedulerState.PREPARE_TARGET)

    def _select_target(self) -> None:
        if self._pause_before_transition(SchedulerState.SELECT_TARGET, SchedulerState.SELECT_CONFIRM):
            return
        if not self._guard_stage_view("SELECT_TARGET", VisualViewState.GRID, refresh_context=True):
            return
        if not self._select_active_cell(
            reason="prepare",
            action_type="select_target",
            allow_paused=False,
            settle_after_action=False,
            skip_guard_before=True,
        ):
            return
        if self._state == SchedulerState.PAUSED or self._stop_requested:
            return
        self._publish_current_state(level="info")
        self._transition_state(SchedulerState.SELECT_CONFIRM, from_state=SchedulerState.SELECT_TARGET)

    def _confirm_selected_target(self) -> None:
        if self._pause_before_transition(SchedulerState.SELECT_CONFIRM, SchedulerState.ZOOM_IN):
            return
        if not self._wait_interruptible(self._config.timing.select_settle_ms / 1000.0, allow_pause=True):
            return

        select_result = self._detector.confirm_select(
            self._preview_rect,
            self._active_cell.rect,
            grid_probe=self._last_grid_probe,
        )
        self._select_confirmed = select_result.state != ConfirmState.NO_CHANGE
        self._logger.info(
            "SELECT_CONFIRM cell=%s cycle=%s confirm_state=%s metrics=%s",
            self._active_cell.index,
            self._active_cycle_id,
            select_result.state.value,
            select_result.metrics,
        )
        if not self._guard_stage_view("SELECT_CONFIRM", VisualViewState.GRID, refresh_context=True):
            return

        result = self._detector.inspect(self._active_cell.rect)
        self._cycle_soft_issue_hint = result.status if result.status in {"preview_failure", "black_screen"} else ""
        if result.status in {"preview_failure", "black_screen"}:
            # 关键修复：宫格里的“预览失败 / 黑屏”只是单路内容异常，不等于客户端当前界面错误。
            # 在非政务网和低纹理现场，这类 tile 仍需要完整跑完
            # “单击 -> 双击放大 -> 停留 -> 双击返回 -> 下一路”动作路径，
            # 不能在 SELECT_CONFIRM 预检阶段就直接跳到下一路。
            self._logger.info(
                "PRECHECK soft anomaly on cell=%s result=%s metrics=%s; continuing action path",
                self._active_cell.index,
                result.status,
                result.metrics,
            )
            self._maybe_save_failure_snapshot(result.status, self._active_cell.index, self._active_cell.rect)

        self._transition_state(SchedulerState.ZOOM_IN, from_state=SchedulerState.SELECT_CONFIRM)

    def _zoom_in_active_cell(self) -> None:
        if self._pause_before_transition(SchedulerState.ZOOM_IN, SchedulerState.ZOOM_CONFIRM):
            return
        if not self._guard_stage_view("ZOOM_IN", VisualViewState.GRID, refresh_context=True):
            return

        self._logger.info(
            "ZOOM_IN cell=%s cell_rect=%s select_point=%s zoom_point=%s zoom_out_point=%s action_type=double_click",
            self._active_cell.index,
            self._active_cell.cell_rect,
            self._active_cell.select_point,
            self._active_cell.zoom_point,
            self._current_zoom_out_point(),
        )
        self._publish_current_state(level="info")
        self._zoom_before_preview_probe = self._detector.capture_image(self._preview_rect).convert("L")
        self._zoom_before_cell_probe = self._detector.capture_cell_probe(self._active_cell.rect)

        if not self._perform_pointer_action(
            action_name="zoom_in",
            point_getter=lambda: self._active_cell.zoom_point,
            controller_action=lambda point: self._controller.double_click(
                point,
                hwnd=self._window_info.hwnd,
                client_origin=(self._window_info.client_rect.left, self._window_info.client_rect.top),
                action_type="zoom_in",
            ),
            failure_target_state=SchedulerState.NEXT,
            recover_on_failure=True,
            skip_guard_before=True,
            guard_expected_view_before=VisualViewState.GRID,
        ):
            return

        if self._recovery_requested:
            self._logger.warning(
                "Emergency recovery will preempt cell=%s immediately after ZOOM_IN",
                self._active_cell.index,
            )
            self._state = SchedulerState.ERROR_RECOVERY
            return

        self._transition_state(SchedulerState.ZOOM_CONFIRM, from_state=SchedulerState.ZOOM_IN)

    def _confirm_zoom_in(self) -> None:
        if self._pause_before_transition(SchedulerState.ZOOM_CONFIRM, SchedulerState.ZOOM_DWELL):
            return
        self._publish_current_state(level="info")

        try:
            if self._perform_zoom_confirm_attempt(attempt_label="initial"):
                self._transition_state(SchedulerState.ZOOM_DWELL, from_state=SchedulerState.ZOOM_CONFIRM)
                return

            self._zoom_retry_count = 1
            self._logger.warning(
                "Zoom confirmation failed on cell=%s cycle=%s; retrying once",
                self._active_cell.index,
                self._active_cycle_id,
            )

            if not self._select_active_cell(reason="zoom_retry", action_type="select_target", allow_paused=False):
                return
            if self._state == SchedulerState.PAUSED or self._stop_requested:
                return

            self._zoom_before_preview_probe = self._detector.capture_image(self._preview_rect).convert("L")
            self._zoom_before_cell_probe = self._detector.capture_cell_probe(self._active_cell.rect)
            if not self._perform_pointer_action(
                action_name="zoom_in_retry",
                point_getter=lambda: self._active_cell.zoom_point,
                controller_action=lambda point: self._controller.double_click(
                    point,
                    hwnd=self._window_info.hwnd,
                    client_origin=(self._window_info.client_rect.left, self._window_info.client_rect.top),
                    action_type="zoom_in_retry",
                ),
                failure_target_state=SchedulerState.NEXT,
                recover_on_failure=True,
                guard_expected_view_before=VisualViewState.GRID,
            ):
                return

            if self._perform_zoom_confirm_attempt(attempt_label="retry"):
                self._transition_state(SchedulerState.ZOOM_DWELL, from_state=SchedulerState.ZOOM_CONFIRM)
                return

            self._logger.warning(
                "Zoom confirmation failed twice on cell=%s cycle=%s; restarting current path",
                self._active_cell.index,
                self._active_cycle_id,
            )
            self._handle_zoom_confirm_failure()
        except Exception as exc:
            self._logger.exception("ZOOM_CONFIRM failed on cell=%s: %s", self._active_cell.index, exc)
            self._clear_cycle_context(preserve_zoom_state=True)
            self._plan_recovery(SchedulerState.PREPARE_TARGET, "zoom_confirm_exception")
            self._state = SchedulerState.ERROR_RECOVERY

    def _dwell(self) -> None:
        if not self._zoom_confirmed or self._zoom_confirmed_cycle_id != self._active_cycle_id:
            self._logger.warning(
                "DWELL blocked because zoom_confirmed is false cell=%s cycle=%s confirmed_cycle=%s",
                getattr(self._active_cell, "index", None),
                self._active_cycle_id,
                self._zoom_confirmed_cycle_id,
            )
            self._clear_cycle_context(preserve_zoom_state=True)
            self._plan_recovery(SchedulerState.NEXT, "dwell_without_zoom_confirm")
            self._state = SchedulerState.ERROR_RECOVERY
            return

        dwell_seconds = self._config.timing.dwell_seconds
        self._logger.info("DWELL cell=%s seconds=%s", self._active_cell.index, dwell_seconds)
        started = time.monotonic()
        last_remaining = None
        last_guard_check = 0.0
        last_view_guard_check = -999.0
        guard_interval = 1.4
        view_guard_interval = max(2.8, dwell_seconds * 0.65)

        while True:
            elapsed = time.monotonic() - started
            remaining = max(0, int(dwell_seconds - elapsed + 0.999))
            if remaining != last_remaining:
                self._publish_current_state(level="info", remaining_seconds=remaining)
                last_remaining = remaining
            if elapsed >= dwell_seconds:
                break
            self._consume_commands()
            if self._recovery_requested and not self._recovery_in_progress:
                self._logger.warning(
                    "Emergency recovery interrupted DWELL immediately on cell=%s",
                    self._active_cell.index,
                )
                self._state = SchedulerState.ERROR_RECOVERY
                return
            if self._config.runtime_guard.verify_during_dwell and elapsed - last_guard_check >= guard_interval:
                last_guard_check = elapsed
                inspect_view = elapsed >= view_guard_interval and elapsed - last_view_guard_check >= view_guard_interval
                if inspect_view:
                    last_view_guard_check = elapsed
                if not self._run_runtime_guard(
                    stage="ZOOM_DWELL",
                    expected_view=VisualViewState.ZOOMED,
                    inspect_view=inspect_view,
                ):
                    return
            self._refresh_pause_state()
            if self._state == SchedulerState.PAUSED or self._stop_requested:
                return
            time.sleep(0.05)

        if self._recovery_requested and not self._recovery_in_progress:
            self._logger.warning(
                "Emergency recovery interrupted DWELL before ZOOM_OUT on cell=%s",
                self._active_cell.index,
            )
            self._state = SchedulerState.ERROR_RECOVERY
            return

        self._transition_state(SchedulerState.ZOOM_OUT, from_state=SchedulerState.ZOOM_DWELL)

    def _zoom_out_active_cell(self) -> None:
        if self._pause_before_transition(SchedulerState.ZOOM_OUT, SchedulerState.GRID_CONFIRM):
            return

        zoom_out_point = self._current_zoom_out_point()
        self._logger.info(
            "ZOOM_OUT cell=%s cell_rect=%s select_point=%s zoom_point=%s zoom_out_point=%s action_type=double_click",
            self._active_cell.index,
            self._active_cell.cell_rect,
            self._active_cell.select_point,
            self._active_cell.zoom_point,
            zoom_out_point,
        )
        self._publish_current_state(level="info")

        if not self._perform_pointer_action(
            action_name="zoom_out",
            point_getter=self._current_zoom_out_point,
            controller_action=lambda point: self._controller.restore_zoom(
                point,
                hwnd=self._window_info.hwnd,
                client_origin=(self._window_info.client_rect.left, self._window_info.client_rect.top),
            ),
            failure_target_state=SchedulerState.NEXT,
            recover_on_failure=True,
            guard_expected_view_before=VisualViewState.ZOOMED,
        ):
            return

        self._is_zoomed = False
        self._grid_confirm_esc_used = False
        if self._recovery_requested:
            self._logger.warning(
                "Emergency recovery request arrived during ZOOM_OUT on cell=%s",
                self._active_cell.index,
            )
            self._state = SchedulerState.ERROR_RECOVERY
            return

        self._transition_state(SchedulerState.GRID_CONFIRM, from_state=SchedulerState.ZOOM_OUT)

    def _confirm_grid_restore(self) -> None:
        if self._pause_before_transition(SchedulerState.GRID_CONFIRM, SchedulerState.GRID_DWELL):
            return

        confirm_result = self._detector.confirm_grid(
            self._preview_rect,
            self._active_cell.rect,
            grid_probe=self._last_grid_probe,
            zoom_probe=self._last_zoom_probe,
        )
        confirmed = confirm_result.state == ConfirmState.STATE_CONFIRMED
        self._grid_confirmed = confirmed
        self._logger.info(
            "GRID_CONFIRM cell=%s cycle=%s confirm_state=%s metrics=%s confirmed=%s",
            self._active_cell.index,
            self._active_cycle_id,
            confirm_result.state.value,
            confirm_result.metrics,
            confirmed,
        )
        self._publish_current_state(level="info")

        if confirmed or self._detector.matches_expected_view(VisualViewState.GRID, confirm_result.metrics):
            self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
            self._clear_issue_registry_for_cell(self._active_cell.index)
            self._reset_issue_failure_streak("grid_confirmed")
            self._clear_cycle_context(preserve_zoom_state=False)
            if not self._wait_interruptible(self._config.timing.between_cells_ms / 1000.0, allow_pause=True):
                return
            self._transition_state(SchedulerState.GRID_DWELL, from_state=SchedulerState.GRID_CONFIRM)
            return

        if not self._grid_confirm_esc_used:
            self._grid_confirm_esc_used = True
            self._logger.warning(
                "GRID_CONFIRM fallback using ESC on cell=%s metrics=%s",
                self._active_cell.index,
                confirm_result.metrics,
            )
            if not self._perform_grid_recovery_action(
                action_name="grid_confirm_esc_fallback",
                failure_target_state=SchedulerState.NEXT,
                recover_on_failure=True,
            ):
                return
            if not self._wait_interruptible(self._config.timing.recovery_wait_ms / 1000.0, allow_pause=True):
                return
            self._state = SchedulerState.GRID_CONFIRM
            return

        if not self._guard_stage_view("GRID_CONFIRM", VisualViewState.GRID, refresh_context=True):
            return

    def _grid_dwell(self) -> None:
        if self._pause_before_transition(SchedulerState.GRID_DWELL, SchedulerState.NEXT):
            return

        dwell_seconds = self._config.timing.post_restore_dwell_seconds
        self._logger.info("GRID_DWELL cell=%s seconds=%s", self._active_cell.index, dwell_seconds)
        started = time.monotonic()
        last_remaining = None
        last_guard_check = 0.0
        last_view_guard_check = -999.0
        guard_interval = 1.4
        view_guard_interval = max(2.8, dwell_seconds * 0.65)

        while True:
            elapsed = time.monotonic() - started
            remaining = max(0, int(dwell_seconds - elapsed + 0.999))
            if remaining != last_remaining:
                self._publish_current_state(level="info", remaining_seconds=remaining)
                last_remaining = remaining
            if elapsed >= dwell_seconds:
                break
            self._consume_commands()
            if self._recovery_requested and not self._recovery_in_progress:
                self._state = SchedulerState.ERROR_RECOVERY
                return
            if self._config.runtime_guard.verify_during_dwell and elapsed - last_guard_check >= guard_interval:
                last_guard_check = elapsed
                inspect_view = elapsed >= view_guard_interval and elapsed - last_view_guard_check >= view_guard_interval
                if inspect_view:
                    last_view_guard_check = elapsed
                if not self._run_runtime_guard(
                    stage="GRID_DWELL",
                    expected_view=VisualViewState.GRID,
                    inspect_view=inspect_view,
                ):
                    return
            self._refresh_pause_state()
            if self._state == SchedulerState.PAUSED or self._stop_requested:
                return
            time.sleep(0.05)

        self._next_transition_reason = "normal_completion"
        self._transition_state(SchedulerState.NEXT, from_state=SchedulerState.GRID_DWELL)

    def _advance_to_next_cell(self) -> None:
        if self._pause_before_transition(SchedulerState.NEXT, SchedulerState.PREPARE_TARGET):
            return
        if not self._guard_stage_view("NEXT", VisualViewState.GRID, refresh_context=True):
            return

        previous_index = self._current_index
        previous_cell = self._active_cell
        next_index = (self._current_index + 1) % len(self._cells)
        next_cell = self._cells[next_index]
        if self._pause_before_transition(SchedulerState.NEXT, SchedulerState.PREPARE_TARGET):
            return

        self._current_index = next_index
        self._active_cell = next_cell
        self._path_retry_count = 0
        self._schedule_startup_cached_layout_reverify(reason="post_first_cycle")
        self._logger.info(
            "NEXT transition reason=%s from order_index=%s %s to order_index=%s %s",
            self._next_transition_reason,
            previous_index,
            self._cell_hint(previous_cell),
            self._current_index,
            self._cell_hint(next_cell),
        )
        self._next_transition_reason = "prepare"
        if self._pause_before_transition(SchedulerState.NEXT, SchedulerState.PREPARE_TARGET):
            self._current_index = previous_index
            self._active_cell = previous_cell
            return

        self._state = SchedulerState.PREPARE_TARGET

    def _recover_from_error(self) -> None:
        active_index = getattr(self._active_cell, "index", None)
        if self._recovery_in_progress:
            return

        self._recovery_in_progress = True
        recovery_reason = self._recovery_reason or "state_recovery"
        next_state = self._post_recovery_state
        try:
            self._logger.warning(
                "Entering ERROR_RECOVERY for cell=%s reason=%s target_state=%s",
                active_index,
                recovery_reason,
                next_state,
            )
            self._publish_status(
                message="运行恢复流程中...",
                details=self._hotkey_summary(prefix=f"cell={active_index} | reason={recovery_reason}"),
                level="warning",
            )
            self._maybe_save_client_snapshot("error_recovery")

            if self._is_zoomed:
                if self._perform_grid_recovery_action(
                    action_name="error_recovery",
                    failure_target_state=next_state,
                    recover_on_failure=False,
                ):
                    self._is_zoomed = False
                    self._wait_interruptible(self._config.timing.recovery_wait_ms / 1000.0, allow_pause=False)
                    self._logger.warning("Recovery returned the client to grid on cell=%s", active_index)
                    if self._window_info and self._preview_rect and not self._stop_requested:
                        self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
                else:
                    next_state = SchedulerState.STOPPED
                    self._logger.error(
                        "Recovery aborted because the target window could not be focused safely for cell=%s",
                        active_index,
                    )
            elif recovery_reason == "emergency_hotkey":
                self._logger.warning(
                    "Emergency recovery found the client already in grid on cell=%s",
                    active_index,
                )

            if recovery_reason == "emergency_hotkey":
                next_state = SchedulerState.PREPARE_TARGET
                self._next_transition_reason = "emergency_restart_current"
                self._path_retry_count = 0
                self._logger.warning(
                    "Emergency recovery will restart current cell=%s from PREPARE_TARGET",
                    active_index,
                )
            elif next_state == SchedulerState.NEXT:
                self._next_transition_reason = f"recovery:{recovery_reason}"
        finally:
            self._recovery_in_progress = False
            self._clear_recovery_flags()
            self._pause_acknowledged = False
            self._clear_cycle_context(preserve_zoom_state=False)

        self._state = next_state

    def _handle_paused_state(self) -> None:
        time.sleep(0.03)
        if self._stop_requested:
            return
        if self._recovery_requested and not self._recovery_in_progress:
            self._state = SchedulerState.ERROR_RECOVERY
            return

        self._refresh_pause_state()
        if self._pause_requested():
            return

        if self._last_pause_reason == "input_guard" and self._config.input_guard.resume_settle_ms > 0:
            self._logger.info(
                "Waiting %sms after manual-input pause before resuming",
                self._config.input_guard.resume_settle_ms,
            )
            if not self._wait_interruptible(self._config.input_guard.resume_settle_ms / 1000.0, allow_pause=False):
                return
            self._refresh_pause_state()
            if self._pause_requested():
                return

        self._logger.info("Resuming from PAUSED")
        self._resume_after_pause()
        if self._pause_requested() or self._state == SchedulerState.PAUSED:
            return
        self._publish_current_state(level="success")

    def _refresh_pause_state(self) -> None:
        if self._config.input_guard.enabled:
            self._guard_paused = self._input_guard.has_recent_manual_input()

        should_pause = self._pause_requested()
        if should_pause and self._state != SchedulerState.PAUSED:
            self._last_pause_reason = "input_guard" if self._guard_paused else "user_pause"
            self._latch_pause_barrier(self._last_pause_reason)
            self._resume_requires_recovery = True
            self._clear_cycle_context(preserve_zoom_state=self._is_zoomed, reason="pause_resume")
            self._logger.warning(
                "Pausing scheduler user_paused=%s guard_paused=%s cell=%s",
                self._user_paused,
                self._guard_paused,
                getattr(self._active_cell, "index", None),
            )
            self._state = SchedulerState.PAUSED
            self._acknowledge_pause()
            self._publish_current_state(level="warning")

    def _stop_with_recovery(self) -> None:
        self._logger.info("Stop requested. Performing safe shutdown.")
        self._publish_status(
            message="正在安全停止",
            details=self._hotkey_summary(prefix="返回宫格后退出"),
            level="warning",
        )
        if self._is_zoomed:
            if self._perform_grid_recovery_action(
                action_name="stop_recovery",
                failure_target_state=SchedulerState.STOPPED,
                recover_on_failure=False,
            ):
                self._is_zoomed = False
                self._wait_interruptible(self._config.timing.recovery_wait_ms / 1000.0, allow_pause=False)
            else:
                self._logger.error("Safe stop skipped keyboard recovery because the target window could not be focused")
        self._clear_recovery_flags()
        self._release_pause_barrier()
        self._pause_acknowledged = False
        self._paused_stage = ""
        self._paused_index = None
        self._manual_next_used_during_pause = False
        self._clear_cycle_context(preserve_zoom_state=False)
        self._state = SchedulerState.STOPPED

    def _begin_cycle(self) -> None:
        self._cycle_id += 1
        self._active_cycle_id = self._cycle_id
        self._guard_failure_streak = 0
        self._cycle_soft_issue_hint = ""
        self._clear_cycle_context(preserve_zoom_state=False)
        if self._zoom_confirm_poll_boost_cycles_remaining > 0:
            self._current_cycle_zoom_confirm_poll_count = 3
            self._zoom_confirm_poll_boost_cycles_remaining -= 1
        else:
            self._current_cycle_zoom_confirm_poll_count = 1

    def _clear_cycle_context(self, *, preserve_zoom_state: bool, reason: str | None = None) -> None:
        self._select_confirmed = False
        self._zoom_confirmed = False
        self._zoom_confirmed_cycle_id = 0
        self._zoom_retry_count = 0
        self._grid_confirmed = False
        self._zoom_before_preview_probe = None
        self._zoom_before_cell_probe = None
        self._zoom_partial_signal_seen = False
        self._grid_confirm_esc_used = False
        if not preserve_zoom_state:
            self._is_zoomed = False
            self._last_zoom_probe = None
        if reason:
            self._logger.info(
                "CONTEXT_RESET reason=%s cell=%s cycle=%s preserve_zoom_state=%s",
                reason,
                getattr(self._active_cell, "index", None),
                self._active_cycle_id,
                preserve_zoom_state,
            )

    def _clear_runtime_context_for_restart(self, *, reason: str) -> None:
        self._last_grid_probe = None
        self._last_zoom_probe = None
        self._zoom_before_preview_probe = None
        self._zoom_before_cell_probe = None
        self._zoom_retry_count = 0
        self._select_confirmed = False
        self._grid_confirmed = False
        self._zoom_confirmed = False
        self._zoom_confirmed_cycle_id = 0
        self._grid_confirm_esc_used = False
        self._cycle_soft_issue_hint = ""
        self._is_zoomed = False
        self._path_retry_count = 0
        self._prepare_target_context_reason = reason
        self._mark_windowed_runtime_layout_sync_needed(f"{reason}:runtime_restart")
        if reason == "resume_hard_reset":
            self._logger.info("RESUME_CLEAR_CONTEXT done")
        else:
            self._logger.info("CONTEXT_RESET reason=%s runtime_context=full", reason)

    def _should_accept_zoom_confirm_fast_path(self, confirm_result: ConfirmResult) -> bool:
        metrics = dict(confirm_result.metrics)
        if not self._detector.matches_expected_view(VisualViewState.ZOOMED, metrics):
            return False
        if metrics.get("locked_fullscreen_transition_zoom_confirmed") == 1.0:
            return True
        if metrics.get("runtime_transition_zoom_confirmed") == 1.0:
            return True
        if metrics.get("expansion_dominant_zoom_confirmed") == 1.0:
            return True
        if metrics.get("low_texture_zoom_confirmed") == 1.0:
            return True
        runtime_view_zoomed = metrics.get("runtime_view_zoomed") == 1.0
        main_view_expansion_confirmed = metrics.get("main_view_expansion_confirmed") == 1.0
        layout_change_confirmed = metrics.get("layout_change_confirmed") == 1.0
        return runtime_view_zoomed and (main_view_expansion_confirmed or layout_change_confirmed)

    def _perform_zoom_confirm_attempt(self, *, attempt_label: str) -> bool:
        cycle_id = self._active_cycle_id
        if cycle_id != self._active_cycle_id or self._recovery_requested:
            return False

        poll_count = max(1, self._current_cycle_zoom_confirm_poll_count)
        for poll_index in range(poll_count):
            if poll_index > 0 and not self._wait_interruptible(0.14, allow_pause=True):
                return False

            confirm_result = self._detector.confirm_zoom(
                self._preview_rect,
                self._active_cell.rect,
                cell_rect=self._active_cell.cell_rect,
                before_preview_probe=self._zoom_before_preview_probe,
                before_cell_probe=self._zoom_before_cell_probe,
                grid_probe=self._last_grid_probe,
                soft_issue_hint=self._cycle_soft_issue_hint,
                locked_fullscreen_layout=self._locked_fullscreen_layout_for_hint(),
            )
            confirmed = confirm_result.state == ConfirmState.STATE_CONFIRMED
            if confirm_result.state == ConfirmState.PARTIAL_CHANGE:
                self._zoom_partial_signal_seen = True
            self._logger.info(
                "ZOOM_CONFIRM cell=%s cycle=%s attempt=%s poll=%s/%s soft_issue_hint=%s layout_change_confirmed=%s main_view_expansion_confirmed=%s content_continuity_confirmed=%s low_texture_zoom_confirmed=%s preview_failure_zoom_confirmed=%s continuity_dominant_zoom_confirmed=%s locked_fullscreen_transition_zoom_confirmed=%s expansion_dominant_zoom_confirmed=%s runtime_transition_zoom_confirmed=%s metrics=%s confirm_state=%s confirmed=%s",
                self._active_cell.index,
                cycle_id,
                attempt_label,
                poll_index + 1,
                poll_count,
                self._cycle_soft_issue_hint or "none",
                bool(confirm_result.metrics.get("layout_change_confirmed")),
                bool(confirm_result.metrics.get("main_view_expansion_confirmed")),
                bool(confirm_result.metrics.get("content_continuity_confirmed")),
                bool(confirm_result.metrics.get("low_texture_zoom_confirmed")),
                bool(confirm_result.metrics.get("preview_failure_zoom_confirmed")),
                bool(confirm_result.metrics.get("continuity_dominant_zoom_confirmed")),
                bool(confirm_result.metrics.get("locked_fullscreen_transition_zoom_confirmed")),
                bool(confirm_result.metrics.get("expansion_dominant_zoom_confirmed")),
                bool(confirm_result.metrics.get("runtime_transition_zoom_confirmed")),
                confirm_result.metrics,
                confirm_result.state.value,
                confirmed,
            )
            if not confirmed and self._should_accept_zoom_confirm_fast_path(confirm_result):
                confirmed = True
                self._logger.warning(
                    "ZOOM_CONFIRM fast-path accepted cell=%s cycle=%s attempt=%s poll=%s/%s runtime_view_zoomed=%s main_view_expansion_confirmed=%s layout_change_confirmed=%s confirm_state=%s",
                    self._active_cell.index,
                    cycle_id,
                    attempt_label,
                    poll_index + 1,
                    poll_count,
                    bool(confirm_result.metrics.get("runtime_view_zoomed")),
                    bool(confirm_result.metrics.get("main_view_expansion_confirmed")),
                    bool(confirm_result.metrics.get("layout_change_confirmed")),
                    confirm_result.state.value,
                )
            if confirmed:
                self._is_zoomed = True
                self._zoom_confirmed = True
                self._zoom_confirmed_cycle_id = cycle_id
                self._last_zoom_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
                self._clear_issue_registry_for_cell(self._active_cell.index, reason="zoom_confirm_failed")
                return True

        self._logger.warning(
            "Zoom confirm check failed on cell=%s cycle=%s attempt=%s",
            self._active_cell.index,
            cycle_id,
            attempt_label,
        )
        return False

    def _handle_zoom_confirm_failure(self) -> None:
        partial_signal_seen = self._zoom_partial_signal_seen
        current_fail_streak = 0
        cooldown_remaining = 0
        if self._active_cell:
            key = self._issue_key(self._active_cell.index, "zoom_confirm_failed")
            current_fail_streak = int(self._issue_registry.get(key, {}).get("fail_streak", 0))
        if partial_signal_seen and self._preview_rect:
            # 关键修复：只要放大确认阶段出现过 PARTIAL_CHANGE，就不能假定客户端仍在宫格。
            # VSClient 真全屏的低纹理单路错误页经常会在 confirm_zoom 落入 PARTIAL_CHANGE。
            # 这里保守地按“可能已经放大”处理，先回宫格，再重走当前路，避免误跳下一路。
            self._is_zoomed = True
            self._last_zoom_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
            self._logger.warning(
                "ZOOM_CONFIRM partial signal detected on cell=%s cycle=%s; forcing grid recovery before restarting current path",
                self._active_cell.index,
                self._active_cycle_id,
            )

        self._maybe_save_failure_snapshot("zoom_confirm_failed", self._active_cell.index, self._active_cell.rect)
        auto_paused = self._register_issue_failure("zoom_confirm_failed")
        if self._active_cell:
            key = self._issue_key(self._active_cell.index, "zoom_confirm_failed")
            current_fail_streak = int(self._issue_registry.get(key, {}).get("fail_streak", current_fail_streak))
            cooldown_remaining = int(self._issue_registry.get(key, {}).get("cooldown_remaining", 0))
        if partial_signal_seen and (current_fail_streak >= 2 or cooldown_remaining > 0):
            self._logger.warning(
                "ZOOM_CONFIRM partial signal unstable on cell=%s cycle=%s fail_streak=%s cooldown_remaining=%s; continuing grid recovery because skip_on_detected_issue=%s",
                self._active_cell.index,
                self._active_cycle_id,
                current_fail_streak,
                cooldown_remaining,
                self._config.detection.skip_on_detected_issue,
            )
            if not self._config.detection.skip_on_detected_issue:
                self._publish_status(
                    message=f"放大判定反复不稳定，已暂停：{self._cell_hint(self._active_cell)}",
                    details="已经检测到局部放大信号，且当前路又进入失败/冷却；程序已停止自动恢复，避免继续乱点。",
                    level="warning",
                )
                if self._state != SchedulerState.PAUSED:
                    self._pause_for_detected_issue("zoom_confirm_partial_repeat")
                return
            self._publish_status(
                message=f"放大判定反复不稳定：{self._cell_hint(self._active_cell)}，继续回宫格并重走当前路",
                details="skip_on_detected_issue 已启用；当前路进入失败/冷却时不再自动暂停，优先继续回宫格恢复。",
                level="warning",
            )
        if auto_paused:
            return

        message = f"放大失败：{self._cell_hint(self._active_cell)}，正在重走当前路"
        details = ""
        if partial_signal_seen:
            message = f"放大确认不稳定：{self._cell_hint(self._active_cell)}，正在回宫格并重走当前路"
            details = "已捕获局部放大信号，优先回宫格，避免误跳下一路。"
        self._publish_status(message=message, details=details, level="warning")
        self._path_retry_count = 0
        self._clear_cycle_context(preserve_zoom_state=self._is_zoomed)
        self._plan_recovery(SchedulerState.PREPARE_TARGET, "zoom_confirm_failed")
        self._state = SchedulerState.ERROR_RECOVERY

    def _plan_recovery(self, target_state: SchedulerState, reason: str) -> None:
        self._post_recovery_state = target_state
        self._recovery_reason = reason

    def _queue_emergency_recovery(self, target_state: SchedulerState, reason: str) -> None:
        self._recovery_requested = True
        self._user_paused = False
        self._resume_requires_recovery = False
        self._release_pause_barrier()
        self._plan_recovery(target_state, reason)

    def _clear_recovery_flags(self) -> None:
        self._recovery_requested = False
        self._recovery_reason = ""
        self._resume_requires_recovery = False
        self._post_recovery_state = SchedulerState.PREPARE_TARGET
        self._resume_request_pending = False
        self._manual_next_target_index = None
        self._manual_next_queue_depth = 0
        if self._state == SchedulerState.STOPPED:
            self._resume_clear_cooldown_bypass_index = None

    def _enqueue_command(self, command: HotkeyCommand) -> None:
        self._command_queue.put(command)

    def _consume_commands(self) -> None:
        self._consume_external_control_commands()
        while True:
            try:
                command = self._command_queue.get_nowait()
            except Empty:
                return
            self._handle_command(command)

    def _consume_external_control_commands(self) -> None:
        payload = self._read_external_control_payload()
        if not payload:
            return
        command_name = str(payload.get("command") or "").strip().lower()
        origin = str(payload.get("origin") or "external_control")
        if command_name == "stop":
            self._logger.warning("External control requested STOP origin=%s", origin)
            self._command_queue.put(HotkeyCommand.STOP_REQUEST)
            return
        self._logger.warning("Ignoring unknown external control command payload=%s", payload)

    def _read_external_control_payload(self) -> dict[str, object] | None:
        control_path = self._runtime_control_path
        if not control_path.exists():
            return None
        try:
            raw = control_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return None
        except PermissionError:
            return None
        except OSError as exc:
            self._logger.warning("Failed to read external control file %s: %s", control_path, exc)
            with suppress(Exception):
                control_path.unlink(missing_ok=True)
            return None
        with suppress(Exception):
            control_path.unlink(missing_ok=True)
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._logger.warning("Ignoring malformed external control payload %s: %s", control_path, exc)
            return None
        if not isinstance(payload, dict):
            self._logger.warning("Ignoring non-object external control payload from %s", control_path)
            return None
        return payload

    def _handle_command(self, command: HotkeyCommand) -> None:
        if command == HotkeyCommand.PAUSE_REQUEST:
            self._handle_pause_request()
        elif command == HotkeyCommand.RESUME_REQUEST:
            self._handle_resume_request()
        elif command == HotkeyCommand.NEXT_REQUEST:
            self._handle_next_request()
        elif command == HotkeyCommand.STOP_REQUEST:
            self._handle_stop_request()
        elif command == HotkeyCommand.EMERGENCY_RECOVER_REQUEST:
            self._handle_emergency_recover_request()
        elif command == HotkeyCommand.CLEAR_COOLDOWN_REQUEST:
            self._handle_clear_cooldown_request()
        elif command == HotkeyCommand.PROFILE_SOURCE_TOGGLE_REQUEST:
            self._handle_profile_source_toggle_request()
        elif command == HotkeyCommand.MODE_CYCLE_REQUEST:
            self._handle_mode_cycle_request()
        elif command == HotkeyCommand.LAYOUT_CYCLE_REQUEST:
            self._handle_layout_cycle_request()
        elif command == HotkeyCommand.GRID_ORDER_CYCLE_REQUEST:
            self._handle_grid_order_cycle_request()

    def _handle_pause_request(self) -> None:
        if self._state == SchedulerState.STOPPED:
            return
        self._user_paused = True
        self._grid_order_changed_during_pause = False
        self._pending_pause_ack_next_requests = 0
        self._last_pause_reason = "user_pause"
        self._resume_request_pending = False
        self._latch_pause_barrier("user_pause")
        self._resume_requires_recovery = True
        self._clear_cycle_context(preserve_zoom_state=self._is_zoomed, reason="pause_resume")
        if self._state not in {SchedulerState.STOPPED, SchedulerState.ERROR_RECOVERY}:
            self._state = SchedulerState.PAUSED
            self._acknowledge_pause()
        self._logger.warning("Hotkey requested PAUSE")
        self._publish_current_state(level="warning")

    def _handle_resume_request(self) -> None:
        if not self._pause_acknowledged and self._state != SchedulerState.PAUSED:
            self._logger.warning("Hotkey RESUME ignored because scheduler is not paused")
            self._publish_status(
                message="继续无效：当前不在暂停态",
                details=f"请先按 {self._config.hotkeys.start_pause} 暂停，再继续。",
                level="warning",
            )
            return
        if self._last_pause_reason == "runtime_profile_mismatch":
            self._invalidate_runtime_observation("resume_request_precheck")
            observation = self._observe_runtime_profile(reason="resume_request_precheck", samples=3, sync_layout=True)
            if not self._observation_matches_requested(observation):
                self._logger.warning(
                    "Hotkey RESUME blocked because runtime profile is still mismatched actual_mode=%s actual_layout=%s requested_mode=%s requested_layout=%s",
                    observation.get("mode"),
                    observation.get("layout"),
                    self._requested_mode,
                    self._requested_layout,
                )
                self._publish_status(
                    message="目标仍未匹配，继续保持冻结",
                    details=(
                        "；".join(self._runtime_profile_mismatch_details())
                        + f"。请先把客户端切到目标状态，或按 {self._config.hotkeys.profile_source_toggle} 切到手动/自动后，再按 {self._config.hotkeys.start_pause}。"
                    ),
                    level="warning",
                )
                return
        self._user_paused = False
        self._pending_pause_ack_next_requests = 0
        self._resume_request_pending = True
        self._input_guard.clear_manual_activity()
        self._logger.warning("Hotkey requested RESUME")

    def _handle_next_request(self) -> None:
        if self._state != SchedulerState.PAUSED:
            self._logger.warning("Hotkey NEXT ignored because scheduler is not in paused mode")
            self._publish_status(
                message="下一路仅支持暂停态步进",
                details=f"请先按 {self._config.hotkeys.start_pause} 暂停，再按 {self._config.hotkeys.next_cell} 步进下一路。",
                level="warning",
            )
            return
        if not self._pause_acknowledged:
            # 关键修复：全屏卡顿时，用户可能在“暂停请求已经触发、但状态刚进入 PAUSED”
            # 的边界时连续按 F9。这里不能直接丢键，先缓存，等 PAUSE_ACK 完成后立刻执行。
            self._pending_pause_ack_next_requests += 1
            self._logger.info(
                "Hotkey NEXT buffered while pause acknowledgement is still settling pending_count=%s state=%s user_paused=%s",
                self._pending_pause_ack_next_requests,
                self._state,
                self._user_paused,
            )
            self._publish_current_state(level="info")
            return
        self._queue_manual_next_request()

    def _queue_manual_next_request(self) -> None:
        if not self._cells:
            self._refresh_window_context()
            if not self._cells:
                return

        previous_index = self._manual_next_target_index
        queue_depth_before = self._manual_next_queue_depth
        max_queue_depth = self._config.controls.max_queued_next_steps
        if max_queue_depth > 0 and queue_depth_before >= max_queue_depth:
            self._logger.warning(
                "Hotkey NEXT ignored because queued next depth already reached max depth=%s target_index=%s",
                max_queue_depth,
                previous_index,
            )
            self._publish_current_state(level="warning")
            return

        base_index = previous_index
        if base_index is None:
            base_index = self._paused_index if self._paused_index is not None else self._current_index
        target_index = self._next_cell_index(base_index)
        if target_index is None:
            return

        self._manual_next_target_index = target_index
        self._manual_next_queue_depth = queue_depth_before + 1
        self._manual_next_used_during_pause = True
        self._next_transition_reason = "manual_pause_next"
        self._path_retry_count = 0

        click_performed = 1 if self._perform_visible_next_selection() else 0
        queued_cell = self._cells[target_index] if self._cells else self._active_cell
        queue_depth_max_repr = "unlimited" if max_queue_depth == 0 else str(max_queue_depth)
        self._logger.info(
            "Hotkey requested NEXT queued_next_prev_index=%s queued_next_new_index=%s manual_next_click_performed=%s queue_depth_before=%s queue_depth_after=%s queue_depth_max=%s cell_rect=%s select_point=%s zoom_point=%s",
            previous_index,
            target_index,
            click_performed,
            queue_depth_before,
            self._manual_next_queue_depth,
            queue_depth_max_repr,
            getattr(queued_cell, "cell_rect", None),
            getattr(queued_cell, "select_point", None),
            getattr(queued_cell, "zoom_point", None),
        )
        self._publish_current_state(level="info")

    def _handle_stop_request(self) -> None:
        self._stop_requested = True
        self._user_paused = False
        self._pending_pause_ack_next_requests = 0
        self._resume_request_pending = False
        self._pause_acknowledged = False
        self._input_guard.clear_manual_activity()
        self._logger.warning("Hotkey requested STOP")
        self._publish_status(message="正在安全停止", details="", level="warning")

    def _handle_emergency_recover_request(self) -> None:
        if self._recovery_in_progress or self._recovery_requested:
            self._logger.warning("Emergency recovery request ignored because recovery is already pending/in progress")
            return
        # 关键修复：F11 不再跳过当前路，而是回宫格后重走当前未完成动作路径。
        self._queue_emergency_recovery(SchedulerState.PREPARE_TARGET, "emergency_hotkey")
        self._pause_acknowledged = False
        self._clear_cycle_context(preserve_zoom_state=True)
        self._input_guard.clear_manual_activity()
        self._logger.warning(
            "Hotkey requested EMERGENCY recovery: current dwell will be interrupted, the client will return to grid, and the current path will be restarted"
        )
        if self._state == SchedulerState.ZOOM_DWELL:
            self._logger.warning(
                "Emergency recovery marked DWELL for immediate interruption on cell=%s",
                getattr(self._active_cell, "index", None),
            )
        self._publish_status(
            message=f"已触发恢复：返回宫格并重走当前 {self._cell_hint(self._active_cell) if self._active_cell else '当前窗格'}",
            details="",
            level="warning",
        )

    def _handle_clear_cooldown_request(self) -> None:
        active_cooldowns = 0
        reset_entries = 0
        for entry in self._issue_registry.values():
            fail_streak = int(entry.get("fail_streak", 0) or 0)
            cooldown_remaining = int(entry.get("cooldown_remaining", 0) or 0)
            if cooldown_remaining > 0:
                active_cooldowns += 1
            if fail_streak > 0 or cooldown_remaining > 0:
                reset_entries += 1
            entry["fail_streak"] = 0
            entry["cooldown_remaining"] = 0
        previous_streak = int(self._issue_failure_streak)
        self._issue_failure_streak = 0
        resume_bypass_index: int | None = None
        if self._pause_acknowledged or self._state == SchedulerState.PAUSED:
            resume_bypass_index = getattr(self._active_cell, "index", None)
        self._resume_clear_cooldown_bypass_index = resume_bypass_index
        self._logger.warning(
            "Hotkey requested CLEAR_COOLDOWN reset_entries=%s active_cooldowns=%s previous_issue_failure_streak=%s resume_bypass_index=%s",
            reset_entries,
            active_cooldowns,
            previous_streak,
            resume_bypass_index,
        )
        if reset_entries > 0 or previous_streak > 0:
            self._publish_status(
                message="异常冷却已清除",
                details=(
                    f"已清空异常失败计数和冷却状态；若当前已暂停，界面正常时按 {self._config.hotkeys.start_pause} 继续，"
                    f"界面不正常时按 {self._config.hotkeys.emergency_recover} 恢复。"
                ),
                level="info",
            )
        else:
            self._publish_status(
                message="当前没有冷却需要清除",
                details="程序里没有残留的异常冷却或失败计数。",
                level="info",
            )

    def _effective_mode_for_cycle(self) -> str:
        if self._effective_mode in {"windowed", "fullscreen"}:
            return self._effective_mode
        if self._current_mode in {"windowed", "fullscreen"}:
            return self._current_mode
        if self._requested_mode in {"windowed", "fullscreen"}:
            return self._requested_mode
        return "windowed"

    def _effective_layout_for_cycle(self) -> int:
        if self._profile_control_manual and self._requested_layout in SUPPORTED_LAYOUTS:
            return int(self._requested_layout)
        if self._effective_layout in SUPPORTED_LAYOUTS:
            return int(self._effective_layout)
        if self._runtime_layout in SUPPORTED_LAYOUTS:
            return int(self._runtime_layout)
        return int(self._config.grid.layout)

    def _sync_runtime_profile_state(self) -> None:
        self._observed_mode = self._current_mode if self._current_mode in {"windowed", "fullscreen"} else "unknown"
        self._observed_layout = int(self._runtime_layout if self._runtime_layout in SUPPORTED_LAYOUTS else self._config.grid.layout)
        if self._profile_control_manual and self._requested_mode in {"windowed", "fullscreen"}:
            self._effective_mode = self._requested_mode
        else:
            self._effective_mode = self._observed_mode if self._observed_mode in {"windowed", "fullscreen"} else "windowed"
        if self._profile_control_manual and self._requested_layout in SUPPORTED_LAYOUTS:
            self._effective_layout = int(self._requested_layout)
        else:
            self._effective_layout = int(self._observed_layout)

    def _use_locked_runtime_profile_fast_path(self) -> bool:
        return bool(
            self._profile_control_manual
            and self._config.controls.lock_runtime_layout_to_requested
            and self._requested_mode in {"windowed", "fullscreen"}
            and self._requested_layout in SUPPORTED_LAYOUTS
        )

    def _invalidate_runtime_observation(self, reason: str) -> None:
        invalidate_marker_cache = getattr(self._window_manager, "invalidate_windowed_marker_cache", None)
        if callable(invalidate_marker_cache):
            with suppress(Exception):
                invalidate_marker_cache(reason=reason)
        self._mark_windowed_runtime_layout_sync_needed(reason)

    def _majority_vote(self, counts: dict[object, int], *, fallback):
        if not counts:
            return fallback, 0.0, 0
        winner, winner_count = max(counts.items(), key=lambda item: (item[1], str(item[0])))
        total = max(1, sum(counts.values()))
        return winner, winner_count / total, winner_count

    @staticmethod
    def _runtime_profile_observation_requires_fresh_probes(reason: str) -> bool:
        normalized = str(reason or "")
        return normalized.startswith(
            (
                "manual_profile_lock",
                "resume_reconcile",
                "resume_post_recover",
                "runtime_target_update",
                "inspect_runtime",
            )
        )

    def _observe_runtime_profile(
        self,
        *,
        reason: str,
        samples: int = 3,
        sync_layout: bool = True,
    ) -> dict[str, object]:
        mode_counts: dict[str, int] = {}
        layout_counts: dict[int, int] = {}
        view_counts: dict[VisualViewState, int] = {}
        last_metrics: dict[str, float] = {}
        sample_records: list[dict[str, object]] = []
        reanchor_for_layout_observation = sync_layout and self._runtime_profile_observation_requires_fresh_probes(reason)
        original_index = self._current_index
        if reanchor_for_layout_observation:
            # 关键修复：F1 手动锁定 / pause-resume 重识别是在回答“现场此刻到底是几宫格”，
            # 这里不能继续沿用 pause 前某一路的 grid_probe / zoom_probe，也不能让当前 cell index
            # 把 runtime-layout 观测锚到旧路径上，否则会把现场真实 6 宫格重新锁回旧 12 宫格。
            self._last_grid_probe = None
            self._last_zoom_probe = None
            if self._cells:
                self._current_index = 0
                self._active_cell = self._cells[0]
            self._logger.info(
                "RUNTIME_OBSERVE cleared stale probes and reanchored layout observation reason=%s original_index=%s",
                reason,
                original_index,
            )

        try:
            for sample_index in range(max(1, samples)):
                if sample_index > 0:
                    time.sleep(0.08)
                self._refresh_window_context()
                if sync_layout:
                    self._try_sync_runtime_layout(reason=f"{reason}:sample_{sample_index + 1}")
                mode = self._current_mode if self._current_mode in {"windowed", "fullscreen"} else "unknown"
                layout = int(self._runtime_layout if self._runtime_layout in SUPPORTED_LAYOUTS else self._config.grid.layout)
                try:
                    actual_view, metrics = self._classify_current_view(refresh_context=False)
                except Exception as exc:
                    actual_view = VisualViewState.UNKNOWN
                    metrics = {"error": str(exc)}
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
                layout_counts[layout] = layout_counts.get(layout, 0) + 1
                view_counts[actual_view] = view_counts.get(actual_view, 0) + 1
                last_metrics = dict(metrics)
                sample_records.append(
                    {
                        "mode": mode,
                        "layout": layout,
                        "view": actual_view.value,
                        "metrics": dict(metrics),
                    }
                )
        finally:
            if self._cells:
                self._current_index = original_index % len(self._cells)
                self._active_cell = self._cells[self._current_index]

        observed_mode, mode_confidence, mode_votes = self._majority_vote(mode_counts, fallback="unknown")
        observed_layout, layout_confidence, layout_votes = self._majority_vote(
            layout_counts,
            fallback=int(self._runtime_layout if self._runtime_layout in SUPPORTED_LAYOUTS else self._config.grid.layout),
        )
        observed_view, view_confidence, view_votes = self._majority_vote(view_counts, fallback=VisualViewState.UNKNOWN)
        observation = {
            "mode": observed_mode,
            "layout": int(observed_layout),
            "view": observed_view,
            "confidence": min(mode_confidence, layout_confidence, view_confidence),
            "mode_confidence": mode_confidence,
            "layout_confidence": layout_confidence,
            "view_confidence": view_confidence,
            "mode_votes": mode_votes,
            "layout_votes": layout_votes,
            "view_votes": view_votes,
            "samples": sample_records,
            "metrics": last_metrics,
        }
        self._logger.info(
            "RUNTIME_OBSERVE reason=%s mode=%s layout=%s view=%s confidence=%.2f sample_count=%s",
            reason,
            observation["mode"],
            observation["layout"],
            observed_view.value,
            float(observation["confidence"]),
            len(sample_records),
        )
        return observation

    def _observation_matches_requested(self, observation: dict[str, object]) -> bool:
        if not self._profile_control_manual:
            return True
        if self._requested_mode in {"windowed", "fullscreen"} and observation.get("mode") != self._requested_mode:
            return False
        if self._requested_layout is not None and int(observation.get("layout") or 0) != int(self._requested_layout):
            return False
        return True

    def _lock_manual_profile_to_current(self) -> bool:
        observation = self._observe_runtime_profile(reason="manual_profile_lock", samples=3, sync_layout=True)
        locked_mode = (
            str(observation.get("mode"))
            if observation.get("mode") in {"windowed", "fullscreen"}
            else self._effective_mode_for_cycle()
        )
        locked_layout = int(observation.get("layout") or self._runtime_layout or self._config.grid.layout)
        confidence = float(observation.get("confidence") or 0.0)
        if confidence < (2.0 / 3.0):
            self._publish_status(
                message="切换手动失败：现场识别不稳定",
                details=(
                    f"模式={self._mode_display_label(observation.get('mode'))} "
                    f"宫格={self._layout_display_label(locked_layout)} "
                    f"置信度={confidence:.2f}。请先让客户端稳定停在目标宫格页，再按 {self._config.hotkeys.profile_source_toggle}。"
                ),
                level="warning",
            )
            return False
        self._profile_control_manual = True
        self._requested_mode = locked_mode
        self._requested_layout = locked_layout
        self._manual_mode_cycle_anchor = locked_mode
        self._manual_layout_cycle_anchor = locked_layout
        self._sync_runtime_profile_state()
        return True

    def _next_requested_mode(self) -> str | None:
        current_mode = self._effective_mode_for_cycle()
        if not self._profile_control_manual:
            if not self._lock_manual_profile_to_current():
                return None
            current_mode = self._effective_mode_for_cycle()
            return "fullscreen" if current_mode == "windowed" else "windowed"
        return "fullscreen" if self._requested_mode == "windowed" else "windowed"

    def _next_requested_layout(self) -> int | None:
        supported_layouts = [12, 9, 6, 4]
        current_layout = int(self._effective_layout_for_cycle())
        if not self._profile_control_manual or self._requested_layout is None:
            if not self._lock_manual_profile_to_current():
                return None
            current_layout = int(self._requested_layout or current_layout)
            anchor_index = supported_layouts.index(current_layout) if current_layout in supported_layouts else 0
            return supported_layouts[(anchor_index + 1) % len(supported_layouts)]

        anchor = int(self._manual_layout_cycle_anchor or self._requested_layout)
        if anchor not in supported_layouts:
            anchor = supported_layouts[0]
        anchor_index = supported_layouts.index(anchor)
        cycle = supported_layouts[anchor_index:] + supported_layouts[:anchor_index]
        current_index = cycle.index(self._requested_layout) if self._requested_layout in cycle else -1
        return cycle[(current_index + 1) % len(cycle)]

    def _runtime_mode_matches_request(self) -> bool:
        if not self._profile_control_manual or self._requested_mode == "auto":
            return True
        return self._observed_mode == self._requested_mode

    def _runtime_layout_matches_request(self) -> bool:
        if not self._profile_control_manual or self._requested_layout is None:
            return True
        return int(self._observed_layout) == int(self._requested_layout)

    def _runtime_profile_matches_request(self) -> bool:
        return self._runtime_mode_matches_request() and self._runtime_layout_matches_request()

    def _runtime_profile_mismatch_details(self) -> list[str]:
        details: list[str] = []
        if not self._runtime_mode_matches_request():
            details.append(
                f"模式目标={self._mode_display_label(self._requested_mode)}，实际={self._mode_display_label(self._current_mode)}"
            )
        if not self._runtime_layout_matches_request():
            details.append(
                f"宫格目标={self._layout_display_label(self._requested_layout)}，实际={self._layout_display_label(self._runtime_layout)}"
            )
        return details

    def _publish_runtime_target_pending_feedback(self, *, changed_label: str) -> None:
        self._publish_status(
            message=changed_label,
            details=(
                "当前运行控制为自动识别。程序会继续按现场真实界面自动识别模式和宫格。"
                f"如果你要手动锁定，请先按 {self._config.hotkeys.profile_source_toggle} 切到手动。"
            ),
            level="info",
        )

    def _drive_manual_target_to_client(self, *, changed_label: str) -> bool:
        if not self._profile_control_manual or self._layout_switcher is None:
            return False
        if not self._config.controls.runtime_hotkeys_drive_client_ui:
            return False
        if self._config.controls.runtime_hotkeys_require_paused and self._state != SchedulerState.PAUSED:
            self._publish_status(
                message=changed_label,
                details=f"当前已开启暂停态热键直控，但只能在暂停时执行。请先按 {self._config.hotkeys.start_pause} 暂停后再切换。",
                level="warning",
            )
            return False

        try:
            actual_view, metrics = self._classify_current_view(refresh_context=True)
        except Exception as exc:
            self._publish_status(
                message=changed_label,
                details=f"无法确认当前现场是否处于宫格页：{exc}",
                level="warning",
            )
            return False
        if actual_view != VisualViewState.GRID and not self._detector.matches_expected_view(VisualViewState.GRID, metrics):
            self._publish_status(
                message=changed_label,
                details="当前画面不是宫格页，已拒绝直接驱动客户端切换。请先回到宫格页后再试。",
                level="warning",
            )
            return False

        try:
            if self._requested_mode in {"windowed", "fullscreen"} and self._current_mode != self._requested_mode:
                self._layout_switcher.switch_mode(self._requested_mode, target_window=self._window_info)
                time.sleep(0.35)
                self._invalidate_runtime_observation("runtime_hotkey_mode_drive")
                self._refresh_window_context()
            if self._requested_layout in SUPPORTED_LAYOUTS and int(self._runtime_layout) != int(self._requested_layout):
                self._layout_switcher.switch_runtime_layout(int(self._requested_layout), target_window=self._window_info)
                time.sleep(0.35)
                self._invalidate_runtime_observation("runtime_hotkey_layout_drive")
                self._refresh_window_context()
                self._try_sync_runtime_layout(reason="runtime_hotkey_drive")
        except Exception as exc:
            self._publish_status(
                message=f"{changed_label}（客户端同步失败）",
                details=f"暂停态热键直控未能完成：{exc}",
                level="warning",
            )
            return False
        return True

    def _handle_runtime_target_update(self, *, changed_label: str) -> None:
        if not self._profile_control_manual:
            self._publish_runtime_target_pending_feedback(changed_label=changed_label)
            return
        self._invalidate_runtime_observation("runtime_target_update")
        self._refresh_window_context()
        self._try_sync_runtime_layout(reason="runtime_target_update")
        self._drive_manual_target_to_client(changed_label=changed_label)
        self._refresh_window_context()
        self._try_sync_runtime_layout(reason="runtime_target_post_drive")
        self._resume_requires_recovery = False
        if self._last_pause_reason == "runtime_profile_mismatch":
            self._last_pause_reason = ""
        if self._runtime_profile_matches_request():
            self._publish_manual_target_cycle_feedback(matched=True, changed_label=changed_label)
            return
        self._publish_manual_target_cycle_feedback(matched=False, changed_label=changed_label)

    def _mark_windowed_runtime_layout_sync_needed(self, reason: str) -> None:
        self._windowed_runtime_layout_sync_needed = True
        self._runtime_layout_uia_confirmed_layout = None
        self._runtime_layout_uia_confirmed_at = 0.0
        self._runtime_layout_recent_sync_at = 0.0
        self._logger.info("RUNTIME_LAYOUT invalidated reason=%s", reason)

    def _runtime_layout_cache_payload(self, *, layout: int, source: str) -> dict[str, object] | None:
        if self._window_info is None or self._current_mode != "windowed":
            return None
        return {
            "version": 1,
            "mode": "windowed",
            "layout": int(layout),
            "source": str(source),
            "updated_at": round(time.time(), 3),
            "title": str(self._window_info.title or "").strip(),
            "process_name": str(self._window_info.process_name or "").strip().casefold(),
            "client_width": int(self._window_info.client_rect.width),
            "client_height": int(self._window_info.client_rect.height),
            "monitor_width": int(self._window_info.monitor_rect.width),
            "monitor_height": int(self._window_info.monitor_rect.height),
            "grid_order": self._runtime_grid_order,
        }

    def _save_windowed_runtime_layout_cache(self, *, layout: int, source: str) -> None:
        payload = self._runtime_layout_cache_payload(layout=layout, source=source)
        if payload is None:
            return
        try:
            self._runtime_layout_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._runtime_layout_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self._logger.warning("RUNTIME_LAYOUT cache save failed layout=%s source=%s error=%s", layout, source, exc)
            return
        self._logger.info(
            "RUNTIME_LAYOUT cache saved layout=%s source=%s path=%s",
            layout,
            source,
            self._runtime_layout_cache_path,
        )

    def _load_windowed_runtime_layout_cache(self) -> dict[str, object] | None:
        if (
            self._requested_layout is not None
            or self._window_info is None
            or self._preview_rect is None
            or self._current_mode != "windowed"
            or not self._runtime_layout_cache_path.exists()
        ):
            return None
        try:
            payload = json.loads(self._runtime_layout_cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._logger.warning("RUNTIME_LAYOUT cache load failed path=%s error=%s", self._runtime_layout_cache_path, exc)
            return None

        try:
            layout = int(payload.get("layout"))
            updated_at = float(payload.get("updated_at", 0.0))
        except (TypeError, ValueError):
            self._logger.warning("RUNTIME_LAYOUT cache payload invalid path=%s payload=%s", self._runtime_layout_cache_path, payload)
            return None

        if layout not in self._candidate_runtime_layouts() or str(payload.get("mode")) != "windowed":
            return None

        age_seconds = time.time() - updated_at
        if updated_at <= 0.0 or age_seconds < 0.0 or age_seconds > self._runtime_layout_cache_ttl_seconds:
            self._logger.info(
                "RUNTIME_LAYOUT cache rejected reason=stale layout=%s age_seconds=%.1f ttl_seconds=%.1f",
                layout,
                max(0.0, age_seconds),
                self._runtime_layout_cache_ttl_seconds,
            )
            return None

        expected_process = str(payload.get("process_name", "") or "").strip().casefold()
        current_process = str(self._window_info.process_name or "").strip().casefold()
        if expected_process and expected_process != current_process:
            self._logger.info(
                "RUNTIME_LAYOUT cache rejected reason=process_mismatch layout=%s cached_process=%s current_process=%s",
                layout,
                expected_process,
                self._window_info.process_name,
            )
            return None

        expected_title = str(payload.get("title", "") or "").strip()
        current_title = str(self._window_info.title or "").strip()
        if expected_title and expected_title != current_title:
            self._logger.info(
                "RUNTIME_LAYOUT cache rejected reason=title_mismatch layout=%s cached_title=%s current_title=%s",
                layout,
                expected_title,
                self._window_info.title,
            )
            return None

        try:
            cached_client_width = int(payload.get("client_width", -1))
            cached_client_height = int(payload.get("client_height", -1))
            cached_monitor_width = int(payload.get("monitor_width", -1))
            cached_monitor_height = int(payload.get("monitor_height", -1))
        except (TypeError, ValueError):
            self._logger.warning("RUNTIME_LAYOUT cache payload geometry invalid path=%s payload=%s", self._runtime_layout_cache_path, payload)
            return None

        if (
            cached_client_width != int(self._window_info.client_rect.width)
            or cached_client_height != int(self._window_info.client_rect.height)
            or cached_monitor_width != int(self._window_info.monitor_rect.width)
            or cached_monitor_height != int(self._window_info.monitor_rect.height)
        ):
            self._logger.info(
                "RUNTIME_LAYOUT cache rejected reason=geometry_mismatch layout=%s cached_client=%sx%s current_client=%sx%s",
                layout,
                cached_client_width,
                cached_client_height,
                self._window_info.client_rect.width,
                self._window_info.client_rect.height,
            )
            return None

        detect_candidate = getattr(self._layout_switcher, "detect_active_grid_layout_candidate", None)
        if callable(detect_candidate):
            with suppress(Exception):
                visual_candidate = detect_candidate(target_window=self._window_info)
                if visual_candidate is not None and int(visual_candidate.get("layout", -1)) != layout:
                    self._logger.info(
                        "RUNTIME_LAYOUT cache rejected reason=visual_candidate_conflict layout=%s candidate_layout=%s candidate_score=%s",
                        layout,
                        visual_candidate.get("layout"),
                        visual_candidate.get("score"),
                    )
                    return None

        payload["_age_seconds"] = round(max(0.0, age_seconds), 1)
        return payload

    def _bootstrap_windowed_runtime_layout_from_cache(self) -> bool:
        payload = self._load_windowed_runtime_layout_cache()
        if payload is None:
            return False

        cached_layout = int(payload["layout"])
        runtime_label_order = self._runtime_favorite_labels if self._runtime_grid_order == "favorites_name" else []
        resolved_cells = self._grid_mapper.build_cells(
            self._preview_rect,
            cached_layout,
            runtime_label_order=runtime_label_order,
            order_override=self._runtime_grid_order,
        )
        if not resolved_cells:
            return False

        self._runtime_layout = cached_layout
        self._cells = resolved_cells
        self._current_index %= len(self._cells)
        self._active_cell = self._cells[self._current_index]
        self._windowed_runtime_layout_sync_needed = True
        self._runtime_layout_uia_confirmed_layout = None
        self._runtime_layout_uia_confirmed_at = 0.0
        self._runtime_layout_recent_sync_at = 0.0
        self._startup_cached_layout_verify_pending = True
        self._sync_runtime_profile_state()
        self._reset_issue_failure_streak("runtime_layout_sync:startup_cache")
        self._logger.info(
            "RUNTIME_LAYOUT confirm reason=startup_cache layout=%s via=provisional_cache age_seconds=%.1f cell=%s source=%s",
            self._runtime_layout,
            float(payload.get("_age_seconds", 0.0)),
            getattr(self._active_cell, "index", None),
            payload.get("source"),
        )
        return True

    def _schedule_startup_cached_layout_reverify(self, *, reason: str) -> None:
        if (
            not self._startup_cached_layout_verify_pending
            or self._requested_layout is not None
            or self._current_mode != "windowed"
        ):
            return
        hold_until_cell = min(4, max(0, len(self._cells) - 1))
        if hold_until_cell > 0 and self._current_index < hold_until_cell:
            self._logger.info(
                "RUNTIME_LAYOUT deferred verify kept pending reason=%s layout=%s next_cell=%s hold_until_cell=%s",
                reason,
                self._runtime_layout,
                getattr(self._active_cell, "index", None),
                hold_until_cell,
            )
            return
        self._startup_cached_layout_verify_pending = False
        self._windowed_runtime_layout_sync_needed = True
        self._runtime_layout_uia_confirmed_layout = None
        self._runtime_layout_uia_confirmed_at = 0.0
        self._runtime_layout_recent_sync_at = 0.0
        self._logger.info(
            "RUNTIME_LAYOUT deferred verify scheduled reason=%s layout=%s next_cell=%s",
            reason,
            self._runtime_layout,
            getattr(self._active_cell, "index", None),
        )

    def _verify_startup_cached_layout_before_actions(self) -> None:
        if (
            not self._startup_cached_layout_verify_pending
            or self._requested_layout is not None
            or self._current_mode != "windowed"
        ):
            return
        self._startup_cached_layout_verify_pending = False
        self._invalidate_runtime_observation("startup_cache_quick_verify")
        verified = self._try_sync_runtime_layout(reason="startup_cache_quick_verify")
        self._logger.info(
            "RUNTIME_LAYOUT startup quick verify verified=%s layout=%s cell=%s",
            int(verified),
            self._runtime_layout,
            getattr(self._active_cell, "index", None),
        )

    def _suppress_input_guard(self, *, duration_ms: int | None = None) -> None:
        suppress_input_guard = getattr(self._input_guard, "suppress_manual_detection", None)
        if callable(suppress_input_guard):
            with suppress(Exception):
                suppress_input_guard(duration_ms)
            return
        with suppress(Exception):
            self._input_guard.mark_programmatic_action()

    def _pause_for_runtime_profile_mismatch(self, *, reason: str) -> bool:
        mismatch_details = self._runtime_profile_mismatch_details()
        if not mismatch_details:
            return True
        details_text = (
            "；".join(mismatch_details)
            + "。当前为自动识别闭环，程序检测到目标与现场不一致；"
            f"你可以按 {self._config.hotkeys.profile_source_toggle} 切到手动后直接锁定，或保持自动继续让程序识别。"
        )
        self._logger.warning(
            "RUNTIME_PROFILE mismatch reason=%s actual_mode=%s actual_layout=%s requested_mode=%s requested_layout=%s",
            reason,
            self._current_mode,
            self._runtime_layout,
            self._requested_mode,
            self._requested_layout,
        )
        self._publish_status(
            message="目标状态未匹配，已暂停等待处理",
            details=details_text,
            level="warning",
        )
        self._user_paused = True
        self._last_pause_reason = "runtime_profile_mismatch"
        self._resume_requires_recovery = True
        self._latch_pause_barrier("runtime_profile_mismatch")
        self._state = SchedulerState.PAUSED
        self._acknowledge_pause()
        return False

    def _freeze_for_runtime_profile_mismatch(self, *, reason: str) -> bool:
        mismatch_details = self._runtime_profile_mismatch_details()
        if not mismatch_details:
            return True
        self._logger.warning(
            "RUNTIME_PROFILE immediate-freeze reason=%s actual_mode=%s actual_layout=%s requested_mode=%s requested_layout=%s",
            reason,
            self._current_mode,
            self._runtime_layout,
            self._requested_mode,
            self._requested_layout,
        )
        self._publish_status(
            message="目标状态未匹配，已立即冻结等待处理",
            details=(
                "；".join(mismatch_details)
                + "。当前动作路径已冻结，不会继续自动恢复或自动切客户端界面；"
                f"你可以按 {self._config.hotkeys.profile_source_toggle} 切到手动后直接锁定，再按 {self._config.hotkeys.start_pause} 继续。"
            ),
            level="warning",
        )
        self._user_paused = True
        self._last_pause_reason = "runtime_profile_mismatch"
        self._resume_requires_recovery = True
        self._latch_pause_barrier("runtime_profile_mismatch")
        self._state = SchedulerState.PAUSED
        self._acknowledge_pause()
        return False

    def _publish_manual_target_cycle_feedback(self, *, matched: bool, changed_label: str) -> None:
        if matched:
            if self._state == SchedulerState.PAUSED:
                self._publish_status(
                    message=f"{changed_label}（已匹配）",
                    details=(
                        "当前为手动目标闭环；程序已重新核对现场模式和宫格，"
                        "恢复后会按现场真实状态继续运行。"
                        f"程序保持暂停，等待你按 {self._config.hotkeys.start_pause} 继续。"
                    ),
                    level="info",
                )
            else:
                self._publish_status(
                    message=f"{changed_label}（已匹配）",
                    details="当前为手动目标闭环；程序会继续核对现场与目标一致后再沿当前路径运行。",
                    level="info",
                )
            return

        self._publish_status(
            message=changed_label,
            details=(
                "当前为手动目标闭环；请先把客户端切到对应状态。"
                "程序恢复前会再次核对现场，不会继续沿用旧宫格或旧模式乱点。"
            ),
            level="info",
        )

    def _handle_mode_cycle_request(self) -> None:
        next_requested_mode = self._next_requested_mode()
        if next_requested_mode is None:
            return
        previous_requested_mode = self._requested_mode
        self._requested_mode = next_requested_mode
        self._manual_mode_cycle_anchor = next_requested_mode

        self._logger.warning(
            "Hotkey requested MODE cycle previous=%s next=%s current_mode=%s",
            previous_requested_mode,
            next_requested_mode,
            self._current_mode,
        )
        changed_label = f"运行模式目标已切换：{self._mode_display_label(next_requested_mode)}"
        self._handle_runtime_target_update(changed_label=changed_label)

    def _handle_layout_cycle_request(self) -> None:
        next_requested_layout = self._next_requested_layout()
        if next_requested_layout is None:
            return
        previous_requested_layout = self._requested_layout
        self._requested_layout = int(next_requested_layout) if next_requested_layout is not None else None
        if self._requested_layout is not None:
            self._manual_layout_cycle_anchor = int(self._requested_layout)

        self._logger.warning(
            "Hotkey requested LAYOUT cycle previous=%s next=%s runtime_layout=%s mode=%s",
            previous_requested_layout,
            self._requested_layout,
            self._runtime_layout,
            self._current_mode,
        )
        changed_label = f"宫格模式目标已切换：{self._layout_display_label(self._requested_layout)}"
        self._handle_runtime_target_update(changed_label=changed_label)

    def _handle_profile_source_toggle_request(self) -> None:
        previous_manual = self._profile_control_manual
        if self._profile_control_manual:
            self._profile_control_manual = False
            self._requested_mode = "auto"
            self._requested_layout = None
            self._manual_mode_cycle_anchor = None
            self._manual_layout_cycle_anchor = None
            changed_label = "运行控制已切换：自动识别"
        else:
            self._refresh_window_context()
            if not self._lock_manual_profile_to_current():
                self._profile_control_manual = False
                self._manual_mode_cycle_anchor = None
                self._manual_layout_cycle_anchor = None
                return
            changed_label = (
                "运行控制已切换：手动锁定"
                f"（{self._mode_display_label(self._requested_mode)} / {self._layout_display_label(self._requested_layout)}）"
            )
        self._logger.warning(
            "Hotkey requested PROFILE source toggle previous_manual=%s next_manual=%s mode=%s layout=%s",
            previous_manual,
            self._profile_control_manual,
            self._requested_mode,
            self._requested_layout,
        )
        self._handle_runtime_target_update(changed_label=changed_label)

    def _handle_grid_order_cycle_request(self) -> None:
        if self._state != SchedulerState.PAUSED:
            self._logger.warning("Hotkey GRID_ORDER ignored because scheduler is not in paused mode")
            self._publish_status(
                message="轮询顺序仅支持暂停态切换",
                details=(
                    f"请先按 {self._config.hotkeys.start_pause} 暂停，再按 {self._config.hotkeys.grid_order_cycle} 切换顺序。"
                ),
                level="warning",
            )
            return

        previous_order = self._runtime_grid_order
        next_order = "column_major" if previous_order == "row_major" else "row_major"
        paused_physical_index = getattr(self._active_cell, "index", None)
        self._runtime_grid_order = next_order
        self._manual_next_target_index = None
        self._manual_next_queue_depth = 0
        self._manual_next_used_during_pause = False
        self._grid_order_changed_during_pause = True
        self._pending_pause_ack_next_requests = 0
        self._runtime_favorite_labels = []
        self._refresh_window_context(fast=self._window_info is not None)
        if paused_physical_index is not None and self._cells:
            for index, cell in enumerate(self._cells):
                if cell.index != paused_physical_index:
                    continue
                self._current_index = index
                self._active_cell = cell
                break
        self._paused_index = self._current_index
        self._logger.warning(
            "Hotkey requested GRID_ORDER cycle previous=%s next=%s current_index=%s cell=%s",
            previous_order,
            next_order,
            self._current_index,
            self._cell_hint(self._active_cell),
        )
        self._publish_status(
            message=f"轮询顺序已切换：{self._grid_order_label(next_order)}",
            details="当前仍处于暂停态，按 F2 继续后会按新的顺序运行。",
            level="info",
        )

    def _pause_requested(self) -> bool:
        return (self._user_paused or self._guard_paused) and not self._recovery_requested and not self._recovery_in_progress

    def _latch_pause_barrier(self, source: str) -> None:
        if self._pause_barrier_latched:
            return
        self._pause_barrier_latched = True
        self._pause_barrier_source = source or "pause"
        self._pause_barrier_state = self._state.value
        self._logger.warning(
            "PAUSE_BARRIER latched at state=%s source=%s cell=%s",
            self._pause_barrier_state,
            self._pause_barrier_source,
            getattr(self._active_cell, "index", None),
        )

    def _release_pause_barrier(self) -> None:
        self._pause_barrier_latched = False
        self._pause_barrier_source = ""
        self._pause_barrier_state = ""

    def _pause_before_transition(self, from_state: SchedulerState, to_state: SchedulerState) -> bool:
        if not self._pause_requested():
            return False
        self._latch_pause_barrier(self._last_pause_reason or "pause")
        self._logger.warning(
            "PAUSE prevented transition from %s to %s cell=%s",
            from_state,
            to_state,
            getattr(self._active_cell, "index", None),
        )
        self._state = SchedulerState.PAUSED
        return True

    def _transition_state(self, to_state: SchedulerState, *, from_state: SchedulerState | None = None) -> None:
        current_state = from_state or self._state
        if self._pause_before_transition(current_state, to_state):
            return
        self._state = to_state

    def _classify_current_view(self, *, refresh_context: bool = True) -> tuple[VisualViewState, dict[str, float]]:
        if refresh_context or not self._window_info or not self._preview_rect or not self._active_cell:
            self._refresh_window_context(fast=refresh_context and self._window_info is not None)
        return self._detector.classify_runtime_view(
            self._preview_rect,
            self._active_cell.rect,
            grid_probe=self._last_grid_probe,
            zoom_probe=self._last_zoom_probe,
        )

    def _is_ignored_auxiliary_foreground(self, snapshot) -> bool:
        title = (getattr(snapshot, "title", "") or "").strip()
        process_name = (getattr(snapshot, "process_name", "") or "").strip().casefold()
        lowered_title = title.casefold()
        if title == "Video Polling Status" and process_name in {"pythonw.exe", "python.exe"}:
            return True
        if process_name in {"windowsterminal.exe", "wt.exe"} and lowered_title.startswith("ubuntu"):
            return True
        return False

    def _ensure_visual_target_foreground(self, *, reason: str) -> bool:
        if not self._config.window.focus_before_action or not self._window_info:
            return True

        visual_surface = None
        find_visual_surface = getattr(self._window_manager, "find_visual_render_surface", None)
        if callable(find_visual_surface):
            with suppress(Exception):
                visual_surface = find_visual_surface(self._window_info)

        foreground = None
        with suppress(Exception):
            foreground = self._window_manager.get_foreground_window_snapshot()
        if foreground is not None:
            same_hwnd = foreground.hwnd == self._window_info.hwnd
            same_owner = foreground.owner_hwnd == self._window_info.hwnd
            same_visual_surface = visual_surface is not None and foreground.hwnd == visual_surface.hwnd
            looks_like_visual_surface = False
            classify_visual_surface = getattr(self._window_manager, "is_visual_render_surface", None)
            if callable(classify_visual_surface):
                with suppress(Exception):
                    looks_like_visual_surface = bool(classify_visual_surface(foreground, self._window_info))
            if same_hwnd or same_owner or same_visual_surface or looks_like_visual_surface:
                return True
            if self._is_ignored_auxiliary_foreground(foreground):
                self._logger.info(
                    "FOREGROUND_RECOVER continuing despite ignored auxiliary foreground reason=%s foreground_hwnd=%s foreground_title=%s",
                    reason,
                    getattr(foreground, "hwnd", None),
                    getattr(foreground, "title", ""),
                )

        # 关键修复：当前全屏客户端被浏览器/Codex 覆盖时，屏幕抓图看到的并不是 VSClient。
        # PREPARE_TARGET 在首轮做 GRID/UNKNOWN 判定前，必须先把目标客户端真正抬到前台。
        self._logger.info(
            "FOREGROUND_RECOVER reason=%s foreground_hwnd=%s foreground_title=%s target_hwnd=%s attached_hwnd=%s",
            reason,
            getattr(foreground, "hwnd", None),
            getattr(foreground, "title", ""),
            self._window_info.hwnd,
            getattr(visual_surface, "hwnd", None),
        )
        focus_hwnds = [self._window_info.hwnd]
        if visual_surface is not None and visual_surface.hwnd not in focus_hwnds:
            # 关键修复：真全屏画面常渲染在附属或无 owner 的 VSClient 渲染窗上。
            # 只抬宿主 hwnd 可能还会继续抓到被覆盖或未激活的旧画面，因此要连带抬起真实渲染面。
            focus_hwnds.append(visual_surface.hwnd)
        focus_succeeded = False
        for hwnd in focus_hwnds:
            focus_succeeded = self._window_manager.focus_window(hwnd) or focus_succeeded
        if not focus_succeeded:
            self._logger.warning(
                "FOREGROUND_RECOVER reason=%s failed to focus any candidate hwnds=%s",
                reason,
                focus_hwnds,
            )
            return False
        wait_seconds = max(0.05, min(0.35, self._config.timing.focus_delay_ms / 1000.0))
        if not self._wait_interruptible(wait_seconds, allow_pause=True):
            return False
        self._refresh_window_context(fast=True)
        refreshed_visual_surface = None
        if callable(find_visual_surface):
            with suppress(Exception):
                refreshed_visual_surface = find_visual_surface(self._window_info)
        refreshed_foreground = None
        with suppress(Exception):
            refreshed_foreground = self._window_manager.get_foreground_window_snapshot()
        if refreshed_foreground is not None:
            same_hwnd = refreshed_foreground.hwnd == self._window_info.hwnd
            same_owner = refreshed_foreground.owner_hwnd == self._window_info.hwnd
            same_visual_surface = (
                refreshed_visual_surface is not None and refreshed_foreground.hwnd == refreshed_visual_surface.hwnd
            )
            looks_like_visual_surface = False
            classify_visual_surface = getattr(self._window_manager, "is_visual_render_surface", None)
            if callable(classify_visual_surface):
                with suppress(Exception):
                    looks_like_visual_surface = bool(classify_visual_surface(refreshed_foreground, self._window_info))
            if same_hwnd or same_owner or same_visual_surface or looks_like_visual_surface:
                return True
        self._logger.warning(
            "FOREGROUND_RECOVER reason=%s could not confirm target foreground after focus attempt foreground_hwnd=%s target_hwnd=%s",
            reason,
            getattr(refreshed_foreground, "hwnd", None),
            self._window_info.hwnd,
        )
        return False

    def _ensure_prepare_target_grid(self) -> bool:
        try:
            if not self._ensure_visual_target_foreground(reason="prepare_target_preflight"):
                return False
            try:
                actual_view, metrics = self._classify_current_view(refresh_context=False)
            except Exception as exc:
                self._logger.warning("PREPARE_TARGET grid preflight failed to classify view: %s", exc)
                actual_view = VisualViewState.UNKNOWN
                metrics = {"error": str(exc)}

            if self._prepare_target_grid_like(actual_view, metrics, reason="prepare_target_grid_ready"):
                # 关键修复：即使当前帧已经判定为“宫格”，也必须顺手同步现场真实布局。
                # 否则 config.yaml 里残留的 12 宫格会继续驱动 4/6/9 宫格的点击坐标，
                # 全屏场景尤其容易在第一轮 PREPARE_TARGET 就直接点错格子。
                return True

            synced_preflight = self._try_sync_runtime_layout(reason="prepare_target_preflight")
            if synced_preflight:
                try:
                    actual_view, metrics = self._classify_current_view(refresh_context=False)
                except Exception as exc:
                    self._logger.warning("PREPARE_TARGET post-sync preflight failed to classify view: %s", exc)
                    actual_view = VisualViewState.UNKNOWN
                    metrics = {"error": str(exc)}
                if self._prepare_target_grid_like(actual_view, metrics, reason="prepare_target_post_sync_grid_ready"):
                    return True

            # 关键修复：如果上一次运行停在单路放大态、错误页或陌生页，
            # 新一轮 PREPARE_TARGET 不能直接继续点选，必须先主动回到宫格。
            self._logger.warning(
                "PREPARE_TARGET detected non-grid view actual=%s cell=%s metrics=%s; forcing grid recovery before action path",
                actual_view.value,
                getattr(self._active_cell, "index", None),
                metrics,
            )
            if not self._perform_grid_recovery_action(
                action_name="prepare_target_recover_grid",
                failure_target_state=SchedulerState.PREPARE_TARGET,
                recover_on_failure=False,
            ):
                self._logger.error("PREPARE_TARGET aborted because prepare-target grid recovery could not run safely")
                self._state = SchedulerState.STOPPED
                return False
            if not self._wait_interruptible(self._config.timing.recovery_wait_ms / 1000.0, allow_pause=True):
                return False
            self._refresh_window_context()
            actual_view, metrics = self._classify_current_view(refresh_context=False)
            if self._prepare_target_grid_like(
                actual_view,
                metrics,
                reason="prepare_target_post_recover_grid_ready",
            ):
                self._try_sync_runtime_layout(reason="prepare_target_post_recover_grid")
                # 关键修复：只有在“确实已经回到宫格”之后，才能刷新 grid_probe。
                # 否则单路错误页 / 黑屏页会先被写成新的基准图，再和自己比成“已回宫格”，
                # 导致 PREPARE_TARGET 在错误界面上继续乱点。
                self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
                self._logger.info(
                    "PREPARE_TARGET grid recovery restored grid view cell=%s metrics=%s",
                    getattr(self._active_cell, "index", None),
                    metrics,
                )
                return True

            synced_post_recover = self._try_sync_runtime_layout(reason="prepare_target_post_recover")
            if synced_post_recover:
                actual_view, metrics = self._classify_current_view(refresh_context=False)
                if self._prepare_target_grid_like(
                    actual_view,
                    metrics,
                    reason="prepare_target_post_recover_post_sync_grid_ready",
                ):
                    self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
                    return True

            self._logger.error(
                "PREPARE_TARGET grid recovery still did not reach grid actual=%s cell=%s metrics=%s",
                actual_view.value,
                getattr(self._active_cell, "index", None),
                metrics,
            )
            if self._config.detection.skip_on_detected_issue:
                self._skip_current_cell_for_detected_issue("prepare_not_grid", from_state=SchedulerState.PREPARE_TARGET)
            else:
                self._pause_for_detected_issue("prepare_not_grid")
            return False
        finally:
            self._prepare_target_context_reason = ""

    def _prepare_target_grid_like(
        self,
        actual_view: VisualViewState,
        metrics: dict[str, float],
        *,
        reason: str,
    ) -> bool:
        if actual_view == VisualViewState.GRID or self._detector.matches_expected_view(VisualViewState.GRID, metrics):
            self._try_sync_runtime_layout(reason=reason)
            return True
        if self._prepare_target_locked_fullscreen_grid_hint(actual_view, metrics):
            locked_layout = self._locked_fullscreen_layout_for_hint()
            self._logger.info(
                "PREPARE_TARGET accepting locked fullscreen %s-grid via layout hint cell=%s metrics=%s",
                locked_layout,
                getattr(self._active_cell, "index", None),
                metrics,
            )
            self._try_sync_runtime_layout(reason=f"{reason}:locked_fullscreen_grid_hint")
            return True
        if self._prepare_target_fullscreen_four_grid_hint(actual_view, metrics):
            self._logger.info(
                "PREPARE_TARGET accepting fullscreen 4-grid via peak hint cell=%s metrics=%s",
                getattr(self._active_cell, "index", None),
                metrics,
            )
            self._try_sync_runtime_layout(reason=f"{reason}:fullscreen_four_peak_hint")
            return True
        return False

    def _locked_fullscreen_layout_for_hint(self) -> int | None:
        fullscreen_mode_locked = any(
            mode == "fullscreen"
            for mode in (
                self._current_mode,
                self._requested_mode,
                self._effective_mode,
            )
        )
        if not fullscreen_mode_locked:
            return None
        if self._requested_mode == "fullscreen" and self._requested_layout in SUPPORTED_LAYOUTS:
            return int(self._requested_layout)
        if self._effective_mode == "fullscreen" and self._effective_layout in SUPPORTED_LAYOUTS:
            return int(self._effective_layout)
        if self._runtime_layout in SUPPORTED_LAYOUTS:
            return int(self._runtime_layout)
        return None

    def _prepare_target_locked_fullscreen_grid_hint(
        self,
        actual_view: VisualViewState,
        metrics: dict[str, float],
    ) -> bool:
        locked_layout = self._locked_fullscreen_layout_for_hint()
        if locked_layout not in DEFAULT_LAYOUT_SPECS:
            return False

        prepare_target_context_reason = str(self._prepare_target_context_reason or "")
        resume_user_pause_context = (
            locked_layout == 6
            and self._last_pause_reason == "user_pause"
            and (
                prepare_target_context_reason == "resume_hard_reset"
                or self._zoom_confirm_poll_boost_cycles_remaining > 0
            )
        )
        allow_zoomed_resume_hint = (
            actual_view == VisualViewState.ZOOMED
            and (resume_user_pause_context or locked_layout == 6)
        )
        if actual_view != VisualViewState.UNKNOWN and not allow_zoomed_resume_hint:
            return False

        expected_rows, expected_cols = DEFAULT_LAYOUT_SPECS[locked_layout]
        expected_count = max(0, expected_rows - 1) + max(0, expected_cols - 1)
        rows = int(round(float(metrics.get("grid_divider_rows_estimate", 0.0))))
        cols = int(round(float(metrics.get("grid_divider_cols_estimate", 0.0))))
        divider_expected_count = int(round(float(metrics.get("grid_divider_expected_count", 0.0))))
        if rows != expected_rows or cols != expected_cols:
            return False
        if divider_expected_count not in {0, expected_count}:
            return False

        row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))
        col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))
        row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))
        col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))
        mean_strength = float(metrics.get("grid_divider_mean_strength", 0.0))
        preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))
        structure_changed_ratio = float(metrics.get("structure_changed_ratio", 0.0))
        flat_interface_like = float(metrics.get("flat_interface_like", 0.0)) == 1.0
        preview_dominant_ratio = float(metrics.get("preview_dominant_ratio", 0.0))
        preview_entropy = float(metrics.get("preview_entropy", 999.0))
        preview_std = float(metrics.get("preview_std", 999.0))

        required_row_matches = float(max(1, (expected_rows - 1) - (1 if expected_rows >= 4 else 0)))
        required_col_matches = float(max(1, (expected_cols - 1) - (1 if expected_cols >= 4 else 0)))
        full_peak_support = row_peak_match_count >= required_row_matches and col_peak_match_count >= required_col_matches
        soft_peak_support = (
            (row_peak_match_count >= required_row_matches or row_local_peak_mean >= 10.0)
            and (col_peak_match_count >= required_col_matches or col_local_peak_mean >= 5.5)
        )

        resume_soft_peak_grid = (
            prepare_target_context_reason == "resume_hard_reset"
            and flat_interface_like
            and soft_peak_support
            and preview_dominant_ratio >= 0.94
            and preview_entropy <= 0.8
            and preview_std <= 8.5
            and preview_edge_ratio >= 0.022
            and structure_changed_ratio >= 0.045
        )
        if resume_soft_peak_grid:
            return True

        startup_soft_peak_grid = (
            prepare_target_context_reason in {"startup_warmup", "resume_hard_reset"}
            and flat_interface_like
            and soft_peak_support
            and preview_dominant_ratio >= 0.90
            and preview_entropy <= 1.15
            and preview_std <= 11.5
            and preview_edge_ratio >= 0.028
            and structure_changed_ratio >= 0.08
        )
        if startup_soft_peak_grid:
            return True

        fullscreen_six_resume_peak_grid = (
            locked_layout == 6
            and flat_interface_like
            and full_peak_support
            and mean_strength >= 4.5
            and preview_dominant_ratio >= 0.90
            and preview_entropy <= 1.2
            and preview_std <= 11.5
            and preview_edge_ratio >= 0.035
            and structure_changed_ratio >= 0.10
        )
        if fullscreen_six_resume_peak_grid:
            # 关键修复：全屏 6 宫格在暂停恢复后的失败页宫格上，虽然还是 flat surface，
            # 但 entropy/std 会比极平坦样本更高；只要 2x3 峰位、平均分隔线强度和结构变化
            # 同时落在窄窗口内，就应继续按真实宫格处理。
            return True

        fullscreen_six_resume_selected_grid = (
            locked_layout == 6
            and actual_view == VisualViewState.ZOOMED
            and not flat_interface_like
            and full_peak_support
            and mean_strength >= 4.3
            and preview_dominant_ratio >= 0.90
            and preview_entropy <= 1.2
            and preview_std <= 10.5
            and preview_edge_ratio >= 0.04
            and structure_changed_ratio >= 0.065
        )
        if fullscreen_six_resume_selected_grid:
            # 关键修复：全屏 6 宫格在人工双击回宫格、再手工点选其他窗格但尚未放大时，
            # classifier 可能短暂把当前帧打成 ZOOMED。这里不再依赖“必须处于恢复上下文”
            # 这种脆弱状态，只要 2x3 峰位和选中宫格结构成立，就直接继续宫格重同步。
            return True

        fullscreen_six_flat_soft_peak_grid = (
            locked_layout == 6
            and flat_interface_like
            and soft_peak_support
            and mean_strength >= 3.8
            and preview_dominant_ratio >= 0.93
            and preview_entropy <= 0.9
            and preview_std <= 7.0
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.075
        )
        if fullscreen_six_flat_soft_peak_grid:
            # 关键修复：全屏 6 宫格在恢复后的“多路失败页/暗色 2x3 宫格”上，UIA 经常给出
            # UNKNOWN，但横纵分隔峰位、边缘占比和结构变化已经足够稳定。这里单独给 2x3
            # 一条窄窗口，不再把真实宫格误判成 prepare_not_grid/cooldown。
            return True

        fullscreen_six_resume_weak_flat_grid = (
            locked_layout == 6
            and flat_interface_like
            and soft_peak_support
            and mean_strength >= 3.5
            and preview_dominant_ratio >= 0.93
            and preview_entropy <= 0.9
            and preview_std <= 6.0
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.03
        )
        if fullscreen_six_resume_weak_flat_grid:
            # 关键修复：全屏 6 宫格偶发会落到更弱的 2x3 暗色选中宫格，
            # 峰位仍然完整，但结构变化只剩 0.03~0.04。这里同样不再依赖恢复上下文，
            # 只按真实 2x3 结构接受，避免 PREPARE_TARGET 被隐式状态拖回冷却。
            return True

        resume_textured_soft_peak_grid = (
            prepare_target_context_reason == "resume_hard_reset"
            and self._last_pause_reason == "user_pause"
            and not flat_interface_like
            and expected_count >= 3
            and soft_peak_support
            and mean_strength >= 4.2
            and preview_edge_ratio >= 0.045
            and structure_changed_ratio >= 0.09
            and 0.88 <= preview_dominant_ratio <= 0.93
            and 1.0 <= preview_entropy <= 1.6
            and 7.0 <= preview_std <= 12.5
        )
        if resume_textured_soft_peak_grid:
            return True

        textured_multicell_soft_peak_grid = (
            not flat_interface_like
            and expected_count >= 3
            and soft_peak_support
            and mean_strength >= max(4.5, 1.5 + expected_count)
            and preview_edge_ratio >= 0.055
            and structure_changed_ratio >= 0.12
            and preview_dominant_ratio <= 0.86
            and preview_entropy >= 1.2
            and preview_std >= 15.0
        )
        if textured_multicell_soft_peak_grid:
            return True

        locked_fullscreen_peak_grid = (
            full_peak_support
            and mean_strength >= max(4.2, 2.0 + expected_count)
            and preview_edge_ratio >= 0.026
            and structure_changed_ratio >= 0.05
        )
        if locked_fullscreen_peak_grid:
            return True

        return False

    def _prepare_target_fullscreen_four_grid_hint(
        self,
        actual_view: VisualViewState,
        metrics: dict[str, float],
    ) -> bool:
        if actual_view != VisualViewState.UNKNOWN:
            return False
        if self._current_mode != "fullscreen":
            return False
        if int(self._requested_layout or 0) != 4 and int(self._runtime_layout or 0) != 4:
            return False

        rows = int(round(float(metrics.get("grid_divider_rows_estimate", 0.0))))
        cols = int(round(float(metrics.get("grid_divider_cols_estimate", 0.0))))
        expected_count = int(round(float(metrics.get("grid_divider_expected_count", 0.0))))
        row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))
        col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))
        row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))
        col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))
        preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))
        structure_changed_ratio = float(metrics.get("structure_changed_ratio", 0.0))
        flat_interface_like = float(metrics.get("flat_interface_like", 0.0)) == 1.0
        preview_dominant_ratio = float(metrics.get("preview_dominant_ratio", 0.0))
        preview_entropy = float(metrics.get("preview_entropy", 999.0))
        preview_std = float(metrics.get("preview_std", 999.0))
        prepare_target_context_reason = str(self._prepare_target_context_reason or "")

        if rows != 2 or cols != 2 or expected_count != 2:
            return False
        if row_peak_match_count < 1.0 or col_peak_match_count < 1.0:
            ultra_flat_prepare_grid = (
                prepare_target_context_reason in {"startup_warmup", "resume_hard_reset"}
                and flat_interface_like
                and preview_dominant_ratio >= 0.96
                and preview_entropy <= 0.55
                and preview_std <= 8.0
                and preview_edge_ratio >= 0.012
                and structure_changed_ratio >= 0.025
            )
            if prepare_target_context_reason == "resume_hard_reset" and self._last_pause_reason != "user_pause":
                ultra_flat_prepare_grid = False
            return ultra_flat_prepare_grid

        resume_pause_soft_peak_grid = (
            prepare_target_context_reason == "resume_hard_reset"
            and self._last_pause_reason == "user_pause"
            and flat_interface_like
            and row_peak_match_count >= 1.0
            and col_peak_match_count >= 1.0
            and row_local_peak_mean >= 12.0
            and col_local_peak_mean >= 6.0
            and preview_dominant_ratio >= 0.947
            and preview_entropy <= 0.7
            and preview_std <= 6.5
            and preview_edge_ratio >= 0.024
            and structure_changed_ratio >= 0.05
        )
        if resume_pause_soft_peak_grid:
            return True

        strong_peak_grid = (
            row_local_peak_mean >= 120.0
            and col_local_peak_mean >= 120.0
            and preview_edge_ratio >= 0.04
            and structure_changed_ratio >= 0.08
        )
        if strong_peak_grid:
            return True

        # 关键修复：真全屏 4 宫格的“全黑/全平失败页”在现场机上经常既没有 hit_count，
        # 也没有很高的平均分隔线强度，但 2x2 的横竖峰值仍会稳定落在预期位置附近。
        # 这里只在固定 fullscreen 4 程序的 PREPARE_TARGET 阶段放开一条极窄兜底，
        # 避免把真实宫格误停在 prepare_not_grid，同时不改变其他阶段的 UNKNOWN 语义。
        weak_flat_grid = (
            flat_interface_like
            and row_local_peak_mean >= 12.0
            and col_local_peak_mean >= 6.0
            and preview_edge_ratio >= 0.02
            and structure_changed_ratio >= 0.08
            and preview_dominant_ratio >= 0.94
            and preview_entropy <= 0.9
        )
        if weak_flat_grid:
            return True

        startup_soft_peak_grid = (
            flat_interface_like
            and row_local_peak_mean >= 15.0
            and col_local_peak_mean >= 6.4
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.10
            and preview_dominant_ratio >= 0.925
            and preview_entropy <= 0.85
            and preview_std <= 11.0
        )
        if startup_soft_peak_grid:
            # 参考非全屏 4 宫格已通过的稳定配置：首轮只要 2x2 峰位、边缘和结构
            # 已经同时落在窄窗口内，就不应在 PREPARE_TARGET 把真实全屏 4 宫格误停。
            # 这里直接覆盖现场反复出现的 0.93x dominant / 15.6 / 6.45 峰值样本。
            return True
        return False

    def _acknowledge_pause(self) -> None:
        self._pause_acknowledged = True
        actual_view = VisualViewState.UNKNOWN
        if self._preview_rect is not None and self._active_cell is not None:
            try:
                actual_view, _metrics = self._classify_current_view(refresh_context=False)
            except Exception as exc:
                self._logger.warning("PAUSE_ACK actual_view=UNKNOWN error=%s", exc)
        self._pause_ack_view = actual_view
        self._paused_index = self._current_index
        self._paused_stage = self._pause_barrier_state or self._state.value
        self._logger.info(
            "PAUSE_ACK state=%s cell=%s actual_view=%s",
            self._state,
            getattr(self._active_cell, "index", None),
            actual_view.value,
        )
        if self._pending_pause_ack_next_requests > 0:
            pending_count = self._pending_pause_ack_next_requests
            self._pending_pause_ack_next_requests = 0
            self._logger.info(
                "PAUSE_ACK draining buffered NEXT requests count=%s cell=%s",
                pending_count,
                getattr(self._active_cell, "index", None),
            )
            for _ in range(pending_count):
                self._queue_manual_next_request()

    def _run_runtime_guard(
        self,
        *,
        stage: str,
        expected_view: VisualViewState | None,
        inspect_view: bool,
    ) -> bool:
        if self._runtime_guard is None or not self._config.runtime_guard.enabled:
            return True

        preview_rect = self._preview_rect if inspect_view else None
        active_rect = getattr(self._active_cell, "rect", None) if inspect_view and self._active_cell else None
        event = self._runtime_guard.check(
            stage=stage,
            target_window=self._window_info,
            preview_rect=preview_rect,
            active_cell_rect=active_rect,
            expected_view=expected_view,
            grid_probe=self._last_grid_probe,
            zoom_probe=self._last_zoom_probe,
        )
        if event.ok:
            return True

        self._guard_failure_streak += 1
        self._logger.warning(
            "RUNTIME_GUARD stage=%s issue=%s reason=%s streak=%s details=%s",
            stage,
            event.issue,
            event.reason,
            self._guard_failure_streak,
            event.details,
        )
        snapshot_path = self._runtime_guard.save_guard_snapshot(
            tag=f"{stage}_{event.issue}",
            detector=self._detector,
            rect=self._preview_rect,
        )
        if snapshot_path:
            self._logger.warning("RUNTIME_GUARD snapshot=%s", snapshot_path)

        healed = self._runtime_guard.try_auto_heal(event=event, target_window=self._window_info)
        if healed and self._guard_failure_streak < self._config.runtime_guard.consecutive_fail_limit:
            # 关键修复：短暂自动修复只记日志，不再把“错误界面”提示频繁刷到桌面上。
            self._logger.warning(
                "RUNTIME_GUARD healed issue=%s; scheduler will restart current path", event.issue
            )
            self._refresh_window_context()
            self._clear_cycle_context(preserve_zoom_state=False, reason=f"runtime_guard:{event.issue}")
            self._is_zoomed = False
            self._next_transition_reason = f"runtime_guard:{event.issue}"
            self._path_retry_count = 0
            self._state = SchedulerState.PREPARE_TARGET
            return False

        if self._config.detection.skip_on_detected_issue:
            self._logger.warning(
                "RUNTIME_GUARD could not safely heal issue=%s; skip_on_detected_issue=%s, restarting current path without auto-pause",
                event.issue,
                self._config.detection.skip_on_detected_issue,
            )
            self._publish_status(
                message=f"检测异常，继续自动恢复：{event.issue}",
                details=f"skip_on_detected_issue 已启用；程序不会自动暂停，会继续重走当前路径。",
                level="warning",
            )
            self._guard_failure_streak = 0
            self._refresh_window_context()
            self._clear_cycle_context(preserve_zoom_state=False, reason=f"runtime_guard_skip:{event.issue}")
            self._is_zoomed = False
            self._next_transition_reason = f"runtime_guard_skip:{event.issue}"
            self._path_retry_count = 0
            self._state = SchedulerState.PREPARE_TARGET
            return False

        self._logger.error(
            "RUNTIME_GUARD could not safely heal issue=%s; switching to PAUSED for manual confirmation",
            event.issue,
        )
        self._publish_status(
            message=f"检测到持续错误界面/窗口，已自动暂停：{event.issue}",
            details=f"请先确认客户端已回到正确宫格，再按 {self._config.hotkeys.start_pause} 继续；必要时按 {self._config.hotkeys.emergency_recover} 恢复。",
            level="warning",
        )
        self._user_paused = True
        self._last_pause_reason = "runtime_guard"
        self._resume_requires_recovery = True
        self._latch_pause_barrier("runtime_guard")
        self._state = SchedulerState.PAUSED
        self._acknowledge_pause()
        return False

    def _guard_stage_view(self, stage: str, expected: VisualViewState, *, refresh_context: bool) -> bool:
        if self._runtime_guard is not None and self._config.runtime_guard.enabled:
            # 关键修复：runtime_guard 已经完成一次“前台/弹窗/界面视图”联合校验，
            # 这里不能再重复做一遍同样的重分类，否则每个阶段都会额外多吃一次整屏检测耗时。
            return self._run_runtime_guard(stage=stage, expected_view=expected, inspect_view=True)
        try:
            actual, metrics = self._classify_current_view(refresh_context=refresh_context)
        except Exception as exc:
            actual = VisualViewState.UNKNOWN
            metrics = {"error": str(exc)}
        if actual == expected:
            return True
        if self._detector.matches_expected_view(expected, metrics):
            self._logger.info(
                "PATH_ACCEPT expected=%s actual=%s stage=%s cell=%s metrics=%s",
                expected.value,
                actual.value,
                stage,
                getattr(self._active_cell, "index", None),
                metrics,
            )
            return True

        self._logger.warning(
            "PATH_MISMATCH expected=%s actual=%s stage=%s cell=%s metrics=%s",
            expected.value,
            actual.value,
            stage,
            getattr(self._active_cell, "index", None),
            metrics,
        )
        self._publish_status(
            message="State mismatch detected; auto-healing",
            details=self._hotkey_summary(prefix=f"stage={stage} | expected={expected.value} | actual={actual.value}"),
            level="warning",
        )
        self._auto_heal_path_mismatch(stage=stage, actual=actual)
        return False

    def _auto_heal_path_mismatch(self, *, stage: str, actual: VisualViewState) -> None:
        if not self._perform_grid_recovery_action(
            action_name=f"path_mismatch_recover:{stage}",
            failure_target_state=SchedulerState.PREPARE_TARGET,
            recover_on_failure=False,
        ):
            self._logger.error(
                "PATH_RECOVERY aborted because the target window could not be focused safely stage=%s cell=%s",
                stage,
                getattr(self._active_cell, "index", None),
            )
            self._state = SchedulerState.STOPPED
            return
        self._wait_interruptible(self._config.timing.recovery_wait_ms / 1000.0, allow_pause=True)
        if self._state == SchedulerState.PAUSED or self._stop_requested:
            return

        self._clear_cycle_context(preserve_zoom_state=False, reason="path_mismatch")

        # 只有在“当前动作基本完成”的阶段，才允许恢复后直接进入下一路。
        if stage in {"GRID_CONFIRM", "GRID_DWELL", "NEXT"}:
            previous_index = self._current_index
            next_index = self._next_cell_index(previous_index)
            if next_index is not None and self._cells:
                self._current_index = next_index
                self._active_cell = self._cells[self._current_index]
            self._logger.warning(
                "PATH_RECOVERY advancing to next cell after stage=%s mismatch because the current cell already completed the action path (from order_index=%s %s to order_index=%s %s)",
                stage,
                previous_index,
                self._cell_hint(self._cells[previous_index] if 0 <= previous_index < len(self._cells) else None),
                self._current_index,
                self._cell_hint(self._active_cell),
            )
            self._next_transition_reason = f"path_mismatch:{stage}"
            self._path_retry_count = 0
            self._state = SchedulerState.PREPARE_TARGET
            return

        if self._path_retry_count < self._config.detection.path_retry_limit:
            self._path_retry_count += 1
            self._logger.warning(
                "PATH_RECOVERY retrying current cell=%s after stage=%s actual=%s attempt=%s",
                getattr(self._active_cell, "index", None),
                stage,
                actual.value,
                self._path_retry_count,
            )
            self._state = SchedulerState.PREPARE_TARGET
            return

        # 关键修复：达到重试上限后仍优先重走当前路径，而不是立刻跳下一路。
        if self._register_issue_failure("path_mismatch"):
            return
        self._logger.warning(
            "PATH_RECOVERY restarting current cell=%s after repeated stage=%s mismatches; future cycles may enter cooldown if failures continue",
            getattr(self._active_cell, "index", None),
            stage,
        )
        self._next_transition_reason = f"path_restart:{stage}"
        self._path_retry_count = 0
        self._state = SchedulerState.PREPARE_TARGET

    def _refresh_window_context(self, *, fast: bool = False) -> None:
        previous_mode = self._current_mode
        if fast and self._window_info is not None:
            self._window_info = self._window_manager.refresh_target_window(self._window_info)
        else:
            self._window_info = self._window_manager.find_target_window()
        if self._use_locked_runtime_profile_fast_path():
            self._current_mode = str(self._requested_mode)
            self._runtime_layout = int(self._requested_layout)
        elif fast and self._requested_mode == "auto" and self._current_mode in {"windowed", "fullscreen"}:
            # 关键修复：阶段内视图校验优先沿用上一跳已确认模式，避免每一步都重新跑昂贵的 auto 模式识别。
            self._current_mode = self._current_mode
        else:
            self._current_mode = self._window_manager.detect_mode(self._window_info, "auto")
        if self._current_mode != previous_mode:
            if self._current_mode == "windowed":
                self._mark_windowed_runtime_layout_sync_needed("mode_changed_to_windowed")
            else:
                self._windowed_runtime_layout_sync_needed = False
            invalidate_marker_cache = getattr(self._window_manager, "invalidate_windowed_marker_cache", None)
            if callable(invalidate_marker_cache):
                with suppress(Exception):
                    invalidate_marker_cache(reason=f"mode_changed:{previous_mode}->{self._current_mode}")
        profile = getattr(self._config.profiles, self._current_mode)
        self._preview_rect = self._exclude_overlay_safe_strip(profile.to_rect(self._window_info.client_rect))

        runtime_label_order: list[str] = []
        self._runtime_favorite_labels = []
        if self._runtime_grid_order == "favorites_name" and self._favorites_reader is not None:
            try:
                runtime_label_order = self._favorites_reader.read_visible_names(self._window_info)
                if runtime_label_order:
                    self._logger.info("FAVORITES_ORDER count=%s names=%s", len(runtime_label_order), runtime_label_order)
            except Exception as exc:
                self._logger.warning("FAVORITES_ORDER read failed: %s", exc)
                runtime_label_order = []
            self._runtime_favorite_labels = list(runtime_label_order)

        self._cells = self._grid_mapper.build_cells(
            self._preview_rect,
            self._runtime_layout,
            runtime_label_order=runtime_label_order,
            order_override=self._runtime_grid_order,
        )
        if not self._cells:
            raise RuntimeError("No grid cells were generated from the calibration profile")
        self._current_index %= len(self._cells)
        self._active_cell = self._cells[self._current_index]
        self._sync_runtime_profile_state()

    def _candidate_runtime_layouts(self) -> list[int]:
        candidates: list[int] = []
        seen: set[int] = set()
        ordered_candidates = [
            int(self._requested_layout) if self._requested_layout is not None else None,
            int(self._runtime_layout),
            int(self._config.grid.layout),
            *(int(layout) for layout in self._config.grid.layout_overrides),
            *(int(layout) for layout in sorted(SUPPORTED_LAYOUTS)),
        ]
        for layout in ordered_candidates:
            if layout is None or layout <= 1 or layout in seen:
                continue
            seen.add(layout)
            candidates.append(layout)
        return candidates

    def _windowed_layout_signal_summary(
        self,
        candidate: dict[str, object],
        *,
        best_score: float,
        second_score: float | None,
    ) -> dict[str, float]:
        layout = int(candidate["layout"])
        metrics = dict(candidate["metrics"])
        expected_rows, expected_cols = DEFAULT_LAYOUT_SPECS.get(layout, (0, 0))
        estimated_rows = int(round(float(metrics.get("grid_divider_rows_estimate", 0.0))))
        estimated_cols = int(round(float(metrics.get("grid_divider_cols_estimate", 0.0))))
        expected_hits = max(1.0, float(metrics.get("grid_divider_expected_count", 0.0)))
        divider_hits = float(metrics.get("grid_divider_hit_count", 0.0))
        peak_matches = float(metrics.get("grid_divider_row_peak_match_count", 0.0)) + float(
            metrics.get("grid_divider_col_peak_match_count", 0.0)
        )
        geometry_confirmed = (
            estimated_rows == expected_rows and estimated_cols == expected_cols
        ) or (expected_rows > 0 and expected_cols > 0 and estimated_rows * estimated_cols == (expected_rows * expected_cols))
        structure_confirmed = (
            float(metrics.get("repeated_grid_like", 0.0)) == 1.0
            or divider_hits >= max(2.0, expected_hits * 0.6)
            or peak_matches >= max(2.0, expected_hits - 1.0)
        )
        score_margin_confirmed = second_score is None or best_score >= (second_score + 9.0)
        signal_count = sum(
            (
                1 if candidate.get("grid_like") else 0,
                1 if structure_confirmed else 0,
                1 if geometry_confirmed else 0,
                1 if score_margin_confirmed else 0,
            )
        )
        return {
            "windowed_layout_visual_confirmed": 1.0 if candidate.get("grid_like") else 0.0,
            "windowed_layout_structure_confirmed": 1.0 if structure_confirmed else 0.0,
            "windowed_layout_geometry_confirmed": 1.0 if geometry_confirmed else 0.0,
            "windowed_layout_score_margin_confirmed": 1.0 if score_margin_confirmed else 0.0,
            "windowed_layout_signal_count": float(signal_count),
            "windowed_layout_second_score": -1.0 if second_score is None else float(second_score),
        }

    def _resolve_windowed_runtime_layout_candidate(
        self,
        candidates: list[dict[str, object]],
        *,
        current_layout: int,
        current_layout_trusted: bool,
        current_layout_score: float | None,
    ) -> tuple[int | None, dict[str, float] | None, str | None]:
        grid_candidates = [candidate for candidate in candidates if candidate.get("grid_like")]
        if not grid_candidates:
            return None, None, None

        score_ranked_candidates = sorted(grid_candidates, key=lambda candidate: float(candidate.get("score") or 0.0), reverse=True)
        summarized_candidates: list[dict[str, object]] = []
        for candidate in score_ranked_candidates:
            candidate_score = float(candidate.get("score") or 0.0)
            competing_scores = [
                float(other.get("score") or 0.0)
                for other in score_ranked_candidates
                if int(other["layout"]) != int(candidate["layout"])
            ]
            summary_metrics = dict(candidate["metrics"])
            summary_metrics.update(
                self._windowed_layout_signal_summary(
                    candidate,
                    best_score=candidate_score,
                    second_score=max(competing_scores) if competing_scores else None,
                )
            )
            summarized_candidates.append(
                {
                    "candidate": candidate,
                    "score": candidate_score,
                    "metrics": summary_metrics,
                    "signal_count": int(summary_metrics.get("windowed_layout_signal_count", 0.0)),
                }
            )

        ranked_candidates = sorted(
            summarized_candidates,
            key=lambda item: (int(item["signal_count"]), float(item["score"])),
            reverse=True,
        )
        best_entry = ranked_candidates[0]
        best_candidate = dict(best_entry["candidate"])
        best_score = float(best_entry["score"])
        second_score = float(ranked_candidates[1]["score"]) if len(ranked_candidates) > 1 else None
        best_metrics = dict(best_entry["metrics"])
        best_layout = int(best_candidate["layout"])
        best_signal_count = int(best_metrics.get("windowed_layout_signal_count", 0.0))
        if best_signal_count < 3:
            return None, best_metrics, "windowed_multisignal_low_confidence"

        best_structure_confirmed = bool(best_metrics.get("windowed_layout_structure_confirmed", 0.0))
        if (
            current_layout_trusted
            and best_layout < current_layout
            and current_layout >= 9
            and best_layout <= 4
            and not best_structure_confirmed
        ):
            # 关键修复：Windowed 12/9 在低纹理或大面积黑屏时，4 宫格候选可能只靠
            # “视觉像 GRID + 2x2 几何 + 分数领先”凑到 3 票，但这不足以证明现场
            # 真的已经从稠密宫格切成了 4 宫格。对这种“稠密 -> 稀疏”的降级，
            # 没有真实结构信号时先保持当前宫格，避免把真实 12/9 误翻成 4。
            return None, best_metrics, "windowed_dense_downshift_low_structure"

        if best_layout != current_layout and current_layout_trusted and current_layout_score is not None:
            current_candidate = next(
                (item for item in ranked_candidates if int(dict(item["candidate"])["layout"]) == current_layout),
                None,
            )
            if current_candidate is not None:
                current_metrics = dict(current_candidate["metrics"])
                current_signal_count = int(current_metrics.get("windowed_layout_signal_count", 0.0))
                if current_signal_count >= 3 and best_score <= (current_layout_score + 14.0):
                    return current_layout, current_metrics, "windowed_visual_keep_current"

        return best_layout, best_metrics, "windowed_multisignal_confirm"

    def _apply_runtime_layout(self, layout: int, *, reason: str, metrics: dict[str, float] | None = None) -> bool:
        if not self._preview_rect:
            return False

        runtime_label_order = self._runtime_favorite_labels if self._runtime_grid_order == "favorites_name" else []
        resolved_cells = self._grid_mapper.build_cells(
            self._preview_rect,
            layout,
            runtime_label_order=runtime_label_order,
            order_override=self._runtime_grid_order,
        )
        if not resolved_cells:
            return False

        previous_layout = self._runtime_layout
        self._runtime_layout = int(layout)
        if ":uia_detect" in reason:
            self._runtime_layout_uia_confirmed_layout = self._runtime_layout
            self._runtime_layout_uia_confirmed_at = time.monotonic()
        elif self._runtime_layout_uia_confirmed_layout != self._runtime_layout:
            self._runtime_layout_uia_confirmed_layout = None
            self._runtime_layout_uia_confirmed_at = 0.0
        if self._current_mode == "windowed":
            self._windowed_runtime_layout_sync_needed = False
        self._runtime_layout_recent_sync_at = time.monotonic()
        self._cells = resolved_cells
        self._current_index %= len(self._cells)
        self._active_cell = self._cells[self._current_index]
        self._sync_runtime_profile_state()
        self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}")
        self._logger.warning(
            "RUNTIME_LAYOUT sync reason=%s from=%s to=%s cell=%s metrics=%s",
            reason,
            previous_layout,
            self._runtime_layout,
            getattr(self._active_cell, "index", None),
            metrics or {},
        )
        if self._current_mode == "windowed" and any(
            marker in reason for marker in (":uia_detect", ":windowed_multisignal_confirm", ":windowed_visual_keep_current")
        ):
            self._save_windowed_runtime_layout_cache(layout=self._runtime_layout, source=reason)
        return True

    def _runtime_layout_low_texture_hint(self, metrics: dict[str, float], *, rows: int, cols: int) -> bool:
        return (
            float(metrics.get("flat_interface_like", 0.0)) == 1.0
            and int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == rows
            and int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == cols
            and int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == ((rows - 1) + (cols - 1))
            and float(metrics.get("grid_divider_mean_strength", 0.0)) >= 4.6
            and float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03
            and float(metrics.get("structure_changed_ratio", 0.0)) >= 0.075
        )

    def _runtime_layout_fullscreen_peak_hint(self, layout: int, metrics: dict[str, float]) -> bool:
        if self._current_mode != "fullscreen":
            return False

        rows = int(round(float(metrics.get("grid_divider_rows_estimate", 0.0))))
        cols = int(round(float(metrics.get("grid_divider_cols_estimate", 0.0))))
        expected_count = int(round(float(metrics.get("grid_divider_expected_count", 0.0))))
        row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))
        col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))
        row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))
        col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))
        preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))
        structure_changed_ratio = float(metrics.get("structure_changed_ratio", 0.0))

        if (
            layout == 9
            and rows == 3
            and cols == 3
            and expected_count == 4
            and row_peak_match_count >= 2.0
            and col_peak_match_count >= 2.0
            and row_local_peak_mean >= 60.0
            and col_local_peak_mean >= 60.0
            and preview_edge_ratio >= 0.045
            and structure_changed_ratio >= 0.11
        ):
            # 关键修复：真全屏 9 宫格在弱纹理现场里，横竖分隔峰值经常已经非常稳定，
            # 但 active probe 对比仍然不够强，detector 会保守给 UNKNOWN。
            # 当前宫格同步阶段不能继续只看通用 structure 门槛，否则 9 会被错误留在 12。
            return True

        if (
            layout == 12
            and rows == 4
            and cols == 3
            and expected_count == 5
            and row_peak_match_count >= 3.0
            and col_peak_match_count >= 2.0
            and row_local_peak_mean >= 40.0
            and col_local_peak_mean >= 40.0
            and preview_edge_ratio >= 0.045
            and structure_changed_ratio >= 0.12
        ):
            # 关键修复：真全屏 12 宫格的横向分隔线更细，很多时候也会先掉到 UNKNOWN。
            # 这里和 9 宫格一样，只在 runtime-layout 同步阶段用峰值结构兜底。
            return True

        return False

    def _runtime_layout_score(self, metrics: dict[str, float]) -> float:
        hit_count = float(metrics.get("grid_divider_hit_count", 0.0))
        expected_count = max(1.0, float(metrics.get("grid_divider_expected_count", 0.0)))
        hit_ratio = hit_count / expected_count
        mean_strength = float(metrics.get("grid_divider_mean_strength", 0.0))
        preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))
        repeated_grid_like = float(metrics.get("repeated_grid_like", 0.0)) == 1.0
        row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))
        col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))
        row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))
        col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))
        divider_support = mean_strength
        peak_support = 0.0
        repeated_grid_bonus = 0.0
        if float(metrics.get("flat_interface_like", 0.0)) == 1.0 and hit_count == 0.0:
            # 关键修复：Fullscreen 6 黑页里，2x2 候选也可能因为单条横线/蓝色边框
            # 被 detector 的低纹理兜底临时认成 GRID。这里不能再给 repeated_grid_like
            # 超大权重，否则 4 宫格假阳性会稳定压过真实 6 宫格。
            # 对“低纹理且 hit_count=0”的场景，改用总分隔线支撑强度来打分，
            # 让 2x3 这类真实存在更多分割线的布局有机会胜出。
            divider_support = mean_strength * expected_count
        elif (
            self._current_mode == "fullscreen"
            and hit_count == 0.0
            and expected_count >= 3.0
            and mean_strength >= 5.0
            and float(metrics.get("preview_edge_ratio", 0.0)) >= 0.06
                and float(metrics.get("structure_changed_ratio", 0.0)) >= 0.12
            ):
                # 关键修复：真全屏 12 宫格这类“分隔线整体可见、但每条都不够强到 hit”的场景里，
                # 4 宫格候选常常因为 expected_count 更小而被轻罚，从而错误压过真实 12 宫格。
                # 这里只在 fullscreen + zero-hit + 分隔线整体仍可见时，给 6/9/12 这类
                # “本来就有更多真实分隔线”的候选补一层总支撑权重，避免 12 被错误翻成 4。
                divider_support = mean_strength * expected_count
        if (
            self._current_mode == "fullscreen"
            and expected_count >= 5.0
            and row_peak_match_count >= 3.0
            and col_peak_match_count >= 2.0
            and row_local_peak_mean >= 40.0
            and col_local_peak_mean >= 40.0
            and preview_edge_ratio >= 0.045
        ):
            # 关键修复：真全屏 12 宫格里，横向分隔线经常是“很细、很短的局部强线”，
            # 用整条 band 的平均强度会被稀释到接近 0，导致 12 长期被 9/6 误压。
            # 当 1/4、1/2、3/4 三个预期横线附近都能稳定找到局部峰值，且两条竖线也存在时，
            # 这是 12 宫格独有的强信号，应该给它一层 fullscreen-only 的补偿权重。
            peak_support = row_local_peak_mean
        if repeated_grid_like and expected_count <= 3.0:
            # 关键修复：真全屏 6 宫格这类稀疏布局里，detector 一旦已经能稳定认出 GRID，
            # 这个信号要比“更稠密候选在低纹理里勉强拼出来的结构分”更可信。
            # 这里只给 2x2/2x3 这类稀疏布局一层小幅加分，避免 12 宫格的假阳性把真实 6 再压回去。
            repeated_grid_bonus = 12.0
        return (
            # 关键修复：Fullscreen 6 宫格在弱纹理现场里，4/9/12 这些错误候选
            # 也可能勉强看见少量分隔线。如果只看原始 hit_count，
            # 分隔线更多的稠密布局会被错误加分。这里改成优先看命中比例，
            # 并对“预期分隔线本来就更多”的候选加一个轻微惩罚。
            + hit_ratio * 120.0
            + hit_count * 10.0
            + divider_support * 1.8
            + peak_support
            + repeated_grid_bonus
            + float(metrics.get("structure_changed_ratio", 0.0)) * 45.0
            - expected_count * 2.5
        )

    def _runtime_layout_divider_support(self, metrics: dict[str, float]) -> float:
        return float(metrics.get("grid_divider_mean_strength", 0.0)) * max(
            1.0,
            float(metrics.get("grid_divider_expected_count", 0.0)),
        )

    def _runtime_layout_has_strong_fullscreen_signal(self, layout: int, metrics: dict[str, float]) -> bool:
        if self._current_mode != "fullscreen":
            return False
        hit_count = float(metrics.get("grid_divider_hit_count", 0.0))
        if layout == 9:
            return hit_count >= 2.0 or self._runtime_layout_fullscreen_peak_hint(9, metrics)
        if layout == 12:
            return hit_count >= 2.0 or self._runtime_layout_fullscreen_peak_hint(12, metrics)
        if layout == 6:
            return hit_count >= 2.0 or self._runtime_layout_low_texture_hint(metrics, rows=2, cols=3)
        return hit_count >= 1.0

    def _runtime_layout_expected_geometry(self, layout: int) -> tuple[int, int] | None:
        return {
            4: (2, 2),
            6: (2, 3),
            9: (3, 3),
            12: (4, 3),
        }.get(int(layout))

    def _runtime_layout_geometry_matches(self, layout: int, metrics: dict[str, float]) -> bool:
        expected_geometry = self._runtime_layout_expected_geometry(layout)
        if expected_geometry is None:
            return False
        expected_rows, expected_cols = expected_geometry
        estimated_rows = int(round(float(metrics.get("grid_divider_rows_estimate", 0.0))))
        estimated_cols = int(round(float(metrics.get("grid_divider_cols_estimate", 0.0))))
        return estimated_rows == expected_rows and estimated_cols == expected_cols

    def _should_hold_fullscreen_dense_layout(
        self,
        *,
        current_layout: int,
        proposed_layout: int,
        current_metrics: dict[str, float],
        proposed_metrics: dict[str, float],
    ) -> bool:
        if self._current_mode != "fullscreen" or current_layout < 9 or proposed_layout >= current_layout:
            return False
        if not self._runtime_layout_geometry_matches(current_layout, current_metrics):
            return False

        current_support = self._runtime_layout_divider_support(current_metrics)
        proposed_support = self._runtime_layout_divider_support(proposed_metrics)
        current_hits = float(current_metrics.get("grid_divider_hit_count", 0.0))
        proposed_hits = float(proposed_metrics.get("grid_divider_hit_count", 0.0))
        current_peaks = float(current_metrics.get("grid_divider_row_peak_match_count", 0.0)) + float(
            current_metrics.get("grid_divider_col_peak_match_count", 0.0)
        )
        proposed_peaks = float(proposed_metrics.get("grid_divider_row_peak_match_count", 0.0)) + float(
            proposed_metrics.get("grid_divider_col_peak_match_count", 0.0)
        )
        current_edge_ratio = float(current_metrics.get("preview_edge_ratio", 0.0))
        proposed_edge_ratio = float(proposed_metrics.get("preview_edge_ratio", 0.0))
        current_structure_ratio = float(current_metrics.get("structure_changed_ratio", 0.0))
        proposed_structure_ratio = float(proposed_metrics.get("structure_changed_ratio", 0.0))
        proposed_has_strong_nine_evidence = (
            proposed_layout == 9 and self._runtime_layout_has_strong_fullscreen_signal(9, proposed_metrics)
        )

        if (
            current_layout == 12
            and proposed_layout == 9
            and current_edge_ratio >= 0.08
            and current_structure_ratio >= max(0.35, proposed_structure_ratio * 0.9)
            and (current_peaks + 1.0) >= proposed_peaks
            and not proposed_has_strong_nine_evidence
        ):
            return True

        # 关键修复：真全屏 12 宫格在高纹理现场里，3x3 候选可能因为 expected_count 更少、
        # 结构平均分更集中而短暂赢过 12 宫格，但 12 候选本身仍保留了 4x3 几何和不弱的分隔支撑。
        # 对这种“稠密布局 -> 更稀疏布局”的降级，如果当前布局仍有足够几何/结构信号，而新候选
        # 并没有明显压倒性的真实优势，就先保持当前布局，避免把真实全屏 12 错翻成 9。
        proposed_clearly_dominant = (
            proposed_hits >= max(2.0, current_hits + 1.0)
            or proposed_peaks >= max(3.0, current_peaks + 2.0)
            or proposed_support >= max(current_support * 1.25, 40.0)
        )
        current_layout_still_supported = (
            current_support >= max(proposed_support * 0.88, 24.0)
            and current_edge_ratio >= max(0.05, proposed_edge_ratio * 0.9)
            and current_structure_ratio >= max(0.12, proposed_structure_ratio * 0.85)
            and current_peaks >= proposed_peaks
        )
        return current_layout_still_supported and not proposed_clearly_dominant

    @staticmethod
    def _fullscreen_layout_reconcile_prefers_observed_state(reason: str) -> bool:
        normalized = str(reason or "")
        return normalized.startswith(
            (
                "manual_profile_lock",
                "resume_reconcile",
                "resume_post_recover",
                "runtime_target_update",
                "inspect_runtime",
            )
        )

    def _best_runtime_layout_candidate(self, candidates: list[dict[str, object]]) -> dict[str, object] | None:
        grid_like_candidates = [candidate for candidate in candidates if candidate.get("grid_like")]
        if not grid_like_candidates:
            return None
        return max(grid_like_candidates, key=lambda candidate: float(candidate.get("score") or 0.0))

    def _collect_runtime_layout_candidates(self) -> list[dict[str, object]]:
        if not self._preview_rect:
            return []

        runtime_label_order = self._runtime_favorite_labels if self._runtime_grid_order == "favorites_name" else []
        current_layout = int(self._runtime_layout)
        candidates: list[dict[str, object]] = []

        for layout in self._candidate_runtime_layouts():
            candidate_cells = self._grid_mapper.build_cells(
                self._preview_rect,
                layout,
                runtime_label_order=runtime_label_order,
                order_override=self._runtime_grid_order,
            )
            if not candidate_cells:
                continue

            candidate_index = self._current_index % len(candidate_cells)
            candidate_cell = candidate_cells[candidate_index]
            actual_view, metrics = self._detector.classify_runtime_view(
                self._preview_rect,
                candidate_cell.rect,
                grid_probe=self._last_grid_probe,
                zoom_probe=self._last_zoom_probe,
            )
            candidate_grid_like = actual_view == VisualViewState.GRID or self._detector.matches_expected_view(
                VisualViewState.GRID,
                metrics,
            )
            peak_grid_hint_used = False
            low_texture_hint_used = False
            if not candidate_grid_like and self._runtime_layout_fullscreen_peak_hint(int(layout), metrics):
                # 关键修复：当前宫格同步需要一套比动作阶段更贴近“几宫格结构”的口径，
                # 否则全屏 9/12 会因为通用 structure 阈值过严，被长期卡在旧布局。
                candidate_grid_like = True
                peak_grid_hint_used = True
            if not candidate_grid_like and self._runtime_layout_low_texture_hint(metrics, rows=2, cols=3):
                # 关键修复：真全屏 6 宫格的低纹理失败页上，detector 会保守地先给 UNKNOWN，
                # 但 2x3 分隔线结构已经足够说明“它更像 6 宫格，而不是被 4 宫格 flat fallback 误认出来的假阳性”。
                # 这里只在 runtime-layout 同步阶段放开这条窄口，不改变其他动作阶段的 UNKNOWN 语义。
                candidate_grid_like = True
                low_texture_hint_used = True

            score = None
            if candidate_grid_like:
                score = round(self._runtime_layout_score(metrics), 4)

            candidates.append(
                {
                    "layout": int(layout),
                    "is_current_layout": int(layout) == current_layout,
                    "candidate_index": candidate_index,
                    "actual_view": actual_view.value,
                    "grid_like": candidate_grid_like,
                    "peak_grid_hint_used": peak_grid_hint_used,
                    "low_texture_hint_used": low_texture_hint_used,
                    "score": score,
                    "metrics": dict(metrics),
                }
            )

        return candidates

    def _confirm_fullscreen_layout_change(
        self,
        *,
        reason: str,
        current_layout: int,
        proposed_layout: int,
        initial_candidates: list[dict[str, object]],
    ) -> tuple[bool, dict[str, float] | None]:
        if self._current_mode != "fullscreen" or proposed_layout == current_layout:
            return True, None

        initial_best = self._best_runtime_layout_candidate(initial_candidates)
        if initial_best is None:
            return False, None

        proposed_support = self._runtime_layout_divider_support(dict(initial_best["metrics"]))
        proposed_hits = float(dict(initial_best["metrics"]).get("grid_divider_hit_count", 0.0))
        if proposed_layout < current_layout and proposed_hits >= 1.0:
            for candidate in initial_candidates:
                candidate_layout = int(candidate["layout"])
                if candidate_layout <= proposed_layout or not candidate.get("grid_like"):
                    continue
                candidate_metrics = dict(candidate["metrics"])
                candidate_support = self._runtime_layout_divider_support(candidate_metrics)
                candidate_hits = float(candidate_metrics.get("grid_divider_hit_count", 0.0))
                if candidate_hits >= max(1.0, proposed_hits - 1.0) and candidate_support >= (proposed_support * 0.95):
                    self._runtime_layout_recent_sync_at = time.monotonic()
                    self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_hold_dense")
                    self._logger.info(
                        "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_hold_dense best_layout=%s dense_layout=%s dense_support=%.4f best_support=%.4f cell=%s",
                        reason,
                        self._runtime_layout,
                        proposed_layout,
                        candidate_layout,
                        candidate_support,
                        proposed_support,
                        getattr(self._active_cell, "index", None),
                    )
                    return False, candidate_metrics

        winner_counts: dict[int, int] = {proposed_layout: 1}
        best_metrics_by_layout: dict[int, dict[str, float]] = {proposed_layout: dict(initial_best["metrics"])}
        strong_proposed_vote_count = 1 if self._runtime_layout_has_strong_fullscreen_signal(proposed_layout, dict(initial_best["metrics"])) else 0
        for _ in range(2):
            time.sleep(0.12)
            sample_candidates = self._collect_runtime_layout_candidates()
            sample_best = self._best_runtime_layout_candidate(sample_candidates)
            if sample_best is None:
                continue
            sample_layout = int(sample_best["layout"])
            winner_counts[sample_layout] = winner_counts.get(sample_layout, 0) + 1
            sample_metrics = dict(sample_best["metrics"])
            best_metrics_by_layout[sample_layout] = sample_metrics
            if sample_layout == proposed_layout and self._runtime_layout_has_strong_fullscreen_signal(proposed_layout, sample_metrics):
                strong_proposed_vote_count += 1

        if current_layout == 12 and proposed_layout == 9 and strong_proposed_vote_count < 1:
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_weak_nine_keep")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_weak_nine_keep best_layout=%s strong_votes=%s votes=%s cell=%s",
                reason,
                self._runtime_layout,
                proposed_layout,
                strong_proposed_vote_count,
                winner_counts,
                getattr(self._active_cell, "index", None),
            )
            return False, best_metrics_by_layout.get(current_layout)

        if winner_counts.get(proposed_layout, 0) < 2:
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_multiframe_keep")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_multiframe_keep best_layout=%s votes=%s cell=%s",
                reason,
                self._runtime_layout,
                proposed_layout,
                winner_counts,
                getattr(self._active_cell, "index", None),
            )
            return False, best_metrics_by_layout.get(current_layout)

        return True, best_metrics_by_layout.get(proposed_layout)

    def _try_sync_runtime_layout(self, *, reason: str) -> bool:
        if not self._preview_rect:
            return False

        if self._lock_runtime_layout_to_requested and self._requested_layout in SUPPORTED_LAYOUTS:
            locked_layout = int(self._requested_layout)
            self._runtime_layout = locked_layout
            self._observed_layout = locked_layout
            self._effective_layout = locked_layout
            self._windowed_runtime_layout_sync_needed = False
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:requested_lock")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=requested_lock cell=%s",
                reason,
                locked_layout,
                getattr(self._active_cell, "index", None),
            )
            return True

        if (
            self._runtime_layout_uia_confirmed_layout == self._runtime_layout
            and (time.monotonic() - self._runtime_layout_uia_confirmed_at)
            < self._runtime_layout_uia_confirm_cooldown_seconds
        ):
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:uia_cache")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=uia_cache cell=%s",
                reason,
                self._runtime_layout,
                getattr(self._active_cell, "index", None),
            )
            return True

        if (
            reason == "prepare_target_grid_ready"
            and (time.monotonic() - self._runtime_layout_recent_sync_at)
            < self._runtime_layout_recent_sync_cooldown_seconds
        ):
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:recent_sync")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=recent_sync cell=%s",
                reason,
                self._runtime_layout,
                getattr(self._active_cell, "index", None),
            )
            return True

        if self._current_mode == "windowed" and not self._windowed_runtime_layout_sync_needed:
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:windowed_cached")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=windowed_cached cell=%s",
                reason,
                self._runtime_layout,
                getattr(self._active_cell, "index", None),
            )
            return True

        current_layout = int(self._runtime_layout)
        current_layout_trusted = (
            self._runtime_layout_recent_sync_at > 0.0
            or self._runtime_layout_uia_confirmed_layout == current_layout
        )
        fullscreen_reconcile_mode = (
            self._current_mode == "fullscreen"
            and self._fullscreen_layout_reconcile_prefers_observed_state(reason)
        )
        if fullscreen_reconcile_mode and current_layout_trusted:
            self._logger.info(
                "RUNTIME_LAYOUT reconcile prefers observed fullscreen state reason=%s current_layout=%s",
                reason,
                current_layout,
            )
            current_layout_trusted = False
        current_layout_score: float | None = None
        current_candidate_metrics: dict[str, float] | None = None

        candidates = self._collect_runtime_layout_candidates()
        current_candidate = next((candidate for candidate in candidates if int(candidate["layout"]) == current_layout), None)
        if current_candidate is not None:
            current_candidate_metrics = dict(current_candidate["metrics"])
        if self._current_mode == "windowed":
            for candidate in candidates:
                if int(candidate["layout"]) == current_layout and candidate.get("grid_like"):
                    current_layout_score = float(candidate["score"])
                    break
            resolved_layout, resolved_metrics, resolved_reason = self._resolve_windowed_runtime_layout_candidate(
                candidates,
                current_layout=current_layout,
                current_layout_trusted=current_layout_trusted,
                current_layout_score=current_layout_score,
            )
            if resolved_layout is None:
                self._logger.info(
                    "RUNTIME_LAYOUT keep reason=%s layout=%s via=%s cell=%s metrics=%s",
                    reason,
                    self._runtime_layout,
                    resolved_reason or "windowed_multisignal_hold",
                    getattr(self._active_cell, "index", None),
                    resolved_metrics or {},
                )
                return False
            if resolved_layout == current_layout:
                self._runtime_layout_recent_sync_at = time.monotonic()
                self._windowed_runtime_layout_sync_needed = False
                self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:{resolved_reason}")
                self._logger.info(
                    "RUNTIME_LAYOUT confirm reason=%s layout=%s via=%s cell=%s metrics=%s",
                    reason,
                    self._runtime_layout,
                    resolved_reason,
                    getattr(self._active_cell, "index", None),
                    resolved_metrics or {},
                )
                if resolved_reason is not None:
                    self._save_windowed_runtime_layout_cache(layout=self._runtime_layout, source=f"{reason}:{resolved_reason}")
                return True
            return self._apply_runtime_layout(
                int(resolved_layout),
                reason=f"{reason}:{resolved_reason}",
                metrics=resolved_metrics,
            )

        best_match: tuple[float, int, dict[str, float]] | None = None
        for candidate in candidates:
            if not candidate.get("grid_like"):
                continue
            layout = int(candidate["layout"])
            score = float(candidate["score"])
            if layout == current_layout:
                current_layout_score = score
            if best_match is None or score > best_match[0]:
                best_match = (score, layout, dict(candidate["metrics"]))

        if best_match is None:
            return False

        best_score, resolved_layout, resolved_metrics = best_match
        if (
            self._current_mode == "fullscreen"
            and not fullscreen_reconcile_mode
            and current_layout == 12
            and resolved_layout < 12
            and current_candidate_metrics is not None
            and self._runtime_layout_geometry_matches(12, current_candidate_metrics)
            and float(current_candidate_metrics.get("preview_edge_ratio", 0.0)) >= 0.08
            and float(current_candidate_metrics.get("structure_changed_ratio", 0.0))
            >= max(0.35, float(resolved_metrics.get("structure_changed_ratio", 0.0)) * 0.85)
            and not self._runtime_layout_has_strong_fullscreen_signal(resolved_layout, resolved_metrics)
        ):
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_startup_dense_keep")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_startup_dense_keep best_layout=%s current_structure=%.4f best_structure=%.4f cell=%s",
                reason,
                self._runtime_layout,
                resolved_layout,
                float(current_candidate_metrics.get("structure_changed_ratio", 0.0)),
                float(resolved_metrics.get("structure_changed_ratio", 0.0)),
                getattr(self._active_cell, "index", None),
            )
            return True
        if (
            resolved_layout != current_layout
            and not fullscreen_reconcile_mode
            and current_layout_trusted
            and current_candidate_metrics is not None
            and self._should_hold_fullscreen_dense_layout(
                current_layout=current_layout,
                proposed_layout=resolved_layout,
                current_metrics=current_candidate_metrics,
                proposed_metrics=resolved_metrics,
            )
        ):
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_dense_geometry_keep")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_dense_geometry_keep best_layout=%s current_support=%.4f best_support=%.4f cell=%s",
                reason,
                self._runtime_layout,
                resolved_layout,
                self._runtime_layout_divider_support(current_candidate_metrics),
                self._runtime_layout_divider_support(resolved_metrics),
                getattr(self._active_cell, "index", None),
            )
            return True
        if (
            resolved_layout != current_layout
            and current_layout_score is not None
            and current_layout_trusted
            and self._current_mode == "fullscreen"
            and best_score <= (current_layout_score + 15.0)
        ):
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:fullscreen_margin_keep")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=fullscreen_margin_keep best_layout=%s current_score=%.4f best_score=%.4f cell=%s",
                reason,
                self._runtime_layout,
                resolved_layout,
                current_layout_score,
                best_score,
                getattr(self._active_cell, "index", None),
            )
            return True
        if resolved_layout != current_layout and self._current_mode == "fullscreen" and current_layout_trusted:
            allow_change, confirmed_metrics = self._confirm_fullscreen_layout_change(
                reason=reason,
                current_layout=current_layout,
                proposed_layout=resolved_layout,
                initial_candidates=candidates,
            )
            if confirmed_metrics is not None:
                resolved_metrics = confirmed_metrics
            if not allow_change:
                return True
        if resolved_layout == current_layout:
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:visual_confirm")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=visual_confirm cell=%s",
                reason,
                self._runtime_layout,
                getattr(self._active_cell, "index", None),
            )
            return True
        if (
            current_layout_trusted
            and
            current_layout_score is not None
            and reason == "prepare_target_grid_ready"
            and best_score <= (current_layout_score + 50.0)
        ):
            # 关键修复：当前布局本帧已经能稳定判成宫格时，不要因为弱视觉分数的小幅波动
            # 就把 4 宫格错误翻成 6 宫格。只有候选布局明显更强，才允许在 grid_ready 上切换。
            self._runtime_layout_recent_sync_at = time.monotonic()
            self._reset_issue_failure_streak(f"runtime_layout_sync:{reason}:visual_keep_current")
            self._logger.info(
                "RUNTIME_LAYOUT confirm reason=%s layout=%s via=visual_keep_current best_layout=%s current_score=%.4f best_score=%.4f cell=%s",
                reason,
                self._runtime_layout,
                resolved_layout,
                current_layout_score,
                best_score,
                getattr(self._active_cell, "index", None),
            )
            return True

        # 关键修复：视觉回退分支也必须统一走 _apply_runtime_layout。
        # 否则 recent_sync/uia_cache 相关的时间戳不会更新，下一轮 PREPARE_TARGET
        # 仍会把刚同步成 4 的全屏场景又翻回 6。
        return self._apply_runtime_layout(int(resolved_layout), reason=reason, metrics=resolved_metrics)

    def _select_active_cell(
        self,
        *,
        reason: str,
        action_type: str,
        allow_paused: bool = False,
        settle_after_action: bool = True,
        skip_guard_before: bool = False,
        guard_expected_view_after: VisualViewState | None = None,
    ) -> bool:
        if not self._active_cell or not self._window_info:
            return False
        self._logger.info(
            "SELECT cell=%s cell_rect=%s select_point=%s zoom_point=%s zoom_out_point=%s reason=%s action_type=single_click",
            self._active_cell.index,
            self._active_cell.cell_rect,
            self._active_cell.select_point,
            self._active_cell.zoom_point,
            self._current_zoom_out_point(),
            reason,
        )
        action_success = self._perform_pointer_action(
            action_name=action_type,
            point_getter=lambda: self._active_cell.select_point,
            controller_action=lambda point: self._controller.click_once(
                point,
                hwnd=self._window_info.hwnd,
                client_origin=(self._window_info.client_rect.left, self._window_info.client_rect.top),
                action_type=action_type,
            ),
            failure_target_state=SchedulerState.NEXT,
            recover_on_failure=not allow_paused,
            skip_guard_before=skip_guard_before,
            guard_expected_view_before=VisualViewState.GRID,
            guard_expected_view_after=guard_expected_view_after,
        )
        if not action_success:
            return False

        if not settle_after_action:
            return True
        settle_seconds = self._config.timing.select_settle_ms / 1000.0
        if allow_paused:
            self._sleep_while_paused(settle_seconds)
            return True
        return self._wait_interruptible(settle_seconds, allow_pause=True)

    def _perform_visible_next_selection(self) -> bool:
        if not self._cells or self._manual_next_target_index is None:
            return False
        target_cell = self._cells[self._manual_next_target_index]
        actual_view = VisualViewState.UNKNOWN
        view_metrics = {}
        try:
            actual_view, view_metrics = self._classify_current_view(refresh_context=True)
        except Exception as exc:
            self._logger.warning("NEXT selection reconcile failed before visible click: %s", exc)

        # 暂停态 F9 预选只允许在“当前画面已经是宫格，或者 UNKNOWN 但具备固定宫格峰值”
        # 的前提下直接点下一格。若当前仍是放大态，即便旧 probe 误给出 GRID 相似分，
        # 也必须先回宫格，否则恢复后会把单路页当成 PREPARE_TARGET 起点继续乱点。
        grid_like = actual_view == VisualViewState.GRID
        if not grid_like and actual_view != VisualViewState.ZOOMED:
            grid_like = self._prepare_target_grid_like(actual_view, view_metrics, reason="manual_next_queue_grid_ready")

        if not grid_like:
            self._logger.info(
                "NEXT_QUEUE recover_to_grid_for_visible_select cell=%s actual_view=%s metrics=%s",
                target_cell.index,
                actual_view.value,
                view_metrics,
            )
            recovered_to_grid = False
            for attempt in range(2):
                used_pointer_recovery = attempt == 1 and actual_view == VisualViewState.ZOOMED
                if used_pointer_recovery:
                    recovery_ok = self._perform_zoom_out_grid_recovery_action(
                        action_name="manual_next_queue_zoom_out_recover",
                        failure_target_state=SchedulerState.PREPARE_TARGET,
                        recover_on_failure=False,
                        allow_paused_action=True,
                    )
                else:
                    recovery_ok = self._perform_grid_recovery_action(
                        action_name="manual_next_queue_recover",
                        failure_target_state=SchedulerState.PREPARE_TARGET,
                        recover_on_failure=False,
                    )
                if not recovery_ok:
                    self._logger.error(
                        "NEXT_QUEUE aborted because the target window could not be focused safely cell=%s attempt=%s pointer_recovery=%s",
                        target_cell.index,
                        attempt + 1,
                        used_pointer_recovery,
                    )
                    return False
                self._sleep_while_paused(0.75 if attempt == 0 else 1.15)
                self._is_zoomed = False
                self._refresh_window_context()
                actual_view, view_metrics = self._classify_current_view(refresh_context=True)
                grid_like = actual_view == VisualViewState.GRID
                if not grid_like and actual_view != VisualViewState.ZOOMED:
                    grid_like = self._prepare_target_grid_like(
                        actual_view,
                        view_metrics,
                        reason="manual_next_queue_post_recover_grid_ready",
                    )
                if grid_like:
                    recovered_to_grid = True
                    break
                self._logger.warning(
                    "NEXT_QUEUE post-recover still not grid cell=%s attempt=%s actual_view=%s metrics=%s",
                    target_cell.index,
                    attempt + 1,
                    actual_view.value,
                    view_metrics,
                )
            if not recovered_to_grid:
                return False
            # 关键修复：暂停态 F9 在回宫格后必须立刻刷新新的宫格 probe。
            # 否则后续 before_select_next_queue 仍会拿旧 probe 去做 runtime_guard，
            # 把已经回到的低纹理宫格误判成 unexpected_interface。
            self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))
            target_cell = self._cells[self._manual_next_target_index]

        self._logger.info(
            "SELECT cell=%s cell_rect=%s select_point=%s zoom_point=%s zoom_out_point=%s reason=%s action_type=single_click queued_next_index=%s queued_next_depth=%s",
            target_cell.index,
            target_cell.cell_rect,
            target_cell.select_point,
            target_cell.zoom_point,
            self._current_zoom_out_point(),
            "manual_next_queue",
            self._manual_next_target_index,
            self._manual_next_queue_depth,
        )
        action_success = self._perform_pointer_action(
            action_name="select_next_queue",
            point_getter=lambda: self._cells[self._manual_next_target_index].select_point,
            controller_action=lambda point: self._controller.click_once(
                point,
                hwnd=self._window_info.hwnd,
                client_origin=(self._window_info.client_rect.left, self._window_info.client_rect.top),
                action_type="select_next_queue",
            ),
            failure_target_state=SchedulerState.PREPARE_TARGET,
            recover_on_failure=False,
            allow_paused_action=True,
            skip_guard_before=True,
            guard_expected_view_before=VisualViewState.GRID,
        )
        if action_success:
            self._sleep_while_paused(self._config.timing.select_settle_ms / 1000.0)
        return action_success

    def _cell_hint(self, cell) -> str:
        if cell is None:
            return "未知窗格"
        label = getattr(cell, "label", "") or ""
        suffix = f" [{label}]" if label else ""
        return f"第{cell.row + 1}行第{cell.col + 1}列{suffix}"

    def _current_zoom_out_point(self) -> tuple[int, int]:
        if self._preview_rect:
            return self._preview_rect.center
        if self._window_info:
            return self._window_info.client_rect.center
        return (0, 0)

    def _exclude_overlay_safe_strip(self, rect: Rect) -> Rect:
        if not self._config.status_overlay.enabled or not self._window_info:
            return rect
        safe_bottom = self._window_info.monitor_rect.bottom - self._config.status_overlay.safe_strip_height_px - 8
        if rect.bottom <= safe_bottom:
            return rect
        adjusted_bottom = max(rect.top + 80, safe_bottom)
        return Rect(rect.left, rect.top, rect.right, adjusted_bottom)

    def _sleep_while_paused(self, seconds: float) -> None:
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            time.sleep(0.05)

    def _issue_key(self, cell_index: int, reason: str) -> tuple[int, str]:
        return (cell_index, reason)

    def _register_issue_failure(self, reason: str) -> bool:
        if not self._active_cell:
            return False
        key = self._issue_key(self._active_cell.index, reason)
        entry = self._issue_registry.setdefault(key, {"fail_streak": 0, "cooldown_remaining": 0})
        entry["fail_streak"] += 1
        self._issue_failure_streak += 1
        self._logger.warning(
            "ISSUE_FAILURE_STREAK cell=%s reason=%s streak=%s",
            self._active_cell.index,
            reason,
            self._issue_failure_streak,
        )
        if entry["fail_streak"] >= self._config.detection.max_fail_streak_before_cooldown:
            entry["cooldown_remaining"] = self._config.detection.issue_cooldown_cycles
            self._logger.warning(
                "ISSUE_COOLDOWN cell=%s reason=%s remaining_cycles=%s",
                self._active_cell.index,
                reason,
                entry["cooldown_remaining"],
            )
        if self._issue_failure_streak >= self._config.detection.max_fail_streak_before_cooldown:
            if self._config.detection.skip_on_detected_issue:
                self._logger.warning(
                    "ISSUE_FAILURE consecutive issues reached cooldown threshold cell=%s reason=%s skip_on_detected_issue=%s; continuing recovery without auto-pause",
                    self._active_cell.index,
                    reason,
                    self._config.detection.skip_on_detected_issue,
                )
                return False
            self._pause_for_detected_issue(reason)
            return True
        return False

    def _reset_issue_failure_streak(self, reason: str) -> None:
        if self._issue_failure_streak <= 0:
            return
        self._logger.info("ISSUE_FAILURE_STREAK reset streak=%s reason=%s", self._issue_failure_streak, reason)
        self._issue_failure_streak = 0

    def _pause_for_detected_issue(self, reason: str) -> None:
        # 仅在显式需要人工介入的致命异常上暂停；普通连续异常是否自动暂停由
        # detection.skip_on_detected_issue 在 _register_issue_failure 中决定。
        self._logger.error(
            "ISSUE_FAILURE auto-pausing after consecutive detected issues cell=%s reason=%s streak=%s",
            getattr(self._active_cell, "index", None),
            reason,
            self._issue_failure_streak,
        )
        self._publish_status(
            message=f"连续异常已自动暂停：{reason}",
            details=f"请先确认客户端已回到正确宫格，再按 {self._config.hotkeys.start_pause} 继续；必要时按 {self._config.hotkeys.emergency_recover} 恢复。",
            level="warning",
        )
        self._user_paused = True
        self._last_pause_reason = "detected_issue"
        self._resume_requires_recovery = True
        self._latch_pause_barrier("detected_issue")
        self._state = SchedulerState.PAUSED
        self._acknowledge_pause()

    def _clear_issue_registry_for_cell(self, cell_index: int, reason: str | None = None) -> None:
        keys = [key for key in self._issue_registry if key[0] == cell_index and (reason is None or key[1] == reason)]
        for key in keys:
            self._issue_registry[key] = {"fail_streak": 0, "cooldown_remaining": 0}

    def _skip_current_cell_for_detected_issue(self, reason: str, *, from_state: SchedulerState) -> None:
        auto_paused = self._register_issue_failure(reason)
        if auto_paused:
            return
        self._logger.warning(
            "ISSUE_SKIP cell=%s reason=%s from_state=%s next_state=%s",
            getattr(self._active_cell, "index", None),
            reason,
            from_state,
            SchedulerState.NEXT,
        )
        self._publish_status(
            message=f"检测异常，已跳过 {self._cell_hint(self._active_cell)}",
            details=f"skip_on_detected_issue 已启用；{reason} 不再自动暂停。",
            level="warning",
        )
        self._next_transition_reason = f"issue_skip:{reason}"
        self._transition_state(SchedulerState.NEXT, from_state=from_state)

    def _resume_skip_current_cell_for_detected_issue(
        self,
        *,
        reason: str,
        queued_next_index: int | None,
        actual_view: VisualViewState,
    ) -> bool:
        auto_paused = self._register_issue_failure(reason)
        if auto_paused:
            return False
        self._refresh_window_context(fast=self._window_info is not None)
        if self._cells:
            restart_index = queued_next_index if queued_next_index is not None else self._current_index
            self._current_index = restart_index % len(self._cells)
            self._active_cell = self._cells[self._current_index]
        self._clear_recovery_flags()
        self._input_guard.clear_manual_activity()
        self._release_pause_barrier()
        self._pause_acknowledged = False
        self._pause_ack_view = VisualViewState.UNKNOWN
        self._paused_stage = ""
        self._paused_index = None
        self._manual_next_used_during_pause = False
        self._grid_order_changed_during_pause = False
        self._resume_requires_recovery = False
        self._user_paused = False
        self._next_transition_reason = f"issue_skip:{reason}"
        self._logger.warning(
            "RESUME_SKIP cell=%s reason=%s actual_view=%s next_state=%s",
            getattr(self._active_cell, "index", None),
            reason,
            actual_view.value,
            SchedulerState.NEXT,
        )
        self._publish_status(
            message=f"恢复后仍未识别宫格，已跳过 {self._cell_hint(self._active_cell)}",
            details=f"skip_on_detected_issue 已启用；{reason} 不再自动暂停。",
            level="warning",
        )
        self._state = SchedulerState.NEXT
        return True

    def _maybe_skip_for_issue_cooldown(self) -> bool:
        if not self._active_cell:
            return False
        if (
            self._resume_clear_cooldown_bypass_index is not None
            and self._active_cell.index == self._resume_clear_cooldown_bypass_index
        ):
            self._logger.info(
                "BYPASS_ISSUE_COOLDOWN cell=%s reason=manual_clear_cooldown_resume",
                self._active_cell.index,
            )
            self._resume_clear_cooldown_bypass_index = None
            return False
        for reason in (
            "black_screen",
            "preview_failure",
            "zoom_confirm_failed",
            "path_mismatch",
            "prepare_not_grid",
            "resume_not_grid",
        ):
            key = self._issue_key(self._active_cell.index, reason)
            entry = self._issue_registry.get(key)
            if not entry or entry.get("cooldown_remaining", 0) <= 0:
                continue
            entry["cooldown_remaining"] -= 1
            self._logger.warning(
                "ISSUE_COOLDOWN cell=%s reason=%s remaining_cycles=%s",
                self._active_cell.index,
                reason,
                entry["cooldown_remaining"],
            )
            self._publish_status(
                message=f"异常冷却中，已跳过 {self._cell_hint(self._active_cell)}",
                details="",
                level="warning",
            )
            self._next_transition_reason = f"issue_cooldown:{reason}"
            self._transition_state(SchedulerState.NEXT, from_state=SchedulerState.PREPARE_TARGET)
            return True
        return False

    def _reconcile_visual_state_on_resume(self) -> tuple[VisualViewState, dict[str, float]]:
        actual_view, metrics = self._classify_current_view(refresh_context=True)
        self._logger.info(
            "RESUME_RECONCILE actual_view=%s cell=%s metrics=%s",
            actual_view.value,
            getattr(self._active_cell, "index", None),
            metrics,
        )
        return actual_view, metrics

    def _resume_after_pause_locked_runtime_profile(self) -> bool:
        queued_next_index = self._manual_next_target_index
        queued_next_depth = self._manual_next_queue_depth
        pause_source = self._pause_barrier_source or self._last_pause_reason or "pause"
        if self._manual_next_used_during_pause and queued_next_index is not None:
            pause_source = "queued_next"

        if self._paused_index is not None and self._cells:
            self._current_index = self._paused_index
            self._active_cell = self._cells[self._current_index]

        actual_view, metrics = self._classify_current_view(refresh_context=True)
        self._logger.info(
            "RESUME_POLICY fast_locked_profile source=%s queued_next_index=%s queued_next_depth=%s paused_stage=%s paused_index=%s actual_view=%s metrics=%s",
            pause_source,
            queued_next_index,
            queued_next_depth,
            self._paused_stage or "unknown",
            self._paused_index,
            actual_view.value,
            metrics,
        )

        paused_stage = self._paused_stage or ""
        paused_during_zoom_transition = (
            paused_stage in {"ZOOM_IN", "ZOOM_OUT", "ZOOM_CONFIRM"}
            or paused_stage.startswith("before_zoom_")
            or paused_stage.startswith("after_zoom_")
        )
        paused_with_zoom_surface = (
            actual_view == VisualViewState.ZOOMED
            or self._pause_ack_view == VisualViewState.ZOOMED
            or paused_stage == "ZOOM_DWELL"
            or paused_during_zoom_transition
        )
        order_changed_from_zoom_surface = self._grid_order_changed_during_pause and paused_with_zoom_surface
        operator_returned_to_grid = (
            paused_stage == "ZOOM_DWELL"
            and self._last_pause_reason == "user_pause"
            and actual_view == VisualViewState.GRID
            and not paused_during_zoom_transition
            and not self._grid_order_changed_during_pause
        )
        prefer_explicit_zoom_out_recovery = (
            paused_stage == "ZOOM_DWELL"
            or paused_during_zoom_transition
            or actual_view == VisualViewState.ZOOMED
            or self._pause_ack_view == VisualViewState.ZOOMED
        )
        recovered_from_zoom_surface = False
        if operator_returned_to_grid:
            # 操作员在暂停期间已经手工双击回宫格，恢复时不要再补发 zoom-out/ESC。
            # 这条链如果继续做“恢复动作”，反而会把当前已回到宫格的选中态打坏，
            # 随后在 PREPARE_TARGET 掉成 UNKNOWN，并被放大成 prepare_not_grid/cooldown。
            self._logger.info(
                "RESUME_ZOOM_SURFACE detected operator-returned grid; skipping explicit zoom-out recovery cell=%s paused_stage=%s actual_view=%s metrics=%s",
                getattr(self._active_cell, "index", None),
                paused_stage or "unknown",
                actual_view.value,
                metrics,
            )
            recovered_from_zoom_surface = True
        elif prefer_explicit_zoom_out_recovery:
            self._logger.warning(
                "RESUME_ZOOM_SURFACE forcing explicit zoom-out recovery cell=%s paused_stage=%s actual_view=%s metrics=%s",
                getattr(self._active_cell, "index", None),
                paused_stage or "unknown",
                actual_view.value,
                metrics,
            )
            if self._perform_zoom_out_grid_recovery_action(
                action_name="resume_zoom_surface_recover",
                failure_target_state=SchedulerState.PREPARE_TARGET,
                recover_on_failure=False,
                allow_paused_action=False,
            ):
                if not self._wait_interruptible(1.15, allow_pause=False):
                    return False
                actual_view, metrics = self._classify_current_view(refresh_context=True)
                recovered_from_zoom_surface = True
        unsafe_grid_frame = (
            (paused_during_zoom_transition or order_changed_from_zoom_surface)
            and not recovered_from_zoom_surface
        )
        # 关键修复：暂停时如果仍停在放大态，或刚好卡在 zoom 过渡阶段，恢复阶段都不能
        # 把当前帧继续当成 grid-like 直接进入 PREPARE_TARGET。此时看到的 GRID 常常只是
        # 过渡帧，下一帧就会掉成 UNKNOWN，随后连续触发 prepare_not_grid/cooldown。
        grid_like = actual_view == VisualViewState.GRID and not unsafe_grid_frame
        if not grid_like and actual_view != VisualViewState.ZOOMED and not unsafe_grid_frame:
            grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_grid_ready")

        if not grid_like:
            if not self._perform_grid_recovery_action(
                action_name="resume_recover",
                failure_target_state=SchedulerState.PREPARE_TARGET,
                recover_on_failure=False,
            ):
                self._logger.error("RESUME aborted because the target window could not be focused safely")
                self._state = SchedulerState.STOPPED
                return False
            settle_after_recover = 0.95 if actual_view == VisualViewState.ZOOMED or (self._paused_stage or "").startswith("ZOOM_") else 0.35
            if not self._wait_interruptible(settle_after_recover, allow_pause=False):
                return False
            actual_view, metrics = self._classify_current_view(refresh_context=True)
            grid_like = actual_view == VisualViewState.GRID and not unsafe_grid_frame
            if not grid_like and actual_view != VisualViewState.ZOOMED and not unsafe_grid_frame:
                grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_post_recover_grid_ready")
            if not grid_like and actual_view == VisualViewState.ZOOMED:
                if self._perform_zoom_out_grid_recovery_action(
                    action_name="resume_zoom_out_recover",
                    failure_target_state=SchedulerState.PREPARE_TARGET,
                    recover_on_failure=False,
                    allow_paused_action=False,
                ):
                    if not self._wait_interruptible(1.15, allow_pause=False):
                        return False
                    actual_view, metrics = self._classify_current_view(refresh_context=True)
                    grid_like = actual_view == VisualViewState.GRID
                    if not grid_like and actual_view != VisualViewState.ZOOMED:
                        grid_like = self._prepare_target_grid_like(
                            actual_view,
                            metrics,
                            reason="resume_post_zoom_out_grid_ready",
                        )
            if not grid_like:
                if order_changed_from_zoom_surface or (recovered_from_zoom_surface and actual_view != VisualViewState.ZOOMED):
                    self._logger.warning(
                        "RESUME_FALLBACK continuing via PREPARE_TARGET after zoom-surface recovery cell=%s paused_stage=%s actual_view=%s metrics=%s",
                        getattr(self._active_cell, "index", None),
                        paused_stage or "unknown",
                        actual_view.value,
                        metrics,
                    )
                    grid_like = True
                if self._config.detection.skip_on_detected_issue:
                    if not grid_like:
                        return self._resume_skip_current_cell_for_detected_issue(
                            reason="resume_not_grid",
                            queued_next_index=queued_next_index,
                            actual_view=actual_view,
                        )
                elif not grid_like:
                    self._pause_for_detected_issue("resume_not_grid")
                    return False

        self._refresh_window_context(fast=self._window_info is not None)
        if self._cells:
            restart_index = queued_next_index if queued_next_index is not None else self._current_index
            self._current_index = restart_index % len(self._cells)
            self._active_cell = self._cells[self._current_index]

        self._clear_runtime_context_for_restart(reason="resume_hard_reset")
        self._set_zoom_confirm_poll_boost_cycles(2)
        self._logger.info(
            "RESUME_RESTART_FROM index=%s cell=%s",
            self._current_index,
            self._cell_hint(self._active_cell),
        )

        self._clear_recovery_flags()
        self._input_guard.clear_manual_activity()
        self._release_pause_barrier()
        self._pause_acknowledged = False
        self._pause_ack_view = VisualViewState.UNKNOWN
        self._paused_stage = ""
        self._paused_index = None
        self._manual_next_used_during_pause = False
        self._grid_order_changed_during_pause = False
        self._resume_requires_recovery = False
        self._state = SchedulerState.PREPARE_TARGET
        self._logger.info("RESUME_ACK fast_locked_profile actual_view=%s next_state=%s", actual_view.value, self._state)
        return True

    def _resume_after_pause(self) -> None:
        if self._use_locked_runtime_profile_fast_path():
            self._resume_after_pause_locked_runtime_profile()
            return
        queued_next_index = self._manual_next_target_index
        queued_next_depth = self._manual_next_queue_depth
        pause_source = self._pause_barrier_source or self._last_pause_reason or "pause"
        if self._manual_next_used_during_pause and queued_next_index is not None:
            pause_source = "queued_next"

        if self._paused_index is not None and self._cells:
            self._current_index = self._paused_index
            self._active_cell = self._cells[self._current_index]

        self._invalidate_runtime_observation("resume_reconcile")
        observation = self._observe_runtime_profile(reason="resume_reconcile", samples=3, sync_layout=True)
        actual_view = observation.get("view", VisualViewState.UNKNOWN)
        if not isinstance(actual_view, VisualViewState):
            actual_view = VisualViewState.UNKNOWN
        if not self._observation_matches_requested(observation):
            self._freeze_for_runtime_profile_mismatch(reason="resume_profile_check")
            return

        self._logger.info(
            "RESUME_POLICY source=%s queued_next_index=%s queued_next_depth=%s paused_stage=%s paused_index=%s",
            pause_source,
            queued_next_index,
            queued_next_depth,
            self._paused_stage or "unknown",
            self._paused_index,
        )

        to_grid = actual_view != VisualViewState.GRID
        self._logger.info("RESUME_HARD_RESET to_grid=%s actual_view=%s", int(to_grid), actual_view.value)
        if to_grid:
            if not self._perform_grid_recovery_action(
                action_name="resume_recover",
                failure_target_state=SchedulerState.PREPARE_TARGET,
                recover_on_failure=False,
            ):
                self._logger.error("RESUME aborted because the target window could not be focused safely")
                self._state = SchedulerState.STOPPED
                return
            if not self._wait_interruptible(0.6, allow_pause=False):
                return
            self._invalidate_runtime_observation("resume_post_recover")
            observation = self._observe_runtime_profile(reason="resume_post_recover", samples=2, sync_layout=True)
            actual_view = observation.get("view", VisualViewState.UNKNOWN)
            if not isinstance(actual_view, VisualViewState):
                actual_view = VisualViewState.UNKNOWN
            if not self._observation_matches_requested(observation):
                self._freeze_for_runtime_profile_mismatch(reason="resume_post_recover_profile_check")
                return
            if actual_view != VisualViewState.GRID:
                if self._config.detection.skip_on_detected_issue:
                    self._resume_skip_current_cell_for_detected_issue(
                        reason="resume_not_grid",
                        queued_next_index=queued_next_index,
                        actual_view=actual_view,
                    )
                    return
                self._pause_for_detected_issue("resume_not_grid")
                return

        self._refresh_window_context()
        if self._cells:
            restart_index = queued_next_index if queued_next_index is not None else self._current_index
            self._current_index = restart_index % len(self._cells)
            self._active_cell = self._cells[self._current_index]

        self._clear_runtime_context_for_restart(reason="resume_hard_reset")
        self._set_zoom_confirm_poll_boost_cycles(2)
        self._logger.info(
            "RESUME_RESTART_FROM index=%s cell=%s",
            self._current_index,
            self._cell_hint(self._active_cell),
        )

        self._clear_recovery_flags()
        self._input_guard.clear_manual_activity()
        self._release_pause_barrier()
        self._pause_acknowledged = False
        self._pause_ack_view = VisualViewState.UNKNOWN
        self._paused_stage = ""
        self._paused_index = None
        self._manual_next_used_during_pause = False
        self._resume_requires_recovery = False
        self._state = SchedulerState.PREPARE_TARGET
        self._logger.info("RESUME_ACK actual_view=%s next_state=%s", actual_view.value, self._state)

    def _next_cell_index(self, current_index: int | None) -> int | None:
        if current_index is None or not self._cells:
            return None
        return (current_index + 1) % len(self._cells)

    def _wait_interruptible(self, seconds: float, *, allow_pause: bool) -> bool:
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            self._consume_commands()
            if self._recovery_requested and not self._recovery_in_progress:
                self._state = SchedulerState.ERROR_RECOVERY
                return False
            if self._stop_requested:
                return False
            if allow_pause:
                self._refresh_pause_state()
                if self._state == SchedulerState.PAUSED:
                    return False
            time.sleep(0.02)
        return True

    def _register_hotkeys(self) -> None:
        # 关键修复：F1/F2/F7/F8/F9/F10/F11 都是单键热键，统一改成 keydown 级别的 on_press_key，
        # 减少 add_hotkey 组合解析带来的迟滞和丢键概率。
        if not self._hotkey_disabled(self._config.hotkeys.profile_source_toggle):
            self._register_single_key_hotkey(
                "profile_source_toggle",
                self._config.hotkeys.profile_source_toggle,
                self._request_profile_source_toggle,
            )
        if not self._hotkey_disabled(self._config.hotkeys.start_pause):
            self._register_single_key_hotkey(
                "start_pause",
                self._config.hotkeys.start_pause,
                self._toggle_user_pause,
            )
        if not self._hotkey_disabled(self._config.hotkeys.next_cell):
            self._register_single_key_hotkey(
                "next_cell",
                self._config.hotkeys.next_cell,
                self._request_next_cell,
            )
        if not self._hotkey_disabled(self._config.hotkeys.grid_order_cycle):
            self._register_single_key_hotkey(
                "grid_order_cycle",
                self._config.hotkeys.grid_order_cycle,
                self._request_grid_order_cycle,
            )
        if self._hotkey_disabled(self._config.hotkeys.stop):
            pass
        elif "+" in self._config.hotkeys.stop:
            self._hotkeys.append(
                (
                    "hotkey",
                    keyboard.add_hotkey(
                        self._config.hotkeys.stop,
                        lambda: self._invoke_hotkey("stop", self._request_stop),
                        suppress=True,
                    ),
                )
            )
        else:
            self._register_single_key_hotkey(
                "stop",
                self._config.hotkeys.stop,
                self._request_stop,
            )
        if not self._hotkey_disabled(self._config.hotkeys.emergency_recover):
            self._register_single_key_hotkey(
                "emergency_recover",
                self._config.hotkeys.emergency_recover,
                self._request_recovery,
            )
        if not self._hotkey_disabled(self._config.hotkeys.clear_cooldown):
            self._register_single_key_hotkey(
                "clear_cooldown",
                self._config.hotkeys.clear_cooldown,
                self._request_clear_cooldown,
            )
        if self._hotkey_disabled(self._config.hotkeys.mode_cycle):
            pass
        elif "+" in self._config.hotkeys.mode_cycle:
            self._hotkeys.append(
                (
                    "hotkey",
                    keyboard.add_hotkey(
                        self._config.hotkeys.mode_cycle,
                        lambda: self._invoke_hotkey("mode_cycle", self._request_mode_cycle),
                        suppress=True,
                    ),
                )
            )
        else:
            self._register_single_key_hotkey(
                "mode_cycle",
                self._config.hotkeys.mode_cycle,
                self._request_mode_cycle,
            )
        if self._hotkey_disabled(self._config.hotkeys.layout_cycle):
            pass
        elif "+" in self._config.hotkeys.layout_cycle:
            self._hotkeys.append(
                (
                    "hotkey",
                    keyboard.add_hotkey(
                        self._config.hotkeys.layout_cycle,
                        lambda: self._invoke_hotkey("layout_cycle", self._request_layout_cycle),
                        suppress=True,
                    ),
                )
            )
        else:
            self._register_single_key_hotkey(
                "layout_cycle",
                self._config.hotkeys.layout_cycle,
                self._request_layout_cycle,
            )
        self._logger.info(
            "Registered hotkeys profile_source=%s mode=%s layout=%s order=%s start_pause=%s next=%s stop=%s recover=%s clear_cooldown=%s",
            self._config.hotkeys.profile_source_toggle,
            self._config.hotkeys.mode_cycle,
            self._config.hotkeys.layout_cycle,
            self._config.hotkeys.grid_order_cycle,
            self._config.hotkeys.start_pause,
            self._config.hotkeys.next_cell,
            self._config.hotkeys.stop,
            self._config.hotkeys.emergency_recover,
            self._config.hotkeys.clear_cooldown,
        )

    @staticmethod
    def _hotkey_disabled(key_name: str | None) -> bool:
        if key_name is None:
            return True
        return str(key_name).strip().lower() in {"", "disabled", "none", "off"}

    def _register_single_key_hotkey(
        self,
        hotkey_name: str,
        key_name: str,
        handler,
        *,
        plain_only: bool = True,
    ):
        if self._register_native_hotkey(hotkey_name, key_name, handler):
            return
        self._hotkey_plain_only[hotkey_name] = plain_only
        self._prime_hotkey_press_latch(hotkey_name, key_name)
        press_hook = keyboard.on_press_key(
            key_name,
            lambda _event: self._invoke_hotkey(hotkey_name, handler),
            # 关键修复：单键热键必须拦截本次按键，避免再外泄给系统或第三方全局热键。
            suppress=True,
        )
        release_hook = keyboard.on_release_key(
            key_name,
            lambda _event: self._release_hotkey_press_latch(hotkey_name),
            suppress=False,
        )
        self._hotkeys.append(("hook", press_hook))
        self._hotkeys.append(("hook", release_hook))

    def _register_native_hotkey(self, hotkey_name: str, key_name: str, handler) -> bool:
        if self._native_hotkeys is None or parse_hotkey_spec(key_name) is None:
            return False
        hotkey_id = self._native_hotkeys.register(
            key_name,
            lambda: self._invoke_hotkey(hotkey_name, handler, from_native=True),
        )
        if hotkey_id is None:
            return False
        self._hotkeys.append(("native", hotkey_id))
        return True

    def _prime_hotkey_press_latch(self, hotkey_name: str, key_name: str) -> None:
        with suppress(Exception):
            self._hotkey_press_latched[hotkey_name] = keyboard.is_pressed(key_name)
            return
        self._hotkey_press_latched[hotkey_name] = False

    def _release_hotkey_press_latch(self, hotkey_name: str) -> None:
        if hotkey_name in self._hotkey_press_latched:
            self._hotkey_press_latched[hotkey_name] = False

    def _plain_modifier_pressed(self) -> bool:
        for key_name in ("ctrl", "shift", "alt", "windows"):
            with suppress(Exception):
                if keyboard.is_pressed(key_name):
                    return True
        return False

    def _cleanup(self) -> None:
        for hotkey_type, hotkey in self._hotkeys:
            try:
                if hotkey_type == "hook":
                    keyboard.unhook(hotkey)
                elif hotkey_type == "hotkey":
                    keyboard.remove_hotkey(hotkey)
                elif hotkey_type == "native" and self._native_hotkeys is not None:
                    self._native_hotkeys.unregister(int(hotkey))
            except KeyError:
                pass
        self._hotkeys.clear()
        if self._native_hotkeys is not None:
            self._native_hotkeys.stop()
        self._input_guard.stop()
        self._logger.info("Scheduler stopped")
        if self._status:
            self._status.stop(message="程序已停止")

    def _toggle_user_pause(self) -> None:
        now = time.monotonic()
        # 关键修复：某些桌面环境/注入路径会把一次启动/暂停热键放大成连续两次 start_pause 事件，
        # 导致“刚暂停又立刻恢复”。这里为启停热键单独加一个很短的切换锁，
        # 只抑制重复切换，不改变正常语义。
        if now < self._start_pause_toggle_lock_until:
            return
        # 关键修复：过长的保护窗会让人工连续触发启停的体感过钝，像是“按不动”。
        # 这里保留一个更短的保护窗，只拦住同一次按键被重复放大的抖动事件。
        self._start_pause_toggle_lock_until = now + 0.35
        command = (
            HotkeyCommand.RESUME_REQUEST
            if (self._pause_acknowledged or self._state == SchedulerState.PAUSED or self._user_paused)
            else HotkeyCommand.PAUSE_REQUEST
        )
        self._enqueue_command(command)

    def _request_next_cell(self) -> None:
        self._enqueue_command(HotkeyCommand.NEXT_REQUEST)

    def _request_stop(self) -> None:
        self._enqueue_command(HotkeyCommand.STOP_REQUEST)

    def _request_recovery(self) -> None:
        self._enqueue_command(HotkeyCommand.EMERGENCY_RECOVER_REQUEST)

    def _request_clear_cooldown(self) -> None:
        self._enqueue_command(HotkeyCommand.CLEAR_COOLDOWN_REQUEST)

    def _request_mode_cycle(self) -> None:
        self._enqueue_command(HotkeyCommand.MODE_CYCLE_REQUEST)

    def _request_layout_cycle(self) -> None:
        self._enqueue_command(HotkeyCommand.LAYOUT_CYCLE_REQUEST)

    def _request_grid_order_cycle(self) -> None:
        self._enqueue_command(HotkeyCommand.GRID_ORDER_CYCLE_REQUEST)

    def _request_profile_source_toggle(self) -> None:
        self._enqueue_command(HotkeyCommand.PROFILE_SOURCE_TOGGLE_REQUEST)

    def _maybe_save_failure_snapshot(self, status: str, cell_index: int, rect) -> None:
        if not self._config.detection.save_failure_screenshots and not self._config.detection.save_anomaly_screenshot:
            return
        output_dir = resolve_output_path(self._config.path, self._config.detection.screenshot_dir)
        destination = output_dir / f"{status}_cell_{cell_index}_{int(time.time())}.png"
        try:
            self._detector.save_cell_snapshot(rect, destination)
        except Exception as exc:
            self._logger.warning("Skipping failure snapshot for cell=%s status=%s: %s", cell_index, status, exc)

    def _maybe_save_client_snapshot(self, tag: str) -> None:
        if not self._config.detection.save_failure_screenshots or not self._window_info:
            return
        output_dir = resolve_output_path(self._config.path, self._config.detection.screenshot_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{tag}_{int(time.time())}.png"
        capture_rect = self._exclude_overlay_safe_strip(self._window_info.client_rect)
        image = ImageGrab.grab(bbox=capture_rect.to_bbox())
        image.save(destination)

    def _invoke_hotkey(self, hotkey_name: str, handler, *, from_native: bool = False) -> None:
        if not from_native and self._hotkey_plain_only.get(hotkey_name) and self._plain_modifier_pressed():
            return
        if not from_native and hotkey_name in self._hotkey_press_latched:
            if self._hotkey_press_latched[hotkey_name]:
                return
            self._hotkey_press_latched[hotkey_name] = True
        now = time.monotonic()
        last_trigger = self._hotkey_last_trigger_at.get(hotkey_name, 0.0)
        debounce_ms = self._config.hotkeys.debounce_ms
        if hotkey_name == "next_cell":
            # 关键修复：F9 语义要求“暂停态可连续步进”，不能继续沿用 F8/F11 的重防抖。
            debounce_ms = self._config.hotkeys.next_cell_debounce_ms
        elif hotkey_name in {"mode_cycle", "layout_cycle", "grid_order_cycle"}:
            debounce_ms = min(debounce_ms, 140)
        elif hotkey_name == "profile_source_toggle":
            debounce_ms = min(debounce_ms, 180)
        elif hotkey_name == "stop":
            debounce_ms = max(debounce_ms, 450)
        elif hotkey_name == "clear_cooldown":
            debounce_ms = max(debounce_ms, 250)
        if (now - last_trigger) * 1000 < debounce_ms:
            return
        self._hotkey_last_trigger_at[hotkey_name] = now
        handler()

    def _mode_display_label(self, mode: str | None = None) -> str:
        resolved_mode = str(mode or self._current_mode or self._requested_mode or "auto")
        return {
            "auto": "自动识别",
            "windowed": "非全屏",
            "fullscreen": "全屏",
            "unknown": "待识别",
        }.get(resolved_mode, resolved_mode)

    def _layout_display_label(self, layout: int | None = None) -> str:
        if layout is None:
            return "自动识别"
        return f"{int(layout)}宫格"

    def _normalize_runtime_grid_order(self, order: str | None) -> str:
        return "column_major" if str(order or "").strip().lower() == "column_major" else "row_major"

    def _profile_source_label(self) -> str:
        return "手动锁定" if self._profile_control_manual else "自动识别"

    def _grid_order_label(self, order: str | None = None) -> str:
        runtime_order = self._normalize_runtime_grid_order(order or self._runtime_grid_order)
        return {
            "row_major": "从左到右/从上到下",
            "column_major": "从上到下/从左到右",
        }.get(runtime_order, "从左到右/从上到下")

    def _runtime_profile_label(self) -> str:
        resolved_mode = self._observed_mode if self._observed_mode in {"windowed", "fullscreen"} else "unknown"
        layout = int(self._observed_layout or self._config.grid.layout)
        return f"{self._mode_display_label(resolved_mode)} {layout}宫格"

    def _requested_runtime_profile_label(self) -> str:
        if not self._profile_control_manual:
            return "现场自动识别"
        return f"{self._mode_display_label(self._requested_mode)} {self._layout_display_label(self._requested_layout)}"

    def _runtime_profile_closure_label(self) -> str:
        if self._profile_control_manual:
            return "已匹配" if self._runtime_profile_matches_request() else "待匹配"
        return "自动识别中"

    def _runtime_meta_summary(self) -> str:
        actual_profile = self._runtime_profile_label()
        requested_profile = self._requested_runtime_profile_label()
        return (
            f"控制: {self._profile_source_label()} | 实际: "
            f"{actual_profile} | 目标: {requested_profile}"
            f" | 闭环: {self._runtime_profile_closure_label()} | 顺序: {self._grid_order_label()}"
        )

    def inspect_runtime_state(self, *, include_candidates: bool = False) -> dict[str, object]:
        self._refresh_window_context()
        self._try_sync_runtime_layout(reason="inspect_runtime")
        payload = {
            "hwnd": None if self._window_info is None else self._window_info.hwnd,
            "pid": None if self._window_info is None else self._window_info.process_id,
            "title": None if self._window_info is None else self._window_info.title,
            "mode": self._current_mode,
            "mode_display": self._mode_display_label(self._current_mode),
            "mode_source": "现场观测",
            "requested_mode": self._requested_mode,
            "requested_mode_display": self._mode_display_label(self._requested_mode),
            "layout": int(self._runtime_layout),
            "layout_display": self._layout_display_label(self._runtime_layout),
            "layout_source": "现场观测",
            "requested_layout": None if self._requested_layout is None else int(self._requested_layout),
            "requested_layout_display": self._layout_display_label(self._requested_layout),
            "profile_source": self._profile_source_label(),
            "runtime_profile": self._runtime_profile_label(),
            "requested_runtime_profile": self._requested_runtime_profile_label(),
            "closure_state": self._runtime_profile_closure_label(),
            "effective_mode": self._effective_mode,
            "effective_layout": int(self._effective_layout),
            "grid_order": self._grid_order_label(),
            "meta": self._runtime_meta_summary(),
            "preview_rect": None if self._preview_rect is None else self._preview_rect.to_bbox(),
            "active_cell_index": None if self._active_cell is None else self._active_cell.index,
        }
        if include_candidates:
            candidates = self._collect_runtime_layout_candidates()
            payload["layout_candidates"] = candidates
            grid_like_candidates = [candidate for candidate in candidates if candidate.get("grid_like")]
            if grid_like_candidates:
                best_candidate = max(grid_like_candidates, key=lambda candidate: float(candidate.get("score") or 0.0))
                payload["best_candidate_layout"] = int(best_candidate["layout"])
                payload["best_candidate_score"] = float(best_candidate["score"])
        return payload

    def _overlay_hotkey_hint(self) -> str:
        parts = [
            self._format_hotkey_hint_entry(self._config.hotkeys.profile_source_toggle, "自动/手动"),
            self._format_hotkey_hint_entry(self._config.hotkeys.mode_cycle, "全屏/非全屏"),
            self._format_hotkey_hint_entry(self._config.hotkeys.layout_cycle, "宫格"),
            self._format_hotkey_hint_entry(self._config.hotkeys.grid_order_cycle, "顺序"),
            self._format_hotkey_hint_entry(self._config.hotkeys.start_pause, "启停"),
            self._format_hotkey_hint_entry(self._config.hotkeys.next_cell, "步进"),
            self._format_hotkey_hint_entry(self._config.hotkeys.stop, "停止"),
            self._format_hotkey_hint_entry(self._config.hotkeys.emergency_recover, "恢复"),
            self._format_hotkey_hint_entry(self._config.hotkeys.clear_cooldown, "清冷却"),
        ]
        return "  ".join(part for part in parts if part)

    def _hotkey_summary(self, prefix: str) -> str:
        parts = [
            self._format_hotkey_hint_entry(self._config.hotkeys.profile_source_toggle, "自动/手动"),
            self._format_hotkey_hint_entry(self._config.hotkeys.mode_cycle, "模式"),
            self._format_hotkey_hint_entry(self._config.hotkeys.layout_cycle, "宫格"),
            self._format_hotkey_hint_entry(self._config.hotkeys.grid_order_cycle, "顺序"),
            self._format_hotkey_hint_entry(self._config.hotkeys.start_pause, "启停"),
            self._format_hotkey_hint_entry(self._config.hotkeys.next_cell, "步进"),
            self._format_hotkey_hint_entry(self._config.hotkeys.stop, "停止"),
            self._format_hotkey_hint_entry(self._config.hotkeys.emergency_recover, "恢复"),
            self._format_hotkey_hint_entry(self._config.hotkeys.clear_cooldown, "清冷却"),
        ]
        active_parts = [part for part in parts if part]
        if not active_parts:
            return prefix
        return f"{prefix} | " + " | ".join(active_parts)

    def _format_hotkey_hint_entry(self, key_name: str | None, label: str) -> str:
        if self._hotkey_disabled(key_name):
            return ""
        return f"{key_name} {label}"

    def _publish_status(self, message: str, details: str, level: str) -> None:
        if not self._status:
            return
        meta = self._runtime_meta_summary()
        hotkey_hint = self._overlay_hotkey_hint()
        status_key = (message, details, level, meta, hotkey_hint)
        if level == "info" and status_key == self._last_published_status_key:
            return
        self._status.publish(
            title="视频轮巡助手",
            message=message,
            details=details,
            level=level,
            meta=meta,
            hotkey_hint=hotkey_hint,
        )
        self._last_published_status_key = status_key

    def _publish_current_state(self, *, level: str = "info", remaining_seconds: int | None = None) -> None:
        self._publish_status(
            message=self._state_message(remaining_seconds=remaining_seconds),
            details=self._state_details(),
            level=level,
        )

    def _state_details(self) -> str:
        if self._state == SchedulerState.PAUSED:
            return (
                f"已暂停。界面正常按 {self._config.hotkeys.start_pause}；"
                f"异常冷却先按 {self._config.hotkeys.clear_cooldown}；"
                f"界面异常按 {self._config.hotkeys.emergency_recover}。"
            )
        control_hint = (
            "当前为手动锁定：程序直接使用你设定的模式和宫格，不再做模式/宫格自动识别。"
            if self._profile_control_manual
            else "当前为自动识别：程序会按现场界面自动识别全屏/非全屏和宫格。"
        )
        stage_hint = {
            SchedulerState.IDLE: "等待进入下一轮动作。",
            SchedulerState.PREPARE_TARGET: "正在校验宫格态并准备下一路点击。",
            SchedulerState.SELECT_TARGET: "正在单击选中目标画面。",
            SchedulerState.SELECT_CONFIRM: "正在确认当前目标已经选中。",
            SchedulerState.ZOOM_IN: "正在双击放大当前目标。",
            SchedulerState.ZOOM_CONFIRM: "正在确认放大是否成功。",
            SchedulerState.ZOOM_DWELL: "当前大图停留观察中，不会切路。",
            SchedulerState.ZOOM_OUT: "正在双击返回宫格。",
            SchedulerState.GRID_CONFIRM: "正在确认已经回到宫格。",
            SchedulerState.GRID_DWELL: "正在宫格态短暂停留，随后切下一路。",
            SchedulerState.NEXT: "正在推进到下一路。",
            SchedulerState.PAUSED: "已暂停。",
            SchedulerState.ERROR_RECOVERY: "当前进入恢复链，程序会先尝试回到安全宫格态。",
            SchedulerState.STOPPED: "程序已停止。",
        }.get(self._state, "等待状态更新。")
        return f"{control_hint} {stage_hint}"

    def _state_message(self, *, remaining_seconds: int | None = None) -> str:
        if self._state == SchedulerState.PAUSED:
            if self._last_pause_reason == "runtime_profile_mismatch":
                if self._runtime_profile_matches_request():
                    return f"已暂停：目标已匹配，可按 {self._config.hotkeys.start_pause} 继续"
                return (
                    f"已暂停：目标未匹配（实际 {self._runtime_profile_label()} / 目标 {self._requested_runtime_profile_label()}）"
                )
            if self._manual_next_target_index is not None and self._cells:
                if self._manual_next_queue_depth > 1:
                    return (
                        f"已预选 {self._manual_next_queue_depth} 次下一路："
                        f"{self._cell_hint(self._cells[self._manual_next_target_index])}"
                    )
                return f"下一路已预选：{self._cell_hint(self._cells[self._manual_next_target_index])}"
            if self._pending_pause_ack_next_requests > 0:
                return f"暂停确认中，已缓存 {self._pending_pause_ack_next_requests} 次下一路"
            return f"已暂停：{self._cell_hint(self._active_cell)}"
        if self._state == SchedulerState.PREPARE_TARGET:
            return f"准备：{self._cell_hint(self._active_cell)}"
        if self._state in {SchedulerState.SELECT_TARGET, SchedulerState.SELECT_CONFIRM}:
            return f"已选中 {self._cell_hint(self._active_cell)}，正在确认后双击放大"
        if self._state == SchedulerState.ZOOM_IN:
            return f"正在双击放大 {self._cell_hint(self._active_cell)}"
        if self._state == SchedulerState.ZOOM_CONFIRM:
            return f"正在确认放大 {self._cell_hint(self._active_cell)}"
        if self._state == SchedulerState.ZOOM_DWELL:
            # 关键修复：浮窗只提示“停留中”，不再每秒刷倒计时，避免提示词看起来卡住。
            return f"已放大 {self._cell_hint(self._active_cell)}，停留中"
        if self._state == SchedulerState.ZOOM_OUT:
            return "正在双击返回宫格"
        if self._state == SchedulerState.GRID_CONFIRM:
            return "正在确认已回到宫格"
        if self._state == SchedulerState.GRID_DWELL:
            return "已回到宫格，准备切下一路"
        if self._state == SchedulerState.ERROR_RECOVERY:
            return f"恢复中：{self._cell_hint(self._active_cell)}"
        if self._state == SchedulerState.NEXT:
            return f"切换下一路：{self._cell_hint(self._active_cell)}"
        return "等待状态更新..."

    def _perform_pointer_action(
        self,
        *,
        action_name: str,
        point_getter,
        controller_action,
        failure_target_state: SchedulerState,
        recover_on_failure: bool,
        allow_paused_action: bool = False,
        skip_guard_before: bool = False,
        guard_expected_view_before: VisualViewState | None = None,
        guard_expected_view_after: VisualViewState | None = None,
    ) -> bool:
        last_error: Exception | None = None
        for attempt in (1, 2):
            if attempt == 2:
                try:
                    self._refresh_window_context()
                except Exception as exc:
                    last_error = exc
                    self._logger.warning(
                        "CONTROL_RETRY action=%s attempt=%s refresh_context_failed=%s",
                        action_name,
                        attempt,
                        exc,
                    )
                    continue

            if self._config.runtime_guard.verify_before_action and not skip_guard_before:
                # 关键修复：点击前必须校验当前仍处在预期视图，避免在同一窗口的错误页上继续点击。
                if not self._run_runtime_guard(
                    stage=f"before_{action_name}",
                    expected_view=guard_expected_view_before,
                    inspect_view=guard_expected_view_before is not None,
                ):
                    return False
                if self._stop_requested:
                    return False
                if not allow_paused_action and self._state == SchedulerState.PAUSED:
                    return False

            point = point_getter()
            if not self._point_is_actionable(point):
                last_error = ControllerActionError(
                    f"point={point} is outside the actionable area client={getattr(self._window_info, 'client_rect', None)} "
                    f"monitor={getattr(self._window_info, 'monitor_rect', None)}"
                )
                self._logger.warning(
                    "CONTROL_POINT_INVALID action=%s attempt=%s point=%s client_rect=%s monitor_rect=%s",
                    action_name,
                    attempt,
                    point,
                    getattr(self._window_info, "client_rect", None),
                    getattr(self._window_info, "monitor_rect", None),
                )
                continue

            try:
                self._input_guard.mark_programmatic_action()
                controller_action(point)
                if self._config.runtime_guard.verify_after_action:
                    if self._config.runtime_guard.post_action_wait_ms > 0:
                        wait_seconds = self._config.runtime_guard.post_action_wait_ms / 1000.0
                        if allow_paused_action:
                            # 关键修复：F9 的暂停态预选本来就需要保持 PAUSED，
                            # 因此这里不能把“当前仍处于暂停”误判成动作失败。
                            end_time = time.monotonic() + wait_seconds
                            while time.monotonic() < end_time:
                                self._consume_commands()
                                if self._stop_requested:
                                    return False
                                if self._recovery_requested and not self._recovery_in_progress:
                                    return False
                                time.sleep(0.05)
                        else:
                            if not self._wait_interruptible(wait_seconds, allow_pause=True):
                                return False
                    if not self._run_runtime_guard(
                        stage=f"after_{action_name}",
                        expected_view=guard_expected_view_after,
                        inspect_view=guard_expected_view_after is not None,
                    ):
                        return False
                    if self._stop_requested:
                        return False
                    if not allow_paused_action and self._state == SchedulerState.PAUSED:
                        return False
                return True
            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "CONTROL_FAILED action=%s attempt=%s point=%s error=%s",
                    action_name,
                    attempt,
                    point,
                    exc,
                )

        if recover_on_failure:
            self._logger.warning(
                "CONTROL_ABORT action=%s failure_target_state=%s error=%s",
                action_name,
                failure_target_state,
                last_error,
            )
            self._plan_recovery(failure_target_state, f"control_failed:{action_name}")
            self._state = SchedulerState.ERROR_RECOVERY
        return False

    def _perform_grid_recovery_action(
        self,
        *,
        action_name: str,
        failure_target_state: SchedulerState,
        recover_on_failure: bool,
    ) -> bool:
        last_error: Exception | None = None
        for attempt in (1, 2):
            if attempt == 2:
                try:
                    self._refresh_window_context()
                except Exception as exc:
                    last_error = exc
                    self._logger.warning(
                        "CONTROL_RETRY action=%s attempt=%s refresh_context_failed=%s",
                        action_name,
                        attempt,
                        exc,
                    )
                    continue

            hwnd = getattr(self._window_info, "hwnd", None)
            if hwnd is None:
                last_error = ControllerActionError(f"No target window is available for {action_name}")
                self._logger.warning(
                    "CONTROL_FAILED action=%s attempt=%s hwnd=%s error=%s",
                    action_name,
                    attempt,
                    hwnd,
                    last_error,
                )
                continue

            try:
                self._input_guard.mark_programmatic_action()
                self._controller.recover_to_grid(hwnd=hwnd)
                self._logger.info("CONTROL action_type=%s hwnd=%s method=keyboard_escape", action_name, hwnd)
                return True
            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "CONTROL_FAILED action=%s attempt=%s hwnd=%s error=%s",
                    action_name,
                    attempt,
                    hwnd,
                    exc,
                )

        if recover_on_failure:
            self._logger.warning(
                "CONTROL_ABORT action=%s failure_target_state=%s error=%s",
                action_name,
                failure_target_state,
                last_error,
            )
            self._plan_recovery(failure_target_state, f"control_failed:{action_name}")
            self._state = SchedulerState.ERROR_RECOVERY
        else:
            self._logger.error("CONTROL_ABORT action=%s error=%s", action_name, last_error)
        return False

    def _perform_zoom_out_grid_recovery_action(
        self,
        *,
        action_name: str,
        failure_target_state: SchedulerState,
        recover_on_failure: bool,
        allow_paused_action: bool,
    ) -> bool:
        if self._window_info is None:
            return False
        client_origin = (self._window_info.client_rect.left, self._window_info.client_rect.top)
        return self._perform_pointer_action(
            action_name=action_name,
            point_getter=self._current_zoom_out_point,
            controller_action=lambda point: self._controller.restore_zoom(
                point,
                hwnd=self._window_info.hwnd,
                client_origin=client_origin,
            ),
            failure_target_state=failure_target_state,
            recover_on_failure=recover_on_failure,
            allow_paused_action=allow_paused_action,
            skip_guard_before=True,
        )

    def _point_is_actionable(self, point: tuple[int, int]) -> bool:
        if not self._window_info:
            return False
        return (
            self._window_info.monitor_rect.contains_point(point)
            and self._window_info.client_rect.contains_point(point)
        )

    def _set_zoom_confirm_poll_boost_cycles(self, cycles: int) -> None:
        self._zoom_confirm_poll_boost_cycles_remaining = max(0, cycles)
