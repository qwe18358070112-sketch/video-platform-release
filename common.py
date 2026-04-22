from __future__ import annotations

"""公共数据结构与配置加载。

本文件这次做了几件关键增强：
1. 让宫格顺序支持 row_major / column_major / custom / favorites_name。
2. 让 4/6/9/12 宫格之外的“同数量不同切法”可以通过 layout_template 落地。
3. 让 F9 的连续预选不再被配置硬性卡死，max_queued_next_steps=0 表示不限制。
4. 去掉写死到某一台电脑的 AutoHotkey 路径，方便跨电脑部署。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import ctypes

import yaml


SUPPORTED_LAYOUTS = {4, 6, 9, 12}
DEFAULT_LAYOUT_SPECS = {
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
    12: (4, 3),
}
GRID_ORDER_ALIASES = {
    "row_major": "row_major",
    "left_to_right": "row_major",
    "column_major": "column_major",
    "top_to_bottom": "column_major",
    "custom": "custom",
    "custom_sequence": "custom",
    "favorites_name": "favorites_name",
    "favorites": "favorites_name",
    "by_favorites": "favorites_name",
}
VALID_GRID_ORDERS = set(GRID_ORDER_ALIASES.values())


def enable_high_dpi_awareness(logger=None) -> str:
    """尽早切到高 DPI 感知，避免窗口矩形和鼠标坐标落在两套缩放坐标系里。"""

    user32 = getattr(ctypes, "windll", None)
    if user32 is None:
        return "unsupported"

    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)
    attempts: list[tuple[str, callable]] = []

    # Windows 10+：优先使用 Per-Monitor V2，能让 Win32 窗口矩形、鼠标和截图坐标保持一致。
    attempts.append(("per_monitor_v2", lambda: user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))))
    if shcore is not None:
        attempts.append(("per_monitor_v1", lambda: shcore.SetProcessDpiAwareness(2)))
    attempts.append(("system_aware", lambda: user32.SetProcessDPIAware()))

    for label, action in attempts:
        try:
            result = action()
            if result:
                if logger:
                    logger.info("Enabled DPI awareness mode=%s", label)
                return label
        except Exception:
            continue

    if logger:
        logger.info("DPI awareness setup skipped or was already set by the host process")
    return "unchanged"


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def to_bbox(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def inset(self, x_padding: int, y_padding: int) -> "Rect":
        return Rect(
            left=self.left + x_padding,
            top=self.top + y_padding,
            right=self.right - x_padding,
            bottom=self.bottom - y_padding,
        )

    def contains_point(self, point: tuple[int, int]) -> bool:
        x, y = point
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass(frozen=True)
class CalibrationProfile:
    left_ratio: float
    top_ratio: float
    right_ratio: float
    bottom_ratio: float

    def to_rect(self, client_rect: Rect) -> Rect:
        width = client_rect.width
        height = client_rect.height
        return Rect(
            left=int(client_rect.left + width * self.left_ratio),
            top=int(client_rect.top + height * self.top_ratio),
            right=int(client_rect.left + width * self.right_ratio),
            bottom=int(client_rect.top + height * self.bottom_ratio),
        )


@dataclass(frozen=True)
class GridSpec:
    rows: int
    cols: int


@dataclass(frozen=True)
class GridTemplateSlot:
    """模板化宫格槽位。

    通过比例描述矩形，不依赖固定的行列切法。
    这样就能支持“其他类型的 12 宫格”以及后续更复杂的布局模板。
    """

    row: int
    col: int
    left_ratio: float
    top_ratio: float
    right_ratio: float
    bottom_ratio: float
    label: str = ""

    def to_rect(self, preview_rect: Rect) -> Rect:
        width = preview_rect.width
        height = preview_rect.height
        return Rect(
            left=int(preview_rect.left + width * self.left_ratio),
            top=int(preview_rect.top + height * self.top_ratio),
            right=int(preview_rect.left + width * self.right_ratio),
            bottom=int(preview_rect.top + height * self.bottom_ratio),
        )


@dataclass(frozen=True)
class GridCell:
    # index 表示“物理槽位编号”，不是当前轮询顺序编号。
    # 轮询顺序由 GridMapper 产出的列表顺序决定。
    index: int
    row: int
    col: int
    rect: Rect
    cell_rect: Rect
    select_point: tuple[int, int]
    zoom_point: tuple[int, int]
    label: str = ""

    @property
    def click_point(self) -> tuple[int, int]:
        return self.select_point


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    process_id: int
    title: str
    process_name: str
    integrity_rid: int
    integrity_label: str
    window_rect: Rect
    client_rect: Rect
    monitor_rect: Rect

@dataclass(frozen=True)
class WindowSnapshot:
    hwnd: int
    process_id: int
    title: str
    process_name: str
    rect: Rect
    owner_hwnd: int = 0
    is_visible: bool = True
    is_foreground: bool = False



@dataclass(frozen=True)
class TimingConfig:
    focus_delay_ms: int = 300
    click_after_select_ms: int = 180
    select_settle_ms: int = 260
    dwell_seconds: float = 4.0
    post_restore_dwell_seconds: float = 4.0
    between_cells_ms: int = 500
    recovery_wait_ms: int = 800
    double_click_interval_ms: int = 120


@dataclass(frozen=True)
class HotkeyConfig:
    start_pause: str
    next_cell: str
    stop: str
    emergency_recover: str
    clear_cooldown: str
    calibration_capture: str
    profile_source_toggle: str = "f1"
    mode_cycle: str = "f7"
    layout_cycle: str = "f8"
    grid_order_cycle: str = "disabled"
    debounce_ms: int = 250
    # F9 需要支持连续步进，不能再被 F8/F11 共用的重防抖吞键。
    next_cell_debounce_ms: int = 120


@dataclass(frozen=True)
class ControlsConfig:
    # 0 表示不限制，可连续多次按 F9 步进下一路。
    max_queued_next_steps: int = 1
    # 为 true 时，暂停态下的 F7/F8 会直接驱动客户端切换全屏/窗口与宫格。
    runtime_hotkeys_drive_client_ui: bool = False
    # 打开客户端直控后，是否仍要求只能在暂停态执行。
    runtime_hotkeys_require_paused: bool = True
    # 为 true 时，运行时不再自动识别宫格，始终锁定到 requested/layout 配置值。
    lock_runtime_layout_to_requested: bool = False
    # 可选：运行时实例锁名称。固定宫格程序会用它避免多套程序并发运行。
    instance_lock_name: str = ""


@dataclass(frozen=True)
class WindowSearchConfig:
    title_keywords: list[str]
    process_names: list[str]
    focus_before_action: bool = True
    control_backend: str = "sendmessage"
    # 默认留空，不再绑定到某一台开发机。
    autohotkey_path: str = ""
    native_runtime_enabled: bool = False
    native_runtime_project: str = "native_runtime/VideoPlatform.NativeProbe/VideoPlatform.NativeProbe.csproj"
    native_runtime_tree_depth: int = 4
    native_runtime_startup_timeout_seconds: float = 20.0
    native_runtime_command_timeout_seconds: float = 4.0
    match_timeout_seconds: float = 5.0
    fullscreen_coverage_ratio: float = 0.96
    client_margin_tolerance_px: int = 8


@dataclass(frozen=True)
class ProfilesConfig:
    active_mode: str
    windowed: CalibrationProfile
    fullscreen: CalibrationProfile


@dataclass(frozen=True)
class GridConfig:
    layout: int
    order: str
    cell_padding_ratio: float = 0.08
    click_point_ratio_x: float = 0.5
    click_point_ratio_y: float = 0.5
    zoom_point_ratio_x: float = 0.5
    zoom_point_ratio_y: float = 0.38
    click_point_ratio_y_by_row: dict[int, float] = field(default_factory=dict)
    zoom_point_ratio_y_by_row: dict[int, float] = field(default_factory=dict)
    layout_overrides: dict[int, GridSpec] = field(default_factory=dict)
    # custom 模式：直接使用 custom_sequence，或使用 active_sequence_profile 指向 sequence_profiles。
    custom_sequence: tuple[int, ...] = ()
    active_sequence_profile: str = ""
    sequence_profiles: dict[str, tuple[int, ...]] = field(default_factory=dict)
    # favorites_name 模式：将自动读取到的收藏夹名称，映射到 cell_labels 中的物理槽位。
    cell_labels: dict[int, str] = field(default_factory=dict)
    # 布局模板：支持同数量不同切法的宫格。
    layout_template: str = ""
    layout_templates: dict[str, tuple[GridTemplateSlot, ...]] = field(default_factory=dict)

    def grid_spec_for_layout(self, layout: int | None = None) -> GridSpec:
        target_layout = layout or self.layout
        if target_layout in self.layout_overrides:
            return self.layout_overrides[target_layout]
        if target_layout not in DEFAULT_LAYOUT_SPECS:
            raise ValueError(f"Unsupported layout: {target_layout}")
        rows, cols = DEFAULT_LAYOUT_SPECS[target_layout]
        return GridSpec(rows=rows, cols=cols)

    def selected_template(self) -> tuple[GridTemplateSlot, ...]:
        if not self.layout_template:
            return ()
        return self.layout_templates.get(self.layout_template, ())

    def resolved_custom_sequence(self, cell_count: int) -> tuple[int, ...]:
        raw_sequence: Iterable[int] = ()
        if self.active_sequence_profile:
            raw_sequence = self.sequence_profiles.get(self.active_sequence_profile, ())
        if not tuple(raw_sequence):
            raw_sequence = self.custom_sequence
        return _normalize_sequence(raw_sequence, cell_count)

    def resolved_favorites_sequence(self, runtime_label_order: list[str], cell_count: int) -> tuple[int, ...]:
        if not runtime_label_order or not self.cell_labels:
            return tuple(range(cell_count))
        normalized_to_index: dict[str, int] = {}
        for index, label in self.cell_labels.items():
            if not label or index >= cell_count:
                continue
            normalized_to_index[_normalize_label(label)] = index

        result: list[int] = []
        seen: set[int] = set()
        for label in runtime_label_order:
            matched = normalized_to_index.get(_normalize_label(label))
            if matched is None or matched in seen:
                continue
            result.append(matched)
            seen.add(matched)
        for index in range(cell_count):
            if index not in seen:
                result.append(index)
        return tuple(result)


@dataclass(frozen=True)
class FavoritesConfig:
    enabled: bool = True
    left_panel_width_ratio: float = 0.28
    top_exclusion_ratio: float = 0.08
    cache_file: str = "tmp/favorites_cache.json"
    visible_only: bool = True
    max_entries: int = 64
    include_control_types: tuple[str, ...] = ("TreeItem", "ListItem", "Text")
    exclude_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeGuardConfig:
    enabled: bool = True
    verify_before_action: bool = True
    verify_after_action: bool = True
    verify_during_dwell: bool = True
    verify_foreground_window: bool = True
    detect_related_popups: bool = True
    auto_close_related_popups: bool = True
    auto_refocus_external_window: bool = True
    post_action_wait_ms: int = 220
    settle_after_recover_ms: int = 600
    rect_drift_tolerance_px: int = 24
    consecutive_fail_limit: int = 3
    screenshot_dir: str = "logs/guard"
    popup_title_keywords: tuple[str, ...] = (
        "提示",
        "告警",
        "错误",
        "异常",
        "消息",
        "确认",
        "warning",
        "error",
        "dialog",
        "prompt",
    )


@dataclass(frozen=True)
class LayoutSwitchConfig:
    require_cleared_scene_before_switch: bool = True
    fail_closed_on_guard_error: bool = True


@dataclass(frozen=True)
class DetectionConfig:
    enabled: bool
    skip_on_detected_issue: bool
    save_failure_screenshots: bool
    save_anomaly_screenshot: bool
    screenshot_dir: str
    precheck_crop_ratio: float
    black_screen_confirm_frames: int
    preview_failure_confirm_frames: int
    black_screen_mean_threshold: float
    black_screen_std_threshold: float
    black_screen_bright_ratio_threshold: float
    black_screen_edge_ratio_threshold: float
    failure_dark_ratio_threshold: float
    failure_bright_ratio_min: float
    failure_bright_ratio_max: float
    failure_edge_ratio_min: float
    failure_edge_ratio_max: float
    zoom_confirm_mean_diff_threshold: float
    zoom_confirm_changed_ratio_threshold: float
    resume_zoomed_mean_diff_max: float
    resume_zoomed_changed_ratio_max: float
    resume_grid_mean_diff_min: float
    resume_grid_changed_ratio_min: float
    runtime_flat_entropy_max: float
    runtime_flat_edge_ratio_max: float
    runtime_flat_dominant_ratio_min: float
    path_retry_limit: int
    max_fail_streak_before_cooldown: int
    issue_cooldown_cycles: int
    use_orb_zoom_confirm: bool


@dataclass(frozen=True)
class InputGuardConfig:
    enabled: bool
    mouse_move_threshold: int
    idle_resume_seconds: float
    poll_interval_ms: int
    suppress_after_programmatic_input_ms: int
    resume_settle_ms: int


@dataclass(frozen=True)
class StatusOverlayConfig:
    enabled: bool
    status_file: str
    close_delay_ms: int = 1800
    auto_hide_ms: int = 2200
    stale_hide_ms: int = 4800
    safe_strip_height_px: int = 96


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    log_dir: str
    keep_console: bool = True


@dataclass(frozen=True)
class AppConfig:
    path: Path
    window: WindowSearchConfig
    profiles: ProfilesConfig
    grid: GridConfig
    favorites: FavoritesConfig
    runtime_guard: RuntimeGuardConfig
    layout_switch: LayoutSwitchConfig
    controls: ControlsConfig
    timing: TimingConfig
    hotkeys: HotkeyConfig
    detection: DetectionConfig
    input_guard: InputGuardConfig
    status_overlay: StatusOverlayConfig
    logging: LoggingConfig


class SchedulerState(str, Enum):
    IDLE = "IDLE"
    PREPARE_TARGET = "PREPARE_TARGET"
    SELECT_TARGET = "SELECT_TARGET"
    SELECT_CONFIRM = "SELECT_CONFIRM"
    ZOOM_IN = "ZOOM_IN"
    ZOOM_CONFIRM = "ZOOM_CONFIRM"
    ZOOM_DWELL = "ZOOM_DWELL"
    ZOOM_OUT = "ZOOM_OUT"
    GRID_CONFIRM = "GRID_CONFIRM"
    GRID_DWELL = "GRID_DWELL"
    NEXT = "NEXT"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR_RECOVERY = "ERROR_RECOVERY"

    PREPARE = PREPARE_TARGET
    PRECHECK = SELECT_CONFIRM
    DWELL = ZOOM_DWELL


class VisualViewState(str, Enum):
    GRID = "GRID"
    ZOOMED = "ZOOMED"
    ZOOMED_ACTIVE_CELL = "ZOOMED_ACTIVE_CELL"
    UNKNOWN = "UNKNOWN"


class HotkeyCommand(str, Enum):
    PAUSE_REQUEST = "PAUSE_REQUEST"
    RESUME_REQUEST = "RESUME_REQUEST"
    NEXT_REQUEST = "NEXT_REQUEST"
    STOP_REQUEST = "STOP_REQUEST"
    EMERGENCY_RECOVER_REQUEST = "EMERGENCY_RECOVER_REQUEST"
    CLEAR_COOLDOWN_REQUEST = "CLEAR_COOLDOWN_REQUEST"
    PROFILE_SOURCE_TOGGLE_REQUEST = "PROFILE_SOURCE_TOGGLE_REQUEST"
    MODE_CYCLE_REQUEST = "MODE_CYCLE_REQUEST"
    LAYOUT_CYCLE_REQUEST = "LAYOUT_CYCLE_REQUEST"
    GRID_ORDER_CYCLE_REQUEST = "GRID_ORDER_CYCLE_REQUEST"


class ConfirmState(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    PARTIAL_CHANGE = "PARTIAL_CHANGE"
    STATE_CONFIRMED = "STATE_CONFIRMED"


@dataclass(frozen=True)
class DetectionResult:
    status: str
    metrics: dict[str, float]
    reason: str = ""


@dataclass(frozen=True)
class ConfirmResult:
    state: ConfirmState
    metrics: dict[str, float]
    reason: str = ""


def _normalize_label(value: Any) -> str:
    return str(value or "").strip().casefold()


def _normalize_grid_order(value: Any) -> str:
    raw = str(value or "row_major").strip().casefold()
    normalized = GRID_ORDER_ALIASES.get(raw)
    if not normalized:
        raise ValueError(
            "grid.order must be one of row_major / left_to_right / column_major / top_to_bottom / custom / favorites_name"
        )
    return normalized


def _normalize_sequence(values: Iterable[int], cell_count: int) -> tuple[int, ...]:
    result: list[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= cell_count or index in seen:
            continue
        result.append(index)
        seen.add(index)
    for index in range(cell_count):
        if index not in seen:
            result.append(index)
    return tuple(result)


def _profile_from_dict(data: dict[str, Any]) -> CalibrationProfile:
    return CalibrationProfile(
        left_ratio=float(data["left_ratio"]),
        top_ratio=float(data["top_ratio"]),
        right_ratio=float(data["right_ratio"]),
        bottom_ratio=float(data["bottom_ratio"]),
    )


def _grid_overrides_from_dict(data: dict[str, Any]) -> dict[int, GridSpec]:
    overrides: dict[int, GridSpec] = {}
    for raw_layout, raw_spec in (data or {}).items():
        layout = int(raw_layout)
        overrides[layout] = GridSpec(rows=int(raw_spec["rows"]), cols=int(raw_spec["cols"]))
    return overrides


def _sequence_from_dict(data: dict[str, Any]) -> dict[str, tuple[int, ...]]:
    profiles: dict[str, tuple[int, ...]] = {}
    for name, raw_sequence in (data or {}).items():
        if raw_sequence is None:
            profiles[str(name)] = ()
            continue
        if isinstance(raw_sequence, str):
            items = [item.strip() for item in raw_sequence.split(",") if item.strip()]
            profiles[str(name)] = tuple(int(item) for item in items)
        else:
            profiles[str(name)] = tuple(int(item) for item in raw_sequence)
    return profiles


def _cell_labels_from_any(data: Any) -> dict[int, str]:
    labels: dict[int, str] = {}
    if isinstance(data, list):
        for index, value in enumerate(data):
            labels[index] = str(value or "")
        return labels
    if isinstance(data, dict):
        for raw_index, value in data.items():
            labels[int(raw_index)] = str(value or "")
    return labels


def _int_float_map_from_any(data: Any) -> dict[int, float]:
    values: dict[int, float] = {}
    if isinstance(data, dict):
        for raw_index, value in data.items():
            values[int(raw_index)] = float(value)
    elif isinstance(data, list):
        for index, value in enumerate(data, start=1):
            values[index] = float(value)
    return values


def _layout_templates_from_dict(data: dict[str, Any]) -> dict[str, tuple[GridTemplateSlot, ...]]:
    templates: dict[str, tuple[GridTemplateSlot, ...]] = {}
    for name, raw_template in (data or {}).items():
        slots_raw = raw_template.get("slots", raw_template) if isinstance(raw_template, dict) else raw_template
        slots: list[GridTemplateSlot] = []
        for slot_index, raw_slot in enumerate(slots_raw or []):
            left_ratio = float(raw_slot["left_ratio"])
            top_ratio = float(raw_slot["top_ratio"])
            right_ratio = float(raw_slot["right_ratio"])
            bottom_ratio = float(raw_slot["bottom_ratio"])
            if not (0.0 <= left_ratio < right_ratio <= 1.0 and 0.0 <= top_ratio < bottom_ratio <= 1.0):
                raise ValueError(f"grid.layout_templates[{name}] slot[{slot_index}] has invalid ratios")
            slots.append(
                GridTemplateSlot(
                    row=int(raw_slot.get("row", slot_index)),
                    col=int(raw_slot.get("col", 0)),
                    left_ratio=left_ratio,
                    top_ratio=top_ratio,
                    right_ratio=right_ratio,
                    bottom_ratio=bottom_ratio,
                    label=str(raw_slot.get("label", "")),
                )
            )
        templates[str(name)] = tuple(slots)
    return templates


def _favorites_from_dict(data: dict[str, Any] | None) -> FavoritesConfig:
    raw = data or {}
    return FavoritesConfig(
        enabled=bool(raw.get("enabled", True)),
        left_panel_width_ratio=float(raw.get("left_panel_width_ratio", 0.28)),
        top_exclusion_ratio=float(raw.get("top_exclusion_ratio", 0.08)),
        cache_file=str(raw.get("cache_file", "tmp/favorites_cache.json")),
        visible_only=bool(raw.get("visible_only", True)),
        max_entries=int(raw.get("max_entries", 64)),
        include_control_types=tuple(str(item) for item in raw.get("include_control_types", ["TreeItem", "ListItem", "Text"])),
        exclude_texts=tuple(str(item) for item in raw.get("exclude_texts", [])),
    )


def _runtime_guard_from_dict(data: dict[str, Any] | None) -> RuntimeGuardConfig:
    raw = data or {}
    return RuntimeGuardConfig(
        enabled=bool(raw.get("enabled", True)),
        verify_before_action=bool(raw.get("verify_before_action", True)),
        verify_after_action=bool(raw.get("verify_after_action", True)),
        verify_during_dwell=bool(raw.get("verify_during_dwell", True)),
        verify_foreground_window=bool(raw.get("verify_foreground_window", True)),
        detect_related_popups=bool(raw.get("detect_related_popups", True)),
        auto_close_related_popups=bool(raw.get("auto_close_related_popups", True)),
        auto_refocus_external_window=bool(raw.get("auto_refocus_external_window", True)),
        post_action_wait_ms=int(raw.get("post_action_wait_ms", 220)),
        settle_after_recover_ms=int(raw.get("settle_after_recover_ms", 600)),
        rect_drift_tolerance_px=int(raw.get("rect_drift_tolerance_px", 24)),
        consecutive_fail_limit=int(raw.get("consecutive_fail_limit", 3)),
        screenshot_dir=str(raw.get("screenshot_dir", "logs/guard")),
        popup_title_keywords=tuple(str(item) for item in raw.get("popup_title_keywords", ["提示", "告警", "错误", "异常", "消息", "确认", "warning", "error", "dialog", "prompt"])),
    )


def _layout_switch_from_dict(data: dict[str, Any] | None) -> LayoutSwitchConfig:
    raw = data or {}
    return LayoutSwitchConfig(
        require_cleared_scene_before_switch=bool(raw.get("require_cleared_scene_before_switch", True)),
        fail_closed_on_guard_error=bool(raw.get("fail_closed_on_guard_error", True)),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))

    grid_layout = int(raw["grid"]["layout"])
    if grid_layout not in SUPPORTED_LAYOUTS:
        raise ValueError(f"Layout {grid_layout} is not supported. Supported: {sorted(SUPPORTED_LAYOUTS)}")

    grid_order = _normalize_grid_order(raw["grid"].get("order", "row_major"))
    max_queued_next_steps = int(raw.get("controls", {}).get("max_queued_next_steps", 1))
    if max_queued_next_steps < 0:
        raise ValueError("controls.max_queued_next_steps must be >= 0")
    runtime_hotkeys_drive_client_ui = bool(raw.get("controls", {}).get("runtime_hotkeys_drive_client_ui", False))
    runtime_hotkeys_require_paused = bool(raw.get("controls", {}).get("runtime_hotkeys_require_paused", True))
    lock_runtime_layout_to_requested = bool(raw.get("controls", {}).get("lock_runtime_layout_to_requested", False))
    instance_lock_name = str(raw.get("controls", {}).get("instance_lock_name", "")).strip()

    active_mode = str(raw["profiles"].get("active_mode", "auto"))
    if active_mode not in {"auto", "windowed", "fullscreen"}:
        raise ValueError("profiles.active_mode must be auto / windowed / fullscreen")

    grid_config = GridConfig(
        layout=grid_layout,
        order=grid_order,
        cell_padding_ratio=float(raw["grid"].get("cell_padding_ratio", 0.08)),
        click_point_ratio_x=float(raw["grid"].get("click_point_ratio_x", 0.5)),
        click_point_ratio_y=float(raw["grid"].get("click_point_ratio_y", 0.5)),
        zoom_point_ratio_x=float(raw["grid"].get("zoom_point_ratio_x", raw["grid"].get("click_point_ratio_x", 0.5))),
        zoom_point_ratio_y=float(raw["grid"].get("zoom_point_ratio_y", 0.38)),
        click_point_ratio_y_by_row=_int_float_map_from_any(raw["grid"].get("click_point_ratio_y_by_row", {})),
        zoom_point_ratio_y_by_row=_int_float_map_from_any(raw["grid"].get("zoom_point_ratio_y_by_row", {})),
        layout_overrides=_grid_overrides_from_dict(raw["grid"].get("layout_overrides", {})),
        custom_sequence=tuple(int(item) for item in raw["grid"].get("custom_sequence", [])),
        active_sequence_profile=str(raw["grid"].get("active_sequence_profile", "")),
        sequence_profiles=_sequence_from_dict(raw["grid"].get("sequence_profiles", {})),
        cell_labels=_cell_labels_from_any(raw["grid"].get("cell_labels", {})),
        layout_template=str(raw["grid"].get("layout_template", "")),
        layout_templates=_layout_templates_from_dict(raw["grid"].get("layout_templates", {})),
    )

    if grid_config.layout_template:
        template_slots = grid_config.selected_template()
        if not template_slots:
            raise ValueError(f"grid.layout_template '{grid_config.layout_template}' was not found in grid.layout_templates")
        if len(template_slots) != grid_layout:
            raise ValueError(
                f"grid.layout_template '{grid_config.layout_template}' slot count={len(template_slots)} does not match grid.layout={grid_layout}"
            )

    return AppConfig(
        path=config_path,
        window=WindowSearchConfig(
            title_keywords=list(raw["window"].get("title_keywords", [])),
            process_names=list(raw["window"].get("process_names", [])),
            focus_before_action=bool(raw["window"].get("focus_before_action", True)),
            control_backend=str(raw["window"].get("control_backend", "sendmessage")),
            autohotkey_path=str(raw["window"].get("autohotkey_path", "")),
            native_runtime_enabled=bool(raw["window"].get("native_runtime_enabled", False)),
            native_runtime_project=str(
                raw["window"].get(
                    "native_runtime_project",
                    "native_runtime/VideoPlatform.NativeProbe/VideoPlatform.NativeProbe.csproj",
                )
            ),
            native_runtime_tree_depth=int(raw["window"].get("native_runtime_tree_depth", 4)),
            native_runtime_startup_timeout_seconds=float(
                raw["window"].get("native_runtime_startup_timeout_seconds", 20.0)
            ),
            native_runtime_command_timeout_seconds=float(
                raw["window"].get("native_runtime_command_timeout_seconds", 4.0)
            ),
            match_timeout_seconds=float(raw["window"].get("match_timeout_seconds", 5.0)),
            fullscreen_coverage_ratio=float(raw["window"].get("fullscreen_coverage_ratio", 0.96)),
            client_margin_tolerance_px=int(raw["window"].get("client_margin_tolerance_px", 8)),
        ),
        profiles=ProfilesConfig(
            active_mode=active_mode,
            windowed=_profile_from_dict(raw["profiles"]["windowed"]),
            fullscreen=_profile_from_dict(raw["profiles"]["fullscreen"]),
        ),
        grid=grid_config,
        favorites=_favorites_from_dict(raw.get("favorites")),
        runtime_guard=_runtime_guard_from_dict(raw.get("runtime_guard")),
        layout_switch=_layout_switch_from_dict(raw.get("layout_switch")),
        controls=ControlsConfig(
            max_queued_next_steps=max_queued_next_steps,
            runtime_hotkeys_drive_client_ui=runtime_hotkeys_drive_client_ui,
            runtime_hotkeys_require_paused=runtime_hotkeys_require_paused,
            lock_runtime_layout_to_requested=lock_runtime_layout_to_requested,
            instance_lock_name=instance_lock_name,
        ),
        timing=TimingConfig(
            focus_delay_ms=int(raw["timing"].get("focus_delay_ms", 300)),
            click_after_select_ms=int(raw["timing"].get("click_after_select_ms", 180)),
            select_settle_ms=int(raw["timing"].get("select_settle_ms", raw["timing"].get("click_after_select_ms", 180))),
            dwell_seconds=float(raw["timing"].get("dwell_seconds", 4)),
            post_restore_dwell_seconds=float(raw["timing"].get("post_restore_dwell_seconds", raw["timing"].get("dwell_seconds", 4))),
            between_cells_ms=int(raw["timing"].get("between_cells_ms", 500)),
            recovery_wait_ms=int(raw["timing"].get("recovery_wait_ms", 800)),
            double_click_interval_ms=int(raw["timing"].get("double_click_interval_ms", 120)),
        ),
        hotkeys=HotkeyConfig(
            start_pause=str(raw["hotkeys"].get("start_pause", "f2")),
            next_cell=str(raw["hotkeys"]["next_cell"]),
            stop=str(raw["hotkeys"]["stop"]),
            emergency_recover=str(raw["hotkeys"]["emergency_recover"]),
            clear_cooldown=str(raw["hotkeys"].get("clear_cooldown", "f6")),
            profile_source_toggle=str(raw["hotkeys"].get("profile_source_toggle", "f1")),
            mode_cycle=str(raw["hotkeys"].get("mode_cycle", "f7")),
            layout_cycle=str(raw["hotkeys"].get("layout_cycle", "f8")),
            grid_order_cycle=str(raw["hotkeys"].get("grid_order_cycle", "disabled")),
            calibration_capture=str(raw["hotkeys"]["calibration_capture"]),
            debounce_ms=int(raw["hotkeys"].get("debounce_ms", 250)),
            next_cell_debounce_ms=int(raw["hotkeys"].get("next_cell_debounce_ms", 120)),
        ),
        detection=DetectionConfig(
            enabled=bool(raw["detection"].get("enabled", True)),
            skip_on_detected_issue=bool(raw["detection"].get("skip_on_detected_issue", True)),
            save_failure_screenshots=bool(raw["detection"].get("save_failure_screenshots", True)),
            save_anomaly_screenshot=bool(raw["detection"].get("save_anomaly_screenshot", raw["detection"].get("save_failure_screenshots", True))),
            screenshot_dir=str(raw["detection"].get("screenshot_dir", "logs/screenshots")),
            precheck_crop_ratio=float(raw["detection"].get("precheck_crop_ratio", 0.92)),
            black_screen_confirm_frames=int(raw["detection"].get("black_screen_confirm_frames", 2)),
            preview_failure_confirm_frames=int(raw["detection"].get("preview_failure_confirm_frames", 2)),
            black_screen_mean_threshold=float(raw["detection"].get("black_screen_mean_threshold", 28)),
            black_screen_std_threshold=float(raw["detection"].get("black_screen_std_threshold", 16)),
            black_screen_bright_ratio_threshold=float(raw["detection"].get("black_screen_bright_ratio_threshold", 0.01)),
            black_screen_edge_ratio_threshold=float(raw["detection"].get("black_screen_edge_ratio_threshold", 0.015)),
            failure_dark_ratio_threshold=float(raw["detection"].get("failure_dark_ratio_threshold", 0.72)),
            failure_bright_ratio_min=float(raw["detection"].get("failure_bright_ratio_min", 0.003)),
            failure_bright_ratio_max=float(raw["detection"].get("failure_bright_ratio_max", 0.12)),
            failure_edge_ratio_min=float(raw["detection"].get("failure_edge_ratio_min", 0.01)),
            failure_edge_ratio_max=float(raw["detection"].get("failure_edge_ratio_max", 0.12)),
            zoom_confirm_mean_diff_threshold=float(raw["detection"].get("zoom_confirm_mean_diff_threshold", 18.0)),
            zoom_confirm_changed_ratio_threshold=float(raw["detection"].get("zoom_confirm_changed_ratio_threshold", 0.14)),
            resume_zoomed_mean_diff_max=float(raw["detection"].get("resume_zoomed_mean_diff_max", 10.0)),
            resume_zoomed_changed_ratio_max=float(raw["detection"].get("resume_zoomed_changed_ratio_max", 0.08)),
            resume_grid_mean_diff_min=float(raw["detection"].get("resume_grid_mean_diff_min", 18.0)),
            resume_grid_changed_ratio_min=float(raw["detection"].get("resume_grid_changed_ratio_min", 0.18)),
            runtime_flat_entropy_max=float(raw["detection"].get("runtime_flat_entropy_max", 2.0)),
            runtime_flat_edge_ratio_max=float(raw["detection"].get("runtime_flat_edge_ratio_max", 0.04)),
            runtime_flat_dominant_ratio_min=float(raw["detection"].get("runtime_flat_dominant_ratio_min", 0.55)),
            path_retry_limit=int(raw["detection"].get("path_retry_limit", 1)),
            max_fail_streak_before_cooldown=int(raw["detection"].get("max_fail_streak_before_cooldown", 3)),
            issue_cooldown_cycles=int(raw["detection"].get("issue_cooldown_cycles", 2)),
            use_orb_zoom_confirm=bool(raw["detection"].get("use_orb_zoom_confirm", True)),
        ),
        input_guard=InputGuardConfig(
            enabled=bool(raw["input_guard"].get("enabled", True)),
            mouse_move_threshold=int(raw["input_guard"].get("mouse_move_threshold", 18)),
            idle_resume_seconds=float(raw["input_guard"].get("idle_resume_seconds", 5)),
            poll_interval_ms=int(raw["input_guard"].get("poll_interval_ms", 200)),
            suppress_after_programmatic_input_ms=int(raw["input_guard"].get("suppress_after_programmatic_input_ms", 1200)),
            resume_settle_ms=int(raw["input_guard"].get("resume_settle_ms", 1200)),
        ),
        status_overlay=StatusOverlayConfig(
            enabled=bool(raw.get("status_overlay", {}).get("enabled", True)),
            status_file=str(raw.get("status_overlay", {}).get("status_file", "tmp/runtime_status.json")),
            close_delay_ms=int(raw.get("status_overlay", {}).get("close_delay_ms", 1800)),
            auto_hide_ms=int(raw.get("status_overlay", {}).get("auto_hide_ms", 2200)),
            stale_hide_ms=int(raw.get("status_overlay", {}).get("stale_hide_ms", 4800)),
            safe_strip_height_px=int(raw.get("status_overlay", {}).get("safe_strip_height_px", 96)),
        ),
        logging=LoggingConfig(
            level=str(raw["logging"].get("level", "INFO")),
            log_dir=str(raw["logging"].get("log_dir", "logs")),
            keep_console=bool(raw["logging"].get("keep_console", True)),
        ),
    )


def resolve_output_path(config_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()
