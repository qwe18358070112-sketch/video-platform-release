from __future__ import annotations

"""平台化预览运行时的最小契约。

这个文件不绑定海康 SDK，也不绑定 Web 插件。
它的用途是先把“新运行时必须自己持有的状态”固定下来，
避免后续又退回到靠外部桌面客户端截图猜状态。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class PreviewBackendKind(str, Enum):
    HIK_PLATFORM_WEB_PLUGIN = "hik_platform_web_plugin"
    HIK_DEVICE_HCNETSDK = "hik_device_hcnet_sdk"


class LayoutPreset(int, Enum):
    FOUR = 4
    SIX = 6
    NINE = 9
    TWELVE = 12


class PollingMode(str, Enum):
    SELECT = "select"
    FULLSCREEN = "fullscreen"


class RendererKind(str, Enum):
    MOCK_WS = "mock-ws"
    MOCK_HLS = "mock-hls"
    WEB_PLUGIN_STUB = "web-plugin-stub"


class RendererDriverMode(str, Enum):
    DRY_RUN = "dry-run"
    SIMULATE_SUCCESS = "simulate-success"
    BRIDGE_STUB = "bridge-stub"


@dataclass(frozen=True)
class CameraResource:
    resource_id: str
    name: str
    backend: PreviewBackendKind
    channel_id: str
    preview_token: str | None = None
    device_host: str | None = None
    device_port: int | None = None
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class TileBinding:
    tile_index: int
    resource_id: str


@dataclass
class LayoutSession:
    layout: LayoutPreset
    bindings: list[TileBinding] = field(default_factory=list)
    selected_tile_index: int | None = None
    fullscreen_tile_index: int | None = None


@dataclass
class PollingCheckpoint:
    mode: PollingMode
    dwell_ms: int
    route_tile_indexes: list[int] = field(default_factory=list)
    current_route_index: int | None = None
    running: bool = False
    cycle_count: int = 0


@dataclass
class RendererCheckpoint:
    kind: RendererKind
    auto_attach: bool = True
    attached_tile_indexes: list[int] = field(default_factory=list)


@dataclass
class RendererAttachment:
    tile_index: int
    kind: RendererKind
    session_id: str
    surface_type: str
    transport: str
    display_url: str


@dataclass
class RendererAttachPayload:
    tile_index: int
    kind: RendererKind
    mount_selector: str
    surface_type: str
    transport: str
    camera_index_code: str
    preview_url: str
    preview_protocol: str | None = None
    attach_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class RendererCommand:
    command_id: str
    action: str
    tile_index: int
    kind: RendererKind
    bridge_method: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class RendererBridgeCheckpoint:
    last_action: str = "Idle"
    driver_mode: RendererDriverMode = RendererDriverMode.DRY_RUN
    pending_commands: list[RendererCommand] = field(default_factory=list)
    recent_history: list[RendererCommand] = field(default_factory=list)


@dataclass
class RendererExecutionResult:
    command_id: str
    action: str
    tile_index: int
    driver_mode: RendererDriverMode
    status: str
    summary: str


@dataclass
class RendererDriverLifecycle:
    phase: str
    status: str
    driver_mode: RendererDriverMode
    runtime_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RendererDriverCapability:
    init: bool = True
    attach: bool = True
    refresh: bool = True
    detach: bool = True
    dispose: bool = True
    requires_bridge: bool = False
    requires_runtime: bool = True


@dataclass
class RendererHostContract:
    host_type: str
    required_methods: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class RendererHealthCheckpoint:
    bridge_readiness: str = "Pending"
    host_readiness: str = "Pending"
    heartbeat_enabled: bool = False
    heartbeat_interval_ms: int = 4800
    heartbeat_status: str = "Stopped"
    last_heartbeat_at: str | None = None
    last_check_at: str | None = None
    last_summary: str = "Not checked"
    recovery_policy: str = "reinit-driver"
    last_recovery_action: str = "Not triggered"
    failure_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RendererHostPreflight:
    overall: str = "Pending"
    blocking_issues: int = 0
    missing_methods: list[str] = field(default_factory=list)
    missing_artifacts: list[str] = field(default_factory=list)
    checked_at: str | None = None
    last_export_at: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RendererAdmissionCheckpoint:
    last_action: str = "None"
    last_decision: str = "Not evaluated"
    last_checked_at: str | None = None
    last_summary: str = "Not evaluated"
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RendererActionPolicyCheckpoint:
    last_evaluated_at: str | None = None
    summary: str = "Not evaluated"
    matrix: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RendererProfileCheckpoint:
    preset: str = "auto"
    resolved_preset: str = "auto"
    summary: str = "Auto"
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RendererBridgeTemplateCheckpoint:
    host_type: str = "unknown"
    driver_kind: str = "mock-ws"
    required_methods: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    method_templates: dict[str, str] = field(default_factory=dict)


@dataclass
class RendererDriverTemplateCheckpoint:
    driver_kind: str = "mock-ws"
    runtime_prefix: str = "drv"
    capabilities: dict[str, Any] = field(default_factory=dict)
    lifecycle: dict[str, Any] = field(default_factory=dict)
    implementation_checklist: list[str] = field(default_factory=list)


@dataclass
class RendererTemplatePresetCheckpoint:
    bridge_preset: str = "auto"
    resolved_bridge_preset: str = "auto"
    driver_preset: str = "auto"
    resolved_driver_preset: str = "auto"
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RuntimeBundle:
    session: LayoutSession
    polling: PollingCheckpoint
    renderer: RendererCheckpoint
    bridge: RendererBridgeCheckpoint = field(default_factory=RendererBridgeCheckpoint)
    attachments: list[RendererAttachment] = field(default_factory=list)
    attach_payloads: list[RendererAttachPayload] = field(default_factory=list)
    execution_results: list[RendererExecutionResult] = field(default_factory=list)
    driver_lifecycle: list[RendererDriverLifecycle] = field(default_factory=list)
    driver_capability: RendererDriverCapability | None = None
    host_contract: RendererHostContract | None = None
    health: RendererHealthCheckpoint | None = None
    host_preflight: RendererHostPreflight | None = None
    admission: RendererAdmissionCheckpoint | None = None
    action_policy: RendererActionPolicyCheckpoint | None = None
    profile: RendererProfileCheckpoint | None = None
    bridge_template: RendererBridgeTemplateCheckpoint | None = None
    driver_template: RendererDriverTemplateCheckpoint | None = None
    template_presets: RendererTemplatePresetCheckpoint | None = None


class IResourceCatalog(Protocol):
    def list_cameras(self) -> list[CameraResource]: ...


class IPreviewBackend(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def configure_renderer(self, kind: RendererKind) -> None: ...
    def apply_layout(self, layout: LayoutPreset) -> None: ...
    def bind_tiles(self, bindings: list[TileBinding]) -> None: ...
    def select_tile(self, tile_index: int) -> None: ...
    def enter_fullscreen(self, tile_index: int) -> None: ...
    def exit_fullscreen(self) -> None: ...


class IPollingRuntime(Protocol):
    def seed_route(self, tile_indexes: list[int]) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def step_next(self) -> None: ...
    def set_mode(self, mode: PollingMode) -> None: ...
    def set_dwell_ms(self, dwell_ms: int) -> None: ...
    def change_layout(self, layout: LayoutPreset) -> None: ...
