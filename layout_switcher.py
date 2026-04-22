from __future__ import annotations

"""窗口分割布局切换。

这层能力只做一件事：
1. 打开顶部工具栏里的“窗口分割”面板
2. 按已验证过的分组与编号点击目标布局
3. 关闭面板，回到主预览区

现场验证结果：
- 4  宫格 -> 平均 / 4
- 6  宫格 -> 水平 / 6
- 9  宫格 -> 平均 / 9
- 12 宫格 -> 其他 / 12
- 13 宫格 -> 其他 / 13

注意：
- 左侧收藏夹树里的“9个画面 / 6个画面 / 4个画面”不是实际布局切换入口。
- 13 宫格仅用于现场切换与观察；当前轮询主流程仍只支持 4 / 6 / 9 / 12。
"""

import time
import subprocess
import sys
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageGrab, ImageStat

try:
    from pywinauto import Desktop
except Exception:  # pragma: no cover - 允许在非 Windows / 未装 UIA 依赖环境下做静态自测
    Desktop = None

from common import Rect, VisualViewState
from grid_mapper import GridMapper


SECTION_TITLES = ("平均", "高亮分割", "水平", "垂直", "其他")
FULLSCREEN_TOGGLE_TITLES = ("全屏", "退出全屏")
NATIVE_RENDER_PROCESS_NAMES = ["VSClient.exe"]


class LayoutSwitchError(RuntimeError):
    pass


@dataclass(frozen=True)
class LayoutSwitchTarget:
    layout: int
    section: str
    label: str


@dataclass(frozen=True)
class RuntimeLayoutOption:
    section: str
    label: str
    rect: Rect
    selected: bool = False


DEFAULT_LAYOUT_SWITCH_TARGETS = {
    4: LayoutSwitchTarget(layout=4, section="平均", label="4"),
    6: LayoutSwitchTarget(layout=6, section="水平", label="6"),
    9: LayoutSwitchTarget(layout=9, section="平均", label="9"),
    12: LayoutSwitchTarget(layout=12, section="其他", label="12"),
    13: LayoutSwitchTarget(layout=13, section="其他", label="13"),
}
LAYOUT_BY_SECTION_AND_LABEL = {
    (target.section, target.label): target.layout for target in DEFAULT_LAYOUT_SWITCH_TARGETS.values()
}


def resolve_layout_switch_target(layout: int) -> LayoutSwitchTarget:
    target = DEFAULT_LAYOUT_SWITCH_TARGETS.get(int(layout))
    if target is None:
        raise LayoutSwitchError(f"Unsupported layout switch target: {layout}")
    return target


def assign_layout_section(header_rows: list[tuple[str, int]], checkbox_top: int) -> str | None:
    """按“离它最近且在它上方的标题”把数字选项归到对应分组。"""

    selected: str | None = None
    for title, top in sorted(header_rows, key=lambda item: item[1]):
        if top <= checkbox_top:
            selected = title
            continue
        break
    return selected


def build_layout_option_index(
    header_rects: list[tuple[str, Rect]],
    checkbox_rects: list[tuple[str, Rect]],
) -> dict[tuple[str, str], list[Rect]]:
    header_rows = [(title, rect.top) for title, rect in header_rects]
    grouped: dict[tuple[str, str], list[Rect]] = {}
    for label, rect in sorted(checkbox_rects, key=lambda item: (item[1].top, item[1].left)):
        section = assign_layout_section(header_rows, rect.top)
        if not section:
            continue
        grouped.setdefault((section, label), []).append(rect)
    return grouped


class LayoutSwitcher:
    def __init__(self, window_manager, controller, logger, *, config=None, detector=None, native_client=None):
        self._window_manager = window_manager
        self._controller = controller
        self._logger = logger
        self._desktop = None
        self._config = config
        self._detector = detector
        self._grid_mapper = GridMapper(config.grid) if config is not None else None
        self._native_client = native_client

    def _native_runtime_available(self) -> bool:
        return bool(self._native_client is not None and getattr(self._native_client, "enabled", False))

    def _require_desktop(self):
        if Desktop is None:
            raise LayoutSwitchError("pywinauto/Desktop is unavailable in the current environment; runtime UIA operations require Windows with project dependencies installed")
        if self._desktop is None:
            self._logger.info("layout_switcher creating UIA desktop backend")
            self._desktop = Desktop(backend="uia")
        return self._desktop

    def _resolve_target_window(self, target_window=None):
        if target_window is None:
            return self._window_manager.find_target_window()
        refresh = getattr(self._window_manager, "refresh_target_window", None)
        if callable(refresh):
            try:
                return refresh(target_window)
            except Exception:
                pass
        return target_window

    def _focus_target_window(self, hwnd: int, *, action: str, required: bool) -> bool:
        focused = bool(self._window_manager.focus_window(hwnd))
        if focused:
            return True
        message = f"Could not focus target window before {action}"
        if required:
            raise LayoutSwitchError(message)
        self._logger.warning(message)
        return False

    def _guard_layout_switch_error(self, message: str) -> None:
        guard_config = None if self._config is None else getattr(self._config, "layout_switch", None)
        if guard_config is None or guard_config.fail_closed_on_guard_error:
            raise LayoutSwitchError(message)
        self._logger.warning(message)

    def _layout_switch_guard_enabled(self) -> bool:
        if self._config is None:
            return False
        guard_config = getattr(self._config, "layout_switch", None)
        return bool(guard_config is not None and guard_config.require_cleared_scene_before_switch)

    def _guard_candidate_layouts(self) -> list[int]:
        if self._config is None:
            return [4, 6, 9, 12]
        candidates = {4, 6, 9, 12}
        candidates.add(int(self._config.grid.layout))
        candidates.update(int(layout) for layout in self._config.grid.layout_overrides)
        return sorted(layout for layout in candidates if layout in {4, 6, 9, 12})

    @staticmethod
    def _grid_guard_score(metrics: dict[str, float]) -> float:
        repeated_grid_bonus = 30.0 if float(metrics.get("repeated_grid_like", 0.0)) == 1.0 else 0.0
        mean_strength = float(metrics.get("grid_divider_mean_strength", 0.0))
        expected_count = max(1.0, float(metrics.get("grid_divider_expected_count", 0.0)))
        structure_ratio = float(metrics.get("structure_changed_ratio", 0.0)) * 100.0
        return round((mean_strength * expected_count) + structure_ratio + repeated_grid_bonus, 4)

    def _detect_runtime_mode(self, target_window) -> str:
        if self._config is None:
            return "auto"
        requested_mode = getattr(self._config.profiles, "active_mode", "auto")
        return self._window_manager.detect_mode(target_window, requested_mode)

    def _detect_active_grid_scene(self, preview_rect: Rect, *, preview_image: Image.Image) -> dict[str, object] | None:
        if self._detector is None or self._grid_mapper is None:
            return None

        best_candidate: dict[str, object] | None = None
        for layout in self._guard_candidate_layouts():
            candidate_cells = self._grid_mapper.build_cells(preview_rect, layout)
            if not candidate_cells:
                continue
            sample_indexes = sorted({0, len(candidate_cells) // 2, len(candidate_cells) - 1})
            for candidate_index in sample_indexes:
                candidate_cell = candidate_cells[candidate_index]
                actual_view, metrics = self._detector.classify_runtime_view(
                    preview_rect,
                    candidate_cell.rect,
                    preview_image=preview_image,
                )
                grid_like = actual_view == VisualViewState.GRID or self._detector.matches_expected_view(
                    VisualViewState.GRID,
                    metrics,
                )
                if not grid_like:
                    continue
                score = self._grid_guard_score(metrics)
                candidate = {
                    "layout": int(layout),
                    "candidate_index": int(candidate_index),
                    "actual_view": actual_view.value,
                    "score": score,
                    "metrics": dict(metrics),
                }
                if best_candidate is None or float(candidate["score"]) > float(best_candidate["score"]):
                    best_candidate = candidate
        return best_candidate

    @staticmethod
    def _zoom_guard_rect(preview_rect: Rect) -> Rect:
        margin_x = max(24, int(preview_rect.width * 0.24))
        margin_y = max(24, int(preview_rect.height * 0.24))
        max_margin_x = max(1, (preview_rect.width - 64) // 2)
        max_margin_y = max(1, (preview_rect.height - 64) // 2)
        margin_x = min(margin_x, max_margin_x)
        margin_y = min(margin_y, max_margin_y)
        return preview_rect.inset(margin_x, margin_y)

    def _detect_zoomed_scene_state(self, preview_rect: Rect, *, preview_image: Image.Image) -> dict[str, object]:
        if self._detector is None:
            return {
                "actual_view": VisualViewState.UNKNOWN.value,
                "zoom_like": False,
                "scene_cleared": False,
                "metrics": {},
            }
        active_rect = self._zoom_guard_rect(preview_rect)
        actual_view, metrics = self._detector.classify_runtime_view(
            preview_rect,
            active_rect,
            preview_image=preview_image,
        )
        zoom_like = actual_view == VisualViewState.ZOOMED or self._detector.matches_expected_view(
            VisualViewState.ZOOMED,
            metrics,
        )
        scene_cleared = actual_view == VisualViewState.UNKNOWN and float(metrics.get("flat_interface_like", 0.0)) == 1.0
        return {
            "actual_view": actual_view.value,
            "zoom_like": zoom_like,
            "scene_cleared": scene_cleared,
            "metrics": dict(metrics),
        }

    def _ensure_layout_switch_scene_is_clear(self, target_window) -> None:
        if not self._layout_switch_guard_enabled():
            return
        if self._detector is None or self._grid_mapper is None:
            self._guard_layout_switch_error(
                "Layout switch protection is enabled but runtime detector is unavailable; refusing to touch 窗口分割."
            )
            return

        preview_rect = self._resolve_preview_probe_rect(target_window)
        if preview_rect is None:
            self._guard_layout_switch_error(
                "Layout switch protection could not resolve the preview area; refusing to touch 窗口分割."
            )
            return
        try:
            preview_image = self._detector.capture_image(preview_rect)
        except Exception as exc:
            self._guard_layout_switch_error(
                f"Layout switch protection could not capture the current preview: {exc}; refusing to touch 窗口分割."
            )
            return

        detected_mode = self._detect_runtime_mode(target_window)
        grid_candidate = self._detect_active_grid_scene(preview_rect, preview_image=preview_image)
        if grid_candidate is not None:
            self._logger.info(
                "layout_switch guard allowing stable grid scene mode=%s layout=%s cell=%s view=%s score=%s",
                detected_mode,
                grid_candidate["layout"],
                grid_candidate["candidate_index"],
                grid_candidate["actual_view"],
                grid_candidate["score"],
            )
            return

        zoom_state = self._detect_zoomed_scene_state(preview_rect, preview_image=preview_image)
        if bool(zoom_state["zoom_like"]):
            raise LayoutSwitchError(
                "A live monitoring view is still open; close all monitoring views before switching layout. "
                f"mode={detected_mode} view={zoom_state['actual_view']}"
            )
        if not bool(zoom_state["scene_cleared"]):
            raise LayoutSwitchError(
                "Could not confirm that the client has been cleared; the preview still looks like a dynamic scene. "
                "Close all monitoring views before switching layout. "
                f"mode={detected_mode} view={zoom_state['actual_view']} "
                f"flat_interface_like={zoom_state['metrics'].get('flat_interface_like')}"
            )
        self._logger.info(
            "layout_switch clear-scene guard passed mode=%s view=%s metrics=%s",
            detected_mode,
            zoom_state["actual_view"],
            zoom_state["metrics"],
        )

    def switch_layout(self, layout: int, *, target_window=None) -> dict[str, object]:
        return self._switch_layout_internal(layout, target_window=target_window, require_cleared_scene=True)

    def switch_runtime_layout(self, layout: int, *, target_window=None) -> dict[str, object]:
        return self._switch_layout_internal(layout, target_window=target_window, require_cleared_scene=False)

    def detect_active_grid_layout_candidate(self, *, target_window=None) -> dict[str, object] | None:
        if self._detector is None or self._grid_mapper is None:
            return None
        target_window = self._resolve_target_window(target_window)
        preview_rect = self._resolve_preview_probe_rect(target_window)
        preview_image = self._capture_preview_probe(preview_rect)
        if preview_rect is None or preview_image is None:
            return None
        candidate = self._detect_active_grid_scene(preview_rect, preview_image=preview_image)
        if candidate is not None:
            self._logger.info(
                "layout_switch visual grid candidate layout=%s score=%s cell=%s view=%s",
                candidate["layout"],
                candidate["score"],
                candidate["candidate_index"],
                candidate["actual_view"],
            )
        return candidate

    def _switch_layout_internal(
        self,
        layout: int,
        *,
        target_window=None,
        require_cleared_scene: bool,
    ) -> dict[str, object]:
        target = resolve_layout_switch_target(layout)
        self._logger.info("layout_switch begin layout=%s require_cleared_scene=%s", layout, require_cleared_scene)
        target_window = self._resolve_target_window(target_window)
        self._logger.info("layout_switch target_resolved layout=%s hwnd=%s", layout, target_window.hwnd)
        self._focus_target_window(target_window.hwnd, action="switch_layout_prepare", required=True)
        time.sleep(0.2)
        if require_cleared_scene:
            self._ensure_layout_switch_scene_is_clear(target_window)

        preview_rect = self._resolve_preview_probe_rect(target_window)
        preview_before = self._capture_preview_probe(preview_rect)
        native_selection: dict[str, object] | None = None
        native_state = self._native_get_runtime_layout_state(
            target_window,
            open_layout_panel=True,
            close_panel=False,
        )
        native_option = self._resolve_runtime_option_from_native_state(native_state, target)
        if native_option is not None:
            option = native_option
            was_selected = option.selected

            if was_selected:
                option_selected = True
                self._logger.info(
                    "layout_switch native target already selected layout=%s section=%s label=%s",
                    layout,
                    option.section,
                    option.label,
                )
            else:
                try:
                    native_selection = self._native_select_runtime_layout(
                        target_window,
                        section=target.section,
                        label=target.label,
                        close_panel=True,
                    )
                except Exception as exc:
                    self._logger.warning(
                        "layout_switch native select fallback to controller click layout=%s: %s",
                        layout,
                        exc,
                    )
                    self._focus_target_window(target_window.hwnd, action=f"switch_layout_{layout}", required=True)
                    self._controller.click_once(
                        option.rect.center,
                        hwnd=target_window.hwnd,
                        action_type=f"switch_layout_{layout}",
                    )
                    time.sleep(0.45)
                    option_selected = None
                else:
                    selected_option_payload = native_selection.get("option")
                    selected_option = self._runtime_option_from_native_descriptor(selected_option_payload)
                    if selected_option is not None:
                        option = selected_option
                    selection_confirmed = bool(native_selection.get("selectionConfirmed", False))
                    option_selected = bool(native_selection.get("alreadySelected", False)) or selection_confirmed or option.selected
                    if not bool(native_selection.get("panelClosed", False)):
                        self._logger.warning(
                            "layout_switch native panel close not confirmed layout=%s close_method=%s fallback=%s",
                            layout,
                            native_selection.get("closeMethod"),
                            native_selection.get("closeFallbackUsed"),
                        )
                    self._logger.info(
                        "layout_switch native select layout=%s method=%s already_selected=%s selection_confirmed=%s close_method=%s",
                        layout,
                        native_selection.get("method"),
                        native_selection.get("alreadySelected"),
                        native_selection.get("selectionConfirmed"),
                        native_selection.get("closeMethod"),
                    )
        else:
            desktop = self._require_desktop()
            root = desktop.window(handle=target_window.hwnd)
            self._open_layout_panel(root, target_window.hwnd)
            # 关键修复：面板弹出后必须重新抓最新 root；旧 root 偶发会保留过期控件树。
            panel_root = desktop.window(handle=target_window.hwnd)
            options = self._collect_runtime_options(panel_root)
            option = self._resolve_runtime_option(options, target)
            was_selected = option.selected

            # 这里必须走真实点击语义；单纯 toggle 勾选框不会真正触发布局切换。
            self._focus_target_window(target_window.hwnd, action=f"switch_layout_{layout}", required=True)
            self._controller.click_once(option.rect.center, hwnd=target_window.hwnd, action_type=f"switch_layout_{layout}")
            self._logger.info(
                "layout_switch_target layout=%s section=%s label=%s rect=%s",
                layout,
                option.section,
                option.label,
                option.rect,
            )
            time.sleep(0.45)

            # 关键修复：某些全屏场景下，点击布局项后立即重建 UIA 控件树会长时间卡住，
            # 9 宫格切换尤其明显。这里不再做“点击后读取勾选态”的重 UIA 刷新，
            # 而是直接走轻量级的快速关面板路径，最后只用视觉结果确认是否真正切图。
            option_selected: bool | None = None
            self._logger.info("layout_switch skipping post-click UIA refresh layout=%s", layout)

        if native_selection is None:
            # 关键修复：回退到旧 UIA 路径时，点完布局项后仍不再主动关面板。
            # 现场复测表明，这个阶段无论是 UIA 判开、再次点工具栏按钮，还是额外 dismiss/ESC，
            # 都可能把全屏 9 宫格切换拖进长时间卡死。后续只依赖视觉探针确认真实宫格是否变化。
            self._logger.info("layout_switch deferring explicit panel close; relying on visual confirmation only")
        else:
            self._logger.info(
                "layout_switch native transaction completed layout=%s panel_closed=%s close_method=%s",
                layout,
                native_selection.get("panelClosed"),
                native_selection.get("closeMethod"),
            )

        # 关键修复：不能只验证“窗口分割面板里的选项被点到了”，还要验证预览区真的变化了。
        # 否则在非政务网、卡顿或客户端无响应时，命令会误报成功，实际宫格并没有切换。
        visual_metrics = {"mean_diff": 0.0, "changed_ratio": 0.0}
        if preview_before is not None and not was_selected:
            self._logger.info("layout_switch visual confirmation begin layout=%s", layout)
            visual_metrics = self._wait_for_visual_layout_change(preview_rect, preview_before)
            if not self._layout_change_confirmed(visual_metrics):
                raise LayoutSwitchError(
                    f"Layout switch to {layout} was not visually confirmed: {visual_metrics}"
                )
            self._logger.info("layout_switch visual confirmation success layout=%s metrics=%s", layout, visual_metrics)

        return {
            "layout": layout,
            "section": option.section,
            "label": option.label,
            "option_rect": option.rect.to_bbox(),
            "option_selected": option_selected,
            "native_panel_close_confirmed": None
            if native_selection is None
            else bool(native_selection.get("panelClosed", False)),
            "native_panel_close_method": None if native_selection is None else native_selection.get("closeMethod"),
            "visual_change": visual_metrics,
        }

    def switch_mode(self, mode: str, *, target_window=None) -> dict[str, object]:
        if mode not in {"windowed", "fullscreen"}:
            raise LayoutSwitchError(f"Unsupported runtime mode switch target: {mode}")

        target_window = self._resolve_target_window(target_window)
        detected_before = self._detect_actual_mode(target_window)
        if detected_before == mode:
            return {
                "mode": mode,
                "changed": False,
                "detected_before": detected_before,
                "detected_after": detected_before,
            }

        desktop = self._require_desktop()
        self._focus_target_window(target_window.hwnd, action=f"switch_mode_{mode}_prepare", required=True)
        time.sleep(0.12)
        root = desktop.window(handle=target_window.hwnd)
        toggle_control = None
        toggle_rect: Rect | None = None
        try:
            toggle_control = self._fullscreen_toggle_control(root)
            toggle_rect = self._rect_from_control(toggle_control)
        except Exception as exc:
            self._logger.info("switch_mode python/uia toggle probe unavailable mode=%s: %s", mode, exc)

        attempts: list[tuple[str, object, tuple[int, int] | None]] = [
            (
                "switch_mode_toggle_native_invoke",
                lambda target=target_window, expected=mode: self._invoke_fullscreen_toggle_native(
                    target,
                    expected_mode=expected,
                ),
                None,
            ),
        ]
        if toggle_control is not None and toggle_rect is not None:
            attempts.extend(
                [
                    (
                        "switch_mode_toggle_invoke",
                        lambda ctrl=toggle_control: self._invoke_control(ctrl, action_type=f"switch_mode_{mode}_invoke"),
                        toggle_rect.center,
                    ),
                    (
                        "switch_mode_toggle_click_input",
                        lambda ctrl=toggle_control: self._click_control_input(
                            ctrl,
                            action_type=f"switch_mode_{mode}_click_input",
                        ),
                        toggle_rect.center,
                    ),
                    (
                        "switch_mode_toggle_pointer",
                        lambda point=toggle_rect.center, hwnd=target_window.hwnd: self._controller.click_once(
                            point,
                            hwnd=hwnd,
                            action_type=f"switch_mode_{mode}_pointer",
                        ),
                        toggle_rect.center,
                    ),
                    (
                        "switch_mode_toggle_helper",
                        lambda point=toggle_rect.center: self._click_point_with_helper(point),
                        toggle_rect.center,
                    ),
                ]
            )
        last_detected = detected_before
        for action_name, action, action_point in attempts:
            self._logger.info("CONTROL action_type=%s point=%s backend=mode_switch", action_name, action_point)
            self._focus_target_window(target_window.hwnd, action=action_name, required=True)
            action()
            changed, refreshed_window, detected_after = self._wait_for_mode_change(
                target_window,
                expected_mode=mode,
                timeout_seconds=2.6,
            )
            last_detected = detected_after
            if changed:
                return {
                    "mode": mode,
                    "changed": True,
                    "detected_before": detected_before,
                    "detected_after": detected_after,
                    "toggle_rect": None if toggle_rect is None else toggle_rect.to_bbox(),
                    "hwnd": refreshed_window.hwnd,
                }
        raise LayoutSwitchError(
            f"Mode switch to {mode} was not confirmed. detected_before={detected_before} detected_after={last_detected}"
        )

    def detect_current_layout(self, *, target_window=None) -> int | None:
        """读取当前窗口分割面板里真正被选中的布局。

        这里只做“读取当前真实布局”，不触发布局切换。
        当主流程发现 config.grid.layout 与现场不一致时，优先依赖这条 UIA 读数，
        避免再靠视觉启发式去猜 4/6/9/12。
        """
        target_window = self._resolve_target_window(target_window)
        self._focus_target_window(target_window.hwnd, action="detect_current_layout", required=True)
        time.sleep(0.2)

        native_state = self._native_get_runtime_layout_state(
            target_window,
            open_layout_panel=True,
            close_panel=True,
        )
        native_layout = self._selected_layout_from_native_state(native_state)
        if native_layout is not None:
            selected_section = None if native_state is None else native_state.get("selectedSection")
            selected_label = None if native_state is None else native_state.get("selectedLabel")
            self._logger.info(
                "runtime_layout_detected_native layout=%s section=%s label=%s",
                native_layout,
                selected_section,
                selected_label,
            )
            self._window_manager.focus_window(target_window.hwnd)
            time.sleep(0.1)
            return native_layout

        desktop = self._require_desktop()
        root = desktop.window(handle=target_window.hwnd)
        self._open_layout_panel(
            root,
            target_window.hwnd,
            allow_pointer_fallback=True,
            prefer_pointer_fallback=True,
        )
        # 关键修复：detect_current_layout 读取选项和关闭面板时，也要基于最新 root。
        panel_root = desktop.window(handle=target_window.hwnd)
        try:
            options = self._collect_runtime_options(panel_root)
            for key, candidates in options.items():
                layout = LAYOUT_BY_SECTION_AND_LABEL.get(key)
                if layout is None:
                    continue
                if any(option.selected for option in candidates):
                    self._logger.info(
                        "runtime_layout_detected layout=%s section=%s label=%s",
                        layout,
                        key[0],
                        key[1],
                    )
                    return layout
            return None
        finally:
            try:
                self._close_layout_panel(
                    panel_root,
                    target_window.hwnd,
                    allow_pointer_fallback=True,
                    prefer_pointer_fallback=True,
                )
            except Exception as exc:
                # 关键修复：即使面板关闭失败，也先把主窗口重新拉回前台，
                # 避免下一步 PREPARE_TARGET 立刻被 VSClient 辅窗前台漂移打断。
                self._window_manager.focus_window(target_window.hwnd)
                time.sleep(0.15)
                self._logger.warning("detect_current_layout failed to close layout panel cleanly: %s", exc)
            else:
                self._window_manager.focus_window(target_window.hwnd)
                time.sleep(0.1)

    def _detect_actual_mode(self, target_window) -> str:
        return self._window_manager.detect_mode(target_window, "auto")

    def _wait_for_mode_change(
        self,
        target_window,
        *,
        expected_mode: str,
        timeout_seconds: float,
    ) -> tuple[bool, object, str]:
        deadline = time.monotonic() + timeout_seconds
        current_window = target_window
        last_detected = self._detect_actual_mode(current_window)
        while time.monotonic() < deadline:
            time.sleep(0.15)
            try:
                current_window = self._resolve_target_window(current_window)
                last_detected = self._detect_actual_mode(current_window)
            except Exception:
                continue
            if last_detected == expected_mode:
                return True, current_window, last_detected
        return False, current_window, last_detected

    def _fullscreen_toggle_control(self, root):
        for title in FULLSCREEN_TOGGLE_TITLES:
            for control_type in ("CheckBox", "Button"):
                try:
                    ctrl = root.child_window(title=title, control_type=control_type)
                    if ctrl.exists(timeout=0.1):
                        rect = self._rect_from_control(ctrl)
                        if rect.width > 0 and rect.height > 0:
                            return ctrl
                except Exception:
                    continue

        for control_type in ("CheckBox", "Button"):
            try:
                descendants = root.descendants(control_type=control_type)
            except Exception:
                descendants = []
            for ctrl in descendants:
                text = (ctrl.window_text() or "").strip()
                if text not in FULLSCREEN_TOGGLE_TITLES:
                    continue
                rect = self._rect_from_control(ctrl)
                if rect.width > 0 and rect.height > 0:
                    return ctrl

        raise LayoutSwitchError("Could not find fullscreen toggle control")

    def _resolve_runtime_option(
        self,
        options: dict[tuple[str, str], list[RuntimeLayoutOption]],
        target: LayoutSwitchTarget,
    ) -> RuntimeLayoutOption:
        candidates = options.get((target.section, target.label), [])
        if not candidates:
            raise LayoutSwitchError(f"Could not find layout option: {target.section}/{target.label}")
        return sorted(candidates, key=lambda item: (item.rect.top, item.rect.left))[0]

    def _open_layout_panel(
        self,
        root,
        hwnd: int,
        *,
        allow_pointer_fallback: bool = True,
        prefer_pointer_fallback: bool = False,
    ) -> None:
        current_root = self._desktop.window(handle=hwnd)
        if self._panel_title_rect(current_root) is not None:
            return
        button_control = self._layout_toolbar_button_control(current_root)
        button_rect = self._rect_from_control(button_control)
        control_attempts: list[tuple[str, callable]] = [
            (
                "open_layout_panel_click_input",
                lambda ctrl=button_control: self._click_control_input(ctrl, action_type="open_layout_panel_click_input"),
            ),
            (
                "open_layout_panel_invoke",
                lambda ctrl=button_control: self._invoke_control(ctrl, action_type="open_layout_panel_invoke"),
            ),
        ]
        pointer_attempts: list[tuple[str, callable]] = []
        if allow_pointer_fallback:
            pointer_attempts.extend(
                [
                    (
                        "open_layout_panel",
                        lambda point=button_rect.center: self._controller.click_once(
                            point,
                            hwnd=hwnd,
                            action_type="open_layout_panel",
                        ),
                    ),
                    (
                        "open_layout_panel_helper",
                        lambda point=button_rect.center: self._click_point_with_helper(point),
                    ),
                    (
                        "open_layout_panel_retry",
                        lambda point=button_rect.center: self._controller.click_once(
                            point,
                            hwnd=hwnd,
                            action_type="open_layout_panel_retry",
                        ),
                    ),
                ]
            )
        attempts = (
            control_attempts[:1] + pointer_attempts + control_attempts[1:]
            if prefer_pointer_fallback and pointer_attempts
            else control_attempts + pointer_attempts
        )
        # 关键修复：全屏场景下“窗口分割”按钮偶发第一次点击无响应。
        # 如果这里直接超时，运行时布局识别就会退回视觉猜测，6 宫格这类现场会被误判。
        # 因此打开面板必须带重试与辅助点击兜底。
        for action_name, action in attempts:
            self._logger.info("CONTROL action_type=%s point=%s backend=layout_open", action_name, button_rect.center)
            pointer_action = action_name in {"open_layout_panel", "open_layout_panel_helper", "open_layout_panel_retry"}
            if pointer_action and not self._focus_target_window(hwnd, action=action_name, required=False):
                continue
            self._window_manager.focus_window(hwnd)
            time.sleep(0.05)
            action()
            self._window_manager.focus_window(hwnd)
            time.sleep(0.2)
            if self._wait_for_panel(current_root, hwnd=hwnd, visible=True, timeout_seconds=1.6, raise_on_timeout=False):
                return
        raise LayoutSwitchError("Timed out waiting for layout panel to become open")

    def _close_layout_panel(
        self,
        root,
        hwnd: int,
        *,
        allow_pointer_fallback: bool = True,
        prefer_pointer_fallback: bool = False,
    ) -> None:
        # 关键修复：不同版本客户端里“X 热区”并不总是稳定，单一点击路径会导致
        # 面板读到了布局却关不掉，进而把后续动作卡在 VSClient 辅窗漂移恢复循环里。
        current_root = self._desktop.window(handle=hwnd)
        title_rect = self._panel_title_rect(current_root)
        if title_rect is None:
            return
        close_button_control = self._panel_close_button_control(current_root)
        close_button = self._rect_from_control(close_button_control) if close_button_control is not None else None
        toolbar_button: Rect | None = None
        dismiss_point: tuple[int, int] | None = None
        close_point: tuple[int, int] | None = None
        toolbar_button_control = None
        try:
            toolbar_button_control = self._layout_toolbar_button_control(current_root)
            toolbar_button = self._rect_from_control(toolbar_button_control)
        except Exception:
            toolbar_button = None
        dismiss_point = (max(20, title_rect.left - 80), max(20, title_rect.bottom + 40))
        if close_button is not None:
            close_point = self._panel_close_click_point(current_root)

        control_attempts: list[tuple[str, tuple[int, int] | None, callable]] = []
        pointer_attempts: list[tuple[str, tuple[int, int] | None, callable]] = []
        # 关键修复：只读识别当前宫格时，关闭面板必须优先走“不会穿进布局选项区域”的安全路径。
        # 否则像 6 宫格这种现场，右上热区误差会直接打到面板里的数字选项，导致客户端卡在错误布局上。
        if toolbar_button_control is not None and toolbar_button is not None:
            control_attempts.append(
                (
                    "close_layout_panel_toggle_invoke",
                    toolbar_button.center,
                    lambda ctrl=toolbar_button_control: self._invoke_control(ctrl, action_type="close_layout_panel_toggle_invoke"),
                )
            )
            control_attempts.append(
                (
                    "close_layout_panel_toggle_click_input",
                    toolbar_button.center,
                    lambda ctrl=toolbar_button_control: self._click_control_input(ctrl, action_type="close_layout_panel_toggle_click_input"),
                )
            )
            if allow_pointer_fallback:
                pointer_attempts.append(
                    (
                        "close_layout_panel_toggle",
                        toolbar_button.center,
                        lambda point=toolbar_button.center: self._controller.click_once(
                            point,
                            hwnd=hwnd,
                            action_type="close_layout_panel_toggle",
                        ),
                    )
                )
        if dismiss_point is not None and allow_pointer_fallback:
            pointer_attempts.append(
                (
                    "close_layout_panel_dismiss",
                    dismiss_point,
                    lambda point=dismiss_point: self._controller.click_once(
                        point,
                        hwnd=hwnd,
                        action_type="close_layout_panel_dismiss",
                    ),
                )
                )
        if close_button_control is not None and close_button is not None:
            control_attempts.append(
                (
                    "close_layout_panel_center_invoke",
                    close_button.center,
                    lambda ctrl=close_button_control: self._invoke_control(ctrl, action_type="close_layout_panel_center_invoke"),
                )
            )
            if allow_pointer_fallback:
                pointer_attempts.append(
                    (
                        "close_layout_panel_center_helper",
                        close_button.center,
                        lambda point=close_button.center: self._click_point_with_helper(point),
                    )
                )
            if allow_pointer_fallback:
                pointer_attempts.append(
                    (
                        "close_layout_panel_center",
                        close_button.center,
                        lambda point=close_button.center: self._controller.click_once(
                            point,
                            hwnd=hwnd,
                            action_type="close_layout_panel_center",
                        ),
                    )
                )
        control_attempts.append(
            (
                "close_layout_panel_escape",
                None,
                lambda current_hwnd=hwnd: self._controller.emergency_recover(hwnd=current_hwnd),
            )
        )
        if close_point is not None and allow_pointer_fallback:
            pointer_attempts.append(
                (
                    "close_layout_panel_hotspot",
                    close_point,
                    lambda point=close_point: self._click_point_with_helper(point),
                )
            )
        if prefer_pointer_fallback and pointer_attempts:
            attempts = []
            if dismiss_point is not None:
                attempts.extend([attempt for attempt in pointer_attempts if attempt[0] == "close_layout_panel_dismiss"])
            attempts.extend(
                [
                    attempt
                    for attempt in pointer_attempts
                    if attempt[0] in {"close_layout_panel_toggle", "close_layout_panel_center_helper", "close_layout_panel_center"}
                ]
            )
            attempts.extend(
                [
                    attempt
                    for attempt in control_attempts
                    if attempt[0] in {"close_layout_panel_toggle_click_input", "close_layout_panel_toggle_invoke"}
                ]
            )
            attempts.extend(
                [
                    attempt
                    for attempt in pointer_attempts
                    if attempt[0] == "close_layout_panel_hotspot"
                ]
            )
            attempts.extend(
                [
                    attempt
                    for attempt in control_attempts
                    if attempt[0] in {"close_layout_panel_center_invoke", "close_layout_panel_escape"}
                ]
            )
        else:
            attempts = control_attempts + pointer_attempts

        for action_name, point, action in attempts:
            self._logger.info("CONTROL action_type=%s point=%s backend=layout_close", action_name, point)
            pointer_action = action_name in {
                "close_layout_panel_toggle",
                "close_layout_panel_dismiss",
                "close_layout_panel_center_helper",
                "close_layout_panel_center",
                "close_layout_panel_escape",
                "close_layout_panel_hotspot",
            }
            if pointer_action and not self._focus_target_window(hwnd, action=action_name, required=False):
                continue
            self._window_manager.focus_window(hwnd)
            time.sleep(0.05)
            action()
            self._window_manager.focus_window(hwnd)
            time.sleep(0.3)
            if self._wait_for_panel(root, hwnd=hwnd, visible=False, timeout_seconds=1.4, raise_on_timeout=False):
                return
        raise LayoutSwitchError("窗口分割面板关闭失败")

    def _close_layout_panel_after_selection(
        self,
        hwnd: int,
        *,
        toolbar_button_rect: Rect | None,
        dismiss_point: tuple[int, int] | None,
    ) -> None:
        if toolbar_button_rect is not None:
            action_name = "close_layout_panel_after_select_toggle"
            point = toolbar_button_rect.center
            action = lambda click_point=point: self._controller.click_once(
                click_point,
                hwnd=hwnd,
                action_type=action_name,
            )
        elif dismiss_point is not None:
            action_name = "close_layout_panel_after_select_dismiss"
            point = dismiss_point
            action = lambda click_point=point: self._controller.click_once(
                click_point,
                hwnd=hwnd,
                action_type=action_name,
            )
        else:
            action_name = "close_layout_panel_after_select_escape"
            point = None
            action = lambda current_hwnd=hwnd: self._controller.emergency_recover(hwnd=current_hwnd)

        # 关键修复：点击布局项后不再做任何 post-click UIA 轮询/判开检查。
        # 某些全屏客户端在这个阶段只要再次访问 UIA 控件树就会卡住。
        self._logger.info("CONTROL action_type=%s point=%s backend=layout_close_fast", action_name, point)
        pointer_action = action_name != "close_layout_panel_after_select_escape"
        if pointer_action:
            self._focus_target_window(hwnd, action=action_name, required=False)
        self._window_manager.focus_window(hwnd)
        time.sleep(0.05)
        action()
        self._window_manager.focus_window(hwnd)
        time.sleep(0.25)

    def _panel_open_quick(self, hwnd: int) -> bool:
        current_root = self._desktop.window(handle=hwnd)
        return self._panel_title_rect_quick(current_root) is not None

    def _wait_for_panel(
        self,
        root,
        *,
        hwnd: int | None = None,
        visible: bool,
        timeout_seconds: float = 1.5,
        raise_on_timeout: bool = True,
    ) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            current_root = self._desktop.window(handle=hwnd) if hwnd is not None else root
            panel_open = self._panel_title_rect(current_root) is not None
            if panel_open == visible:
                return True
            time.sleep(0.1)
        if raise_on_timeout:
            state = "open" if visible else "closed"
            raise LayoutSwitchError(f"Timed out waiting for layout panel to become {state}")
        return False

    def _layout_toolbar_button_control(self, root):
        config_button_rect: Rect | None = None
        all_buttons: list[tuple[object, Rect, str]] = []
        for ctrl in root.descendants(control_type="Button"):
            rect = self._rect_from_control(ctrl)
            if rect.top < 60 or rect.bottom > 160:
                continue
            text = (ctrl.window_text() or "").strip()
            all_buttons.append((ctrl, rect, text))
            if text == "视频监控配置":
                config_button_rect = rect

        if config_button_rect is None:
            raise LayoutSwitchError("Could not find 视频监控配置 button; cannot locate layout toolbar button")

        empty_buttons = [
            (ctrl, rect)
            for ctrl, rect, text in sorted(all_buttons, key=lambda item: item[1].left)
            if rect.left > config_button_rect.right and not text and abs(rect.top - config_button_rect.top) <= 12
        ]
        if len(empty_buttons) < 2:
            raise LayoutSwitchError("Could not identify layout toolbar button from top toolbar controls")
        return empty_buttons[1][0]

    def _layout_toolbar_button_rect(self, root) -> Rect:
        return self._rect_from_control(self._layout_toolbar_button_control(root))

    def _panel_close_button_control(self, root):
        title_rect = self._panel_title_rect(root)
        if title_rect is None:
            return None
        candidates: list[tuple[object, Rect]] = []
        for ctrl in root.descendants(control_type="Button"):
            rect = self._rect_from_control(ctrl)
            if rect.left <= title_rect.right:
                continue
            if rect.top < title_rect.top - 5 or rect.bottom > title_rect.top + 30:
                continue
            candidates.append((ctrl, rect))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item[1].left, item[1].top))[-1][0]

    def _panel_close_button_rect(self, root) -> Rect | None:
        ctrl = self._panel_close_button_control(root)
        if ctrl is None:
            return None
        return self._rect_from_control(ctrl)

    def _panel_close_click_point(self, root) -> tuple[int, int]:
        close_button = self._panel_close_button_rect(root)
        if close_button is None:
            raise LayoutSwitchError("Could not find layout panel close button")
        # 这个控件本身的 invoke/中心点击都不稳定；现场热区位于按钮左侧约 40px、顶部约 2px 处。
        return (close_button.left - 40, close_button.top + 2)

    def _click_point_with_helper(self, point: tuple[int, int]) -> None:
        x, y = point
        script = (
            "from pywinauto import mouse\n"
            f"mouse.click(coords=({x}, {y}))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise LayoutSwitchError(
                f"layout close helper failed with code {completed.returncode}: {completed.stderr or completed.stdout}"
            )

    def _click_control_input(self, ctrl, *, action_type: str) -> None:
        click_input = getattr(ctrl, "click_input", None)
        if click_input is None:
            raise LayoutSwitchError(f"Control does not support click_input for action={action_type}")
        click_input()

    def _invoke_control(self, ctrl, *, action_type: str) -> None:
        invoke = getattr(ctrl, "invoke", None)
        if callable(invoke):
            invoke()
            return
        iface_invoke = getattr(ctrl, "iface_invoke", None)
        if iface_invoke is not None:
            iface_invoke.Invoke()
            return
        raise LayoutSwitchError(f"Control does not support invoke for action={action_type}")

    def _panel_title_rect_quick(self, root) -> Rect | None:
        try:
            ctrl = root.child_window(title="窗口分割", control_type="Text")
            if ctrl.exists(timeout=0.05):
                rect = self._rect_from_control(ctrl)
                if rect.width > 0 and rect.height > 0:
                    return rect
        except Exception:
            pass
        return None

    def _panel_title_rect(self, root) -> Rect | None:
        quick = self._panel_title_rect_quick(root)
        if quick is not None:
            return quick
        try:
            ctrl = root.child_window(title="窗口分割", control_type="Text")
            if ctrl.exists(timeout=0.1):
                rect = self._rect_from_control(ctrl)
                if rect.width > 0 and rect.height > 0:
                    return rect
        except Exception:
            pass
        for ctrl in root.descendants(control_type="Text"):
            text = (ctrl.window_text() or "").strip()
            if text == "窗口分割":
                rect = self._rect_from_control(ctrl)
                # 关键修复：面板关闭瞬间 UIA 偶发仍残留一个 0 尺寸标题文本。
                # 这种残影不能再算“面板还开着”，否则关闭逻辑会拿着失效控件树重试。
                if rect.width <= 0 or rect.height <= 0:
                    continue
                return rect
        return None

    def _collect_runtime_options(self, root) -> dict[tuple[str, str], list[RuntimeLayoutOption]]:
        header_rects: list[tuple[str, Rect]] = []
        checkbox_controls: list[tuple[str, Rect, bool]] = []

        title_rect = self._panel_title_rect(root)
        if title_rect is None:
            raise LayoutSwitchError("Layout panel is not open")

        for ctrl in root.descendants(control_type="Text"):
            text = (ctrl.window_text() or "").strip()
            if text not in SECTION_TITLES:
                continue
            rect = self._rect_from_control(ctrl)
            if rect.left < title_rect.left or rect.top <= title_rect.bottom:
                header_rects.append((text, rect))
                continue
            header_rects.append((text, rect))

        for ctrl in root.descendants(control_type="CheckBox"):
            label = (ctrl.window_text() or "").strip()
            if not label.isdigit():
                continue
            rect = self._rect_from_control(ctrl)
            if rect.left < title_rect.left or rect.top <= title_rect.bottom:
                continue
            checkbox_controls.append((label, rect, self._checkbox_selected(ctrl)))

        grouped = build_layout_option_index(header_rects, [(label, rect) for label, rect, _selected in checkbox_controls])
        runtime_options: dict[tuple[str, str], list[RuntimeLayoutOption]] = {}
        for key, rects in grouped.items():
            options: list[RuntimeLayoutOption] = []
            for rect in rects:
                selected = False
                for label, checkbox_rect, checkbox_selected in checkbox_controls:
                    if key[1] == label and checkbox_rect == rect:
                        selected = checkbox_selected
                        break
                options.append(RuntimeLayoutOption(section=key[0], label=key[1], rect=rect, selected=selected))
            runtime_options[key] = options
        if not runtime_options:
            raise LayoutSwitchError("No runtime layout options were discovered in the layout panel")
        return runtime_options

    def _native_get_runtime_layout_state(
        self,
        target_window,
        *,
        open_layout_panel: bool,
        close_panel: bool,
    ) -> dict[str, object] | None:
        if not self._native_runtime_available():
            return None
        try:
            payload = self._native_client.get_runtime_layout_state(
                target_window.hwnd,
                target_window.process_id,
                NATIVE_RENDER_PROCESS_NAMES,
                open_layout_panel=open_layout_panel,
                close_panel=close_panel,
            )
        except Exception as exc:
            self._logger.info("layout_switch native runtime state unavailable hwnd=%s: %s", target_window.hwnd, exc)
            return None

        resolved = payload.get("resolvedOptions", [])
        if isinstance(resolved, list) and resolved:
            self._logger.info("layout_switch native runtime state discovered options=%s", len(resolved))
        return payload

    def _native_select_runtime_layout(
        self,
        target_window,
        *,
        section: str,
        label: str,
        close_panel: bool,
    ) -> dict[str, object]:
        return self._native_client.select_runtime_layout(
            target_window.hwnd,
            target_window.process_id,
            NATIVE_RENDER_PROCESS_NAMES,
            section=section,
            label=label,
            close_panel=close_panel,
        )

    def _resolve_runtime_option_from_native_state(
        self,
        payload: dict[str, object] | None,
        target: LayoutSwitchTarget,
    ) -> RuntimeLayoutOption | None:
        if not isinstance(payload, dict):
            return None
        resolved = payload.get("resolvedOptions", [])
        if not isinstance(resolved, list):
            return None
        for item in resolved:
            option = self._runtime_option_from_native_descriptor(item)
            if option is None:
                continue
            if option.section == target.section and option.label == target.label:
                return option
        return None

    def _selected_layout_from_native_state(self, payload: dict[str, object] | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        raw_layout = payload.get("selectedLayout")
        try:
            if raw_layout is not None:
                return int(raw_layout)
        except Exception:
            pass
        resolved = payload.get("resolvedOptions", [])
        if not isinstance(resolved, list):
            return None
        for item in resolved:
            option = self._runtime_option_from_native_descriptor(item)
            if option is None or not option.selected:
                continue
            return LAYOUT_BY_SECTION_AND_LABEL.get((option.section, option.label))
        return None

    def _runtime_option_from_native_descriptor(self, raw_option) -> RuntimeLayoutOption | None:
        if not isinstance(raw_option, dict):
            return None
        section = str(raw_option.get("section", "") or "").strip()
        label = str(raw_option.get("label", "") or "").strip()
        if not section or not label:
            return None
        rect = self._rect_from_native_payload(raw_option.get("bounds"))
        if rect is None:
            return None
        return RuntimeLayoutOption(
            section=section,
            label=label,
            rect=rect,
            selected=bool(raw_option.get("selected", False)),
        )

    def _runtime_options_from_native_payload(
        self,
        payload: dict[str, object],
    ) -> dict[tuple[str, str], list[RuntimeLayoutOption]]:
        resolved_options = payload.get("resolvedOptions", [])
        if isinstance(resolved_options, list) and resolved_options:
            runtime_options: dict[tuple[str, str], list[RuntimeLayoutOption]] = {}
            for item in resolved_options:
                option = self._runtime_option_from_native_descriptor(item)
                if option is None:
                    continue
                runtime_options.setdefault((option.section, option.label), []).append(option)
            if runtime_options:
                return runtime_options

        header_rects: list[tuple[str, Rect]] = []
        checkbox_controls: list[tuple[str, Rect, bool]] = []

        for item in payload.get("layoutSections", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if name not in SECTION_TITLES:
                continue
            rect = self._rect_from_native_payload(item.get("bounds"))
            if rect is None:
                continue
            header_rects.append((name, rect))

        for item in payload.get("layoutOptions", []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("name", "") or "").strip()
            if not label.isdigit():
                continue
            rect = self._rect_from_native_payload(item.get("bounds"))
            if rect is None:
                continue
            checkbox_controls.append((label, rect, bool(item.get("selected", False))))

        grouped = build_layout_option_index(header_rects, [(label, rect) for label, rect, _ in checkbox_controls])
        runtime_options: dict[tuple[str, str], list[RuntimeLayoutOption]] = {}
        for key, rects in grouped.items():
            options: list[RuntimeLayoutOption] = []
            for rect in rects:
                selected = False
                for label, checkbox_rect, checkbox_selected in checkbox_controls:
                    if key[1] == label and checkbox_rect == rect:
                        selected = checkbox_selected
                        break
                options.append(RuntimeLayoutOption(section=key[0], label=key[1], rect=rect, selected=selected))
            runtime_options[key] = options
        return runtime_options

    @staticmethod
    def _rect_from_native_payload(raw_rect) -> Rect | None:
        if not isinstance(raw_rect, dict):
            return None
        try:
            return Rect(
                left=int(raw_rect.get("left", 0)),
                top=int(raw_rect.get("top", 0)),
                right=int(raw_rect.get("right", 0)),
                bottom=int(raw_rect.get("bottom", 0)),
            )
        except Exception:
            return None

    def _invoke_fullscreen_toggle_native(self, target_window, *, expected_mode: str) -> None:
        if not self._native_runtime_available():
            raise LayoutSwitchError("native runtime is not available for fullscreen toggle invoke")
        control_name = "全屏" if expected_mode == "fullscreen" else "退出全屏"
        self._native_client.invoke_named_control(
            target_window.hwnd,
            target_window.process_id,
            NATIVE_RENDER_PROCESS_NAMES,
            control_name,
        )

    def _close_layout_panel_native(self, target_window) -> bool:
        if not self._native_runtime_available():
            return False
        try:
            self._focus_target_window(target_window.hwnd, action="close_layout_panel_native", required=False)
            self._native_client.invoke_named_control(
                target_window.hwnd,
                target_window.process_id,
                NATIVE_RENDER_PROCESS_NAMES,
                "窗口分割",
            )
            time.sleep(0.2)
        except Exception as exc:
            self._logger.info("close_layout_panel native toggle unavailable hwnd=%s: %s", target_window.hwnd, exc)
            return False

        try:
            desktop = self._require_desktop()
            current_root = desktop.window(handle=target_window.hwnd)
            if self._panel_title_rect(current_root) is None:
                self._logger.info("close_layout_panel native toggle succeeded hwnd=%s", target_window.hwnd)
                return True
        except Exception as exc:
            self._logger.info("close_layout_panel native verification failed hwnd=%s: %s", target_window.hwnd, exc)
            return False

        self._logger.info("close_layout_panel native toggle did not close panel hwnd=%s", target_window.hwnd)
        return False

    def _rect_from_control(self, ctrl) -> Rect:
        rect = ctrl.rectangle()
        return Rect(left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom)

    @staticmethod
    def _checkbox_selected(ctrl) -> bool:
        getter = getattr(ctrl, "get_toggle_state", None)
        if getter is None:
            return False
        try:
            return bool(getter())
        except Exception:
            return False

    def _resolve_preview_probe_rect(self, target_window) -> Rect | None:
        if self._config is None:
            return None
        try:
            requested_mode = getattr(self._config.profiles, "active_mode", "auto")
            mode = self._window_manager.detect_mode(target_window, requested_mode)
            profile = getattr(self._config.profiles, mode)
            return profile.to_rect(target_window.client_rect)
        except Exception as exc:
            self._logger.warning("layout_switch preview rect resolve skipped: %s", exc)
            return None

    def _capture_preview_probe(self, preview_rect: Rect | None) -> Image.Image | None:
        if preview_rect is None:
            return None
        try:
            left, top, right, bottom = preview_rect.to_bbox()
            width = max(1, right - left)
            height = max(1, bottom - top)
            probe_left = left + max(12, int(width * 0.08))
            probe_top = top + max(12, int(height * 0.08))
            probe_right = right - max(160, int(width * 0.28))
            probe_bottom = bottom - max(40, int(height * 0.12))
            if probe_right <= probe_left + 40 or probe_bottom <= probe_top + 40:
                bbox = preview_rect.to_bbox()
            else:
                bbox = (probe_left, probe_top, probe_right, probe_bottom)
            return ImageGrab.grab(bbox=bbox).convert("L")
        except Exception as exc:
            self._logger.warning("layout_switch preview capture skipped: %s", exc)
            return None

    @staticmethod
    def _measure_visual_change(before_image: Image.Image, after_image: Image.Image) -> dict[str, float]:
        reference = before_image.convert("L")
        candidate = after_image.convert("L")
        if reference.size != candidate.size:
            candidate = candidate.resize(reference.size)
        diff = ImageChops.difference(reference, candidate)
        stats = ImageStat.Stat(diff)
        histogram = diff.histogram()
        total_pixels = max(1, sum(histogram))
        changed_pixels = sum(histogram[12:])
        return {
            "mean_diff": round(float(stats.mean[0]), 4),
            "changed_ratio": round(changed_pixels / total_pixels, 4),
        }

    @staticmethod
    def _layout_change_confirmed(metrics: dict[str, float]) -> bool:
        return metrics["mean_diff"] >= 2.5 or metrics["changed_ratio"] >= 0.015

    def _wait_for_visual_layout_change(self, preview_rect: Rect | None, preview_before: Image.Image) -> dict[str, float]:
        last_metrics = {"mean_diff": 0.0, "changed_ratio": 0.0}
        for _attempt in range(1, 6):
            time.sleep(0.35)
            preview_after = self._capture_preview_probe(preview_rect)
            if preview_after is None:
                self._logger.warning("layout_switch visual confirmation attempt=%s preview capture unavailable", _attempt)
                return last_metrics
            last_metrics = self._measure_visual_change(preview_before, preview_after)
            self._logger.info("layout_switch visual confirmation attempt=%s metrics=%s", _attempt, last_metrics)
            if self._layout_change_confirmed(last_metrics):
                return last_metrics
        return last_metrics
