(function () {
  const state = {
    bridgeAvailable: typeof window !== "undefined" && typeof window.cefQuery === "function",
    mockMode: false,
    loginInfo: null,
    ticketInfo: null,
    serviceInfo: null,
    lastTreeCodes: null,
    lastRegions: null,
    lastCameraList: null,
    lastPreviewResponse: null,
    previewUrlByCamera: {},
    autorunStarted: false,
    layout: 4,
    selectedTileIndex: 0,
    fullscreenTileIndex: null,
    tiles: [],
    selectedCameraCodes: [],
    tvwallResources: null,
    tvwallScenes: null,
    tvwallWindows: null,
    selectedDlpId: "",
    selectedMonitorPos: "",
    selectedFloatWindowId: "",
    selectedWndUri: "",
    playerTickSeed: 0,
    renderer: {
      kind: "mock-ws",
      autoAttach: true,
      lastEvent: "Idle",
      bridgeAction: "Idle",
      driverMode: "dry-run",
      lastDriverRun: "Not executed",
      driverInitialized: false,
      driverRuntimeId: "",
      lastDriverLifecycle: "Not initialized",
      lastHostContractExport: "Not exported",
      lastBridgeTemplateExport: "Not exported",
      lastDriverTemplateExport: "Not exported",
      lastImplementationPackageExport: "Not exported",
      commandQueue: [],
      commandHistory: [],
      executionResults: [],
      lifecycleHistory: [],
      health: {
        bridgeReadiness: "Pending",
        hostReadiness: "Pending",
        heartbeatEnabled: false,
        heartbeatIntervalMs: 4800,
        heartbeatStatus: "Stopped",
        lastHeartbeatAt: "",
        lastCheckAt: "",
        lastSummary: "Not checked",
        recoveryPolicy: "reinit-driver",
        lastRecoveryAction: "Not triggered",
        failureCount: 0,
        timerId: null,
        history: []
      },
      preflight: {
        overall: "Pending",
        blockingIssues: 0,
        missingMethods: [],
        missingArtifacts: [],
        checkedAt: "",
        lastExportAt: "",
        history: []
      },
      admission: {
        lastAction: "None",
        lastDecision: "Not evaluated",
        lastCheckedAt: "",
        lastSummary: "Not evaluated",
        blockingReasons: [],
        warnings: [],
        history: []
      },
      actionPolicy: {
        lastEvaluatedAt: "",
        summary: "Not evaluated",
        matrix: {},
        history: []
      },
      profile: {
        preset: "auto",
        resolvedPreset: "auto",
        summary: "Auto",
        history: []
      },
      templatePresets: {
        bridgePreset: "auto",
        resolvedBridgePreset: "auto",
        driverPreset: "auto",
        resolvedDriverPreset: "auto",
        history: []
      }
    },
    runtimeBundleStatus: "Not exported",
    polling: {
      mode: "select",
      dwellMs: 2200,
      route: [],
      running: false,
      currentRouteIndex: -1,
      cycleCount: 0,
      lastStepAt: 0,
      timerId: null
    },
    mockTvwallState: {
      monitorDivision: 4,
      floatDivision: 4,
      zoomMode: "grid"
    },
    authProbe: {
      running: false,
      status: "Idle",
      lastRunAt: "",
      lastSummary: "Not run",
      resultText: "Waiting for container auth probe...",
      snapshot: null
    }
  };

  const el = {
    bridgeMode: document.getElementById("bridge-mode"),
    runtimeModeValue: document.getElementById("runtime-mode-value"),
    ticketValue: document.getElementById("ticket-value"),
    layoutValue: document.getElementById("layout-value"),
    selectedTileValue: document.getElementById("selected-tile-value"),
    authProbeStatusValue: document.getElementById("auth-probe-status-value"),
    authProbeXresValue: document.getElementById("auth-probe-xres-value"),
    authProbeTvmsValue: document.getElementById("auth-probe-tvms-value"),
    authProbeContextValue: document.getElementById("auth-probe-context-value"),
    authProbeResult: document.getElementById("auth-probe-result"),
    boundCameraCount: document.getElementById("bound-camera-count"),
    resolvedUrlCount: document.getElementById("resolved-url-count"),
    fullscreenValue: document.getElementById("fullscreen-value"),
    platformBaseUrl: document.getElementById("platform-base-url"),
    platformToken: document.getElementById("platform-token"),
    serviceType: document.getElementById("service-type"),
    componentId: document.getElementById("component-id"),
    treeCode: document.getElementById("tree-code"),
    regionPageSize: document.getElementById("region-page-size"),
    cameraPageNo: document.getElementById("camera-page-no"),
    cameraPageSize: document.getElementById("camera-page-size"),
    cameraIndexCode: document.getElementById("camera-index-code"),
    streamType: document.getElementById("stream-type"),
    protocol: document.getElementById("protocol"),
    transmode: document.getElementById("transmode"),
    expand: document.getElementById("expand"),
    rendererKind: document.getElementById("renderer-kind"),
    rendererAutoAttach: document.getElementById("renderer-auto-attach"),
    rendererModeValue: document.getElementById("renderer-mode-value"),
    rendererAttachedValue: document.getElementById("renderer-attached-value"),
    rendererReadyValue: document.getElementById("renderer-ready-value"),
    rendererEventValue: document.getElementById("renderer-event-value"),
    rendererSelectedPayloadValue: document.getElementById("renderer-selected-payload-value"),
    runtimeBundleValue: document.getElementById("runtime-bundle-value"),
    rendererCommandQueueValue: document.getElementById("renderer-command-queue-value"),
    rendererBridgeActionValue: document.getElementById("renderer-bridge-action-value"),
    rendererDriverModeValue: document.getElementById("renderer-driver-mode-value"),
    rendererDriverRunValue: document.getElementById("renderer-driver-run-value"),
    rendererDriverStateValue: document.getElementById("renderer-driver-state-value"),
    rendererDriverRuntimeValue: document.getElementById("renderer-driver-runtime-value"),
    rendererDriverCapabilityValue: document.getElementById("renderer-driver-capability-value"),
    rendererHostContractValue: document.getElementById("renderer-host-contract-value"),
    rendererBridgeReadinessValue: document.getElementById("renderer-bridge-readiness-value"),
    rendererHostReadinessValue: document.getElementById("renderer-host-readiness-value"),
    rendererHeartbeatValue: document.getElementById("renderer-heartbeat-value"),
    rendererRecoveryPolicyValue: document.getElementById("renderer-recovery-policy-value"),
    rendererPreflightStatusValue: document.getElementById("renderer-preflight-status-value"),
    rendererPreflightIssuesValue: document.getElementById("renderer-preflight-issues-value"),
    rendererAdmissionStatusValue: document.getElementById("renderer-admission-status-value"),
    rendererAdmissionActionValue: document.getElementById("renderer-admission-action-value"),
    rendererActionPolicyValue: document.getElementById("renderer-action-policy-value"),
    rendererProfileValue: document.getElementById("renderer-profile-value"),
    rendererTemplatePresetValue: document.getElementById("renderer-template-preset-value"),
    rendererDriverMode: document.getElementById("renderer-driver-mode"),
    rendererProfilePreset: document.getElementById("renderer-profile-preset"),
    rendererBridgeTemplatePreset: document.getElementById("renderer-bridge-template-preset"),
    rendererDriverTemplatePreset: document.getElementById("renderer-driver-template-preset"),
    rendererRecoveryPolicy: document.getElementById("renderer-recovery-policy"),
    rendererHeartbeatMs: document.getElementById("renderer-heartbeat-ms"),
    pollingMode: document.getElementById("polling-mode"),
    pollingDwellMs: document.getElementById("polling-dwell-ms"),
    pollingStateValue: document.getElementById("polling-state-value"),
    pollingRouteLengthValue: document.getElementById("polling-route-length-value"),
    pollingCurrentValue: document.getElementById("polling-current-value"),
    pollingCycleValue: document.getElementById("polling-cycle-value"),
    previewStage: document.getElementById("preview-stage"),
    cameraTableBody: document.getElementById("camera-table-body"),
    lastPreviewResponse: document.getElementById("last-preview-response"),
    tvwallSnapshot: document.getElementById("tvwall-snapshot"),
    runtimeSessionSnapshot: document.getElementById("runtime-session-snapshot"),
    rendererDiagnosticsSnapshot: document.getElementById("renderer-diagnostics-snapshot"),
    rendererAttachPlanSnapshot: document.getElementById("renderer-attach-plan-snapshot"),
    rendererCommandSnapshot: document.getElementById("renderer-command-snapshot"),
    rendererExecutionSnapshot: document.getElementById("renderer-execution-snapshot"),
    rendererDriverSnapshot: document.getElementById("renderer-driver-snapshot"),
    rendererHostContractSnapshot: document.getElementById("renderer-host-contract-snapshot"),
    rendererBridgeTemplateSnapshot: document.getElementById("renderer-bridge-template-snapshot"),
    rendererDriverTemplateSnapshot: document.getElementById("renderer-driver-template-snapshot"),
    rendererImplementationPackageSnapshot: document.getElementById("renderer-implementation-package-snapshot"),
    rendererHealthSnapshot: document.getElementById("renderer-health-snapshot"),
    rendererHostPreflightSnapshot: document.getElementById("renderer-host-preflight-snapshot"),
    rendererAdmissionSnapshot: document.getElementById("renderer-admission-snapshot"),
    rendererActionPolicySnapshot: document.getElementById("renderer-action-policy-snapshot"),
    rendererProfileSnapshot: document.getElementById("renderer-profile-snapshot"),
    rendererTemplatePresetSnapshot: document.getElementById("renderer-template-preset-snapshot"),
    runtimeIoBuffer: document.getElementById("runtime-io-buffer"),
    terminal: document.getElementById("terminal"),
    tvwallDlpId: document.getElementById("tvwall-dlp-id"),
    tvwallMonitorPos: document.getElementById("tvwall-monitor-pos"),
    tvwallFloatWindowId: document.getElementById("tvwall-floatwnd-id"),
    tvwallWndUri: document.getElementById("tvwall-wnd-uri"),
    btnLogin: document.getElementById("btn-login"),
    btnTicket: document.getElementById("btn-ticket"),
    btnService: document.getElementById("btn-service"),
    btnRunAuthProbe: document.getElementById("btn-run-auth-probe"),
    btnCopyAuthProbe: document.getElementById("btn-copy-auth-probe"),
    btnRunMinChain: document.getElementById("btn-run-min-chain"),
    btnEnableMock: document.getElementById("btn-enable-mock"),
    btnDisableMock: document.getElementById("btn-disable-mock"),
    btnRunLocalDemo: document.getElementById("btn-run-local-demo"),
    btnAttachRenderers: document.getElementById("btn-attach-renderers"),
    btnDetachRenderers: document.getElementById("btn-detach-renderers"),
    btnSaveSession: document.getElementById("btn-save-session"),
    btnLoadSession: document.getElementById("btn-load-session"),
    btnResetSession: document.getElementById("btn-reset-session"),
    btnRefreshDiagnostics: document.getElementById("btn-refresh-diagnostics"),
    btnExportAttachPlan: document.getElementById("btn-export-attach-plan"),
    btnExportHostContract: document.getElementById("btn-export-host-contract"),
    btnExportBridgeTemplate: document.getElementById("btn-export-bridge-template"),
    btnExportDriverTemplate: document.getElementById("btn-export-driver-template"),
    btnExportImplementationPackage: document.getElementById("btn-export-implementation-package"),
    btnExportRuntimeJson: document.getElementById("btn-export-runtime-json"),
    btnImportRuntimeJson: document.getElementById("btn-import-runtime-json"),
    btnPreviewSelectedCommand: document.getElementById("btn-preview-selected-command"),
    btnPreviewSweepCommands: document.getElementById("btn-preview-sweep-commands"),
    btnRunCommandQueue: document.getElementById("btn-run-command-queue"),
    btnReplayCommandHistory: document.getElementById("btn-replay-command-history"),
    btnInitDriver: document.getElementById("btn-init-driver"),
    btnDisposeDriver: document.getElementById("btn-dispose-driver"),
    btnRunHealthCheck: document.getElementById("btn-run-health-check"),
    btnToggleHeartbeat: document.getElementById("btn-toggle-heartbeat"),
    btnApplyProfileDefaults: document.getElementById("btn-apply-profile-defaults"),
    btnTriggerRecovery: document.getElementById("btn-trigger-recovery"),
    btnRunPreflight: document.getElementById("btn-run-preflight"),
    btnExportPreflight: document.getElementById("btn-export-preflight"),
    btnClearCommandQueue: document.getElementById("btn-clear-command-queue"),
    btnSeedPolling: document.getElementById("btn-seed-polling"),
    btnStartPolling: document.getElementById("btn-start-polling"),
    btnStopPolling: document.getElementById("btn-stop-polling"),
    btnStepPolling: document.getElementById("btn-step-polling"),
    btnSavePrefs: document.getElementById("btn-save-prefs"),
    btnTreeCodes: document.getElementById("btn-tree-codes"),
    btnRegions: document.getElementById("btn-regions"),
    btnCameras: document.getElementById("btn-cameras"),
    btnBindFirst: document.getElementById("btn-bind-first"),
    btnPreviewUrl: document.getElementById("btn-preview-url"),
    btnResolveBound: document.getElementById("btn-resolve-bound"),
    btnClearWall: document.getElementById("btn-clear-wall"),
    btnLayout4: document.getElementById("btn-layout-4"),
    btnLayout9: document.getElementById("btn-layout-9"),
    btnLayout12: document.getElementById("btn-layout-12"),
    btnFullscreenSelected: document.getElementById("btn-fullscreen-selected"),
    btnExitFullscreen: document.getElementById("btn-exit-fullscreen"),
    btnRunFullChain: document.getElementById("btn-run-full-chain"),
    btnClearLog: document.getElementById("btn-clear-log"),
    btnTvwallResources: document.getElementById("btn-tvwall-resources"),
    btnTvwallScenes: document.getElementById("btn-tvwall-scenes"),
    btnTvwallWnds: document.getElementById("btn-tvwall-wnds"),
    btnTvwallDiv4: document.getElementById("btn-tvwall-div4"),
    btnTvwallDiv9: document.getElementById("btn-tvwall-div9"),
    btnTvwallDiv12: document.getElementById("btn-tvwall-div12"),
    btnTvwallFloatDiv4: document.getElementById("btn-tvwall-float-div4"),
    btnTvwallFloatDiv9: document.getElementById("btn-tvwall-float-div9"),
    btnTvwallFloatDiv12: document.getElementById("btn-tvwall-float-div12"),
    btnTvwallZoomNormal: document.getElementById("btn-tvwall-zoom-normal"),
    btnTvwallZoomFull: document.getElementById("btn-tvwall-zoom-full"),
    btnTvwallZoomOut: document.getElementById("btn-tvwall-zoom-out"),
    btnRunReplaySequence: document.getElementById("btn-run-replay-sequence")
  };

  const MOCK_FIXTURES = (function buildMockFixtures() {
    const cameras = [];
    for (let index = 1; index <= 16; index += 1) {
      const code = "mock-camera-" + String(index).padStart(2, "0");
      cameras.push({
        cameraIndexCode: code,
        name: "离线示例点位 " + String(index),
        cameraName: "离线示例点位 " + String(index),
        unitName: index <= 8 ? "综合治理中心" : "应急联动大厅",
        regionName: index <= 8 ? "主楼区域" : "副楼区域",
        deviceIndexCode: "mock-device-" + String(Math.ceil(index / 2)).padStart(2, "0")
      });
    }
    return {
      loginInfo: {
        data: {
          protocol: "https",
          host: "mock.infovision.local",
          port: "443",
          userIndexCode: "mock-operator-001",
          appName: "platform_spike_mock"
        }
      },
      ticketInfo: {
        code: "0",
        msg: "SUCCESS",
        data: {
          ticket: "mock-ticket-offline-replay",
          tokenType: 1,
          expiresIn: 7200
        }
      },
      serviceInfo: {
        code: "0",
        msg: "SUCCESS",
        data: {
          serviceType: "upm",
          componentId: "upm",
          routeMode: "offline-replay",
          endpoint: "mock://platform-spike/upm"
        }
      },
      treeCodes: {
        code: "0",
        msg: "SUCCESS",
        data: {
          treeCodes: ["0", "mock-root-001"]
        }
      },
      regions: {
        code: "0",
        msg: "SUCCESS",
        data: {
          total: 2,
          list: [
            { regionIndexCode: "mock-region-001", regionName: "综合治理中心", treeCode: "mock-root-001" },
            { regionIndexCode: "mock-region-002", regionName: "应急联动大厅", treeCode: "mock-root-001" }
          ]
        }
      },
      cameras: {
        code: "0",
        msg: "SUCCESS",
        data: {
          total: cameras.length,
          list: cameras
        }
      },
      tvwallResources: {
        code: "0",
        msg: "SUCCESS",
        data: {
          tvwalls: [
            {
              dlp_id: 9001,
              tvwall_name: "Mock TV Wall",
              monitors: [
                { pos: 1, monitor_name: "Monitor 1" },
                { pos: 2, monitor_name: "Monitor 2" }
              ],
              windows: [
                { floatwnd_id: 5001, wnd_uri: "mock://tvwall/window/5001", wnd_name: "Mock Window A" },
                { floatwnd_id: 5002, wnd_uri: "mock://tvwall/window/5002", wnd_name: "Mock Window B" }
              ]
            }
          ]
        }
      },
      tvwallScenes: {
        code: "0",
        msg: "SUCCESS",
        data: {
          list: [
            { scene_id: 3001, scene_name: "白天轮巡" },
            { scene_id: 3002, scene_name: "夜间值守" }
          ]
        }
      },
      tvwallWindows: {
        code: "0",
        msg: "SUCCESS",
        data: {
          list: [
            { floatwnd_id: 5001, wnd_uri: "mock://tvwall/window/5001", wnd_name: "Mock Window A" },
            { floatwnd_id: 5002, wnd_uri: "mock://tvwall/window/5002", wnd_name: "Mock Window B" }
          ]
        }
      }
    };
  })();

  const SETTINGS_STORAGE_KEY = "platform_spike_poc_settings_v1";
  const SESSION_STORAGE_KEY = "platform_spike_poc_runtime_session_v1";
  const AUTH_PROBE_STORAGE_KEY = "platform_spike_poc_container_auth_result_v1";
  const DRIVER_PROFILE_PRESETS = {
    auto: {
      label: "Auto",
      notes: ["按当前 driver kind、bridge 和 mock 状态自动推导。"]
    },
    "strict-browser": {
      label: "Strict Browser",
      requireBridgeForPlugin: true,
      blockPluginWithoutBridge: true,
      recommendedDriverMode: "dry-run",
      recommendedAutoAttach: false,
      recommendedRecoveryPolicy: "reinit-driver",
      recommendedHeartbeatMs: 6000,
      warnings: ["适合普通浏览器空环境，优先暴露阻塞项。"]
    },
    "mock-demo": {
      label: "Mock Demo",
      allowStubBridge: true,
      allowFullscreenWithoutAttached: true,
      allowRoutePreviewWithoutFullscreenMode: true,
      recommendedDriverMode: "bridge-stub",
      recommendedAutoAttach: true,
      recommendedRecoveryPolicy: "clear-queue-reinit",
      recommendedHeartbeatMs: 3200,
      warnings: ["适合离线演示和 mock 回放。"]
    },
    "plugin-bridge-ready": {
      label: "Plugin Bridge Ready",
      requireBridgeForPlugin: true,
      requireAttachedForFullscreen: true,
      recommendedDriverMode: "bridge-stub",
      recommendedAutoAttach: true,
      recommendedRecoveryPolicy: "reinit-driver",
      recommendedHeartbeatMs: 2600,
      warnings: ["适合已具备 webcontainer / plugin bridge 的运行时。"]
    },
    "media-runtime-ready": {
      label: "Media Runtime Ready",
      requireBridgeForPlugin: false,
      requireAttachedForFullscreen: true,
      allowRoutePreviewWithoutFullscreenMode: false,
      recommendedDriverMode: "simulate-success",
      recommendedAutoAttach: true,
      recommendedRecoveryPolicy: "replay-history",
      recommendedHeartbeatMs: 2400,
      warnings: ["适合真实 ws / hls 媒体承载运行时。"]
    }
  };
  const BRIDGE_TEMPLATE_PRESETS = {
    auto: {
      label: "Auto"
    },
    "webcontainer-js-interface": {
      label: "Webcontainer JS Interface",
      hostType: "webcontainer-plugin-host",
      methods: ["initializePluginHost", "requestInterface", "startPreview", "stopPreview", "disposePluginHost"]
    },
    "webcontrol-local-service": {
      label: "WebControl Local Service",
      hostType: "webcontrol-local-service",
      methods: ["launchLocalService", "createPluginWindow", "invokePreview", "stopPreview", "disposePluginWindow"]
    },
    "html5-media-basic": {
      label: "HTML5 Media Basic",
      hostType: "html-media",
      methods: ["createVideoElement", "loadSource", "reloadSource", "detachSource", "disposeVideoElement"]
    },
    "canvas-socket-basic": {
      label: "Canvas Socket Basic",
      hostType: "canvas-bridge",
      methods: ["createSurface", "connectSocket", "refreshSocket", "closeSocket", "disposeSurface"]
    }
  };
  const DRIVER_TEMPLATE_PRESETS = {
    auto: {
      label: "Auto"
    },
    "plugin-session-driver": {
      label: "Plugin Session Driver",
      runtimePrefix: "drv-plugin",
      attachStrategy: "plugin-session"
    },
    "hls-hlsjs-driver": {
      label: "HLS.js Driver",
      runtimePrefix: "drv-hls",
      attachStrategy: "hlsjs"
    },
    "hls-native-driver": {
      label: "Native HLS Driver",
      runtimePrefix: "drv-hls-native",
      attachStrategy: "native-hls"
    },
    "ws-canvas-driver": {
      label: "WS Canvas Driver",
      runtimePrefix: "drv-ws",
      attachStrategy: "canvas-ws"
    },
    "ws-webcodecs-driver": {
      label: "WS WebCodecs Driver",
      runtimePrefix: "drv-webcodecs",
      attachStrategy: "webcodecs-ws"
    }
  };
  const RENDERER_DRIVERS = {
    "mock-ws": {
      label: "Mock WS Driver",
      runtimePrefix: "drv-ws",
      initAction: "connectRuntime",
      disposeAction: "disposeRuntime",
      capabilities: {
        init: true,
        attach: true,
        refresh: true,
        detach: true,
        dispose: true,
        requiresBridge: false,
        requiresRuntime: true
      },
      hostContract: {
        hostType: "canvas-bridge",
        requiredMethods: ["createSurface", "connectSocket", "refreshSocket", "closeSocket", "disposeSurface"],
        requiredArtifacts: ["canvas-element", "ws-endpoint", "codec-hint"],
        notes: ["适合后续接 ws + canvas 解码链。"]
      }
    },
    "mock-hls": {
      label: "Mock HLS Driver",
      runtimePrefix: "drv-hls",
      initAction: "bootstrapMediaPipeline",
      disposeAction: "teardownMediaPipeline",
      capabilities: {
        init: true,
        attach: true,
        refresh: true,
        detach: true,
        dispose: true,
        requiresBridge: false,
        requiresRuntime: true
      },
      hostContract: {
        hostType: "html-media",
        requiredMethods: ["createVideoElement", "loadSource", "reloadSource", "detachSource", "disposeVideoElement"],
        requiredArtifacts: ["video-element", "playlist-url", "autoplay-policy"],
        notes: ["适合后续接 HLS.js 或原生 m3u8 承载。"]
      }
    },
    "web-plugin-stub": {
      label: "Web Plugin Driver",
      runtimePrefix: "drv-plugin",
      initAction: "initializePluginHost",
      disposeAction: "disposePluginHost",
      capabilities: {
        init: true,
        attach: true,
        refresh: true,
        detach: true,
        dispose: true,
        requiresBridge: true,
        requiresRuntime: true
      },
      hostContract: {
        hostType: "webcontainer-plugin-host",
        requiredMethods: ["initializePluginHost", "JS_RequestInterface.startPreview", "JS_RequestInterface.stopPreview", "disposePluginHost"],
        requiredArtifacts: ["plugin-container", "cameraIndexCode", "plugin-url", "container-id"],
        notes: ["适合后续接平台 web 插件或 WebControl 容器桥。"]
      }
    }
  };
  const RENDERER_ADAPTERS = {
    "mock-ws": {
      label: "Mock WS Renderer",
      surfaceType: "canvas-overlay",
      transport: "ws",
      attach: function (tile) {
        const normalizedUrl = (tile.previewUrl || "").replace(/^https?:\/\//, "ws://").replace(/^wss?:\/\//, "ws://");
        return {
          attached: !!normalizedUrl,
          sessionId: "ws-" + tile.tileIndex + "-" + (tile.cameraIndexCode || "unknown"),
          surfaceType: "canvas-overlay",
          transport: "ws",
          displayUrl: normalizedUrl,
          status: normalizedUrl ? "WS mock stream attached" : "WS mock stream unavailable"
        };
      }
    },
    "mock-hls": {
      label: "Mock HLS Renderer",
      surfaceType: "video-element",
      transport: "hls",
      attach: function (tile) {
        const normalizedUrl = (tile.previewUrl || "")
          .replace(/^wss?:\/\//, "https://")
          .replace(/^rtsp:\/\//, "https://")
          .replace(/^rtmp:\/\//, "https://")
          .replace(/(\?.*)?$/, ".m3u8");
        return {
          attached: !!normalizedUrl,
          sessionId: "hls-" + tile.tileIndex + "-" + (tile.cameraIndexCode || "unknown"),
          surfaceType: "video-element",
          transport: "hls",
          displayUrl: normalizedUrl,
          status: normalizedUrl ? "HLS mock stream attached" : "HLS mock stream unavailable"
        };
      }
    },
    "web-plugin-stub": {
      label: "Web Plugin Stub",
      surfaceType: "plugin-container",
      transport: "plugin",
      attach: function (tile) {
        const normalizedUrl = "plugin://preview?cameraIndexCode=" + encodeURIComponent(tile.cameraIndexCode || "");
        return {
          attached: !!tile.cameraIndexCode,
          sessionId: "plugin-" + tile.tileIndex + "-" + (tile.cameraIndexCode || "unknown"),
          surfaceType: "plugin-container",
          transport: "plugin",
          displayUrl: normalizedUrl,
          status: tile.cameraIndexCode ? "Plugin stub attached" : "Plugin stub requires camera binding"
        };
      }
    }
  };

  function safeJson(value) {
    if (typeof value !== "string") {
      return value;
    }
    try {
      return JSON.parse(value);
    } catch (error) {
      return value;
    }
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function pretty(value) {
    if (typeof value === "string") {
      return value;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch (error) {
      return String(value);
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function log(kind, label, payload) {
    const line = document.createElement("div");
    line.className = kind;
    const stamp = new Date().toLocaleTimeString();
    let content = "[" + stamp + "] " + label;
    if (payload !== undefined) {
      content += "\n" + pretty(payload);
    }
    line.textContent = content;
    el.terminal.appendChild(line);
    el.terminal.scrollTop = el.terminal.scrollHeight;
  }

  function getSearchParam(name) {
    return new URLSearchParams(window.location.search || "").get(name);
  }

  function shouldAutorun() {
    return getSearchParam("autorun") === "1";
  }

  function shouldUseMock() {
    return getSearchParam("mock") === "1";
  }

  function redactToken(token) {
    const value = String(token || "");
    if (!value) {
      return "missing";
    }
    if (value.length <= 8) {
      return "present(len=" + String(value.length) + ")";
    }
    return value.slice(0, 4) + "..." + value.slice(-4) + " (len=" + String(value.length) + ")";
  }

  function summarizePayload(payload) {
    if (payload === null || payload === undefined) {
      return "empty";
    }
    const text = typeof payload === "string" ? payload : pretty(payload);
    const compact = String(text).replace(/\s+/g, " ").trim();
    if (!compact) {
      return "empty";
    }
    return compact.length > 180 ? compact.slice(0, 177) + "..." : compact;
  }

  function hasAppAuthFailure(payload) {
    const text = summarizePayload(payload);
    return /token is null|request forbidden|0x11900001|forbidden/i.test(text);
  }

  function looksSuccessfulPayload(payload) {
    if (payload === null || payload === undefined) {
      return false;
    }
    if (hasAppAuthFailure(payload)) {
      return false;
    }
    if (typeof payload === "string") {
      return /\bok\b|success|healthy|true/i.test(payload);
    }
    if (payload && typeof payload === "object") {
      const code = payload.code;
      const msg = payload.msg || payload.message || "";
      if (code === 0 || code === "0" || code === 200 || code === "200") {
        return true;
      }
      if (typeof msg === "string" && /\bok\b|success|healthy/i.test(msg)) {
        return true;
      }
      if (payload.data && typeof payload.data === "object") {
        return Object.keys(payload.data).length > 0;
      }
      if (Array.isArray(payload.data)) {
        return payload.data.length > 0;
      }
    }
    return false;
  }

  function probeOutcomeLabel(result) {
    if (!result) {
      return "Not run";
    }
    const candidate = result.bestCandidate ? " / " + result.bestCandidate : "";
    return result.status + candidate;
  }

  function authProbeContexts() {
    return {
      xresSearch: "/xres-search",
      tvms: "/tvms"
    };
  }

  function userIndexCodeFromObject(root) {
    const visited = new Set();
    const queue = [root];
    const keyOrder = ["userIndexCode", "userCode", "userId", "loginName", "username"];
    while (queue.length) {
      const current = queue.shift();
      if (!current || typeof current !== "object" || visited.has(current)) {
        continue;
      }
      visited.add(current);
      for (let index = 0; index < keyOrder.length; index += 1) {
        const key = keyOrder[index];
        const value = current[key];
        if (typeof value === "string" && value.trim()) {
          return value.trim();
        }
      }
      Object.keys(current).forEach(function (key) {
        const value = current[key];
        if (value && typeof value === "object") {
          queue.push(value);
        }
      });
    }
    return "";
  }

  function resolveUserIndexCode() {
    return userIndexCodeFromObject(state.loginInfo) || "admin";
  }

  function resolvePlatformBaseUrl() {
    return normalizeBaseUrl() || candidateBaseUrl(state.loginInfo) || "";
  }

  function buildAuthProbeSummary(snapshot) {
    if (!snapshot) {
      return "Not run";
    }
    if (snapshot.xresProbe && snapshot.xresProbe.ok && snapshot.tvmsAllProbe && snapshot.tvmsAllProbe.ok) {
      return "xres/tvms ready";
    }
    if ((snapshot.xresProbe && snapshot.xresProbe.status === "auth-failed")
      || (snapshot.tvmsAllProbe && snapshot.tvmsAllProbe.status === "auth-failed")
      || (snapshot.tvmsRuokProbe && snapshot.tvmsRuokProbe.status === "auth-failed")) {
      return "auth mismatch";
    }
    if ((snapshot.xresProbe && snapshot.xresProbe.status === "transport-failed")
      && (snapshot.tvmsAllProbe && snapshot.tvmsAllProbe.status === "transport-failed")
      && (!snapshot.tvmsRuokProbe || snapshot.tvmsRuokProbe.status === "transport-failed")) {
      return "network or proxy unstable";
    }
    return "partial readiness";
  }

  function buildAuthProbeResultBlock(snapshot) {
    if (!snapshot) {
      return "Waiting for container auth probe...";
    }
    const lines = [
      "=== CONTAINER_AUTH_RESULT ===",
      "generatedAt=" + snapshot.generatedAt,
      "bridgeMode=" + snapshot.bridgeMode,
      "runtimeMode=" + snapshot.runtimeMode,
      "platformBaseUrl=" + (snapshot.platformBaseUrl || ""),
      "userIndexCode=" + snapshot.userIndexCode,
      "xresContext=" + snapshot.contexts.xresSearch,
      "tvmsContext=" + snapshot.contexts.tvms,
      "ticket.type0_token1=" + snapshot.ticketVariants.type0_token1,
      "ticket.type0_token2=" + snapshot.ticketVariants.type0_token2,
      "ticket.type2=" + snapshot.ticketVariants.type2,
      "xres.status=" + snapshot.xresProbe.status,
      "xres.bestCandidate=" + (snapshot.xresProbe.bestCandidate || ""),
      "xres.summary=" + snapshot.xresProbe.summary,
      "tvmsAll.status=" + snapshot.tvmsAllProbe.status,
      "tvmsAll.bestCandidate=" + (snapshot.tvmsAllProbe.bestCandidate || ""),
      "tvmsAll.summary=" + snapshot.tvmsAllProbe.summary,
      "tvmsRuok.status=" + snapshot.tvmsRuokProbe.status,
      "tvmsRuok.bestCandidate=" + (snapshot.tvmsRuokProbe.bestCandidate || ""),
      "tvmsRuok.summary=" + snapshot.tvmsRuokProbe.summary,
      "nextStep=" + snapshot.nextStep,
      "CONTAINER_AUTH_RESULT_END"
    ];
    return lines.join("\n");
  }

  function readStoredSettings() {
    try {
      const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
      return raw ? safeJson(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function readStoredAuthProbeSnapshot() {
    try {
      const raw = window.localStorage.getItem(AUTH_PROBE_STORAGE_KEY);
      return raw ? safeJson(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function writeStoredAuthProbeSnapshot() {
    try {
      window.localStorage.setItem(AUTH_PROBE_STORAGE_KEY, JSON.stringify({
        running: false,
        status: state.authProbe.status,
        lastRunAt: state.authProbe.lastRunAt,
        lastSummary: state.authProbe.lastSummary,
        resultText: state.authProbe.resultText,
        snapshot: state.authProbe.snapshot
      }));
    } catch (error) {
      log("warn", "Saving auth probe snapshot failed", String(error && error.message ? error.message : error));
    }
  }

  function applyStoredAuthProbeSnapshot() {
    const stored = readStoredAuthProbeSnapshot();
    if (!stored || typeof stored !== "object") {
      return;
    }
    state.authProbe.running = false;
    state.authProbe.status = typeof stored.status === "string" && stored.status ? stored.status : state.authProbe.status;
    state.authProbe.lastRunAt = typeof stored.lastRunAt === "string" ? stored.lastRunAt : "";
    state.authProbe.lastSummary = typeof stored.lastSummary === "string" && stored.lastSummary ? stored.lastSummary : state.authProbe.lastSummary;
    state.authProbe.resultText = typeof stored.resultText === "string" && stored.resultText ? stored.resultText : state.authProbe.resultText;
    state.authProbe.snapshot = stored.snapshot && typeof stored.snapshot === "object" ? stored.snapshot : null;
  }

  function writeStoredSettings() {
    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify({
        layout: state.layout,
        protocol: el.protocol.value,
        rendererKind: state.renderer.kind,
        rendererAutoAttach: state.renderer.autoAttach,
        rendererDriverMode: state.renderer.driverMode,
        rendererProfilePreset: state.renderer.profile.preset,
        rendererBridgeTemplatePreset: state.renderer.templatePresets.bridgePreset,
        rendererDriverTemplatePreset: state.renderer.templatePresets.driverPreset,
        rendererRecoveryPolicy: state.renderer.health.recoveryPolicy,
        rendererHeartbeatMs: state.renderer.health.heartbeatIntervalMs,
        pollingMode: state.polling.mode,
        pollingDwellMs: state.polling.dwellMs
      }));
      log("ok", "Local preferences saved", {
        layout: state.layout,
        protocol: el.protocol.value,
        rendererKind: state.renderer.kind,
        rendererAutoAttach: state.renderer.autoAttach,
        rendererProfilePreset: state.renderer.profile.preset,
        rendererBridgeTemplatePreset: state.renderer.templatePresets.bridgePreset,
        rendererDriverTemplatePreset: state.renderer.templatePresets.driverPreset,
        rendererRecoveryPolicy: state.renderer.health.recoveryPolicy,
        rendererHeartbeatMs: state.renderer.health.heartbeatIntervalMs,
        pollingMode: state.polling.mode,
        pollingDwellMs: state.polling.dwellMs
      });
    } catch (error) {
      log("warn", "Saving local preferences failed", String(error && error.message ? error.message : error));
    }
  }

  function applyStoredSettings() {
    const stored = readStoredSettings();
    if (!stored || typeof stored !== "object") {
      return;
    }
    if (stored.layout === 4 || stored.layout === 9 || stored.layout === 12) {
      state.layout = stored.layout;
    }
    if (typeof stored.protocol === "string" && stored.protocol) {
      el.protocol.value = stored.protocol;
    }
    if (typeof stored.rendererKind === "string" && stored.rendererKind) {
      state.renderer.kind = stored.rendererKind;
      el.rendererKind.value = stored.rendererKind;
    }
    if (typeof stored.rendererAutoAttach === "boolean") {
      state.renderer.autoAttach = stored.rendererAutoAttach;
      el.rendererAutoAttach.value = stored.rendererAutoAttach ? "1" : "0";
    }
    if (typeof stored.rendererDriverMode === "string" && stored.rendererDriverMode) {
      state.renderer.driverMode = stored.rendererDriverMode;
      el.rendererDriverMode.value = stored.rendererDriverMode;
    }
    if (typeof stored.rendererProfilePreset === "string" && stored.rendererProfilePreset) {
      state.renderer.profile.preset = stored.rendererProfilePreset;
      el.rendererProfilePreset.value = stored.rendererProfilePreset;
    }
    if (typeof stored.rendererBridgeTemplatePreset === "string" && stored.rendererBridgeTemplatePreset) {
      state.renderer.templatePresets.bridgePreset = stored.rendererBridgeTemplatePreset;
      el.rendererBridgeTemplatePreset.value = stored.rendererBridgeTemplatePreset;
    }
    if (typeof stored.rendererDriverTemplatePreset === "string" && stored.rendererDriverTemplatePreset) {
      state.renderer.templatePresets.driverPreset = stored.rendererDriverTemplatePreset;
      el.rendererDriverTemplatePreset.value = stored.rendererDriverTemplatePreset;
    }
    if (typeof stored.rendererRecoveryPolicy === "string" && stored.rendererRecoveryPolicy) {
      state.renderer.health.recoveryPolicy = stored.rendererRecoveryPolicy;
      el.rendererRecoveryPolicy.value = stored.rendererRecoveryPolicy;
    }
    if (Number(stored.rendererHeartbeatMs) >= 1000) {
      state.renderer.health.heartbeatIntervalMs = Number(stored.rendererHeartbeatMs);
      el.rendererHeartbeatMs.value = String(state.renderer.health.heartbeatIntervalMs);
    }
    if (typeof stored.pollingMode === "string" && (stored.pollingMode === "select" || stored.pollingMode === "fullscreen")) {
      state.polling.mode = stored.pollingMode;
      el.pollingMode.value = stored.pollingMode;
    }
    if (Number(stored.pollingDwellMs) >= 300) {
      state.polling.dwellMs = Number(stored.pollingDwellMs);
      el.pollingDwellMs.value = String(state.polling.dwellMs);
    }
  }

  function getRendererDriver(kind) {
    return RENDERER_DRIVERS[kind] || RENDERER_DRIVERS["mock-ws"];
  }

  function buildInputSnapshot() {
    syncTvwallSelection();
    return {
      platformBaseUrl: el.platformBaseUrl.value.trim(),
      platformToken: el.platformToken.value.trim(),
      serviceType: el.serviceType.value.trim(),
      componentId: el.componentId.value.trim(),
      treeCode: el.treeCode.value.trim(),
      regionPageSize: Number(el.regionPageSize.value || 50),
      cameraPageNo: Number(el.cameraPageNo.value || 1),
      cameraPageSize: Number(el.cameraPageSize.value || 20),
      cameraIndexCode: el.cameraIndexCode.value.trim(),
      streamType: Number(el.streamType.value || 0),
      protocol: el.protocol.value,
      transmode: Number(el.transmode.value || 1),
      expand: el.expand.value.trim(),
      tvwall: {
        selectedDlpId: state.selectedDlpId || "",
        selectedMonitorPos: state.selectedMonitorPos || "",
        selectedFloatWindowId: state.selectedFloatWindowId || "",
        selectedWndUri: state.selectedWndUri || ""
      }
    };
  }

  function applyInputSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") {
      return;
    }
    if (typeof snapshot.platformBaseUrl === "string") {
      el.platformBaseUrl.value = snapshot.platformBaseUrl;
    }
    if (typeof snapshot.platformToken === "string") {
      el.platformToken.value = snapshot.platformToken;
    }
    if (typeof snapshot.serviceType === "string") {
      el.serviceType.value = snapshot.serviceType;
    }
    if (typeof snapshot.componentId === "string") {
      el.componentId.value = snapshot.componentId;
    }
    if (typeof snapshot.treeCode === "string") {
      el.treeCode.value = snapshot.treeCode;
    }
    if (snapshot.regionPageSize !== undefined) {
      el.regionPageSize.value = String(snapshot.regionPageSize);
    }
    if (snapshot.cameraPageNo !== undefined) {
      el.cameraPageNo.value = String(snapshot.cameraPageNo);
    }
    if (snapshot.cameraPageSize !== undefined) {
      el.cameraPageSize.value = String(snapshot.cameraPageSize);
    }
    if (typeof snapshot.cameraIndexCode === "string") {
      el.cameraIndexCode.value = snapshot.cameraIndexCode;
    }
    if (snapshot.streamType !== undefined) {
      el.streamType.value = String(snapshot.streamType);
    }
    if (typeof snapshot.protocol === "string" && snapshot.protocol) {
      el.protocol.value = snapshot.protocol;
    }
    if (snapshot.transmode !== undefined) {
      el.transmode.value = String(snapshot.transmode);
    }
    if (typeof snapshot.expand === "string") {
      el.expand.value = snapshot.expand;
    }
    if (snapshot.tvwall && typeof snapshot.tvwall === "object") {
      state.selectedDlpId = String(snapshot.tvwall.selectedDlpId || "");
      state.selectedMonitorPos = String(snapshot.tvwall.selectedMonitorPos || "");
      state.selectedFloatWindowId = String(snapshot.tvwall.selectedFloatWindowId || "");
      state.selectedWndUri = String(snapshot.tvwall.selectedWndUri || "");
      el.tvwallWndUri.value = state.selectedWndUri;
    }
  }

  function buildRuntimeSessionSnapshot() {
    return {
      layout: state.layout,
      selectedTileIndex: state.selectedTileIndex,
      fullscreenTileIndex: state.fullscreenTileIndex,
      protocol: el.protocol.value,
      tiles: state.tiles.map(function (tile) {
        return {
          tileIndex: tile.tileIndex,
          cameraIndexCode: tile.cameraIndexCode,
          cameraName: tile.cameraName,
          previewUrl: tile.previewUrl,
          previewProtocol: tile.previewProtocol,
          status: tile.status,
          rendererAttached: !!tile.rendererAttached,
          rendererKind: tile.rendererKind || "",
          rendererSessionId: tile.rendererSessionId || "",
          rendererSurfaceType: tile.rendererSurfaceType || "",
          rendererTransport: tile.rendererTransport || "",
          rendererDisplayUrl: tile.rendererDisplayUrl || "",
          rendererStatus: tile.rendererStatus || ""
        };
      }),
      renderer: {
        kind: state.renderer.kind,
        autoAttach: state.renderer.autoAttach,
        lastEvent: state.renderer.lastEvent,
        bridgeAction: state.renderer.bridgeAction,
        driverMode: state.renderer.driverMode,
        lastDriverRun: state.renderer.lastDriverRun,
        driverInitialized: state.renderer.driverInitialized,
        driverRuntimeId: state.renderer.driverRuntimeId,
        lastDriverLifecycle: state.renderer.lastDriverLifecycle,
        lastHostContractExport: state.renderer.lastHostContractExport,
        lastBridgeTemplateExport: state.renderer.lastBridgeTemplateExport,
        lastDriverTemplateExport: state.renderer.lastDriverTemplateExport,
        lastImplementationPackageExport: state.renderer.lastImplementationPackageExport,
        health: {
          bridgeReadiness: state.renderer.health.bridgeReadiness,
          hostReadiness: state.renderer.health.hostReadiness,
          heartbeatEnabled: state.renderer.health.heartbeatEnabled,
          heartbeatIntervalMs: state.renderer.health.heartbeatIntervalMs,
          heartbeatStatus: state.renderer.health.heartbeatStatus,
          lastHeartbeatAt: state.renderer.health.lastHeartbeatAt,
          lastCheckAt: state.renderer.health.lastCheckAt,
          lastSummary: state.renderer.health.lastSummary,
          recoveryPolicy: state.renderer.health.recoveryPolicy,
          lastRecoveryAction: state.renderer.health.lastRecoveryAction,
          failureCount: state.renderer.health.failureCount,
          history: state.renderer.health.history.slice(-40)
        },
        preflight: {
          overall: state.renderer.preflight.overall,
          blockingIssues: state.renderer.preflight.blockingIssues,
          missingMethods: state.renderer.preflight.missingMethods.slice(),
          missingArtifacts: state.renderer.preflight.missingArtifacts.slice(),
          checkedAt: state.renderer.preflight.checkedAt || "",
          lastExportAt: state.renderer.preflight.lastExportAt || "",
          history: state.renderer.preflight.history.slice(-40)
        },
        admission: {
          lastAction: state.renderer.admission.lastAction,
          lastDecision: state.renderer.admission.lastDecision,
          lastCheckedAt: state.renderer.admission.lastCheckedAt || "",
          lastSummary: state.renderer.admission.lastSummary,
          blockingReasons: state.renderer.admission.blockingReasons.slice(),
          warnings: state.renderer.admission.warnings.slice(),
          history: state.renderer.admission.history.slice(-40)
        },
        actionPolicy: {
          lastEvaluatedAt: state.renderer.actionPolicy.lastEvaluatedAt || "",
          summary: state.renderer.actionPolicy.summary,
          matrix: clone(state.renderer.actionPolicy.matrix || {}),
          history: state.renderer.actionPolicy.history.slice(-40)
        },
        profile: {
          preset: state.renderer.profile.preset,
          resolvedPreset: state.renderer.profile.resolvedPreset,
          summary: state.renderer.profile.summary,
          history: state.renderer.profile.history.slice(-40)
        },
        templatePresets: {
          bridgePreset: state.renderer.templatePresets.bridgePreset,
          resolvedBridgePreset: state.renderer.templatePresets.resolvedBridgePreset,
          driverPreset: state.renderer.templatePresets.driverPreset,
          resolvedDriverPreset: state.renderer.templatePresets.resolvedDriverPreset,
          history: state.renderer.templatePresets.history.slice(-40)
        },
        commandQueue: state.renderer.commandQueue.slice(),
        commandHistory: state.renderer.commandHistory.slice(-24),
        executionResults: state.renderer.executionResults.slice(-24),
        lifecycleHistory: state.renderer.lifecycleHistory.slice(-24)
      },
      polling: {
        mode: state.polling.mode,
        dwellMs: state.polling.dwellMs,
        route: state.polling.route.slice(),
        currentRouteIndex: state.polling.currentRouteIndex,
        cycleCount: state.polling.cycleCount
      },
      savedAt: new Date().toISOString()
    };
  }

  function readyTileCount() {
    return state.tiles.filter(function (tile) {
      return !!tile.previewUrl;
    }).length;
  }

  function mountSelectorForTile(tileIndex) {
    return '[data-render-surface="' + String(tileIndex) + '"]';
  }

  function buildRendererAttachPayload(tile) {
    const adapter = getRendererAdapter(state.renderer.kind);
    const payload = {
      tileIndex: tile.tileIndex,
      tileOrdinal: tile.tileIndex + 1,
      layout: state.layout,
      fullscreenTileIndex: state.fullscreenTileIndex,
      cameraIndexCode: tile.cameraIndexCode || "",
      cameraName: tile.cameraName || "",
      previewUrl: tile.previewUrl || "",
      previewProtocol: tile.previewProtocol || el.protocol.value || "",
      rendererKind: state.renderer.kind,
      rendererLabel: adapter.label,
      surfaceType: adapter.surfaceType,
      transport: adapter.transport,
      mountSelector: mountSelectorForTile(tile.tileIndex),
      mountId: "tile-render-surface-" + String(tile.tileIndex),
      runtimeMode: runtimeModeLabel(),
      autoAttach: state.renderer.autoAttach,
      bridgeAvailable: state.bridgeAvailable
    };
    if (state.renderer.kind === "mock-ws") {
      payload.attachConfig = {
        connectUrl: (tile.previewUrl || "").replace(/^https?:\/\//, "ws://").replace(/^wss?:\/\//, "ws://"),
        heartbeatMs: 15000,
        codecHint: "h264"
      };
    } else if (state.renderer.kind === "mock-hls") {
      payload.attachConfig = {
        playlistUrl: (tile.previewUrl || "")
          .replace(/^wss?:\/\//, "https://")
          .replace(/^rtsp:\/\//, "https://")
          .replace(/^rtmp:\/\//, "https://")
          .replace(/(\?.*)?$/, ".m3u8"),
        autoplay: true,
        muted: true
      };
    } else {
      payload.attachConfig = {
        pluginMethod: "JS_RequestInterface",
        pluginAction: "startPreview",
        pluginUrl: "plugin://preview?cameraIndexCode=" + encodeURIComponent(tile.cameraIndexCode || ""),
        containerMode: "embedded-web-plugin"
      };
    }
    return payload;
  }

  function buildRendererAttachPlan() {
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      runtimeMode: runtimeModeLabel(),
      renderer: {
        kind: state.renderer.kind,
        label: rendererLabel(),
        capability: rendererCapabilitySummary(),
        autoAttach: state.renderer.autoAttach,
        lastEvent: state.renderer.lastEvent,
        driverMode: state.renderer.driverMode,
        lastDriverRun: state.renderer.lastDriverRun
      },
      tiles: state.tiles
        .filter(function (tile) { return !!tile.previewUrl; })
        .map(buildRendererAttachPayload)
    };
  }

  function buildRendererCommand(action, tile, payload) {
    const adapter = getRendererAdapter(state.renderer.kind);
    const attachPayload = payload || buildRendererAttachPayload(tile);
    const tileOrdinal = attachPayload.tileOrdinal || (tile.tileIndex + 1);
    const command = {
      id: "cmd-" + String(Date.now()) + "-" + String(tile.tileIndex) + "-" + action,
      createdAt: new Date().toISOString(),
      action: action,
      rendererKind: state.renderer.kind,
      rendererLabel: adapter.label,
      bridgeMode: state.bridgeAvailable ? "webcontainer" : "browser",
      runtimeMode: runtimeModeLabel(),
      tileIndex: tile.tileIndex,
      tileOrdinal: tileOrdinal,
      cameraIndexCode: tile.cameraIndexCode || "",
      sessionId: tile.rendererSessionId || "",
      mountSelector: attachPayload.mountSelector,
      payload: attachPayload
    };
    if (state.renderer.kind === "web-plugin-stub") {
      command.bridgeInvocation = {
        method: "JS_RequestInterface",
        action: action === "detach" ? "stopPreview" : "startPreview",
        args: {
          cameraIndexCode: tile.cameraIndexCode || "",
          containerId: attachPayload.mountId,
          pluginUrl: attachPayload.attachConfig.pluginUrl
        }
      };
    } else if (state.renderer.kind === "mock-hls") {
      command.bridgeInvocation = {
        method: "HTMLMediaElement.attach",
        action: action === "detach" ? "detachSource" : "loadSource",
        args: {
          elementSelector: attachPayload.mountSelector,
          playlistUrl: attachPayload.attachConfig.playlistUrl || "",
          muted: true,
          autoplay: true
        }
      };
    } else {
      command.bridgeInvocation = {
        method: "WebSocketCanvasBridge.attach",
        action: action === "detach" ? "close" : "connect",
        args: {
          elementSelector: attachPayload.mountSelector,
          connectUrl: attachPayload.attachConfig.connectUrl || "",
          codecHint: attachPayload.attachConfig.codecHint || "h264"
        }
      };
    }
    return command;
  }

  function enqueueRendererCommand(command, options) {
    const shouldLog = !options || options.log !== false;
    const shouldPersist = !options || options.persist !== false;
    state.renderer.commandQueue.push(command);
    state.renderer.commandHistory.push(command);
    if (state.renderer.commandHistory.length > 80) {
      state.renderer.commandHistory = state.renderer.commandHistory.slice(-80);
    }
    state.renderer.bridgeAction = command.action + " queued for tile " + String(command.tileOrdinal);
    if (shouldPersist) {
      persistRuntimeSession();
    }
    if (shouldLog) {
      log("ok", "Renderer command queued", {
        action: command.action,
        tile: command.tileOrdinal,
        rendererKind: command.rendererKind,
        method: command.bridgeInvocation.method
      });
    }
    return command;
  }

  function clearRendererCommandQueue(reason) {
    state.renderer.commandQueue = [];
    state.renderer.bridgeAction = "Command queue cleared";
    renderAll();
    persistRuntimeSession(reason || "clear-command-queue");
    log("warn", "Renderer command queue cleared", { reason: reason || "manual" });
  }

  function driverModeLabel() {
    return state.renderer.driverMode === "simulate-success"
      ? "Simulate Success"
      : state.renderer.driverMode === "bridge-stub"
        ? "Bridge Stub"
        : "Dry Run";
  }

  function recoveryPolicyLabel() {
    return state.renderer.health.recoveryPolicy === "clear-queue-reinit"
      ? "Clear Queue + Reinit"
      : state.renderer.health.recoveryPolicy === "replay-history"
        ? "Replay Recent History"
        : "Reinit Driver";
  }

  function pushRendererHealthHistory(source, overall, details) {
    const entry = {
      id: "health-" + String(Date.now()) + "-" + source,
      checkedAt: new Date().toISOString(),
      source: source,
      overall: overall,
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      runtimeId: state.renderer.driverRuntimeId || "",
      details: details || {}
    };
    state.renderer.health.history.push(entry);
    if (state.renderer.health.history.length > 80) {
      state.renderer.health.history = state.renderer.health.history.slice(-80);
    }
    return entry;
  }

  function evaluateBridgeReadiness(driver) {
    if (!driver.capabilities.requiresBridge) {
      return {
        level: "ok",
        status: "Not required"
      };
    }
    if (state.bridgeAvailable) {
      return {
        level: "ok",
        status: "Detected / webcontainer"
      };
    }
    if (state.mockMode) {
      return {
        level: "warn",
        status: "Stubbed / mock runtime"
      };
    }
    if (state.renderer.driverMode === "bridge-stub" || state.renderer.driverMode === "simulate-success") {
      return {
        level: "warn",
        status: "Stubbed / driver mode"
      };
    }
    return {
      level: "error",
      status: "Missing / browser mode"
    };
  }

  function evaluateHostReadiness() {
    if (!state.renderer.driverInitialized) {
      return {
        level: "warn",
        status: "Driver not initialized"
      };
    }
    if (!readyTileCount()) {
      return {
        level: "warn",
        status: "No ready tiles"
      };
    }
    if (!attachedRendererCount()) {
      return {
        level: "ok",
        status: "Ready to attach " + String(readyTileCount()) + " tiles"
      };
    }
    return {
      level: "ok",
      status: "Attached " + String(attachedRendererCount()) + " / " + String(readyTileCount()) + " ready"
    };
  }

  function summarizeRendererHealthOverall(bridgeState, hostState) {
    if (bridgeState.level === "error" || hostState.level === "error") {
      return "blocked";
    }
    if (bridgeState.level === "warn" || hostState.level === "warn") {
      return "degraded";
    }
    return "healthy";
  }

  function executeRendererCommand(command) {
    if (!state.renderer.driverInitialized) {
      initRendererDriver("auto-before-run");
    }
    const execution = {
      id: "exec-" + command.id,
      executedAt: new Date().toISOString(),
      driverMode: state.renderer.driverMode,
      runtimeId: state.renderer.driverRuntimeId,
      commandId: command.id,
      action: command.action,
      tileIndex: command.tileIndex,
      tileOrdinal: command.tileOrdinal,
      method: command.bridgeInvocation.method,
      bridgeAction: command.bridgeInvocation.action,
      status: "simulated",
      summary: ""
    };
    if (state.renderer.driverMode === "dry-run") {
      execution.status = "dry-run";
      execution.summary = "Dry run only, no bridge side effect";
    } else if (state.renderer.driverMode === "bridge-stub") {
      execution.status = "bridge-stub";
      execution.summary = "Bridge stub executed " + command.bridgeInvocation.method;
    } else {
      execution.status = "success";
      execution.summary = "Simulated success for " + command.bridgeInvocation.action;
    }
    state.renderer.executionResults.push(execution);
    if (state.renderer.executionResults.length > 120) {
      state.renderer.executionResults = state.renderer.executionResults.slice(-120);
    }
    state.renderer.bridgeAction = execution.summary;
    return execution;
  }

  function runPendingRendererCommands() {
    const admission = guardRendererAdmission("run", { silent: true, persist: false });
    if (!admission.allowed) {
      throw new Error("Renderer admission blocked run: " + admission.blockingReasons.join("; "));
    }
    const queue = state.renderer.commandQueue.slice();
    if (!queue.length) {
      throw new Error("Renderer command queue is empty");
    }
    const results = queue.map(executeRendererCommand);
    state.renderer.commandQueue = [];
    state.renderer.lastDriverRun = "Executed " + String(results.length) + " commands via " + driverModeLabel();
    pushRendererLifecycle("run", "completed", {
      count: results.length,
      driverMode: state.renderer.driverMode,
      runtimeId: state.renderer.driverRuntimeId
    });
    runRendererHealthCheck("post-run", { silent: true, persist: false });
    renderAll();
    persistRuntimeSession("run-command-queue");
    log("ok", "Renderer command queue executed", {
      driverMode: state.renderer.driverMode,
      count: results.length
    });
    return results;
  }

  function replayRecentRendererHistory() {
    const recent = state.renderer.commandHistory.slice(-12);
    if (!recent.length) {
      throw new Error("Renderer command history is empty");
    }
    state.renderer.commandQueue = recent.map(function (command) {
      return {
        id: command.id + "-replay-" + String(Date.now()),
        createdAt: new Date().toISOString(),
        action: command.action,
        rendererKind: command.rendererKind,
        rendererLabel: command.rendererLabel,
        bridgeMode: command.bridgeMode,
        runtimeMode: command.runtimeMode,
        tileIndex: command.tileIndex,
        tileOrdinal: command.tileOrdinal,
        cameraIndexCode: command.cameraIndexCode,
        sessionId: command.sessionId,
        mountSelector: command.mountSelector,
        payload: command.payload,
        bridgeInvocation: command.bridgeInvocation
      };
    });
    state.renderer.bridgeAction = "Replayed " + String(state.renderer.commandQueue.length) + " history commands";
    pushRendererLifecycle("replay", "queued", {
      count: state.renderer.commandQueue.length
    });
    renderAll();
    persistRuntimeSession("replay-command-history");
    log("ok", "Renderer command history replayed", {
      count: state.renderer.commandQueue.length
    });
    return state.renderer.commandQueue;
  }

  function buildRendererCommandSnapshot() {
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverMode: state.renderer.driverMode,
      pendingCount: state.renderer.commandQueue.length,
      lastBridgeAction: state.renderer.bridgeAction,
      queue: state.renderer.commandQueue,
      recentHistory: state.renderer.commandHistory.slice(-16)
    };
  }

  function buildRendererDriverSnapshot() {
    const driver = getRendererDriver(state.renderer.kind);
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driver: {
        kind: state.renderer.kind,
        label: driver.label,
        mode: state.renderer.driverMode,
        initialized: state.renderer.driverInitialized,
        runtimeId: state.renderer.driverRuntimeId || "",
        lastLifecycle: state.renderer.lastDriverLifecycle || "Not initialized",
        lastDriverRun: state.renderer.lastDriverRun || "Not executed",
        capabilities: driver.capabilities,
        hostType: driver.hostContract.hostType,
        lastHostContractExport: state.renderer.lastHostContractExport || "Not exported"
      },
      lifecycleHistory: state.renderer.lifecycleHistory.slice(-20)
    };
  }

  function driverCapabilitySummary() {
    const capabilities = getRendererDriver(state.renderer.kind).capabilities;
    const enabled = ["init", "attach", "refresh", "detach", "dispose"].filter(function (key) {
      return !!capabilities[key];
    });
    return enabled.join(" / ");
  }

  function buildRendererHostContractSnapshot() {
    const driver = getRendererDriver(state.renderer.kind);
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverLabel: driver.label,
      driverMode: state.renderer.driverMode,
      hostContract: driver.hostContract,
      capabilities: driver.capabilities,
      runtimeState: {
        initialized: state.renderer.driverInitialized,
        runtimeId: state.renderer.driverRuntimeId || "",
        lastHostContractExport: state.renderer.lastHostContractExport || "Not exported"
      },
      preflight: {
        overall: state.renderer.preflight.overall,
        blockingIssues: state.renderer.preflight.blockingIssues,
        checkedAt: state.renderer.preflight.checkedAt || "",
        lastExportAt: state.renderer.preflight.lastExportAt || ""
      }
    };
  }

  function buildRendererBridgeTemplate() {
    const driver = getRendererDriver(state.renderer.kind);
    const profile = currentRendererProfile();
    const bridgePreset = currentRendererBridgeTemplatePreset();
    const attachPlan = buildRendererAttachPlan();
    let methodTemplates;
    const hostType = bridgePreset.config.hostType || driver.hostContract.hostType;
    if (bridgePreset.key === "webcontainer-js-interface") {
      methodTemplates = {
        initializePluginHost: "async function initializePluginHost(ctx) { return { hostId: 'plugin-host-' + Date.now(), mountSelector: ctx.mountSelector }; }",
        requestInterface: "async function requestInterface(action, payload) { return window.JS_RequestInterface ? window.JS_RequestInterface({ action: action, payload: payload }) : Promise.reject(new Error('JS_RequestInterface unavailable')); }",
        startPreview: "async function startPreview(ctx) { return requestInterface('startPreview', { cameraIndexCode: ctx.cameraIndexCode, mountSelector: ctx.mountSelector, previewUrl: ctx.previewUrl }); }",
        stopPreview: "async function stopPreview(ctx) { return requestInterface('stopPreview', { sessionId: ctx.sessionId, mountSelector: ctx.mountSelector }); }",
        disposePluginHost: "async function disposePluginHost(ctx) { return { released: true, hostId: ctx.hostId }; }"
      };
    } else if (bridgePreset.key === "webcontrol-local-service") {
      methodTemplates = {
        launchLocalService: "async function launchLocalService(ctx) { return { port: 14600, lockName: 'InfoSightWebControl.lock' }; }",
        createPluginWindow: "async function createPluginWindow(ctx) { return { windowId: 'wc-' + Date.now(), mountSelector: ctx.mountSelector }; }",
        invokePreview: "async function invokePreview(ctx) { return { previewStarted: true, cameraIndexCode: ctx.cameraIndexCode, servicePort: ctx.servicePort || 14600 }; }",
        stopPreview: "async function stopPreview(ctx) { return { previewStopped: true, sessionId: ctx.sessionId }; }",
        disposePluginWindow: "async function disposePluginWindow(ctx) { return { disposed: true, windowId: ctx.windowId }; }"
      };
    } else if (bridgePreset.key === "html5-media-basic") {
      methodTemplates = {
        createVideoElement: "function createVideoElement(ctx) { const video = document.createElement('video'); video.autoplay = true; video.muted = true; video.playsInline = true; document.querySelector(ctx.mountSelector).appendChild(video); return video; }",
        loadSource: "async function loadSource(ctx) { ctx.video.src = ctx.previewUrl; await ctx.video.play().catch(() => undefined); }",
        reloadSource: "async function reloadSource(ctx) { ctx.video.load(); await ctx.video.play().catch(() => undefined); }",
        detachSource: "function detachSource(ctx) { ctx.video.removeAttribute('src'); ctx.video.load(); }",
        disposeVideoElement: "function disposeVideoElement(ctx) { ctx.video.remove(); }"
      };
    } else {
      methodTemplates = {
        createSurface: "function createSurface(ctx) { const canvas = document.createElement('canvas'); document.querySelector(ctx.mountSelector).appendChild(canvas); return canvas; }",
        connectSocket: "async function connectSocket(ctx) { return { socketId: 'ws-' + Date.now(), endpoint: ctx.previewUrl }; }",
        refreshSocket: "async function refreshSocket(ctx) { return { refreshed: true, socketId: ctx.socketId }; }",
        closeSocket: "async function closeSocket(ctx) { return { closed: true, socketId: ctx.socketId }; }",
        disposeSurface: "function disposeSurface(ctx) { ctx.canvas.remove(); }"
      };
    }
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverLabel: driver.label,
      driverMode: state.renderer.driverMode,
      profilePreset: state.renderer.profile.preset,
      resolvedProfilePreset: profile.key,
      bridgePreset: state.renderer.templatePresets.bridgePreset,
      resolvedBridgePreset: bridgePreset.key,
      bridgeLabel: bridgePreset.config.label,
      hostType: hostType,
      bridgeAvailable: state.bridgeAvailable,
      mockMode: state.mockMode,
      requiredMethods: bridgePreset.config.methods || driver.hostContract.requiredMethods,
      requiredArtifacts: driver.hostContract.requiredArtifacts,
      attachContextExample: attachPlan.tiles[0] || null,
      methodTemplates: methodTemplates,
      integrationNotes: {
        admissionSummary: state.renderer.admission.lastSummary,
        actionPolicySummary: state.renderer.actionPolicy.summary,
        preflightOverall: state.renderer.preflight.overall,
        warnings: (profile.config.warnings || []).slice()
      }
    };
  }

  function buildRendererDriverTemplate() {
    const driver = getRendererDriver(state.renderer.kind);
    const profile = currentRendererProfile();
    const driverPreset = currentRendererDriverTemplatePreset();
    let attachSteps = ["resolve mount selector", "create host surface", "start preview or connect stream", "return session descriptor"];
    if (driverPreset.key === "plugin-session-driver") {
      attachSteps = ["initialize plugin runtime", "bind plugin container", "request preview session", "cache session descriptor"];
    } else if (driverPreset.key === "hls-hlsjs-driver") {
      attachSteps = ["create video element", "bootstrap Hls.js instance", "attach media and load playlist", "monitor MANIFEST_PARSED"];
    } else if (driverPreset.key === "hls-native-driver") {
      attachSteps = ["create video element", "check native HLS capability", "set src directly", "await canplay event"];
    } else if (driverPreset.key === "ws-webcodecs-driver") {
      attachSteps = ["create canvas/video surface", "start WebSocket transport", "decode frames with WebCodecs", "blit frames and update health"];
    }
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverLabel: driver.label,
      runtimePrefix: driverPreset.config.runtimePrefix || driver.runtimePrefix,
      driverMode: state.renderer.driverMode,
      profilePreset: state.renderer.profile.preset,
      resolvedProfilePreset: profile.key,
      driverPreset: state.renderer.templatePresets.driverPreset,
      resolvedDriverPreset: driverPreset.key,
      driverPresetLabel: driverPreset.config.label,
      capabilities: driver.capabilities,
      hostType: driver.hostContract.hostType,
      lifecycle: {
        init: {
          action: driver.initAction,
          signature: "async function init(ctx, hostBridge) {}",
          steps: ["prepare runtime context", "validate host bridge", "return runtime id"]
        },
        attach: {
          signature: "async function attach(ctx, payload, hostBridge) {}",
          steps: attachSteps
        },
        refresh: {
          signature: "async function refresh(ctx, payload, hostBridge) {}",
          steps: ["reuse session", "refresh preview source", "confirm renderer health"]
        },
        detach: {
          signature: "async function detach(ctx, payload, hostBridge) {}",
          steps: ["stop preview or close stream", "release tile session", "keep runtime alive if needed"]
        },
        dispose: {
          action: driver.disposeAction,
          signature: "async function dispose(ctx, hostBridge) {}",
          steps: ["drain queue", "dispose host resources", "release runtime context"]
        }
      },
      payloadContracts: {
        attachPayload: buildRendererAttachPayload(state.tiles[state.selectedTileIndex] || createTile(0)),
        commandPreview: state.renderer.commandQueue[0] || state.renderer.commandHistory.slice(-1)[0] || null
      },
      implementationChecklist: [
        "Map host bridge methods to concrete runtime APIs",
        "Implement preset-specific attach strategy: " + (driverPreset.config.attachStrategy || "default"),
        "Honor renderer admission and action policy before side effects",
        "Return stable session ids per tile",
        "Surface refresh/detach failures through execution results",
        "Integrate heartbeat and recovery callbacks"
      ]
    };
  }

  function buildImplementationPackageFiles(bridgeTemplate, driverTemplate, presetSnapshot, runtimeSupport) {
    const support = runtimeSupport || {};
    const bridgeFileName = "bridge/" + String(bridgeTemplate.resolvedBridgePreset || bridgeTemplate.bridgePreset || "auto") + ".js";
    const driverFileName = "driver/" + String(driverTemplate.resolvedDriverPreset || driverTemplate.driverPreset || "auto") + ".js";
    const healthFileName = "runtime/health.js";
    const wiringFileName = "runtime/wiring.js";
    const policyFileName = "runtime/policy.json";
    const packageJsonFileName = "package.json";
    const requiredBridgeMethods = (bridgeTemplate.requiredMethods || []).slice();
    const attachBridgeMethods = requiredBridgeMethods.filter(function (methodName) {
      return !/^(stop|dispose|close|detach)/i.test(methodName);
    });
    const detachBridgeMethods = requiredBridgeMethods.filter(function (methodName) {
      return /^(stop|close|detach)/i.test(methodName);
    });
    const disposeBridgeMethods = requiredBridgeMethods.filter(function (methodName) {
      return /^dispose/i.test(methodName);
    });
    const bridgeMethodBody = Object.entries(bridgeTemplate.methodTemplates || {}).map(function (entry) {
      const body = String(entry[1] || "").trim();
      return body.startsWith("export ") ? body : "export " + body;
    }).join("\n\n");
    const driverScaffold = [
      "const REQUIRED_BRIDGE_METHODS = " + JSON.stringify(requiredBridgeMethods, null, 2) + ";",
      "const ATTACH_BRIDGE_METHODS = " + JSON.stringify(attachBridgeMethods, null, 2) + ";",
      "const DETACH_BRIDGE_METHODS = " + JSON.stringify(detachBridgeMethods, null, 2) + ";",
      "const DISPOSE_BRIDGE_METHODS = " + JSON.stringify(disposeBridgeMethods, null, 2) + ";",
      "",
      "function buildResult(action, extra) {",
      "  return Object.assign({ action: action, ok: true, at: new Date().toISOString() }, extra || {});",
      "}",
      "",
      "async function callBridge(hostBridge, methodName, payload) {",
      "  if (!hostBridge || typeof hostBridge[methodName] !== 'function') {",
      "    return buildResult('bridge-skip', { methodName: methodName, skipped: true, payload: payload || null });",
      "  }",
      "  const value = await hostBridge[methodName](payload || {});",
      "  return buildResult('bridge-call', { methodName: methodName, value: value });",
      "}",
      "",
      "export async function init(ctx, hostBridge) {",
      "  const runtimeId = String((ctx && ctx.runtimePrefix) || " + JSON.stringify(driverTemplate.runtimePrefix || "drv-runtime") + ") + '-' + Date.now();",
      "  const bootstrap = REQUIRED_BRIDGE_METHODS.length ? await callBridge(hostBridge, REQUIRED_BRIDGE_METHODS[0], Object.assign({}, ctx || {}, { runtimeId: runtimeId })) : null;",
      "  return buildResult('init', { runtimeId: runtimeId, bootstrap: bootstrap, steps: " + JSON.stringify((driverTemplate.lifecycle && driverTemplate.lifecycle.init && driverTemplate.lifecycle.init.steps) || []) + " });",
      "}",
      "",
      "export async function attach(ctx, payload, hostBridge) {",
      "  const calls = [];",
      "  for (const methodName of ATTACH_BRIDGE_METHODS) {",
      "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
      "  }",
      "  const sessionId = String((ctx && ctx.runtimeId) || " + JSON.stringify(driverTemplate.runtimePrefix || "drv-runtime") + ") + '-session-' + String((payload && payload.tileIndex) || 0);",
      "  return buildResult('attach', { sessionId: sessionId, calls: calls, payload: payload || null, steps: " + JSON.stringify((driverTemplate.lifecycle && driverTemplate.lifecycle.attach && driverTemplate.lifecycle.attach.steps) || []) + " });",
      "}",
      "",
      "export async function refresh(ctx, payload, hostBridge) {",
      "  const methodName = ATTACH_BRIDGE_METHODS.length > 1 ? ATTACH_BRIDGE_METHODS[ATTACH_BRIDGE_METHODS.length - 1] : ATTACH_BRIDGE_METHODS[0];",
      "  const refreshResult = methodName ? await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { refresh: true })) : null;",
      "  return buildResult('refresh', { payload: payload || null, refreshResult: refreshResult, steps: " + JSON.stringify((driverTemplate.lifecycle && driverTemplate.lifecycle.refresh && driverTemplate.lifecycle.refresh.steps) || []) + " });",
      "}",
      "",
      "export async function detach(ctx, payload, hostBridge) {",
      "  const calls = [];",
      "  for (const methodName of DETACH_BRIDGE_METHODS) {",
      "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
      "  }",
      "  return buildResult('detach', { calls: calls, payload: payload || null, steps: " + JSON.stringify((driverTemplate.lifecycle && driverTemplate.lifecycle.detach && driverTemplate.lifecycle.detach.steps) || []) + " });",
      "}",
      "",
      "export async function dispose(ctx, hostBridge) {",
      "  const calls = [];",
      "  for (const methodName of DISPOSE_BRIDGE_METHODS) {",
      "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
      "  }",
      "  return buildResult('dispose', { calls: calls, steps: " + JSON.stringify((driverTemplate.lifecycle && driverTemplate.lifecycle.dispose && driverTemplate.lifecycle.dispose.steps) || []) + " });",
      "}"
    ].join("\n");
    const healthScaffold = [
      "export async function runHealthCheck(ctx) {",
      "  return {",
      "    bridgeReadiness: " + JSON.stringify((support.health && support.health.bridgeReadiness) || "Pending") + ",",
      "    hostReadiness: " + JSON.stringify((support.health && support.health.hostReadiness) || "Pending") + ",",
      "    preflight: " + JSON.stringify((support.preflight && support.preflight.overall) || "Pending") + ",",
      "    admission: " + JSON.stringify((support.admission && support.admission.lastDecision) || "Not evaluated") + ",",
      "    actionPolicy: " + JSON.stringify((support.actionPolicy && support.actionPolicy.summary) || "Not evaluated") ,
      "  };",
      "}",
      "",
      "export function startHeartbeat(ctx) {",
      "  // intervalMs: " + String((support.health && support.health.heartbeatIntervalMs) || 4800),
      "}",
      "",
      "export function stopHeartbeat(ctx) {",
      "  // stop runtime heartbeat",
      "}",
      "",
      "export async function recover(ctx) {",
      "  // policy: " + JSON.stringify((support.health && support.health.recoveryPolicy) || "reinit-driver"),
      "}"
    ].join("\n");
    const wiringScaffold = [
      "import * as bridge from '../" + bridgeFileName + "';",
      "import * as driver from '../" + driverFileName + "';",
      "import * as health from '../" + healthFileName + "';",
      "",
      "export function createRuntimeWiring() {",
      "  return { bridge, driver, health };",
      "}"
    ].join("\n");
    const policyJson = JSON.stringify({
      preflight: support.preflight || null,
      admission: support.admission || null,
      actionPolicy: support.actionPolicy || null,
      health: support.health || null,
      templatePresets: presetSnapshot
    }, null, 2);
    const readme = [
      "# Renderer Implementation Package",
      "",
      "- Driver kind: `" + driverTemplate.driverKind + "`",
      "- Bridge preset: `" + presetSnapshot.resolvedBridgePreset + "`",
      "- Driver preset: `" + presetSnapshot.resolvedDriverPreset + "`",
      "- Host type: `" + bridgeTemplate.hostType + "`",
      "- Runtime prefix: `" + driverTemplate.runtimePrefix + "`",
      "",
      "## Next Step",
      "",
      "1. Fill the bridge methods in `" + bridgeFileName + "`.",
      "2. Fill the lifecycle implementation in `" + driverFileName + "`.",
      "3. Wire the exported functions back into the runtime shell.",
      "4. Validate runtime health and policy using `" + healthFileName + "` and `" + policyFileName + "`.",
      ""
    ].join("\n");
    return {
      [packageJsonFileName]: JSON.stringify({
        name: String(presetSnapshot.resolvedBridgePreset || "renderer-package") + "-" + String(presetSnapshot.resolvedDriverPreset || "runtime"),
        private: true,
        type: "module"
      }, null, 2),
      "manifest.json": JSON.stringify({
        driverKind: driverTemplate.driverKind,
        bridgePreset: presetSnapshot.resolvedBridgePreset,
        driverPreset: presetSnapshot.resolvedDriverPreset,
        hostType: bridgeTemplate.hostType,
        runtimePrefix: driverTemplate.runtimePrefix,
        runtimeSupportFiles: [healthFileName, wiringFileName, policyFileName],
        requiredBridgeMethods: requiredBridgeMethods,
        moduleType: "module"
      }, null, 2),
      [bridgeFileName]: bridgeMethodBody,
      [driverFileName]: driverScaffold,
      [healthFileName]: healthScaffold,
      [wiringFileName]: wiringScaffold,
      [policyFileName]: policyJson,
      "README.md": readme
    };
  }

  function buildRendererImplementationPackage() {
    const bridgeTemplate = buildRendererBridgeTemplate();
    const driverTemplate = buildRendererDriverTemplate();
    const presetSnapshot = buildRendererTemplatePresetSnapshot();
    const healthSnapshot = buildRendererHealthSnapshot();
    const preflightSnapshot = buildRendererHostPreflightSnapshot();
    const admissionSnapshot = buildRendererAdmissionSnapshot();
    const actionPolicySnapshot = buildRendererActionPolicySnapshot();
    const packageName = [
      "renderer-package",
      state.renderer.kind,
      presetSnapshot.resolvedBridgePreset,
      presetSnapshot.resolvedDriverPreset
    ].join("-");
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      packageName: packageName,
      rendererKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      profilePreset: state.renderer.profile.preset,
      bridgeTemplate: bridgeTemplate,
      driverTemplate: driverTemplate,
      healthSnapshot: healthSnapshot,
      hostPreflight: preflightSnapshot,
      admission: admissionSnapshot,
      actionPolicy: actionPolicySnapshot,
      templatePresets: presetSnapshot,
      files: buildImplementationPackageFiles(bridgeTemplate, driverTemplate, presetSnapshot, {
        health: healthSnapshot,
        preflight: preflightSnapshot,
        admission: admissionSnapshot,
        actionPolicy: actionPolicySnapshot
      })
    };
  }

  function buildRendererHealthSnapshot() {
    const driver = getRendererDriver(state.renderer.kind);
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverLabel: driver.label,
      driverMode: state.renderer.driverMode,
      bridgeReadiness: state.renderer.health.bridgeReadiness,
      hostReadiness: state.renderer.health.hostReadiness,
      heartbeatEnabled: state.renderer.health.heartbeatEnabled,
      heartbeatIntervalMs: state.renderer.health.heartbeatIntervalMs,
      heartbeatStatus: state.renderer.health.heartbeatStatus,
      lastHeartbeatAt: state.renderer.health.lastHeartbeatAt || "",
      lastCheckAt: state.renderer.health.lastCheckAt || "",
      lastSummary: state.renderer.health.lastSummary || "Not checked",
      recoveryPolicy: state.renderer.health.recoveryPolicy,
      lastRecoveryAction: state.renderer.health.lastRecoveryAction || "Not triggered",
      failureCount: state.renderer.health.failureCount || 0,
      history: state.renderer.health.history.slice(-20)
    };
  }

  function availableHostMethods(driver) {
    const methods = [];
    if (driver.hostContract.hostType === "html-media") {
      methods.push("createVideoElement", "loadSource", "reloadSource", "detachSource", "disposeVideoElement");
    } else if (driver.hostContract.hostType === "canvas-bridge") {
      methods.push("createSurface", "connectSocket", "refreshSocket", "closeSocket", "disposeSurface");
    } else if (driver.hostContract.hostType === "webcontainer-plugin-host") {
      if (state.bridgeAvailable) {
        methods.push("initializePluginHost", "JS_RequestInterface.startPreview", "JS_RequestInterface.stopPreview", "disposePluginHost");
      }
      if (state.mockMode || state.renderer.driverMode === "bridge-stub" || state.renderer.driverMode === "simulate-success") {
        methods.push("initializePluginHost", "JS_RequestInterface.startPreview", "JS_RequestInterface.stopPreview", "disposePluginHost");
      }
    }
    return Array.from(new Set(methods));
  }

  function availableHostArtifacts(driver) {
    const artifacts = [];
    const readyTiles = state.tiles.filter(function (tile) { return !!tile.previewUrl; });
    const hasMounts = state.tiles.every(function (tile) {
      return !!document.querySelector(mountSelectorForTile(tile.tileIndex));
    });
    if (driver.hostContract.hostType === "html-media") {
      artifacts.push("video-element");
      if (readyTiles.length) {
        artifacts.push("playlist-url");
      }
      artifacts.push("autoplay-policy");
    } else if (driver.hostContract.hostType === "canvas-bridge") {
      if (hasMounts) {
        artifacts.push("canvas-element");
      }
      if (readyTiles.length) {
        artifacts.push("ws-endpoint");
      }
      artifacts.push("codec-hint");
    } else if (driver.hostContract.hostType === "webcontainer-plugin-host") {
      if (hasMounts) {
        artifacts.push("plugin-container", "container-id");
      }
      if (state.tiles.some(function (tile) { return !!tile.cameraIndexCode; })) {
        artifacts.push("cameraIndexCode");
      }
      if (state.tiles.some(function (tile) { return !!tile.cameraIndexCode || !!tile.previewUrl; })) {
        artifacts.push("plugin-url");
      }
    }
    return Array.from(new Set(artifacts));
  }

  function determinePreflightOverall(missingMethods, missingArtifacts) {
    if (!missingMethods.length && !missingArtifacts.length) {
      return "ready";
    }
    if (state.mockMode || state.renderer.driverMode === "bridge-stub" || state.renderer.driverMode === "simulate-success") {
      return "degraded";
    }
    return "blocked";
  }

  function buildRendererHostPreflightSnapshot() {
    const driver = getRendererDriver(state.renderer.kind);
    const availableMethods = availableHostMethods(driver);
    const availableArtifacts = availableHostArtifacts(driver);
    const missingMethods = driver.hostContract.requiredMethods.filter(function (method) {
      return availableMethods.indexOf(method) < 0;
    });
    const missingArtifacts = driver.hostContract.requiredArtifacts.filter(function (artifact) {
      return availableArtifacts.indexOf(artifact) < 0;
    });
    const overall = determinePreflightOverall(missingMethods, missingArtifacts);
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverLabel: driver.label,
      driverMode: state.renderer.driverMode,
      hostType: driver.hostContract.hostType,
      overall: overall,
      bridgeAvailable: state.bridgeAvailable,
      mockMode: state.mockMode,
      availableMethods: availableMethods,
      availableArtifacts: availableArtifacts,
      missingMethods: missingMethods,
      missingArtifacts: missingArtifacts,
      blockingIssues: missingMethods.length + missingArtifacts.length,
      notes: driver.hostContract.notes,
      runtimeState: {
        initialized: state.renderer.driverInitialized,
        runtimeId: state.renderer.driverRuntimeId || "",
        readyTiles: readyTileCount(),
        attachedTiles: attachedRendererCount(),
        selectedTileIndex: state.selectedTileIndex,
        fullscreenTileIndex: state.fullscreenTileIndex
      },
      history: state.renderer.preflight.history.slice(-20)
    };
  }

  function pushRendererPreflightHistory(entry) {
    state.renderer.preflight.history.push(entry);
    if (state.renderer.preflight.history.length > 80) {
      state.renderer.preflight.history = state.renderer.preflight.history.slice(-80);
    }
    return entry;
  }

  function pushRendererAdmissionHistory(entry) {
    state.renderer.admission.history.push(entry);
    if (state.renderer.admission.history.length > 80) {
      state.renderer.admission.history = state.renderer.admission.history.slice(-80);
    }
    return entry;
  }

  function pushRendererActionPolicyHistory(entry) {
    state.renderer.actionPolicy.history.push(entry);
    if (state.renderer.actionPolicy.history.length > 80) {
      state.renderer.actionPolicy.history = state.renderer.actionPolicy.history.slice(-80);
    }
    return entry;
  }

  function pushRendererProfileHistory(entry) {
    state.renderer.profile.history.push(entry);
    if (state.renderer.profile.history.length > 80) {
      state.renderer.profile.history = state.renderer.profile.history.slice(-80);
    }
    return entry;
  }

  function pushRendererTemplatePresetHistory(entry) {
    state.renderer.templatePresets.history.push(entry);
    if (state.renderer.templatePresets.history.length > 80) {
      state.renderer.templatePresets.history = state.renderer.templatePresets.history.slice(-80);
    }
    return entry;
  }

  function resolveRendererProfilePreset() {
    if (state.renderer.profile.preset && state.renderer.profile.preset !== "auto") {
      return state.renderer.profile.preset;
    }
    if (state.mockMode) {
      return "mock-demo";
    }
    if (state.renderer.kind === "web-plugin-stub") {
      return state.bridgeAvailable ? "plugin-bridge-ready" : "strict-browser";
    }
    return "media-runtime-ready";
  }

  function currentRendererProfile() {
    const resolvedPreset = resolveRendererProfilePreset();
    const config = DRIVER_PROFILE_PRESETS[resolvedPreset] || DRIVER_PROFILE_PRESETS.auto;
    state.renderer.profile.resolvedPreset = resolvedPreset;
    state.renderer.profile.summary = config.label;
    return {
      key: resolvedPreset,
      config: config
    };
  }

  function resolveRendererBridgeTemplatePreset() {
    if (state.renderer.templatePresets.bridgePreset && state.renderer.templatePresets.bridgePreset !== "auto") {
      return state.renderer.templatePresets.bridgePreset;
    }
    if (state.renderer.kind === "web-plugin-stub") {
      return state.bridgeAvailable ? "webcontainer-js-interface" : "webcontrol-local-service";
    }
    if (state.renderer.kind === "mock-hls") {
      return "html5-media-basic";
    }
    return "canvas-socket-basic";
  }

  function currentRendererBridgeTemplatePreset() {
    const resolvedPreset = resolveRendererBridgeTemplatePreset();
    const config = BRIDGE_TEMPLATE_PRESETS[resolvedPreset] || BRIDGE_TEMPLATE_PRESETS.auto;
    state.renderer.templatePresets.resolvedBridgePreset = resolvedPreset;
    return {
      key: resolvedPreset,
      config: config
    };
  }

  function resolveRendererDriverTemplatePreset() {
    if (state.renderer.templatePresets.driverPreset && state.renderer.templatePresets.driverPreset !== "auto") {
      return state.renderer.templatePresets.driverPreset;
    }
    if (state.renderer.kind === "web-plugin-stub") {
      return "plugin-session-driver";
    }
    if (state.renderer.kind === "mock-hls") {
      return "hls-hlsjs-driver";
    }
    return "ws-canvas-driver";
  }

  function currentRendererDriverTemplatePreset() {
    const resolvedPreset = resolveRendererDriverTemplatePreset();
    const config = DRIVER_TEMPLATE_PRESETS[resolvedPreset] || DRIVER_TEMPLATE_PRESETS.auto;
    state.renderer.templatePresets.resolvedDriverPreset = resolvedPreset;
    return {
      key: resolvedPreset,
      config: config
    };
  }

  function buildRendererProfileSnapshot() {
    const profile = currentRendererProfile();
    const bridgePreset = currentRendererBridgeTemplatePreset();
    const driverPreset = currentRendererDriverTemplatePreset();
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      selectedPreset: state.renderer.profile.preset,
      resolvedPreset: profile.key,
      label: profile.config.label,
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      bridgeAvailable: state.bridgeAvailable,
      mockMode: state.mockMode,
      templatePresets: {
        bridgePreset: state.renderer.templatePresets.bridgePreset,
        resolvedBridgePreset: bridgePreset.key,
        bridgeLabel: bridgePreset.config.label,
        driverPreset: state.renderer.templatePresets.driverPreset,
        resolvedDriverPreset: driverPreset.key,
        driverLabel: driverPreset.config.label
      },
      recommendedDefaults: {
        driverMode: profile.config.recommendedDriverMode || state.renderer.driverMode,
        autoAttach: profile.config.recommendedAutoAttach !== undefined ? !!profile.config.recommendedAutoAttach : state.renderer.autoAttach,
        recoveryPolicy: profile.config.recommendedRecoveryPolicy || state.renderer.health.recoveryPolicy,
        heartbeatMs: Math.max(1000, Number(profile.config.recommendedHeartbeatMs || state.renderer.health.heartbeatIntervalMs || 4800))
      },
      config: profile.config,
      history: state.renderer.profile.history.slice(-20)
    };
  }

  function buildRendererTemplatePresetSnapshot() {
    const bridgePreset = currentRendererBridgeTemplatePreset();
    const driverPreset = currentRendererDriverTemplatePreset();
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      selectedBridgePreset: state.renderer.templatePresets.bridgePreset,
      resolvedBridgePreset: bridgePreset.key,
      bridgeLabel: bridgePreset.config.label,
      selectedDriverPreset: state.renderer.templatePresets.driverPreset,
      resolvedDriverPreset: driverPreset.key,
      driverLabel: driverPreset.config.label,
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      history: state.renderer.templatePresets.history.slice(-20)
    };
  }

  function applyRendererProfileDefaults(reason) {
    const profile = currentRendererProfile();
    const defaults = {
      driverMode: profile.config.recommendedDriverMode || state.renderer.driverMode || "dry-run",
      autoAttach: profile.config.recommendedAutoAttach !== undefined ? !!profile.config.recommendedAutoAttach : state.renderer.autoAttach,
      recoveryPolicy: profile.config.recommendedRecoveryPolicy || state.renderer.health.recoveryPolicy || "reinit-driver",
      heartbeatMs: Math.max(1000, Number(profile.config.recommendedHeartbeatMs || state.renderer.health.heartbeatIntervalMs || 4800))
    };
    el.rendererDriverMode.value = defaults.driverMode;
    el.rendererAutoAttach.value = defaults.autoAttach ? "1" : "0";
    el.rendererRecoveryPolicy.value = defaults.recoveryPolicy;
    el.rendererHeartbeatMs.value = String(defaults.heartbeatMs);
    syncRendererInputsToState();
    evaluateRendererActionPolicy(reason || "profile-defaults", { silent: true, persist: false });
    pushRendererProfileHistory({
      id: "profile-defaults-" + String(Date.now()),
      at: new Date().toISOString(),
      source: reason || "profile-defaults",
      preset: state.renderer.profile.preset,
      resolvedPreset: profile.key,
      defaults: defaults
    });
    renderAll();
    persistRuntimeSession(reason || "apply-profile-defaults");
    writeStoredSettings();
    log("ok", "Applied renderer profile defaults", {
      preset: state.renderer.profile.preset,
      resolvedPreset: profile.key,
      defaults: defaults
    });
    return defaults;
  }

  function runRendererHostPreflight(reason, options) {
    const settings = options || {};
    const snapshot = buildRendererHostPreflightSnapshot();
    state.renderer.preflight.overall = snapshot.overall;
    state.renderer.preflight.blockingIssues = snapshot.blockingIssues;
    state.renderer.preflight.missingMethods = snapshot.missingMethods.slice();
    state.renderer.preflight.missingArtifacts = snapshot.missingArtifacts.slice();
    state.renderer.preflight.checkedAt = snapshot.generatedAt;
    pushRendererPreflightHistory({
      id: "preflight-" + String(Date.now()),
      checkedAt: snapshot.generatedAt,
      source: reason || "manual-preflight",
      overall: snapshot.overall,
      blockingIssues: snapshot.blockingIssues,
      missingMethods: snapshot.missingMethods,
      missingArtifacts: snapshot.missingArtifacts
    });
    if (settings.persist !== false) {
      persistRuntimeSession(reason || "host-preflight");
    }
    renderAll();
    if (!settings.silent) {
      const logKind = snapshot.overall === "ready" ? "ok" : snapshot.overall === "degraded" ? "warn" : "err";
      log(logKind, "Renderer host preflight completed", {
        source: reason || "manual-preflight",
        overall: snapshot.overall,
        blockingIssues: snapshot.blockingIssues,
        missingMethods: snapshot.missingMethods,
        missingArtifacts: snapshot.missingArtifacts
      });
    }
    return snapshot;
  }

  function exportRendererHostPreflight() {
    const snapshot = runRendererHostPreflight("export-preflight", { silent: true, persist: false });
    state.renderer.preflight.lastExportAt = "Preflight exported at " + snapshot.generatedAt;
    writeRuntimeIoBuffer(snapshot, state.renderer.preflight.lastExportAt);
    renderAll();
    log(snapshot.overall === "ready" ? "ok" : snapshot.overall === "degraded" ? "warn" : "err", "Renderer host preflight exported", {
      overall: snapshot.overall,
      blockingIssues: snapshot.blockingIssues,
      missingMethods: snapshot.missingMethods,
      missingArtifacts: snapshot.missingArtifacts
    });
    return snapshot;
  }

  function buildRendererAdmissionSnapshot() {
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      lastAction: state.renderer.admission.lastAction,
      lastDecision: state.renderer.admission.lastDecision,
      lastCheckedAt: state.renderer.admission.lastCheckedAt || "",
      lastSummary: state.renderer.admission.lastSummary,
      blockingReasons: state.renderer.admission.blockingReasons.slice(),
      warnings: state.renderer.admission.warnings.slice(),
      queueLength: state.renderer.commandQueue.length,
      readyTiles: readyTileCount(),
      attachedTiles: attachedRendererCount(),
      history: state.renderer.admission.history.slice(-20)
    };
  }

  function selectedTileHasPreview() {
    const tile = state.tiles[state.selectedTileIndex];
    return !!(tile && tile.previewUrl);
  }

  function selectedTileAttached() {
    const tile = state.tiles[state.selectedTileIndex];
    return !!(tile && tile.rendererAttached);
  }

  function buildActionPolicyEntry(action, capabilityEnabled, details) {
    const info = details || {};
    const reasons = (info.blockingReasons || []).slice();
    const warnings = (info.warnings || []).slice();
    if (!capabilityEnabled) {
      reasons.push("Driver capability disabled");
    }
    const decision = reasons.length ? "blocked" : warnings.length ? "admitted-degraded" : "admitted";
    return {
      action: action,
      decision: decision,
      blockingReasons: reasons,
      warnings: warnings
    };
  }

  function buildRendererActionPolicyMatrix() {
    const profile = currentRendererProfile();
    const profileConfig = profile.config;
    const driver = getRendererDriver(state.renderer.kind);
    const routeHasEntries = state.polling.route.length > 0;
    const pluginRequiresBridge = state.renderer.kind === "web-plugin-stub" && profileConfig.requireBridgeForPlugin;
    const attachedRequiredForFullscreen = !!profileConfig.requireAttachedForFullscreen;
    const matrix = {
      attach: buildActionPolicyEntry("attach", !!driver.capabilities.attach, {
        blockingReasons: []
          .concat(readyTileCount() ? [] : ["No ready tiles with preview URLs"])
          .concat(pluginRequiresBridge && !state.bridgeAvailable && !profileConfig.allowStubBridge ? ["Profile requires webcontainer bridge"] : []),
        warnings: []
          .concat(state.renderer.health.bridgeReadiness.indexOf("Stubbed") >= 0 && profileConfig.allowStubBridge ? ["Bridge is stubbed"] : [])
          .concat(profileConfig.warnings || [])
      }),
      refresh: buildActionPolicyEntry("refresh", !!driver.capabilities.refresh, {
        blockingReasons: selectedTileHasPreview() ? [] : ["Selected tile has no preview URL"],
        warnings: selectedTileAttached() ? [] : ["Selected tile is not attached"]
      }),
      detach: buildActionPolicyEntry("detach", !!driver.capabilities.detach, {
        blockingReasons: attachedRendererCount() ? [] : ["No attached renderer sessions"]
      }),
      run: buildActionPolicyEntry("run", true, {
        blockingReasons: []
          .concat(state.renderer.commandQueue.length ? [] : ["Renderer command queue is empty"])
          .concat(pluginRequiresBridge && !state.bridgeAvailable && !profileConfig.allowStubBridge ? ["Profile requires webcontainer bridge"] : []),
        warnings: []
          .concat(state.renderer.driverInitialized ? [] : ["Driver will auto-init before run"])
          .concat(state.renderer.health.bridgeReadiness.indexOf("Stubbed") >= 0 && profileConfig.allowStubBridge ? ["Bridge is stubbed"] : [])
      }),
      "fullscreen-select": buildActionPolicyEntry("fullscreen-select", true, {
        blockingReasons: []
          .concat(selectedTileHasPreview() ? [] : ["Selected tile has no preview URL"])
          .concat(attachedRequiredForFullscreen && !selectedTileAttached() ? ["Profile requires attached renderer for fullscreen"] : []),
        warnings: []
          .concat(selectedTileAttached() || profileConfig.allowFullscreenWithoutAttached ? [] : ["Selected tile is not attached"])
      }),
      "fullscreen-route": buildActionPolicyEntry("fullscreen-route", true, {
        blockingReasons: []
          .concat(routeHasEntries ? [] : ["Polling route is empty"])
          .concat(state.polling.mode === "fullscreen" || profileConfig.allowRoutePreviewWithoutFullscreenMode ? [] : ["Profile requires fullscreen polling mode"]),
        warnings: []
          .concat(state.polling.mode === "fullscreen" ? [] : ["Polling mode is not fullscreen"])
      })
    };
    return matrix;
  }

  function buildRendererActionPolicySnapshot() {
    const profile = currentRendererProfile();
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      profilePreset: state.renderer.profile.preset,
      resolvedProfilePreset: profile.key,
      profileLabel: profile.config.label,
      selectedTileIndex: state.selectedTileIndex,
      pollingMode: state.polling.mode,
      matrix: clone(state.renderer.actionPolicy.matrix || buildRendererActionPolicyMatrix()),
      summary: state.renderer.actionPolicy.summary,
      lastEvaluatedAt: state.renderer.actionPolicy.lastEvaluatedAt || "",
      history: state.renderer.actionPolicy.history.slice(-20)
    };
  }

  function evaluateRendererActionPolicy(source, options) {
    const settings = options || {};
    const matrix = buildRendererActionPolicyMatrix();
    const blocked = Object.values(matrix).filter(function (entry) {
      return entry.decision === "blocked";
    }).length;
    const degraded = Object.values(matrix).filter(function (entry) {
      return entry.decision === "admitted-degraded";
    }).length;
    const summary = blocked ? "blocked:" + String(blocked) : degraded ? "degraded:" + String(degraded) : "admitted";
    const checkedAt = new Date().toISOString();
    state.renderer.actionPolicy.matrix = matrix;
    state.renderer.actionPolicy.lastEvaluatedAt = checkedAt;
    state.renderer.actionPolicy.summary = summary;
    pushRendererActionPolicyHistory({
      id: "policy-" + String(Date.now()),
      checkedAt: checkedAt,
      source: source || "manual-policy",
      summary: summary,
      blocked: blocked,
      degraded: degraded
    });
    if (settings.persist !== false) {
      persistRuntimeSession(source || "action-policy");
    }
    renderAll();
    if (!settings.silent) {
      log(blocked ? "warn" : "ok", "Renderer action policy evaluated", {
        source: source || "manual-policy",
        summary: summary
      });
    }
    return matrix;
  }

  function guardRendererAdmission(action, options) {
    const settings = options || {};
    const policyMatrix = evaluateRendererActionPolicy("admission-" + action, { silent: true, persist: false });
    const preflight = runRendererHostPreflight("admission-" + action, { silent: true, persist: false });
    const health = runRendererHealthCheck("admission-" + action, { silent: true, persist: false });
    const reasons = [];
    const warnings = [];
    const policy = policyMatrix[action];

    if (preflight.overall === "blocked") {
      reasons.push("Host preflight blocked");
    } else if (preflight.overall === "degraded") {
      warnings.push("Host preflight degraded");
    }

    if (policy) {
      reasons.push.apply(reasons, policy.blockingReasons);
      warnings.push.apply(warnings, policy.warnings);
    }

    if (health.bridgeReadiness.indexOf("Missing") >= 0) {
      reasons.push("Bridge is not available");
    } else if (health.bridgeReadiness.indexOf("Stubbed") >= 0) {
      warnings.push("Bridge is stubbed");
    }

    const dedupe = function (items) {
      return Array.from(new Set(items.filter(Boolean)));
    };
    const uniqueReasons = dedupe(reasons);
    const uniqueWarnings = dedupe(warnings);

    const decision = uniqueReasons.length ? "blocked" : uniqueWarnings.length ? "admitted-degraded" : "admitted";
    const checkedAt = new Date().toISOString();
    state.renderer.admission.lastAction = action;
    state.renderer.admission.lastDecision = decision;
    state.renderer.admission.lastCheckedAt = checkedAt;
    state.renderer.admission.lastSummary = decision + " / " + action;
    state.renderer.admission.blockingReasons = uniqueReasons.slice();
    state.renderer.admission.warnings = uniqueWarnings.slice();
    pushRendererAdmissionHistory({
      id: "admission-" + String(Date.now()) + "-" + action,
      checkedAt: checkedAt,
      action: action,
      decision: decision,
      blockingReasons: uniqueReasons.slice(),
      warnings: uniqueWarnings.slice(),
      preflightOverall: preflight.overall,
      bridgeReadiness: health.bridgeReadiness,
      hostReadiness: health.hostReadiness
    });
    if (settings.persist !== false) {
      persistRuntimeSession("admission-" + action);
    }
    renderAll();
    if (!settings.silent) {
      const logKind = decision === "blocked" ? "err" : decision === "admitted-degraded" ? "warn" : "ok";
      log(logKind, "Renderer admission evaluated", {
        action: action,
        decision: decision,
        blockingReasons: uniqueReasons,
        warnings: uniqueWarnings
      });
    }
    return {
      allowed: !uniqueReasons.length,
      decision: decision,
      blockingReasons: uniqueReasons,
      warnings: uniqueWarnings,
      policy: policy,
      preflight: preflight,
      health: health
    };
  }

  function pushRendererLifecycle(phase, status, details) {
    const entry = {
      id: "life-" + String(Date.now()) + "-" + phase,
      at: new Date().toISOString(),
      phase: phase,
      status: status,
      driverKind: state.renderer.kind,
      driverMode: state.renderer.driverMode,
      runtimeId: state.renderer.driverRuntimeId || "",
      details: details || {}
    };
    state.renderer.lifecycleHistory.push(entry);
    if (state.renderer.lifecycleHistory.length > 80) {
      state.renderer.lifecycleHistory = state.renderer.lifecycleHistory.slice(-80);
    }
    state.renderer.lastDriverLifecycle = phase + " / " + status;
    return entry;
  }

  function runRendererHealthCheck(reason, options) {
    const settings = options || {};
    const driver = getRendererDriver(state.renderer.kind);
    const bridgeState = evaluateBridgeReadiness(driver);
    const hostState = evaluateHostReadiness();
    const overall = summarizeRendererHealthOverall(bridgeState, hostState);
    const checkedAt = new Date().toISOString();
    const actionableFailure = bridgeState.level === "error" || hostState.level === "warn" || hostState.level === "error";
    if (overall === "healthy" || !actionableFailure) {
      state.renderer.health.failureCount = 0;
    } else {
      state.renderer.health.failureCount += 1;
    }
    state.renderer.health.bridgeReadiness = bridgeState.status;
    state.renderer.health.hostReadiness = hostState.status;
    state.renderer.health.lastCheckAt = checkedAt;
    state.renderer.health.lastSummary = overall + " / " + driver.label;
    if (reason === "heartbeat" || reason === "heartbeat-start") {
      state.renderer.health.lastHeartbeatAt = checkedAt;
      state.renderer.health.heartbeatStatus = "Running / " + overall;
    } else if (!state.renderer.health.heartbeatEnabled) {
      state.renderer.health.heartbeatStatus = "Stopped";
    }
    const entry = pushRendererHealthHistory(reason || "manual-check", overall, {
      bridgeReadiness: bridgeState.status,
      hostReadiness: hostState.status,
      readyTiles: readyTileCount(),
      attachedTiles: attachedRendererCount(),
      failureCount: state.renderer.health.failureCount,
      recoveryPolicy: state.renderer.health.recoveryPolicy
    });
    if (settings.persist !== false) {
      persistRuntimeSession(reason || "health-check");
    }
    renderAll();
    if (!settings.silent) {
      const logKind = overall === "healthy" ? "ok" : overall === "degraded" ? "warn" : "err";
      log(logKind, "Renderer health check completed", {
        source: reason || "manual-check",
        overall: overall,
        bridge: bridgeState.status,
        host: hostState.status,
        failureCount: state.renderer.health.failureCount,
        recoveryPolicy: state.renderer.health.recoveryPolicy
      });
    }
    return {
      checkedAt: checkedAt,
      overall: overall,
      bridgeReadiness: bridgeState.status,
      hostReadiness: hostState.status,
      failureCount: state.renderer.health.failureCount,
      entry: entry
    };
  }

  function stopRendererHeartbeat(reason, options) {
    const settings = options || {};
    if (state.renderer.health.timerId) {
      window.clearInterval(state.renderer.health.timerId);
      state.renderer.health.timerId = null;
    }
    state.renderer.health.heartbeatEnabled = false;
    state.renderer.health.heartbeatStatus = "Stopped";
    if (!settings.silent) {
      pushRendererHealthHistory("heartbeat-stop", "stopped", {
        reason: reason || "manual-stop"
      });
      log("warn", "Renderer heartbeat stopped", {
        reason: reason || "manual-stop"
      });
    }
    if (settings.persist !== false) {
      persistRuntimeSession(reason || "stop-heartbeat");
    }
    renderAll();
  }

  function startRendererHeartbeat(reason) {
    const intervalMs = Math.max(1000, Number(state.renderer.health.heartbeatIntervalMs || 4800));
    stopRendererHeartbeat("restart-heartbeat", { silent: true, persist: false });
    state.renderer.health.heartbeatEnabled = true;
    state.renderer.health.heartbeatIntervalMs = intervalMs;
    state.renderer.health.heartbeatStatus = "Starting / " + String(intervalMs) + "ms";
    runRendererHealthCheck(reason || "heartbeat-start", { silent: true, persist: false });
    state.renderer.health.timerId = window.setInterval(function () {
      try {
        runRendererHealthCheck("heartbeat", { silent: true, persist: false });
      } catch (error) {
        state.renderer.health.failureCount += 1;
        state.renderer.health.heartbeatStatus = "Heartbeat error";
        pushRendererHealthHistory("heartbeat", "error", {
          message: String(error && error.message ? error.message : error)
        });
        renderAll();
      }
    }, intervalMs);
    pushRendererHealthHistory("heartbeat-start", "running", {
      intervalMs: intervalMs,
      reason: reason || "manual-start"
    });
    persistRuntimeSession(reason || "start-heartbeat");
    renderAll();
    log("ok", "Renderer heartbeat started", {
      intervalMs: intervalMs,
      reason: reason || "manual-start"
    });
  }

  function toggleRendererHeartbeat() {
    if (state.renderer.health.heartbeatEnabled) {
      stopRendererHeartbeat("manual-toggle");
      return;
    }
    startRendererHeartbeat("manual-toggle");
  }

  function initRendererDriver(reason) {
    const driver = getRendererDriver(state.renderer.kind);
    if (state.renderer.driverInitialized) {
      state.renderer.lastDriverLifecycle = "init / already-ready";
      renderAll();
      log("warn", "Renderer driver already initialized", {
        driverKind: state.renderer.kind,
        runtimeId: state.renderer.driverRuntimeId
      });
      return buildRendererDriverSnapshot();
    }
    state.renderer.driverInitialized = true;
    state.renderer.driverRuntimeId = driver.runtimePrefix + "-" + String(Date.now());
    state.renderer.bridgeAction = driver.initAction + " prepared";
    pushRendererLifecycle("init", "ready", {
      reason: reason || "manual",
      initAction: driver.initAction,
      runtimeId: state.renderer.driverRuntimeId
    });
    renderAll();
    persistRuntimeSession(reason || "init-driver");
    log("ok", "Renderer driver initialized", {
      driverKind: state.renderer.kind,
      runtimeId: state.renderer.driverRuntimeId,
      mode: state.renderer.driverMode
    });
    runRendererHealthCheck("post-init", { silent: true, persist: false });
    return buildRendererDriverSnapshot();
  }

  function disposeRendererDriver(reason) {
    const driver = getRendererDriver(state.renderer.kind);
    if (!state.renderer.driverInitialized) {
      state.renderer.lastDriverLifecycle = "dispose / already-stopped";
      renderAll();
      log("warn", "Renderer driver is not initialized", {
        driverKind: state.renderer.kind
      });
      return buildRendererDriverSnapshot();
    }
    if (state.renderer.health.heartbeatEnabled) {
      stopRendererHeartbeat("dispose-driver", { silent: true, persist: false });
    }
    const runtimeId = state.renderer.driverRuntimeId;
    state.renderer.driverInitialized = false;
    state.renderer.driverRuntimeId = "";
    state.renderer.bridgeAction = driver.disposeAction + " prepared";
    pushRendererLifecycle("dispose", "released", {
      reason: reason || "manual",
      disposeAction: driver.disposeAction,
      runtimeId: runtimeId
    });
    renderAll();
    persistRuntimeSession(reason || "dispose-driver");
    log("warn", "Renderer driver disposed", {
      driverKind: state.renderer.kind,
      previousRuntimeId: runtimeId
    });
    runRendererHealthCheck("post-dispose", { silent: true, persist: false });
    return buildRendererDriverSnapshot();
  }

  function recoverRendererDriver(reason) {
    const policy = state.renderer.health.recoveryPolicy || "reinit-driver";
    const preflight = runRendererHostPreflight("recovery-preflight", { silent: true, persist: false });
    if (preflight.overall === "blocked") {
      state.renderer.health.lastRecoveryAction = "Preflight blocked recovery";
      renderAll();
      log("err", "Renderer recovery blocked by host preflight", {
        missingMethods: preflight.missingMethods,
        missingArtifacts: preflight.missingArtifacts
      });
      return buildRendererHealthSnapshot();
    }
    const recoveredAt = new Date().toISOString();
    if (policy === "clear-queue-reinit") {
      clearRendererCommandQueue("recovery-clear-queue");
    }
    if (state.renderer.driverInitialized) {
      disposeRendererDriver("recovery-dispose");
    }
    initRendererDriver("recovery-init");
    if (policy === "replay-history") {
      replayRecentRendererHistory();
      if (state.renderer.commandQueue.length) {
        runPendingRendererCommands();
      }
    }
    state.renderer.health.failureCount = 0;
    state.renderer.health.lastRecoveryAction = recoveryPolicyLabel() + " at " + recoveredAt;
    pushRendererHealthHistory("recovery", "completed", {
      policy: policy,
      reason: reason || "manual-recovery",
      runtimeId: state.renderer.driverRuntimeId || ""
    });
    runRendererHealthCheck("recovery", { silent: true, persist: false });
    persistRuntimeSession(reason || "trigger-recovery");
    renderAll();
    log("warn", "Renderer recovery executed", {
      policy: policy,
      reason: reason || "manual-recovery",
      runtimeId: state.renderer.driverRuntimeId || ""
    });
    return buildRendererHealthSnapshot();
  }

  function buildRendererExecutionSnapshot() {
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      driverMode: state.renderer.driverMode,
      lastDriverRun: state.renderer.lastDriverRun,
      totalExecutions: state.renderer.executionResults.length,
      recentExecutions: state.renderer.executionResults.slice(-20)
    };
  }

  function selectedTilePayloadSummary() {
    const tile = state.tiles[state.selectedTileIndex];
    if (!tile) {
      return "No selected tile";
    }
    if (!tile.previewUrl) {
      return "Tile " + String(tile.tileIndex + 1) + " / preview pending";
    }
    return "Tile " + String(tile.tileIndex + 1) + " / " + state.renderer.kind + " / " + (tile.cameraIndexCode || "camera-pending");
  }

  function buildRendererDiagnosticsSnapshot() {
    return {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      runtimeMode: runtimeModeLabel(),
      bridgeAvailable: state.bridgeAvailable,
      mockMode: state.mockMode,
      renderer: {
        kind: state.renderer.kind,
        label: rendererLabel(),
        capability: rendererCapabilitySummary(),
        autoAttach: state.renderer.autoAttach,
        attachedTiles: attachedRendererCount(),
        readyTiles: readyTileCount(),
        lastEvent: state.renderer.lastEvent,
        bridgeReadiness: state.renderer.health.bridgeReadiness,
        hostReadiness: state.renderer.health.hostReadiness,
        heartbeatStatus: state.renderer.health.heartbeatStatus,
        recoveryPolicy: state.renderer.health.recoveryPolicy,
        admissionDecision: state.renderer.admission.lastDecision,
        admissionAction: state.renderer.admission.lastAction,
        actionPolicy: state.renderer.actionPolicy.summary,
        bridgeTemplatePreset: state.renderer.templatePresets.resolvedBridgePreset,
        driverTemplatePreset: state.renderer.templatePresets.resolvedDriverPreset
      },
      selectedTile: buildRendererAttachPayload(state.tiles[state.selectedTileIndex] || createTile(0)),
      attachedSessions: state.tiles
        .filter(function (tile) { return !!tile.rendererAttached; })
        .map(function (tile) {
          return {
            tileIndex: tile.tileIndex,
            tileOrdinal: tile.tileIndex + 1,
            cameraIndexCode: tile.cameraIndexCode,
            sessionId: tile.rendererSessionId,
            surfaceType: tile.rendererSurfaceType,
            transport: tile.rendererTransport,
            displayUrl: tile.rendererDisplayUrl,
            status: tile.rendererStatus
          };
        }),
      polling: {
        mode: state.polling.mode,
        running: state.polling.running,
        dwellMs: state.polling.dwellMs,
        route: state.polling.route.slice(),
        currentTileIndex: currentPollingRouteTileIndex(),
        cycleCount: state.polling.cycleCount
      },
      admission: buildRendererAdmissionSnapshot(),
      actionPolicy: buildRendererActionPolicySnapshot(),
      bridge: buildRendererCommandSnapshot(),
      execution: buildRendererExecutionSnapshot()
    };
  }

  function writeRuntimeIoBuffer(value, label) {
    el.runtimeIoBuffer.value = pretty(value);
    if (label) {
      state.runtimeBundleStatus = label;
    }
    renderAll();
  }

  function readRuntimeIoBufferJson() {
    const raw = el.runtimeIoBuffer.value.trim();
    if (!raw) {
      throw new Error("Runtime JSON Buffer is empty");
    }
    return safeJson(raw);
  }

  function buildRuntimeBundle() {
    return {
      schemaVersion: 1,
      exportedAt: new Date().toISOString(),
      runtimeMode: runtimeModeLabel(),
      inputs: buildInputSnapshot(),
      settings: readStoredSettings(),
      runtimeSession: buildRuntimeSessionSnapshot(),
      rendererDiagnostics: buildRendererDiagnosticsSnapshot(),
      rendererAttachPlan: buildRendererAttachPlan(),
      rendererCommands: buildRendererCommandSnapshot(),
      rendererDriver: buildRendererDriverSnapshot(),
      rendererHostContract: buildRendererHostContractSnapshot(),
      rendererBridgeTemplate: buildRendererBridgeTemplate(),
      rendererDriverTemplate: buildRendererDriverTemplate(),
      rendererImplementationPackage: buildRendererImplementationPackage(),
      rendererHealth: buildRendererHealthSnapshot(),
      rendererHostPreflight: buildRendererHostPreflightSnapshot(),
      rendererAdmission: buildRendererAdmissionSnapshot(),
      rendererActionPolicy: buildRendererActionPolicySnapshot(),
      rendererProfile: buildRendererProfileSnapshot(),
      rendererTemplatePresets: buildRendererTemplatePresetSnapshot()
    };
  }

  function persistRuntimeSession(reason) {
    const snapshot = buildRuntimeSessionSnapshot();
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(snapshot));
      el.runtimeSessionSnapshot.textContent = pretty(snapshot);
      if (reason) {
        log("ok", "Runtime session snapshot saved", { reason: reason, savedAt: snapshot.savedAt });
      }
    } catch (error) {
      log("warn", "Saving runtime session snapshot failed", String(error && error.message ? error.message : error));
    }
    return snapshot;
  }

  function readRuntimeSessionSnapshot() {
    try {
      const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
      return raw ? safeJson(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function loadRuntimeSessionSnapshotFromObject(snapshot, reason) {
    if (!snapshot || typeof snapshot !== "object") {
      throw new Error("Runtime session snapshot is empty");
    }
    stopPollingRuntime(null, { persist: false });
    state.layout = snapshot.layout === 9 ? 9 : snapshot.layout === 12 ? 12 : 4;
    state.selectedTileIndex = Number(snapshot.selectedTileIndex || 0);
    state.fullscreenTileIndex = snapshot.fullscreenTileIndex === null || snapshot.fullscreenTileIndex === undefined
      ? null
      : Number(snapshot.fullscreenTileIndex);
    if (snapshot.protocol) {
      el.protocol.value = snapshot.protocol;
    }
    if (snapshot.renderer && typeof snapshot.renderer === "object") {
      state.renderer.kind = snapshot.renderer.kind || state.renderer.kind;
      state.renderer.autoAttach = snapshot.renderer.autoAttach !== false;
      state.renderer.lastEvent = snapshot.renderer.lastEvent || "Idle";
      state.renderer.bridgeAction = snapshot.renderer.bridgeAction || "Idle";
      state.renderer.driverMode = snapshot.renderer.driverMode || state.renderer.driverMode;
      state.renderer.lastDriverRun = snapshot.renderer.lastDriverRun || "Not executed";
      state.renderer.driverInitialized = !!snapshot.renderer.driverInitialized;
      state.renderer.driverRuntimeId = snapshot.renderer.driverRuntimeId || "";
      state.renderer.lastDriverLifecycle = snapshot.renderer.lastDriverLifecycle || "Not initialized";
      state.renderer.lastHostContractExport = snapshot.renderer.lastHostContractExport || "Not exported";
      state.renderer.lastBridgeTemplateExport = snapshot.renderer.lastBridgeTemplateExport || "Not exported";
      state.renderer.lastDriverTemplateExport = snapshot.renderer.lastDriverTemplateExport || "Not exported";
      state.renderer.lastImplementationPackageExport = snapshot.renderer.lastImplementationPackageExport || "Not exported";
      if (snapshot.renderer.health && typeof snapshot.renderer.health === "object") {
        state.renderer.health.bridgeReadiness = snapshot.renderer.health.bridgeReadiness || "Pending";
        state.renderer.health.hostReadiness = snapshot.renderer.health.hostReadiness || "Pending";
        state.renderer.health.heartbeatEnabled = false;
        state.renderer.health.heartbeatIntervalMs = Math.max(1000, Number(snapshot.renderer.health.heartbeatIntervalMs || state.renderer.health.heartbeatIntervalMs || 4800));
        state.renderer.health.heartbeatStatus = snapshot.renderer.health.heartbeatEnabled ? "Stopped / restore snapshot" : (snapshot.renderer.health.heartbeatStatus || "Stopped");
        state.renderer.health.lastHeartbeatAt = snapshot.renderer.health.lastHeartbeatAt || "";
        state.renderer.health.lastCheckAt = snapshot.renderer.health.lastCheckAt || "";
        state.renderer.health.lastSummary = snapshot.renderer.health.lastSummary || "Not checked";
        state.renderer.health.recoveryPolicy = snapshot.renderer.health.recoveryPolicy || state.renderer.health.recoveryPolicy;
        state.renderer.health.lastRecoveryAction = snapshot.renderer.health.lastRecoveryAction || "Not triggered";
        state.renderer.health.failureCount = Number(snapshot.renderer.health.failureCount || 0);
        state.renderer.health.timerId = null;
        state.renderer.health.history = Array.isArray(snapshot.renderer.health.history) ? snapshot.renderer.health.history.slice(-80) : [];
      }
      if (snapshot.renderer.preflight && typeof snapshot.renderer.preflight === "object") {
        state.renderer.preflight.overall = snapshot.renderer.preflight.overall || "Pending";
        state.renderer.preflight.blockingIssues = Number(snapshot.renderer.preflight.blockingIssues || 0);
        state.renderer.preflight.missingMethods = Array.isArray(snapshot.renderer.preflight.missingMethods) ? snapshot.renderer.preflight.missingMethods.slice() : [];
        state.renderer.preflight.missingArtifacts = Array.isArray(snapshot.renderer.preflight.missingArtifacts) ? snapshot.renderer.preflight.missingArtifacts.slice() : [];
        state.renderer.preflight.checkedAt = snapshot.renderer.preflight.checkedAt || "";
        state.renderer.preflight.lastExportAt = snapshot.renderer.preflight.lastExportAt || "";
        state.renderer.preflight.history = Array.isArray(snapshot.renderer.preflight.history) ? snapshot.renderer.preflight.history.slice(-80) : [];
      }
      if (snapshot.renderer.admission && typeof snapshot.renderer.admission === "object") {
        state.renderer.admission.lastAction = snapshot.renderer.admission.lastAction || "None";
        state.renderer.admission.lastDecision = snapshot.renderer.admission.lastDecision || "Not evaluated";
        state.renderer.admission.lastCheckedAt = snapshot.renderer.admission.lastCheckedAt || "";
        state.renderer.admission.lastSummary = snapshot.renderer.admission.lastSummary || "Not evaluated";
        state.renderer.admission.blockingReasons = Array.isArray(snapshot.renderer.admission.blockingReasons) ? snapshot.renderer.admission.blockingReasons.slice() : [];
        state.renderer.admission.warnings = Array.isArray(snapshot.renderer.admission.warnings) ? snapshot.renderer.admission.warnings.slice() : [];
        state.renderer.admission.history = Array.isArray(snapshot.renderer.admission.history) ? snapshot.renderer.admission.history.slice(-80) : [];
      }
      if (snapshot.renderer.actionPolicy && typeof snapshot.renderer.actionPolicy === "object") {
        state.renderer.actionPolicy.lastEvaluatedAt = snapshot.renderer.actionPolicy.lastEvaluatedAt || "";
        state.renderer.actionPolicy.summary = snapshot.renderer.actionPolicy.summary || "Not evaluated";
        state.renderer.actionPolicy.matrix = snapshot.renderer.actionPolicy.matrix && typeof snapshot.renderer.actionPolicy.matrix === "object"
          ? clone(snapshot.renderer.actionPolicy.matrix)
          : {};
        state.renderer.actionPolicy.history = Array.isArray(snapshot.renderer.actionPolicy.history) ? snapshot.renderer.actionPolicy.history.slice(-80) : [];
      }
      if (snapshot.renderer.profile && typeof snapshot.renderer.profile === "object") {
      state.renderer.profile.preset = snapshot.renderer.profile.preset || "auto";
      state.renderer.profile.resolvedPreset = snapshot.renderer.profile.resolvedPreset || state.renderer.profile.preset;
      state.renderer.profile.summary = snapshot.renderer.profile.summary || "Auto";
      state.renderer.profile.history = Array.isArray(snapshot.renderer.profile.history) ? snapshot.renderer.profile.history.slice(-80) : [];
      el.rendererProfilePreset.value = state.renderer.profile.preset;
      }
      if (snapshot.renderer.templatePresets && typeof snapshot.renderer.templatePresets === "object") {
        state.renderer.templatePresets.bridgePreset = snapshot.renderer.templatePresets.bridgePreset || "auto";
        state.renderer.templatePresets.resolvedBridgePreset = snapshot.renderer.templatePresets.resolvedBridgePreset || state.renderer.templatePresets.bridgePreset;
        state.renderer.templatePresets.driverPreset = snapshot.renderer.templatePresets.driverPreset || "auto";
        state.renderer.templatePresets.resolvedDriverPreset = snapshot.renderer.templatePresets.resolvedDriverPreset || state.renderer.templatePresets.driverPreset;
        state.renderer.templatePresets.history = Array.isArray(snapshot.renderer.templatePresets.history) ? snapshot.renderer.templatePresets.history.slice(-80) : [];
        el.rendererBridgeTemplatePreset.value = state.renderer.templatePresets.bridgePreset;
        el.rendererDriverTemplatePreset.value = state.renderer.templatePresets.driverPreset;
      }
      state.renderer.commandQueue = Array.isArray(snapshot.renderer.commandQueue) ? snapshot.renderer.commandQueue.slice() : [];
      state.renderer.commandHistory = Array.isArray(snapshot.renderer.commandHistory) ? snapshot.renderer.commandHistory.slice(-80) : [];
      state.renderer.executionResults = Array.isArray(snapshot.renderer.executionResults) ? snapshot.renderer.executionResults.slice(-120) : [];
      state.renderer.lifecycleHistory = Array.isArray(snapshot.renderer.lifecycleHistory) ? snapshot.renderer.lifecycleHistory.slice(-80) : [];
      el.rendererKind.value = state.renderer.kind;
      el.rendererAutoAttach.value = state.renderer.autoAttach ? "1" : "0";
      el.rendererDriverMode.value = state.renderer.driverMode;
      el.rendererRecoveryPolicy.value = state.renderer.health.recoveryPolicy;
      el.rendererHeartbeatMs.value = String(state.renderer.health.heartbeatIntervalMs);
    }
    syncTiles(state.layout);
    if (Array.isArray(snapshot.tiles)) {
      snapshot.tiles.forEach(function (savedTile, index) {
        if (!state.tiles[index]) {
          return;
        }
        state.tiles[index] = {
          tileIndex: index,
          cameraIndexCode: savedTile.cameraIndexCode || "",
          cameraName: savedTile.cameraName || "",
          previewUrl: savedTile.previewUrl || "",
          previewProtocol: savedTile.previewProtocol || "",
          status: savedTile.status || (savedTile.cameraIndexCode ? "bound" : "empty"),
          rendererAttached: !!savedTile.rendererAttached,
          rendererKind: savedTile.rendererKind || "",
          rendererSessionId: savedTile.rendererSessionId || "",
          rendererSurfaceType: savedTile.rendererSurfaceType || "",
          rendererTransport: savedTile.rendererTransport || "",
          rendererDisplayUrl: savedTile.rendererDisplayUrl || "",
          rendererStatus: savedTile.rendererStatus || ""
        };
      });
    }
    if (snapshot.polling && typeof snapshot.polling === "object") {
      state.polling.mode = snapshot.polling.mode === "fullscreen" ? "fullscreen" : "select";
      state.polling.dwellMs = Number(snapshot.polling.dwellMs || 2200);
      state.polling.route = Array.isArray(snapshot.polling.route) ? snapshot.polling.route.slice() : [];
      state.polling.currentRouteIndex = snapshot.polling.currentRouteIndex === null || snapshot.polling.currentRouteIndex === undefined
        ? -1
        : Number(snapshot.polling.currentRouteIndex);
      state.polling.cycleCount = Number(snapshot.polling.cycleCount || 0);
      el.pollingMode.value = state.polling.mode;
      el.pollingDwellMs.value = String(state.polling.dwellMs);
    }
    syncRendererInputsToState();
    renderAll();
    log("ok", "Runtime session snapshot loaded", {
      reason: reason || "manual",
      savedAt: snapshot.savedAt || "unknown"
    });
  }

  function loadRuntimeSessionSnapshot(reason) {
    const snapshot = readRuntimeSessionSnapshot();
    if (!snapshot || typeof snapshot !== "object") {
      throw new Error("No saved runtime session snapshot");
    }
    loadRuntimeSessionSnapshotFromObject(snapshot, reason);
  }

  function resetRuntimeSessionSnapshot() {
    if (state.renderer.health.heartbeatEnabled) {
      stopRendererHeartbeat("reset-runtime-session", { silent: true, persist: false });
    }
    try {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      el.runtimeSessionSnapshot.textContent = "No runtime session snapshot yet.";
      state.runtimeBundleStatus = "Runtime snapshot cleared";
      log("warn", "Runtime session snapshot cleared");
    } catch (error) {
      log("warn", "Clearing runtime session snapshot failed", String(error && error.message ? error.message : error));
    }
  }

  function exportRendererAttachPlan() {
    const attachPlan = buildRendererAttachPlan();
    writeRuntimeIoBuffer(attachPlan, "Attach plan exported at " + attachPlan.generatedAt);
    log("ok", "Renderer attach plan exported", {
      tileCount: attachPlan.tiles.length,
      rendererKind: attachPlan.renderer.kind
    });
    return attachPlan;
  }

  function exportRendererHostContract() {
    const contract = buildRendererHostContractSnapshot();
    state.renderer.lastHostContractExport = "Host contract exported at " + contract.generatedAt;
    writeRuntimeIoBuffer(contract, state.renderer.lastHostContractExport);
    log("ok", "Renderer host contract exported", {
      driverKind: state.renderer.kind,
      hostType: contract.hostContract.hostType,
      methods: contract.hostContract.requiredMethods.length
    });
    return contract;
  }

  function exportRendererBridgeTemplate() {
    const template = buildRendererBridgeTemplate();
    state.renderer.lastBridgeTemplateExport = "Bridge template exported at " + template.generatedAt;
    writeRuntimeIoBuffer(template, state.renderer.lastBridgeTemplateExport);
    log("ok", "Renderer bridge template exported", {
      driverKind: template.driverKind,
      hostType: template.hostType,
      profilePreset: template.profilePreset
    });
    return template;
  }

  function exportRendererDriverTemplate() {
    const template = buildRendererDriverTemplate();
    state.renderer.lastDriverTemplateExport = "Driver template exported at " + template.generatedAt;
    writeRuntimeIoBuffer(template, state.renderer.lastDriverTemplateExport);
    log("ok", "Renderer driver template exported", {
      driverKind: template.driverKind,
      hostType: template.hostType,
      runtimePrefix: template.runtimePrefix
    });
    return template;
  }

  function exportRendererImplementationPackage() {
    const implementationPackage = buildRendererImplementationPackage();
    state.renderer.lastImplementationPackageExport = "Implementation package exported at " + implementationPackage.generatedAt;
    writeRuntimeIoBuffer(implementationPackage, state.renderer.lastImplementationPackageExport);
    log("ok", "Renderer implementation package exported", {
      packageName: implementationPackage.packageName,
      fileCount: Object.keys(implementationPackage.files || {}).length,
      rendererKind: implementationPackage.rendererKind
    });
    return implementationPackage;
  }

  function previewSelectedRendererCommand() {
    const tile = state.tiles[state.selectedTileIndex];
    if (!tile || !tile.previewUrl) {
      throw new Error("Selected tile does not have a resolved preview URL");
    }
    const command = buildRendererCommand(tile.rendererAttached ? "refresh" : "attach", tile);
    writeRuntimeIoBuffer(command, "Selected renderer command exported at " + command.createdAt);
    log("ok", "Selected renderer command previewed", {
      tile: command.tileOrdinal,
      action: command.action,
      method: command.bridgeInvocation.method
    });
    return command;
  }

  function previewSweepRendererCommands() {
    const commands = state.tiles
      .filter(function (tile) { return !!tile.previewUrl; })
      .map(function (tile) {
        return buildRendererCommand(tile.rendererAttached ? "refresh" : "attach", tile);
      });
    const plan = {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      rendererKind: state.renderer.kind,
      count: commands.length,
      commands: commands
    };
    writeRuntimeIoBuffer(plan, "Renderer command sweep exported at " + plan.generatedAt);
    log("ok", "Renderer command sweep previewed", {
      rendererKind: state.renderer.kind,
      count: commands.length
    });
    return plan;
  }

  function exportRuntimeBundle() {
    const bundle = buildRuntimeBundle();
    writeRuntimeIoBuffer(bundle, "Runtime bundle exported at " + bundle.exportedAt);
    log("ok", "Runtime bundle exported", {
      layout: bundle.runtimeSession.layout,
      readyTiles: readyTileCount(),
      attachedTiles: attachedRendererCount()
    });
    return bundle;
  }

  function importRuntimeBundle(reason) {
    const payload = readRuntimeIoBufferJson();
    const bundle = payload && payload.runtimeSession ? payload : { runtimeSession: payload };
    if (bundle.inputs) {
      applyInputSnapshot(bundle.inputs);
    }
    if (bundle.settings && typeof bundle.settings === "object") {
      if (bundle.settings.layout === 4 || bundle.settings.layout === 9 || bundle.settings.layout === 12) {
        state.layout = bundle.settings.layout;
      }
      if (typeof bundle.settings.rendererKind === "string" && bundle.settings.rendererKind) {
        state.renderer.kind = bundle.settings.rendererKind;
        el.rendererKind.value = bundle.settings.rendererKind;
      }
      if (typeof bundle.settings.rendererAutoAttach === "boolean") {
        state.renderer.autoAttach = bundle.settings.rendererAutoAttach;
        el.rendererAutoAttach.value = state.renderer.autoAttach ? "1" : "0";
      }
      if (typeof bundle.settings.pollingMode === "string") {
        state.polling.mode = bundle.settings.pollingMode === "fullscreen" ? "fullscreen" : "select";
        el.pollingMode.value = state.polling.mode;
      }
      if (Number(bundle.settings.pollingDwellMs) >= 300) {
        state.polling.dwellMs = Number(bundle.settings.pollingDwellMs);
        el.pollingDwellMs.value = String(state.polling.dwellMs);
      }
    }
    if (!bundle.runtimeSession || typeof bundle.runtimeSession !== "object") {
      throw new Error("Imported JSON must contain runtimeSession or be a runtimeSession snapshot");
    }
    loadRuntimeSessionSnapshotFromObject(bundle.runtimeSession, reason || "buffer-import");
    persistRuntimeSession(reason || "buffer-import");
    state.runtimeBundleStatus = "Runtime bundle imported at " + new Date().toISOString();
    renderAll();
    log("ok", "Runtime bundle imported", {
      reason: reason || "buffer-import",
      layout: state.layout,
      rendererKind: state.renderer.kind
    });
    return bundle;
  }

  function isBridgeRuntime() {
    return state.bridgeAvailable && !state.mockMode;
  }

  function runtimeModeLabel() {
    if (state.mockMode) {
      return "Mock Replay";
    }
    return state.bridgeAvailable ? "Live API via webcontainer" : "Live API via browser";
  }

  function setTitle(status) {
    document.title = "Platform Spike POC - " + status;
  }

  function normalizeBaseUrl() {
    return (el.platformBaseUrl.value || "").trim().replace(/\/+$/, "");
  }

  function extractTicket(ticketInfo) {
    if (!ticketInfo) {
      return "";
    }
    const data = ticketInfo.data || ticketInfo;
    if (data.ticket || data.Token || data.token) {
      return data.ticket || data.Token || data.token || "";
    }
    if (Array.isArray(data.list) && data.list.length) {
      const first = data.list[0] || {};
      return first.token || first.ticket || first.Token || "";
    }
    return "";
  }

  function normalizeToken() {
    return (el.platformToken.value || "").trim() || extractTicket(state.ticketInfo);
  }

  function protocolForPreviewUrl(cameraIndexCode) {
    return el.protocol.value || "ws";
  }

  function getRendererAdapter(kind) {
    return RENDERER_ADAPTERS[kind] || RENDERER_ADAPTERS["mock-ws"];
  }

  function rendererLabel() {
    return getRendererAdapter(state.renderer.kind).label;
  }

  function rendererCapabilitySummary() {
    const adapter = getRendererAdapter(state.renderer.kind);
    return adapter.transport + " / " + adapter.surfaceType;
  }

  function syncRendererInputsToState() {
    const previousKind = state.renderer.kind;
    const previousPreset = state.renderer.profile.preset;
    const previousBridgePreset = state.renderer.templatePresets.bridgePreset;
    const previousDriverPreset = state.renderer.templatePresets.driverPreset;
    state.renderer.kind = el.rendererKind.value || "mock-ws";
    state.renderer.autoAttach = el.rendererAutoAttach.value !== "0";
    state.renderer.driverMode = el.rendererDriverMode.value || "dry-run";
    state.renderer.profile.preset = el.rendererProfilePreset.value || "auto";
    state.renderer.templatePresets.bridgePreset = el.rendererBridgeTemplatePreset.value || "auto";
    state.renderer.templatePresets.driverPreset = el.rendererDriverTemplatePreset.value || "auto";
    state.renderer.health.recoveryPolicy = el.rendererRecoveryPolicy.value || "reinit-driver";
    state.renderer.health.heartbeatIntervalMs = Math.max(1000, Number(el.rendererHeartbeatMs.value || state.renderer.health.heartbeatIntervalMs || 4800));
    if (previousKind && previousKind !== state.renderer.kind) {
      if (state.renderer.health.heartbeatEnabled) {
        stopRendererHeartbeat("kind-switch", { silent: true, persist: false });
      }
      state.renderer.driverInitialized = false;
      state.renderer.driverRuntimeId = "";
      state.renderer.lastDriverLifecycle = "kind-switch / reset";
      state.renderer.lastDriverRun = "Reset after renderer kind switch";
      pushRendererLifecycle("kind-switch", "reset", {
        previousKind: previousKind,
        nextKind: state.renderer.kind
      });
    }
    if (previousPreset !== state.renderer.profile.preset) {
      pushRendererProfileHistory({
        id: "profile-" + String(Date.now()),
        at: new Date().toISOString(),
        previousPreset: previousPreset || "auto",
        nextPreset: state.renderer.profile.preset
      });
    }
    if (previousBridgePreset !== state.renderer.templatePresets.bridgePreset || previousDriverPreset !== state.renderer.templatePresets.driverPreset) {
      pushRendererTemplatePresetHistory({
        id: "template-preset-" + String(Date.now()),
        at: new Date().toISOString(),
        previousBridgePreset: previousBridgePreset || "auto",
        nextBridgePreset: state.renderer.templatePresets.bridgePreset,
        previousDriverPreset: previousDriverPreset || "auto",
        nextDriverPreset: state.renderer.templatePresets.driverPreset
      });
    }
    currentRendererProfile();
    currentRendererBridgeTemplatePreset();
    currentRendererDriverTemplatePreset();
  }

  function attachedRendererCount() {
    return state.tiles.filter(function (tile) {
      return !!tile.rendererAttached;
    }).length;
  }

  function syncPollingInputsToState() {
    const dwell = Number(el.pollingDwellMs.value || state.polling.dwellMs || 2200);
    state.polling.dwellMs = Number.isFinite(dwell) && dwell >= 300 ? dwell : 2200;
    state.polling.mode = el.pollingMode.value === "fullscreen" ? "fullscreen" : "select";
  }

  function currentPollingRouteTileIndex() {
    if (state.polling.currentRouteIndex < 0 || state.polling.currentRouteIndex >= state.polling.route.length) {
      return null;
    }
    return state.polling.route[state.polling.currentRouteIndex];
  }

  function pollingProgress() {
    if (!state.polling.running || !state.polling.lastStepAt || state.polling.dwellMs <= 0) {
      return 0;
    }
    return Math.max(0, Math.min(1, (Date.now() - state.polling.lastStepAt) / state.polling.dwellMs));
  }

  function derivePollingRouteFromTiles() {
    const route = [];
    state.tiles.forEach(function (tile) {
      if (tile.cameraIndexCode) {
        route.push(tile.tileIndex);
      }
    });
    return route;
  }

  function seedPollingRoute() {
    const route = derivePollingRouteFromTiles();
    if (!route.length) {
      throw new Error("No bound tiles available for polling");
    }
    state.polling.route = route;
    if (route.indexOf(state.selectedTileIndex) >= 0) {
      state.polling.currentRouteIndex = route.indexOf(state.selectedTileIndex);
    } else {
      state.polling.currentRouteIndex = 0;
    }
    state.polling.lastStepAt = 0;
    renderAll();
    log("ok", "Polling route seeded from bound tiles", {
      route: route.map(function (tileIndex) { return tileIndex + 1; })
    });
  }

  function candidateBaseUrl(loginInfo) {
    const visited = new Set();
    const queue = [loginInfo];
    while (queue.length) {
      const current = queue.shift();
      if (!current || typeof current !== "object" || visited.has(current)) {
        continue;
      }
      visited.add(current);
      const protocol = current.protocol || current.scheme || current.schema || current.httpProtocol;
      const host = current.host || current.hostname || current.ip || current.serverIp || current.serverIP;
      const port = current.port || current.serverPort || current.httpsPort;
      if (host && port) {
        return String(protocol || "https") + "://" + String(host) + ":" + String(port);
      }
      Object.keys(current).forEach(function (key) {
        const value = current[key];
        if (value && typeof value === "object") {
          queue.push(value);
        }
      });
    }
    return "";
  }

  function mockPreviewResponse(cameraIndexCode) {
    const protocol = protocolForPreviewUrl(cameraIndexCode);
    const suffix = protocol === "hls" ? ".m3u8" : protocol === "rtmp" ? "" : protocol === "rtsp" ? "" : "";
    const url = protocol === "hls"
      ? "https://mock-media.local/live/" + cameraIndexCode + suffix
      : protocol === "rtmp"
        ? "rtmp://mock-media.local/live/" + cameraIndexCode
        : protocol === "rtsp"
          ? "rtsp://mock-media.local/live/" + cameraIndexCode
          : "ws://mock-media.local/live/" + cameraIndexCode;
    return {
      code: "0",
      msg: "SUCCESS",
      data: {
        cameraIndexCode: cameraIndexCode,
        protocol: protocol,
        url: url
      }
    };
  }

  function enableMockMode(reason) {
    stopPollingRuntime(null, { persist: false });
    state.mockMode = true;
    state.loginInfo = clone(MOCK_FIXTURES.loginInfo);
    state.ticketInfo = clone(MOCK_FIXTURES.ticketInfo);
    state.serviceInfo = clone(MOCK_FIXTURES.serviceInfo);
    state.lastTreeCodes = clone(MOCK_FIXTURES.treeCodes);
    state.lastRegions = clone(MOCK_FIXTURES.regions);
    state.lastCameraList = clone(MOCK_FIXTURES.cameras);
    state.tvwallResources = clone(MOCK_FIXTURES.tvwallResources);
    state.tvwallScenes = clone(MOCK_FIXTURES.tvwallScenes);
    state.tvwallWindows = clone(MOCK_FIXTURES.tvwallWindows);
    state.selectedDlpId = "9001";
    state.selectedMonitorPos = "1";
    state.selectedFloatWindowId = "5001";
    state.selectedWndUri = "mock://tvwall/window/5001";
    state.mockTvwallState = {
      monitorDivision: state.layout,
      floatDivision: state.layout,
      zoomMode: state.fullscreenTileIndex === null ? "grid" : "full_screen"
    };
    if (!el.platformBaseUrl.value) {
      el.platformBaseUrl.value = "https://mock.infovision.local:443";
    }
    el.platformToken.value = extractTicket(state.ticketInfo);
    el.lastPreviewResponse.textContent = "Mock replay mode enabled. Resolve tiles to generate local preview URLs.";
    renderAll();
    setTitle("ready-mock");
    if (reason && reason !== "query-string") {
      persistRuntimeSession(reason);
    }
    log("warn", "Mock replay enabled", {
      reason: reason || "manual",
      layout: state.layout,
      cameraCount: getCameraList().length
    });
  }

  function disableMockMode() {
    stopPollingRuntime(null, { persist: false });
    state.mockMode = false;
    state.loginInfo = null;
    state.ticketInfo = null;
    state.serviceInfo = null;
    state.lastTreeCodes = null;
    state.lastRegions = null;
    state.lastCameraList = null;
    state.tvwallResources = null;
    state.tvwallScenes = null;
    state.tvwallWindows = null;
    state.selectedDlpId = "";
    state.selectedMonitorPos = "";
    state.selectedFloatWindowId = "";
    state.selectedWndUri = "";
    renderAll();
    setTitle(isBridgeRuntime() ? "ready-container" : "ready-browser");
    persistRuntimeSession("disable-mock");
    log("warn", "Returned to live API mode");
  }

  function mockApiResponse(path, body) {
    if (path === "/api/resource/v1/unit/getAllTreeCode") {
      return clone(MOCK_FIXTURES.treeCodes);
    }
    if (path === "/api/resource/v1/regions") {
      return clone(MOCK_FIXTURES.regions);
    }
    if (path === "/api/resource/v1/cameras") {
      return clone(MOCK_FIXTURES.cameras);
    }
    if (path === "/api/video/v1/cameras/previewURLs") {
      return mockPreviewResponse((body || {}).cameraIndexCode || "mock-camera-01");
    }
    if (path === "/api/tvms/v1/tvwall/allResources") {
      return clone(MOCK_FIXTURES.tvwallResources);
    }
    if (path === "/api/tvms/v1/tvwall/scenes") {
      return clone(MOCK_FIXTURES.tvwallScenes);
    }
    if (path === "/api/tvms/v1/tvwall/wnds/get") {
      return clone(MOCK_FIXTURES.tvwallWindows);
    }
    if (path === "/api/tvms/v1/public/tvwall/monitor/division") {
      state.mockTvwallState.monitorDivision = Number((body || {}).div_num || state.mockTvwallState.monitorDivision || 4);
      setLayout(state.mockTvwallState.monitorDivision);
      return {
        code: "0",
        msg: "SUCCESS",
        data: {
          mode: "mock-monitor-division",
          div_num: state.mockTvwallState.monitorDivision
        }
      };
    }
    if (path === "/api/tvms/v1/public/tvwall/floatWnd/division") {
      state.mockTvwallState.floatDivision = Number((body || {}).div_num || state.mockTvwallState.floatDivision || 4);
      setLayout(state.mockTvwallState.floatDivision);
      return {
        code: "0",
        msg: "SUCCESS",
        data: {
          mode: "mock-float-division",
          div_num: state.mockTvwallState.floatDivision
        }
      };
    }
    if (path === "/api/tvms/v1/public/tvwall/floatWnd/zoomIn") {
      state.mockTvwallState.zoomMode = (body || {}).type || "normal";
      if (state.mockTvwallState.zoomMode === "full_screen") {
        state.fullscreenTileIndex = state.selectedTileIndex;
      }
      return {
        code: "0",
        msg: "SUCCESS",
        data: {
          mode: "mock-zoom-in",
          type: state.mockTvwallState.zoomMode,
          selectedTileIndex: state.selectedTileIndex
        }
      };
    }
    if (path === "/api/tvms/v1/public/tvwall/floatWnd/zoomOut") {
      state.mockTvwallState.zoomMode = "grid";
      state.fullscreenTileIndex = null;
      return {
        code: "0",
        msg: "SUCCESS",
        data: {
          mode: "mock-zoom-out"
        }
      };
    }
    throw new Error("Mock handler not implemented for " + path);
  }

  function invokeCef(requestObject) {
    return new Promise(function (resolve, reject) {
      if (!state.bridgeAvailable) {
        reject(new Error("window.cefQuery is not available"));
        return;
      }
      window.cefQuery({
        request: JSON.stringify(requestObject),
        persistent: false,
        onSuccess: function (response) {
          resolve(safeJson(response));
        },
        onFailure: function (errorCode, errorMessage) {
          reject(new Error(String(errorCode) + ": " + String(errorMessage)));
        }
      });
    });
  }

  async function callContainerMethod(method, data) {
    const request = {
      request: "GetInfoFromFrame",
      params: {
        method: method,
        data: data
      }
    };
    log("ok", "Container request: " + method, request);
    const result = await invokeCef(request);
    log("ok", "Container response: " + method, result);
    return result;
  }

  async function getLoginInfo() {
    if (state.mockMode) {
      state.loginInfo = clone(MOCK_FIXTURES.loginInfo);
      if (!el.platformBaseUrl.value) {
        el.platformBaseUrl.value = candidateBaseUrl(state.loginInfo);
      }
      log("warn", "Mock response: GetLoginInfo", state.loginInfo);
      return state.loginInfo;
    }
    const request = { request: "GetLoginInfo" };
    log("ok", "Container request: GetLoginInfo", request);
    const result = await invokeCef(request);
    state.loginInfo = result;
    const baseUrl = candidateBaseUrl(result);
    if (baseUrl && !el.platformBaseUrl.value) {
      el.platformBaseUrl.value = baseUrl;
      log("ok", "Filled platform base URL from login info", baseUrl);
    }
    log("ok", "Container response: GetLoginInfo", result);
    return result;
  }

  async function getTickets() {
    if (state.mockMode) {
      state.ticketInfo = clone(MOCK_FIXTURES.ticketInfo);
      el.platformToken.value = extractTicket(state.ticketInfo);
      log("warn", "Mock response: getTickets", state.ticketInfo);
      return state.ticketInfo;
    }
    const result = await callContainerMethod("getTickets", {
      total: 1,
      type: 0,
      tokenType: 1
    });
    state.ticketInfo = result;
    const token = extractTicket(result);
    if (token && !el.platformToken.value) {
      el.platformToken.value = token;
    }
    return result;
  }

  async function getServiceInfo() {
    if (state.mockMode) {
      state.serviceInfo = clone(MOCK_FIXTURES.serviceInfo);
      log("warn", "Mock response: getServiceInfoByType", state.serviceInfo);
      return state.serviceInfo;
    }
    const result = await callContainerMethod("getServiceInfoByType", {
      serviceType: el.serviceType.value.trim(),
      componentId: el.componentId.value.trim()
    });
    state.serviceInfo = result;
    return result;
  }

  async function requestAuthProbeTicket(label, data) {
    try {
      const result = await callContainerMethod("getTickets", data);
      const token = extractTicket(result);
      return {
        label: label,
        ok: !result || !result.errorCode,
        request: clone(data),
        token: token,
        ticketLabel: redactToken(token),
        summary: summarizePayload(result),
        errorCode: result && result.errorCode ? String(result.errorCode) : "",
        raw: result
      };
    } catch (error) {
      return {
        label: label,
        ok: false,
        request: clone(data),
        token: "",
        ticketLabel: "error",
        summary: String(error && error.message ? error.message : error),
        errorCode: "",
        raw: null
      };
    }
  }

  async function collectAuthProbeTickets() {
    const variants = [
      { key: "type0_token1", label: "type=0 tokenType=1", request: { total: 1, type: 0, tokenType: 1 } },
      { key: "type0_token2", label: "type=0 tokenType=2", request: { total: 1, type: 0, tokenType: 2 } },
      { key: "type2", label: "type=2", request: { total: 1, type: 2 } }
    ];
    const results = {};
    for (let index = 0; index < variants.length; index += 1) {
      const variant = variants[index];
      results[variant.key] = await requestAuthProbeTicket(variant.label, variant.request);
    }
    if (!state.ticketInfo) {
      const preferred = results.type0_token1 && results.type0_token1.token ? results.type0_token1
        : results.type0_token2 && results.type0_token2.token ? results.type0_token2
        : results.type2 && results.type2.token ? results.type2
        : null;
      if (preferred && preferred.raw) {
        state.ticketInfo = preferred.raw;
        if (!el.platformToken.value) {
          el.platformToken.value = preferred.token;
        }
      }
    }
    return results;
  }

  function authProbeCandidates(ticketResults) {
    const candidates = [
      {
        key: "proxy-empty-token",
        label: "Proxy Token empty string",
        heads: {
          "Content-Type": "application/json",
          Token: ""
        }
      },
      {
        key: "proxy-no-auth-headers",
        label: "Proxy no auth headers",
        heads: {
          "Content-Type": "application/json"
        }
      }
    ];
    Object.keys(ticketResults || {}).forEach(function (key) {
      const item = ticketResults[key];
      if (!item || !item.token) {
        return;
      }
      candidates.push({
        key: "proxy-" + key + "-token",
        label: "Proxy Token from " + item.label,
        heads: {
          "Content-Type": "application/json",
          Token: item.token
        }
      });
      candidates.push({
        key: "proxy-" + key + "-bearer",
        label: "Proxy Authorization Bearer from " + item.label,
        heads: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + item.token
        }
      });
    });
    return candidates;
  }

  async function runProxyProbeSeries(spec, candidates) {
    const attempts = [];
    for (let index = 0; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      try {
        const response = await proxyRequest({
          method: spec.method,
          timeout: spec.timeout || 3,
          url: spec.path,
          heads: candidate.heads,
          body: spec.body
        });
        const ok = looksSuccessfulPayload(response);
        const authFailed = hasAppAuthFailure(response);
        const attempt = {
          key: candidate.key,
          label: candidate.label,
          ok: ok,
          authFailed: authFailed,
          summary: summarizePayload(response)
        };
        attempts.push(attempt);
        if (ok) {
          return {
            status: "ok",
            ok: true,
            bestCandidate: candidate.key,
            summary: attempt.summary,
            attempts: attempts
          };
        }
      } catch (error) {
        attempts.push({
          key: candidate.key,
          label: candidate.label,
          ok: false,
          authFailed: false,
          summary: String(error && error.message ? error.message : error)
        });
      }
    }
    const authFailure = attempts.find(function (attempt) { return attempt.authFailed; });
    if (authFailure) {
      return {
        status: "auth-failed",
        ok: false,
        bestCandidate: authFailure.key,
        summary: authFailure.summary,
        attempts: attempts
      };
    }
    const firstAttempt = attempts[0];
    return {
      status: "transport-failed",
      ok: false,
      bestCandidate: firstAttempt ? firstAttempt.key : "",
      summary: firstAttempt ? firstAttempt.summary : "No attempts executed",
      attempts: attempts
    };
  }

  async function copyAuthProbeResult() {
    const text = state.authProbe.resultText || "";
    if (!text) {
      throw new Error("No auth probe result available");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      log("ok", "Container auth probe result copied to clipboard");
      return;
    }
    el.authProbeResult.focus();
    el.authProbeResult.select();
    document.execCommand("copy");
    log("ok", "Container auth probe result copied via textarea selection");
  }

  async function runContainerAuthProbe() {
    if (!state.bridgeAvailable || state.mockMode) {
      throw new Error("Container auth probe only runs in live webcontainer mode");
    }
    state.authProbe.running = true;
    state.authProbe.status = "Running";
    state.authProbe.lastRunAt = new Date().toISOString();
    state.authProbe.lastSummary = "Running";
    renderAll();
    try {
      if (!state.loginInfo) {
        await getLoginInfo();
      }

      const ticketResults = await collectAuthProbeTickets();
      const contexts = authProbeContexts();
      const userIndexCode = resolveUserIndexCode();
      const candidates = authProbeCandidates(ticketResults);
      const xresPath = contexts.xresSearch + "/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=" + encodeURIComponent(userIndexCode);
      const tvmsAllPath = contexts.tvms + "/v1/all?method=GET&userIndexCode=" + encodeURIComponent(userIndexCode);
      const tvmsRuokPath = contexts.tvms + "/v1/ruok?method=GET";

      const xresProbe = await runProxyProbeSeries(
        {
          method: "POST",
          timeout: 3,
          path: xresPath,
          body: {
            resourceType: "CAMERA",
            catalogDictionaryCode: ["basic_tree", "bvideo_basic_tree", "imp_tree"]
          }
        },
        candidates
      );
      const tvmsAllProbe = await runProxyProbeSeries(
        {
          method: "GET",
          timeout: 3,
          path: tvmsAllPath,
          body: null
        },
        candidates
      );
      const tvmsRuokProbe = await runProxyProbeSeries(
        {
          method: "GET",
          timeout: 2,
          path: tvmsRuokPath,
          body: null
        },
        candidates
      );

      const snapshot = {
        generatedAt: new Date().toISOString(),
        bridgeMode: "webcontainer",
        runtimeMode: runtimeModeLabel(),
        platformBaseUrl: resolvePlatformBaseUrl(),
        userIndexCode: userIndexCode,
        contexts: contexts,
        ticketVariants: {
          type0_token1: ticketResults.type0_token1 ? ticketResults.type0_token1.ticketLabel : "missing",
          type0_token2: ticketResults.type0_token2 ? ticketResults.type0_token2.ticketLabel : "missing",
          type2: ticketResults.type2 ? ticketResults.type2.ticketLabel : "missing"
        },
        xresProbe: xresProbe,
        tvmsAllProbe: tvmsAllProbe,
        tvmsRuokProbe: tvmsRuokProbe,
        nextStep: ""
      };
      if (xresProbe.ok && (tvmsAllProbe.ok || tvmsRuokProbe.ok)) {
        snapshot.nextStep = "容器会话已经拿到 xres/tvms 的可用返回。下一步可以继续接 previewURLs 或 tvwall live wiring。";
        state.authProbe.status = "Ready";
      } else if (xresProbe.status === "auth-failed" || tvmsAllProbe.status === "auth-failed" || tvmsRuokProbe.status === "auth-failed") {
        snapshot.nextStep = "容器代理已经碰到真实服务，但认证头形态还没对上。把这段结果发回来，我继续调整 proxy/token 策略。";
        state.authProbe.status = "Auth Mismatch";
      } else {
        snapshot.nextStep = "当前更像网络或代理不稳定。保持客户端登录，下次再在稳定政务网里进入视频监控重试。";
        state.authProbe.status = "Network Or Proxy Blocked";
      }

      state.authProbe.lastSummary = buildAuthProbeSummary(snapshot);
      state.authProbe.snapshot = snapshot;
      state.authProbe.resultText = buildAuthProbeResultBlock(snapshot);
      writeStoredAuthProbeSnapshot();
      log("ok", "Container auth probe completed", {
        status: state.authProbe.status,
        summary: state.authProbe.lastSummary,
        xres: probeOutcomeLabel(xresProbe),
        tvmsAll: probeOutcomeLabel(tvmsAllProbe),
        tvmsRuok: probeOutcomeLabel(tvmsRuokProbe)
      });
      return snapshot;
    } catch (error) {
      state.authProbe.status = "Failed";
      state.authProbe.lastSummary = String(error && error.message ? error.message : error);
      state.authProbe.snapshot = null;
      state.authProbe.resultText = [
        "=== CONTAINER_AUTH_RESULT ===",
        "generatedAt=" + new Date().toISOString(),
        "status=failed",
        "message=" + state.authProbe.lastSummary,
        "CONTAINER_AUTH_RESULT_END"
      ].join("\n");
      writeStoredAuthProbeSnapshot();
      throw error;
    } finally {
      state.authProbe.running = false;
      renderAll();
    }
  }

  function buildProxyHeaders() {
    const headers = { "Content-Type": "application/json" };
    const token = normalizeToken();
    if (token) {
      headers.Token = token;
    }
    return headers;
  }

  async function proxyRequest(payload) {
    const requestPayload = {
      method: payload.method || "POST",
      timeout: payload.timeout || 15,
      url: payload.url,
      heads: payload.heads || {},
      body: payload.body || {}
    };
    log("ok", "Proxy request", requestPayload);
    const response = await fetch("/proxy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload)
    });
    const text = await response.text();
    const parsed = safeJson(text);
    if (!response.ok) {
      log("err", "Proxy HTTP error", { status: response.status, body: parsed });
      throw new Error("Proxy HTTP " + response.status);
    }
    log("ok", "Proxy response", parsed);
    return parsed;
  }

  async function directRequest(payload) {
    const headers = { "Content-Type": "application/json" };
    const token = normalizeToken();
    if (token) {
      headers.Token = token;
    }
    const response = await fetch(payload.url, {
      method: payload.method || "POST",
      headers: headers,
      body: JSON.stringify(payload.body || {})
    });
    const text = await response.text();
    const parsed = safeJson(text);
    if (!response.ok) {
      log("err", "Direct HTTP error", { status: response.status, body: parsed });
      throw new Error("Direct HTTP " + response.status);
    }
    log("ok", "Direct response", parsed);
    return parsed;
  }

  async function callPlatformApi(path, body) {
    if (state.mockMode) {
      const result = mockApiResponse(path, body || {});
      log("warn", "Mock API response: " + path, result);
      return result;
    }
    const baseUrl = normalizeBaseUrl();
    if (!baseUrl && state.bridgeAvailable) {
      return proxyRequest({
        method: "POST",
        url: path,
        heads: buildProxyHeaders(),
        body: body || {}
      });
    }
    if (!baseUrl) {
      throw new Error("Platform Base URL is required in browser mode");
    }
    return directRequest({
      method: "POST",
      url: baseUrl + path,
      body: body || {}
    });
  }

  async function listTreeCodes() {
    state.lastTreeCodes = await callPlatformApi("/api/resource/v1/unit/getAllTreeCode", {});
    return state.lastTreeCodes;
  }

  async function listRegions() {
    state.lastRegions = await callPlatformApi("/api/resource/v1/regions", {
      pageNo: 1,
      pageSize: Number(el.regionPageSize.value || 50),
      treeCode: el.treeCode.value.trim() || "0"
    });
    return state.lastRegions;
  }

  async function listCameras() {
    state.lastCameraList = await callPlatformApi("/api/resource/v1/cameras", {
      pageNo: Number(el.cameraPageNo.value || 1),
      pageSize: Number(el.cameraPageSize.value || 20),
      treeCode: el.treeCode.value.trim() || "0"
    });
    return state.lastCameraList;
  }

  function buildPreviewRequestBody(cameraIndexCode) {
    const body = {
      cameraIndexCode: cameraIndexCode,
      streamType: Number(el.streamType.value),
      protocol: el.protocol.value,
      transmode: Number(el.transmode.value)
    };
    if (el.expand.value.trim()) {
      body.expand = el.expand.value.trim();
    }
    return body;
  }

  async function getPreviewUrlByCamera(cameraIndexCode) {
    const result = await callPlatformApi("/api/video/v1/cameras/previewURLs", buildPreviewRequestBody(cameraIndexCode));
    state.lastPreviewResponse = result;
    state.previewUrlByCamera[cameraIndexCode] = result;
    el.lastPreviewResponse.textContent = pretty(result);
    return result;
  }

  async function getPreviewUrl() {
    const cameraIndexCode = el.cameraIndexCode.value.trim();
    if (!cameraIndexCode) {
      throw new Error("Camera Index Code is required");
    }
    return getPreviewUrlByCamera(cameraIndexCode);
  }

  function getCameraList() {
    return (((state.lastCameraList || {}).data || {}).list || []);
  }

  function getCameraByIndexCode(cameraIndexCode) {
    const list = getCameraList();
    for (let index = 0; index < list.length; index += 1) {
      if ((list[index].cameraIndexCode || "") === cameraIndexCode) {
        return list[index];
      }
    }
    return null;
  }

  function createTile(tileIndex) {
    return {
      tileIndex: tileIndex,
      cameraIndexCode: "",
      cameraName: "",
      previewUrl: "",
      previewProtocol: "",
      status: "empty",
      rendererAttached: false,
      rendererKind: "",
      rendererSessionId: "",
      rendererSurfaceType: "",
      rendererTransport: "",
      rendererDisplayUrl: "",
      rendererStatus: ""
    };
  }

  function syncTiles(nextLayout) {
    const nextTiles = [];
    for (let index = 0; index < nextLayout; index += 1) {
      nextTiles.push(state.tiles[index] ? {
        tileIndex: index,
        cameraIndexCode: state.tiles[index].cameraIndexCode || "",
        cameraName: state.tiles[index].cameraName || "",
        previewUrl: state.tiles[index].previewUrl || "",
        previewProtocol: state.tiles[index].previewProtocol || "",
        status: state.tiles[index].status || "bound",
        rendererAttached: !!state.tiles[index].rendererAttached,
        rendererKind: state.tiles[index].rendererKind || "",
        rendererSessionId: state.tiles[index].rendererSessionId || "",
        rendererSurfaceType: state.tiles[index].rendererSurfaceType || "",
        rendererTransport: state.tiles[index].rendererTransport || "",
        rendererDisplayUrl: state.tiles[index].rendererDisplayUrl || "",
        rendererStatus: state.tiles[index].rendererStatus || ""
      } : createTile(index));
    }
    state.tiles = nextTiles;
    if (state.selectedTileIndex >= nextTiles.length) {
      state.selectedTileIndex = 0;
    }
    if (state.fullscreenTileIndex !== null && state.fullscreenTileIndex >= nextTiles.length) {
      state.fullscreenTileIndex = null;
    }
  }

  function setLayout(layout) {
    state.layout = layout;
    syncTiles(layout);
    renderAll();
  }

  function layoutColumns() {
    if (state.fullscreenTileIndex !== null) {
      return 1;
    }
    return state.layout === 4 ? 2 : state.layout === 9 ? 3 : 4;
  }

  function assignCameraToTile(tileIndex, camera) {
    state.tiles[tileIndex] = {
      tileIndex: tileIndex,
      cameraIndexCode: camera.cameraIndexCode || "",
      cameraName: camera.name || camera.cameraName || "Unnamed camera",
      previewUrl: state.tiles[tileIndex].previewUrl || "",
      previewProtocol: state.tiles[tileIndex].previewProtocol || "",
      status: "bound",
      rendererAttached: false,
      rendererKind: "",
      rendererSessionId: "",
      rendererSurfaceType: "",
      rendererTransport: "",
      rendererDisplayUrl: "",
      rendererStatus: ""
    };
    el.cameraIndexCode.value = camera.cameraIndexCode || "";
  }

  function clearWall() {
    syncTiles(state.layout);
    state.previewUrlByCamera = {};
    state.lastPreviewResponse = null;
    state.fullscreenTileIndex = null;
    detachAllRenderers(true);
    state.polling.route = [];
    state.polling.currentRouteIndex = -1;
    state.polling.cycleCount = 0;
    state.polling.lastStepAt = 0;
    el.lastPreviewResponse.textContent = "No preview response yet.";
    renderAll();
    log("warn", "Local preview wall cleared");
  }

  function bindFirstCameras() {
    const cameras = getCameraList();
    if (!cameras.length) {
      throw new Error("No camera list available");
    }
    for (let index = 0; index < state.tiles.length; index += 1) {
      if (!cameras[index]) {
        break;
      }
      assignCameraToTile(index, cameras[index]);
    }
  }

  function attachRendererToTile(tileIndex, silent) {
    syncRendererInputsToState();
    const tile = state.tiles[tileIndex];
    if (!tile || !tile.previewUrl) {
      return false;
    }
    const adapter = getRendererAdapter(state.renderer.kind);
    const attachPayload = buildRendererAttachPayload(tile);
    const attachment = adapter.attach(tile);
    tile.rendererAttached = !!attachment.attached;
    tile.rendererKind = state.renderer.kind;
    tile.rendererSessionId = attachment.sessionId || "";
    tile.rendererSurfaceType = attachment.surfaceType || adapter.surfaceType || "";
    tile.rendererTransport = attachment.transport || adapter.transport || "";
    tile.rendererDisplayUrl = attachment.displayUrl || tile.previewUrl || "";
    tile.rendererStatus = attachment.status || "Renderer attached";
    state.renderer.lastEvent = tile.rendererAttached
      ? "Attached " + rendererLabel() + " to tile " + String(tileIndex + 1)
      : "Attach skipped for tile " + String(tileIndex + 1);
    if (tile.rendererAttached) {
      enqueueRendererCommand(buildRendererCommand("attach", tile, attachPayload), { log: !silent, persist: false });
    }
    if (!silent) {
      log("ok", "Renderer attached to tile", {
        tileIndex: tileIndex + 1,
        rendererKind: state.renderer.kind,
        previewUrl: tile.previewUrl,
        sessionId: tile.rendererSessionId,
        transport: tile.rendererTransport,
        surfaceType: tile.rendererSurfaceType
      });
    }
    return tile.rendererAttached;
  }

  function attachRenderersToReadyTiles(silent) {
    const admission = guardRendererAdmission("attach", { silent: true, persist: false });
    if (!admission.allowed) {
      renderAll();
      if (!silent) {
        log("err", "Renderer attach admission blocked", {
          reasons: admission.blockingReasons
        });
      }
      return 0;
    }
    let attached = 0;
    state.tiles.forEach(function (tile, index) {
      if (tile.previewUrl && attachRendererToTile(index, true)) {
        attached += 1;
      }
    });
    renderAll();
    if (!silent) {
      log("ok", "Renderer attach sweep completed", {
        rendererKind: state.renderer.kind,
        attachedTiles: attached
      });
    }
    return attached;
  }

  function detachAllRenderers(silent) {
    const policy = state.renderer.actionPolicy.matrix.detach || evaluateRendererActionPolicy("detach", { silent: true, persist: false }).detach;
    if (policy && policy.decision === "blocked") {
      if (!silent) {
        log("warn", "Renderer detach skipped by action policy", {
          reasons: policy.blockingReasons
        });
      }
      return 0;
    }
    const commands = [];
    state.tiles = state.tiles.map(function (tile) {
      if (tile.rendererAttached) {
        commands.push(buildRendererCommand("detach", tile, buildRendererAttachPayload(tile)));
      }
      return {
        tileIndex: tile.tileIndex,
        cameraIndexCode: tile.cameraIndexCode,
        cameraName: tile.cameraName,
        previewUrl: tile.previewUrl,
        previewProtocol: tile.previewProtocol,
        status: tile.status,
        rendererAttached: false,
        rendererKind: "",
        rendererSessionId: "",
        rendererSurfaceType: "",
        rendererTransport: "",
        rendererDisplayUrl: "",
        rendererStatus: ""
      };
    });
    commands.forEach(function (command) {
      enqueueRendererCommand(command, { log: false, persist: false });
    });
    state.renderer.lastEvent = "Detached all renderer sessions";
    renderAll();
    if (!silent) {
      log("warn", "All renderer attachments cleared");
    }
    return commands.length;
  }

  async function resolveBoundTiles() {
    const seen = new Set();
    for (let index = 0; index < state.tiles.length; index += 1) {
      const tile = state.tiles[index];
      if (!tile.cameraIndexCode || seen.has(tile.cameraIndexCode)) {
        continue;
      }
      seen.add(tile.cameraIndexCode);
      const result = await getPreviewUrlByCamera(tile.cameraIndexCode);
      const url = ((result || {}).data || {}).url || "";
      state.tiles = state.tiles.map(function (currentTile) {
        if (currentTile.cameraIndexCode !== tile.cameraIndexCode) {
          return currentTile;
        }
        return {
          tileIndex: currentTile.tileIndex,
          cameraIndexCode: currentTile.cameraIndexCode,
          cameraName: currentTile.cameraName,
          previewUrl: url,
          previewProtocol: el.protocol.value,
          status: url ? "ready" : "bound",
          rendererAttached: url ? currentTile.rendererAttached : false,
          rendererKind: url ? currentTile.rendererKind : "",
          rendererSessionId: url ? currentTile.rendererSessionId : "",
          rendererSurfaceType: url ? currentTile.rendererSurfaceType : "",
          rendererTransport: url ? currentTile.rendererTransport : "",
          rendererDisplayUrl: url ? currentTile.rendererDisplayUrl : "",
          rendererStatus: url ? currentTile.rendererStatus : ""
        };
      });
      log("ok", "Resolved preview URL for tile camera", {
        cameraIndexCode: tile.cameraIndexCode,
        url: url
      });
    }
    if (state.renderer.autoAttach) {
      attachRenderersToReadyTiles(true);
    }
    persistRuntimeSession();
  }

  function applyPollingTarget(tileIndex, reason) {
    if (tileIndex === null || tileIndex === undefined) {
      return;
    }
    if (state.polling.mode === "fullscreen") {
      const admission = guardRendererAdmission("fullscreen-route", { silent: true, persist: false });
      if (!admission.allowed) {
        log("err", "Fullscreen route admission blocked", {
          reasons: admission.blockingReasons,
          tileIndex: tileIndex + 1
        });
        return;
      }
    }
    state.selectedTileIndex = tileIndex;
    if (state.polling.mode === "fullscreen") {
      state.fullscreenTileIndex = tileIndex;
    } else {
      state.fullscreenTileIndex = null;
    }
    state.polling.lastStepAt = Date.now();
    state.playerTickSeed += 1;
    renderAll();
    persistRuntimeSession();
    log("ok", "Polling target applied", {
      reason: reason,
      tileIndex: tileIndex + 1,
      mode: state.polling.mode
    });
  }

  function advancePollingRoute(reason) {
    syncPollingInputsToState();
    if (!state.polling.route.length) {
      seedPollingRoute();
    }
    const routeLength = state.polling.route.length;
    if (!routeLength) {
      return;
    }
    let nextIndex;
    if (state.polling.currentRouteIndex < 0 || state.polling.currentRouteIndex >= routeLength) {
      nextIndex = 0;
    } else {
      nextIndex = (state.polling.currentRouteIndex + 1) % routeLength;
      if (nextIndex === 0) {
        state.polling.cycleCount += 1;
      }
    }
    state.polling.currentRouteIndex = nextIndex;
    applyPollingTarget(state.polling.route[nextIndex], reason || "manual");
  }

  function stopPollingRuntime(reason, options) {
    const shouldPersist = !options || options.persist !== false;
    state.polling.running = false;
    if (state.polling.timerId) {
      window.clearInterval(state.polling.timerId);
      state.polling.timerId = null;
    }
    renderAll();
    if (shouldPersist) {
      persistRuntimeSession();
    }
    if (reason) {
      log("warn", "Polling runtime stopped", { reason: reason });
    }
  }

  function ensurePollingTimer() {
    if (state.polling.timerId) {
      return;
    }
    state.polling.timerId = window.setInterval(function () {
      if (!state.polling.running) {
        return;
      }
      if (!state.polling.lastStepAt) {
        advancePollingRoute("start");
        return;
      }
      if (Date.now() - state.polling.lastStepAt >= state.polling.dwellMs) {
        advancePollingRoute("timer");
        return;
      }
      renderAll();
    }, 180);
  }

  function startPollingRuntime() {
    syncPollingInputsToState();
    if (!state.polling.route.length) {
      seedPollingRoute();
    }
    state.polling.running = true;
    ensurePollingTimer();
    if (currentPollingRouteTileIndex() === null) {
      advancePollingRoute("start");
    } else {
      applyPollingTarget(currentPollingRouteTileIndex(), "resume");
    }
    writeStoredSettings();
    persistRuntimeSession();
  }

  function toggleCameraSelection(cameraIndexCode, checked) {
    const next = new Set(state.selectedCameraCodes);
    if (checked) {
      next.add(cameraIndexCode);
    } else {
      next.delete(cameraIndexCode);
    }
    state.selectedCameraCodes = Array.from(next);
  }

  function selectedTileLabel() {
    const tile = state.tiles[state.selectedTileIndex];
    if (!tile || !tile.cameraName) {
      return "Tile " + String(state.selectedTileIndex + 1);
    }
    return "Tile " + String(state.selectedTileIndex + 1) + " - " + tile.cameraName;
  }

  function renderStatus() {
    const bridgePreset = currentRendererBridgeTemplatePreset();
    const driverPreset = currentRendererDriverTemplatePreset();
    const authSnapshot = state.authProbe.snapshot;
    el.bridgeMode.textContent = state.bridgeAvailable ? "webcontainer bridge detected" : "browser mode only";
    el.runtimeModeValue.textContent = runtimeModeLabel();
    el.ticketValue.textContent = extractTicket(state.ticketInfo) || "Not loaded";
    el.layoutValue.textContent = String(state.layout) + "-grid";
    el.selectedTileValue.textContent = selectedTileLabel();
    el.authProbeStatusValue.textContent = state.authProbe.running
      ? "Running / " + state.authProbe.lastRunAt
      : state.authProbe.status + (state.authProbe.lastSummary ? " / " + state.authProbe.lastSummary : "");
    el.authProbeXresValue.textContent = authSnapshot ? probeOutcomeLabel(authSnapshot.xresProbe) : "Not run";
    el.authProbeTvmsValue.textContent = authSnapshot
      ? probeOutcomeLabel(authSnapshot.tvmsAllProbe) + " · ruok " + probeOutcomeLabel(authSnapshot.tvmsRuokProbe)
      : "Not run";
    el.authProbeContextValue.textContent = authSnapshot
      ? authSnapshot.contexts.xresSearch + " · " + authSnapshot.contexts.tvms
      : authProbeContexts().xresSearch + " · " + authProbeContexts().tvms;
    el.authProbeResult.value = state.authProbe.resultText || "Waiting for container auth probe...";
    el.boundCameraCount.textContent = String(state.tiles.filter(function (tile) {
      return !!tile.cameraIndexCode;
    }).length) + " / " + String(state.tiles.length);
    el.resolvedUrlCount.textContent = String(state.tiles.filter(function (tile) {
      return !!tile.previewUrl;
    }).length);
    el.fullscreenValue.textContent = state.fullscreenTileIndex === null ? "None" : "Tile " + String(state.fullscreenTileIndex + 1);
    el.rendererModeValue.textContent = rendererLabel();
    el.rendererAttachedValue.textContent = String(attachedRendererCount()) + " / " + rendererCapabilitySummary();
    el.rendererReadyValue.textContent = String(readyTileCount()) + " / " + String(state.tiles.length);
    el.rendererEventValue.textContent = state.renderer.lastEvent || "Idle";
    el.rendererSelectedPayloadValue.textContent = selectedTilePayloadSummary();
    el.runtimeBundleValue.textContent = state.runtimeBundleStatus;
    el.rendererCommandQueueValue.textContent = String(state.renderer.commandQueue.length) + " pending";
    el.rendererBridgeActionValue.textContent = state.renderer.bridgeAction || "Idle";
    el.rendererDriverModeValue.textContent = driverModeLabel();
    el.rendererDriverRunValue.textContent = state.renderer.lastDriverRun || "Not executed";
    el.rendererDriverStateValue.textContent = state.renderer.driverInitialized ? "Initialized" : "Not initialized";
    el.rendererDriverRuntimeValue.textContent = state.renderer.driverRuntimeId || "No runtime";
    el.rendererDriverCapabilityValue.textContent = driverCapabilitySummary();
    el.rendererHostContractValue.textContent = state.renderer.lastHostContractExport || getRendererDriver(state.renderer.kind).hostContract.hostType;
    el.rendererBridgeReadinessValue.textContent = state.renderer.health.bridgeReadiness;
    el.rendererHostReadinessValue.textContent = state.renderer.health.hostReadiness;
    el.rendererHeartbeatValue.textContent = state.renderer.health.heartbeatEnabled
      ? "Running / " + String(state.renderer.health.heartbeatIntervalMs) + "ms / fail " + String(state.renderer.health.failureCount)
      : state.renderer.health.heartbeatStatus;
    el.rendererRecoveryPolicyValue.textContent = recoveryPolicyLabel() + " / " + (state.renderer.health.lastRecoveryAction || "Not triggered");
    el.rendererPreflightStatusValue.textContent = state.renderer.preflight.overall + (state.renderer.preflight.checkedAt ? " / checked" : "");
    el.rendererPreflightIssuesValue.textContent = String(state.renderer.preflight.blockingIssues) + " blocking / "
      + String(state.renderer.preflight.missingMethods.length + state.renderer.preflight.missingArtifacts.length) + " missing";
    el.rendererAdmissionStatusValue.textContent = state.renderer.admission.lastDecision;
    el.rendererAdmissionActionValue.textContent = state.renderer.admission.lastAction + (state.renderer.admission.lastCheckedAt ? " / checked" : "");
    el.rendererActionPolicyValue.textContent = state.renderer.actionPolicy.summary + (state.renderer.actionPolicy.lastEvaluatedAt ? " / checked" : "");
    el.rendererProfileValue.textContent = state.renderer.profile.summary + " / " + state.renderer.profile.resolvedPreset;
    el.rendererTemplatePresetValue.textContent = bridgePreset.config.label + " / " + driverPreset.config.label;
    el.btnToggleHeartbeat.textContent = state.renderer.health.heartbeatEnabled ? "Stop Heartbeat" : "Start Heartbeat";
    el.pollingStateValue.textContent = state.polling.running ? "Running / " + state.polling.mode : "Idle / " + state.polling.mode;
    el.pollingRouteLengthValue.textContent = String(state.polling.route.length);
    el.pollingCycleValue.textContent = String(state.polling.cycleCount);
    const currentTile = currentPollingRouteTileIndex();
    el.pollingCurrentValue.textContent = currentTile === null
      ? "Not started"
      : "Tile " + String(currentTile + 1) + " / " + Math.round(pollingProgress() * 100) + "%";
  }

  function renderPreviewStage() {
    el.previewStage.innerHTML = "";
    el.previewStage.style.setProperty("--cols", String(layoutColumns()));
    el.previewStage.classList.toggle("fullscreen", state.fullscreenTileIndex !== null);
    const tiles = state.fullscreenTileIndex === null ? state.tiles : [state.tiles[state.fullscreenTileIndex]];
    tiles.forEach(function (tile) {
      const card = document.createElement("div");
      card.className = "tile";
      const isPollingTarget = currentPollingRouteTileIndex() === tile.tileIndex;
      const routePosition = state.polling.route.indexOf(tile.tileIndex);
      if (!tile.cameraIndexCode) {
        card.classList.add("empty");
      }
      if (tile.tileIndex === state.selectedTileIndex) {
        card.classList.add("selected");
      }
      if (isPollingTarget) {
        card.classList.add("polling");
      }
      const progress = isPollingTarget ? Math.round(pollingProgress() * 100) : 0;
      const statusLabel = tile.status === "ready" ? "Live preview ready" : tile.status === "bound" ? "Bound / awaiting URL" : "Unbound tile";
      const rendererStatus = tile.rendererAttached ? (tile.rendererKind || state.renderer.kind) : "detached";
      const rendererDisplay = tile.rendererDisplayUrl || tile.previewUrl || "Resolve preview URL to attach renderer";
      card.innerHTML = [
        '<div class="tile-header">',
        '  <div>',
        '    <div class="tile-title">Local Preview Tile</div>',
        '    <div class="tile-camera">' + escapeHtml(tile.cameraName || "Unbound tile") + "</div>",
        "  </div>",
        '  <div class="tile-index">' + String(tile.tileIndex + 1) + "</div>",
        "</div>",
        '<div class="tile-screen ' + (tile.previewUrl ? "live" : "") + '" data-render-surface="' + String(tile.tileIndex) + '" id="tile-render-surface-' + String(tile.tileIndex) + '">',
        '  <div class="tile-screen-head">',
        '    <div class="tile-screen-label"><span class="dot"></span>' + escapeHtml(tile.previewUrl ? "mock stream online" : "stream pending") + "</div>",
        '    <div class="pill">' + escapeHtml(statusLabel) + "</div>",
        "  </div>",
        '  <div class="tile-stream-url">' + escapeHtml(rendererDisplay) + "</div>",
        '  <div class="tile-screen-foot">',
        '    <div class="tile-screen-route">' + escapeHtml(routePosition >= 0 ? "Route #" + String(routePosition + 1) : "Not in route") + '</div>',
        '    <div class="progress-track"><div class="progress-fill" style="width:' + String(progress) + '%"></div></div>',
        '    <div class="signal"><span></span><span></span><span></span><span></span></div>',
        "  </div>",
        "</div>",
        '<div class="tile-meta">',
        "  <div>Status: " + escapeHtml(tile.status) + "</div>",
        "  <div>Camera: <code>" + escapeHtml(tile.cameraIndexCode || "Not assigned") + "</code></div>",
        "  <div>Protocol: " + escapeHtml(tile.previewProtocol || el.protocol.value || "-") + "</div>",
        "  <div>Renderer: " + escapeHtml(rendererStatus) + "</div>",
        "  <div>Renderer Session: " + escapeHtml(tile.rendererSessionId || "-") + "</div>",
        "  <div>Surface: " + escapeHtml(tile.rendererSurfaceType || "-") + "</div>",
        "</div>",
        '<div class="tile-url">' + escapeHtml(tile.previewUrl || "Preview URL not resolved yet") + "</div>",
        '<div class="tile-actions">',
        '  <button data-action="select-tile" data-tile-index="' + String(tile.tileIndex) + '">Select</button>',
        '  <button class="secondary" data-action="use-current-input" data-tile-index="' + String(tile.tileIndex) + '">Use Current Camera</button>',
        '  <button class="secondary" data-action="resolve-tile" data-tile-index="' + String(tile.tileIndex) + '">Resolve URL</button>',
        "</div>"
      ].join("");
      el.previewStage.appendChild(card);
    });
  }

  function renderCameraTable() {
    const cameras = getCameraList();
    if (!cameras.length) {
      el.cameraTableBody.innerHTML = '<tr><td colspan="5">No camera list loaded yet.</td></tr>';
      return;
    }
    el.cameraTableBody.innerHTML = cameras.map(function (camera) {
      const code = camera.cameraIndexCode || "";
      const checked = state.selectedCameraCodes.indexOf(code) >= 0 ? ' checked="checked"' : "";
      return [
        "<tr>",
        '  <td><input type="checkbox" data-action="toggle-camera" data-camera-index-code="' + escapeHtml(code) + '"' + checked + " /></td>",
        "  <td>" + escapeHtml(camera.name || camera.cameraName || "-") + "</td>",
        '  <td><code>' + escapeHtml(code) + "</code></td>",
        "  <td>" + escapeHtml(camera.unitName || camera.regionName || camera.deviceIndexCode || "-") + "</td>",
        '  <td><div class="camera-actions">',
        '    <button data-action="bind-camera" data-camera-index-code="' + escapeHtml(code) + '">Bind To Selected Tile</button>',
        '    <button class="secondary" data-action="fill-camera" data-camera-index-code="' + escapeHtml(code) + '">Use As Current Input</button>',
        '    <button class="secondary" data-action="camera-preview" data-camera-index-code="' + escapeHtml(code) + '">Preview URL</button>',
        "  </div></td>",
        "</tr>"
      ].join("");
    }).join("");
  }

  function recursiveCollect(root, matcher) {
    const queue = [root];
    const visited = new Set();
    const result = [];
    while (queue.length) {
      const current = queue.shift();
      if (!current || typeof current !== "object" || visited.has(current)) {
        continue;
      }
      visited.add(current);
      if (matcher(current)) {
        result.push(current);
      }
      Object.keys(current).forEach(function (key) {
        const value = current[key];
        if (value && typeof value === "object") {
          queue.push(value);
        }
      });
    }
    return result;
  }

  function uniqueBy(items, getKey) {
    const seen = new Set();
    return items.filter(function (item) {
      const key = getKey(item);
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  function tvwallDlps() {
    return uniqueBy(recursiveCollect(state.tvwallResources, function (obj) {
      return obj.dlp_id !== undefined;
    }), function (item) {
      return "dlp:" + String(item.dlp_id);
    });
  }

  function tvwallMonitors() {
    return uniqueBy(recursiveCollect(state.tvwallResources, function (obj) {
      return obj.pos !== undefined;
    }), function (item) {
      return "monitor:" + String(item.pos);
    });
  }

  function tvwallWindows() {
    const items = [];
    recursiveCollect(state.tvwallResources, function (obj) {
      if (obj.wnd_uri || obj.floatwnd_id || obj.id) {
        items.push(obj);
      }
      return false;
    });
    recursiveCollect(state.tvwallWindows, function (obj) {
      if (obj.wnd_uri || obj.floatwnd_id || obj.id || obj.wnd_id) {
        items.push(obj);
      }
      return false;
    });
    return uniqueBy(items, function (item) {
      return "window:" + String(item.floatwnd_id || item.id || item.wnd_id || item.wnd_uri || "");
    });
  }

  function optionMarkup(items, valueOf, labelOf, selectedValue) {
    const rows = ['<option value="">--</option>'];
    items.forEach(function (item) {
      const value = String(valueOf(item));
      const selected = selectedValue && String(selectedValue) === value ? ' selected="selected"' : "";
      rows.push('<option value="' + escapeHtml(value) + '"' + selected + ">" + escapeHtml(labelOf(item)) + "</option>");
    });
    return rows.join("");
  }

  function renderTvwallSelectors() {
    const dlps = tvwallDlps();
    const monitors = tvwallMonitors();
    const windows = tvwallWindows();
    if (!state.selectedDlpId && dlps[0]) {
      state.selectedDlpId = String(dlps[0].dlp_id);
    }
    if (!state.selectedMonitorPos && monitors[0]) {
      state.selectedMonitorPos = String(monitors[0].pos);
    }
    if (!state.selectedFloatWindowId && windows[0]) {
      state.selectedFloatWindowId = String(windows[0].floatwnd_id || windows[0].id || windows[0].wnd_id || "");
      state.selectedWndUri = String(windows[0].wnd_uri || "");
    }
    el.tvwallDlpId.innerHTML = optionMarkup(dlps, function (item) {
      return item.dlp_id;
    }, function (item) {
      return "DLP " + String(item.dlp_id) + (item.tvwall_name ? " - " + item.tvwall_name : "");
    }, state.selectedDlpId);
    el.tvwallMonitorPos.innerHTML = optionMarkup(monitors, function (item) {
      return item.pos;
    }, function (item) {
      return "Pos " + String(item.pos) + (item.monitor_name ? " - " + item.monitor_name : "");
    }, state.selectedMonitorPos);
    el.tvwallFloatWindowId.innerHTML = optionMarkup(windows, function (item) {
      return item.floatwnd_id || item.id || item.wnd_id || "";
    }, function (item) {
      const id = item.floatwnd_id || item.id || item.wnd_id || "";
      return "Wnd " + String(id) + (item.wnd_uri ? " - " + item.wnd_uri.slice(0, 40) : "");
    }, state.selectedFloatWindowId);
    el.tvwallWndUri.value = state.selectedWndUri || "";
    el.tvwallSnapshot.textContent = pretty({
      runtimeMode: runtimeModeLabel(),
      dlpCount: dlps.length,
      monitorCount: monitors.length,
      windowCount: windows.length,
      selectedDlpId: state.selectedDlpId,
      selectedMonitorPos: state.selectedMonitorPos,
      selectedFloatWindowId: state.selectedFloatWindowId,
      selectedWndUri: state.selectedWndUri,
      mockTvwallState: state.mockTvwallState,
      lastResources: state.tvwallResources,
      lastScenes: state.tvwallScenes,
      lastWindows: state.tvwallWindows
    });
    el.runtimeSessionSnapshot.textContent = pretty(buildRuntimeSessionSnapshot());
    el.rendererDiagnosticsSnapshot.textContent = pretty(buildRendererDiagnosticsSnapshot());
    el.rendererAttachPlanSnapshot.textContent = pretty(buildRendererAttachPlan());
    el.rendererCommandSnapshot.textContent = pretty(buildRendererCommandSnapshot());
    el.rendererExecutionSnapshot.textContent = pretty(buildRendererExecutionSnapshot());
    el.rendererDriverSnapshot.textContent = pretty(buildRendererDriverSnapshot());
    el.rendererHostContractSnapshot.textContent = pretty(buildRendererHostContractSnapshot());
    el.rendererBridgeTemplateSnapshot.textContent = pretty(buildRendererBridgeTemplate());
    el.rendererDriverTemplateSnapshot.textContent = pretty(buildRendererDriverTemplate());
    el.rendererImplementationPackageSnapshot.textContent = pretty(buildRendererImplementationPackage());
    el.rendererHealthSnapshot.textContent = pretty(buildRendererHealthSnapshot());
    el.rendererHostPreflightSnapshot.textContent = pretty(buildRendererHostPreflightSnapshot());
    el.rendererAdmissionSnapshot.textContent = pretty(buildRendererAdmissionSnapshot());
    el.rendererActionPolicySnapshot.textContent = pretty(buildRendererActionPolicySnapshot());
    el.rendererProfileSnapshot.textContent = pretty(buildRendererProfileSnapshot());
    el.rendererTemplatePresetSnapshot.textContent = pretty(buildRendererTemplatePresetSnapshot());
  }

  async function loadTvwallResources() {
    state.tvwallResources = await callPlatformApi("/api/tvms/v1/tvwall/allResources", {});
    return state.tvwallResources;
  }

  async function loadTvwallScenes() {
    state.tvwallScenes = await callPlatformApi("/api/tvms/v1/tvwall/scenes", {});
    return state.tvwallScenes;
  }

  async function loadTvwallWindows() {
    const body = {};
    if (state.selectedDlpId) {
      body.dlp_id = Number(state.selectedDlpId);
    }
    state.tvwallWindows = await callPlatformApi("/api/tvms/v1/tvwall/wnds/get", body);
    return state.tvwallWindows;
  }

  function syncTvwallSelection() {
    state.selectedDlpId = el.tvwallDlpId.value;
    state.selectedMonitorPos = el.tvwallMonitorPos.value;
    state.selectedFloatWindowId = el.tvwallFloatWindowId.value;
    state.selectedWndUri = el.tvwallWndUri.value.trim();
  }

  function requiredNumber(value, label) {
    if (value === "" || value === null || value === undefined) {
      throw new Error(label + " is required");
    }
    const number = Number(value);
    if (Number.isNaN(number)) {
      throw new Error(label + " must be a number");
    }
    return number;
  }

  async function tvwallMonitorDivision(divNum) {
    syncTvwallSelection();
    return callPlatformApi("/api/tvms/v1/public/tvwall/monitor/division", {
      dlp_id: requiredNumber(state.selectedDlpId, "DLP ID"),
      monitor_pos: requiredNumber(state.selectedMonitorPos, "Monitor Pos"),
      div_num: divNum
    });
  }

  async function tvwallFloatDivision(divNum) {
    syncTvwallSelection();
    return callPlatformApi("/api/tvms/v1/public/tvwall/floatWnd/division", {
      dlp_id: requiredNumber(state.selectedDlpId, "DLP ID"),
      floatwnd_id: requiredNumber(state.selectedFloatWindowId, "Float Window ID"),
      div_num: divNum
    });
  }

  async function tvwallZoomIn(type) {
    syncTvwallSelection();
    return callPlatformApi("/api/tvms/v1/public/tvwall/floatWnd/zoomIn", {
      dlp_id: requiredNumber(state.selectedDlpId, "DLP ID"),
      floatwnd_id: requiredNumber(state.selectedFloatWindowId, "Float Window ID"),
      wnd_uri: state.selectedWndUri || "",
      type: type
    });
  }

  async function tvwallZoomOut() {
    syncTvwallSelection();
    return callPlatformApi("/api/tvms/v1/public/tvwall/floatWnd/zoomOut", {
      dlp_id: requiredNumber(state.selectedDlpId, "DLP ID"),
      floatwnd_id: requiredNumber(state.selectedFloatWindowId, "Float Window ID")
    });
  }

  function sleep(milliseconds) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, milliseconds);
    });
  }

  async function runReplaySequence() {
    if (!state.mockMode) {
      enableMockMode("replay-sequence");
    }
    log("warn", "Running offline replay sequence", {
      sequence: ["4-grid", "9-grid", "fullscreen selected", "back to grid", "12-grid"]
    });
    setLayout(4);
    state.selectedTileIndex = 0;
    bindFirstCameras();
    renderAll();
    await sleep(220);
    setLayout(9);
    state.selectedTileIndex = 4;
    bindFirstCameras();
    renderAll();
    await sleep(220);
    state.fullscreenTileIndex = state.selectedTileIndex;
    state.mockTvwallState.zoomMode = "full_screen";
    renderAll();
    await sleep(220);
    state.fullscreenTileIndex = null;
    state.mockTvwallState.zoomMode = "grid";
    renderAll();
    await sleep(220);
    setLayout(12);
    state.selectedTileIndex = 8;
    bindFirstCameras();
    await resolveBoundTiles();
    renderAll();
    log("ok", "Offline replay sequence completed", {
      finalLayout: state.layout,
      selectedTileIndex: state.selectedTileIndex,
      fullscreenTileIndex: state.fullscreenTileIndex
    });
  }

  async function runMinimalChain() {
    log("warn", "Running minimal preview chain");
    setTitle("running");
    if (state.mockMode) {
      await getLoginInfo();
      await getTickets();
      await getServiceInfo();
    } else if (state.bridgeAvailable) {
      await getLoginInfo();
      await getTickets();
    } else {
      log("warn", "Skipping container-only bridge calls in browser mode");
    }
    await listTreeCodes();
    await listCameras();
    bindFirstCameras();
    await resolveBoundTiles();
    log("ok", "Minimal preview chain completed");
    setTitle("success");
  }

  async function runFullChain() {
    await runMinimalChain();
    try {
      await loadTvwallResources();
      await loadTvwallScenes();
      await loadTvwallWindows();
      log("ok", "TV wall discovery completed");
    } catch (error) {
      log("warn", "TV wall discovery skipped or failed", String(error && error.message ? error.message : error));
    }
  }

  async function runOfflineDemo() {
    enableMockMode("offline-demo");
    await runFullChain();
    await runReplaySequence();
    seedPollingRoute();
    persistRuntimeSession("offline-demo");
  }

  async function withLog(label, fn) {
    try {
      const result = await fn();
      renderAll();
      return result;
    } catch (error) {
      setTitle("failed");
      log("err", label + " failed", String(error && error.message ? error.message : error));
      throw error;
    }
  }

  function bindEvents() {
    el.btnLogin.addEventListener("click", function () { withLog("GetLoginInfo", getLoginInfo); });
    el.btnTicket.addEventListener("click", function () { withLog("GetTickets", getTickets); });
    el.btnService.addEventListener("click", function () { withLog("GetServiceInfo", getServiceInfo); });
    el.btnRunAuthProbe.addEventListener("click", function () { withLog("Container auth probe", runContainerAuthProbe); });
    el.btnCopyAuthProbe.addEventListener("click", function () { withLog("Copy auth probe result", copyAuthProbeResult); });
    el.btnRunMinChain.addEventListener("click", function () { withLog("Minimal chain", runMinimalChain); });
    el.btnEnableMock.addEventListener("click", function () { enableMockMode("manual-toggle"); });
    el.btnDisableMock.addEventListener("click", function () { disableMockMode(); });
    el.btnRunLocalDemo.addEventListener("click", function () { withLog("Offline demo", runOfflineDemo); });
    el.btnAttachRenderers.addEventListener("click", function () { syncRendererInputsToState(); attachRenderersToReadyTiles(); persistRuntimeSession("attach-renderers"); });
    el.btnDetachRenderers.addEventListener("click", function () { detachAllRenderers(); persistRuntimeSession("detach-renderers"); });
    el.btnSaveSession.addEventListener("click", function () { persistRuntimeSession("manual-save"); writeStoredSettings(); });
    el.btnLoadSession.addEventListener("click", function () {
      try {
        loadRuntimeSessionSnapshot("manual-load");
      } catch (error) {
        log("err", "Load runtime session failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnResetSession.addEventListener("click", function () { resetRuntimeSessionSnapshot(); });
    el.btnRefreshDiagnostics.addEventListener("click", function () {
      renderAll();
      log("ok", "Renderer diagnostics refreshed", {
        rendererKind: state.renderer.kind,
        readyTiles: readyTileCount(),
        attachedTiles: attachedRendererCount()
      });
    });
    el.btnExportAttachPlan.addEventListener("click", function () { exportRendererAttachPlan(); });
    el.btnExportHostContract.addEventListener("click", function () { exportRendererHostContract(); });
    el.btnExportBridgeTemplate.addEventListener("click", function () { exportRendererBridgeTemplate(); });
    el.btnExportDriverTemplate.addEventListener("click", function () { exportRendererDriverTemplate(); });
    el.btnExportImplementationPackage.addEventListener("click", function () { exportRendererImplementationPackage(); });
    el.btnExportRuntimeJson.addEventListener("click", function () { exportRuntimeBundle(); });
    el.btnImportRuntimeJson.addEventListener("click", function () {
      try {
        importRuntimeBundle("manual-import");
      } catch (error) {
        log("err", "Import runtime JSON failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnPreviewSelectedCommand.addEventListener("click", function () {
      try {
        previewSelectedRendererCommand();
      } catch (error) {
        log("err", "Preview selected renderer command failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnPreviewSweepCommands.addEventListener("click", function () {
      try {
        previewSweepRendererCommands();
      } catch (error) {
        log("err", "Preview renderer command sweep failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnInitDriver.addEventListener("click", function () {
      try {
        initRendererDriver("manual-init");
      } catch (error) {
        log("err", "Init renderer driver failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnDisposeDriver.addEventListener("click", function () {
      try {
        disposeRendererDriver("manual-dispose");
      } catch (error) {
        log("err", "Dispose renderer driver failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnApplyProfileDefaults.addEventListener("click", function () {
      try {
        applyRendererProfileDefaults("manual-profile-defaults");
      } catch (error) {
        log("err", "Apply renderer profile defaults failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnRunHealthCheck.addEventListener("click", function () {
      try {
        syncRendererInputsToState();
        runRendererHealthCheck("manual-check");
      } catch (error) {
        log("err", "Renderer health check failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnToggleHeartbeat.addEventListener("click", function () {
      try {
        syncRendererInputsToState();
        toggleRendererHeartbeat();
      } catch (error) {
        log("err", "Toggle renderer heartbeat failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnRunPreflight.addEventListener("click", function () {
      try {
        syncRendererInputsToState();
        runRendererHostPreflight("manual-preflight");
      } catch (error) {
        log("err", "Renderer host preflight failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnExportPreflight.addEventListener("click", function () {
      try {
        syncRendererInputsToState();
        exportRendererHostPreflight();
      } catch (error) {
        log("err", "Export renderer host preflight failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnTriggerRecovery.addEventListener("click", function () {
      try {
        syncRendererInputsToState();
        recoverRendererDriver("manual-recovery");
      } catch (error) {
        log("err", "Renderer recovery failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnRunCommandQueue.addEventListener("click", function () {
      try {
        runPendingRendererCommands();
      } catch (error) {
        log("err", "Run renderer command queue failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnReplayCommandHistory.addEventListener("click", function () {
      try {
        replayRecentRendererHistory();
      } catch (error) {
        log("err", "Replay renderer command history failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnClearCommandQueue.addEventListener("click", function () { clearRendererCommandQueue("manual-clear"); });
    el.btnSeedPolling.addEventListener("click", function () {
      try {
        seedPollingRoute();
        persistRuntimeSession("seed-route");
      } catch (error) {
        log("err", "Seed polling route failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnStartPolling.addEventListener("click", function () {
      try {
        startPollingRuntime();
      } catch (error) {
        log("err", "Start polling failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnStopPolling.addEventListener("click", function () { stopPollingRuntime("manual-stop"); });
    el.btnStepPolling.addEventListener("click", function () {
      try {
        advancePollingRoute("manual-step");
      } catch (error) {
        log("err", "Polling step failed", String(error && error.message ? error.message : error));
      }
    });
    el.btnSavePrefs.addEventListener("click", function () { syncPollingInputsToState(); writeStoredSettings(); });
    el.btnTreeCodes.addEventListener("click", function () { withLog("Tree codes", listTreeCodes); });
    el.btnRegions.addEventListener("click", function () { withLog("Regions", listRegions); });
    el.btnCameras.addEventListener("click", function () { withLog("Cameras", listCameras); });
    el.btnBindFirst.addEventListener("click", function () { try { bindFirstCameras(); renderAll(); } catch (error) { log("err", "Bind first cameras failed", String(error.message || error)); } });
    el.btnPreviewUrl.addEventListener("click", function () { withLog("Preview URL", getPreviewUrl); });
    el.btnResolveBound.addEventListener("click", function () { withLog("Resolve bound tiles", resolveBoundTiles); });
    el.btnClearWall.addEventListener("click", function () { clearWall(); });
    el.btnLayout4.addEventListener("click", function () { setLayout(4); });
    el.btnLayout9.addEventListener("click", function () { setLayout(9); });
    el.btnLayout12.addEventListener("click", function () { setLayout(12); });
    el.btnFullscreenSelected.addEventListener("click", function () {
      const admission = guardRendererAdmission("fullscreen-select", { silent: true, persist: false });
      if (!admission.allowed) {
        log("err", "Fullscreen select admission blocked", {
          reasons: admission.blockingReasons
        });
        return;
      }
      state.fullscreenTileIndex = state.selectedTileIndex;
      renderAll();
      persistRuntimeSession("fullscreen-selected");
    });
    el.btnExitFullscreen.addEventListener("click", function () {
      state.fullscreenTileIndex = null;
      renderAll();
      persistRuntimeSession("exit-fullscreen");
    });
    el.btnRunFullChain.addEventListener("click", function () { withLog("Full chain", runFullChain); });
    el.btnRunReplaySequence.addEventListener("click", function () { withLog("Replay sequence", runReplaySequence); });
    el.btnClearLog.addEventListener("click", function () { el.terminal.textContent = ""; });
    el.btnTvwallResources.addEventListener("click", function () { withLog("TV wall resources", loadTvwallResources); });
    el.btnTvwallScenes.addEventListener("click", function () { withLog("TV wall scenes", loadTvwallScenes); });
    el.btnTvwallWnds.addEventListener("click", function () { withLog("TV wall windows", loadTvwallWindows); });
    el.btnTvwallDiv4.addEventListener("click", function () { withLog("TV wall monitor divide 4", function () { return tvwallMonitorDivision(4); }); });
    el.btnTvwallDiv9.addEventListener("click", function () { withLog("TV wall monitor divide 9", function () { return tvwallMonitorDivision(9); }); });
    el.btnTvwallDiv12.addEventListener("click", function () { withLog("TV wall monitor divide 12", function () { return tvwallMonitorDivision(12); }); });
    el.btnTvwallFloatDiv4.addEventListener("click", function () { withLog("TV wall float divide 4", function () { return tvwallFloatDivision(4); }); });
    el.btnTvwallFloatDiv9.addEventListener("click", function () { withLog("TV wall float divide 9", function () { return tvwallFloatDivision(9); }); });
    el.btnTvwallFloatDiv12.addEventListener("click", function () { withLog("TV wall float divide 12", function () { return tvwallFloatDivision(12); }); });
    el.btnTvwallZoomNormal.addEventListener("click", function () { withLog("TV wall zoom normal", function () { return tvwallZoomIn("normal"); }); });
    el.btnTvwallZoomFull.addEventListener("click", function () { withLog("TV wall zoom fullscreen", function () { return tvwallZoomIn("full_screen"); }); });
    el.btnTvwallZoomOut.addEventListener("click", function () { withLog("TV wall zoom out", tvwallZoomOut); });

    el.previewStage.addEventListener("click", function (event) {
      const target = event.target.closest("[data-action]");
      if (!target) {
        return;
      }
      const action = target.getAttribute("data-action");
      const tileIndex = Number(target.getAttribute("data-tile-index"));
      if (action === "select-tile") {
        state.selectedTileIndex = tileIndex;
        renderAll();
        return;
      }
      if (action === "use-current-input") {
        const code = el.cameraIndexCode.value.trim();
        if (!code) {
          log("err", "Current camera input is empty");
          return;
        }
        assignCameraToTile(tileIndex, getCameraByIndexCode(code) || { cameraIndexCode: code, name: code });
        renderAll();
        return;
      }
      if (action === "resolve-tile") {
        const tile = state.tiles[tileIndex];
        if (!tile || !tile.cameraIndexCode) {
          log("err", "Tile has no bound camera", { tileIndex: tileIndex });
          return;
        }
        withLog("Resolve tile preview", async function () {
          const result = await getPreviewUrlByCamera(tile.cameraIndexCode);
          const url = ((result || {}).data || {}).url || "";
          state.tiles[tileIndex].previewUrl = url;
          state.tiles[tileIndex].previewProtocol = el.protocol.value;
          state.tiles[tileIndex].status = url ? "ready" : "bound";
        });
      }
    });

    el.cameraTableBody.addEventListener("click", function (event) {
      const target = event.target.closest("[data-action]");
      if (!target) {
        return;
      }
      const action = target.getAttribute("data-action");
      const code = target.getAttribute("data-camera-index-code");
      if (action === "bind-camera") {
        assignCameraToTile(state.selectedTileIndex, getCameraByIndexCode(code) || { cameraIndexCode: code, name: code });
        renderAll();
        return;
      }
      if (action === "fill-camera") {
        el.cameraIndexCode.value = code || "";
        renderAll();
        return;
      }
      if (action === "camera-preview") {
        el.cameraIndexCode.value = code || "";
        withLog("Camera preview URL", function () { return getPreviewUrlByCamera(code); });
      }
    });

    el.cameraTableBody.addEventListener("change", function (event) {
      const target = event.target.closest("[data-action='toggle-camera']");
      if (!target) {
        return;
      }
      toggleCameraSelection(target.getAttribute("data-camera-index-code"), !!target.checked);
    });

    el.tvwallDlpId.addEventListener("change", function () { syncTvwallSelection(); renderAll(); });
    el.tvwallMonitorPos.addEventListener("change", function () { syncTvwallSelection(); renderAll(); });
    el.tvwallFloatWindowId.addEventListener("change", function () {
      syncTvwallSelection();
      const matched = tvwallWindows().find(function (item) {
        return String(item.floatwnd_id || item.id || item.wnd_id || "") === state.selectedFloatWindowId;
      });
      if (matched) {
        state.selectedWndUri = String(matched.wnd_uri || "");
      }
      renderAll();
    });
    el.tvwallWndUri.addEventListener("change", function () { syncTvwallSelection(); renderAll(); });
    el.rendererKind.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererAutoAttach.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererDriverMode.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererProfilePreset.addEventListener("change", function () { syncRendererInputsToState(); evaluateRendererActionPolicy("profile-change", { silent: true, persist: false }); renderAll(); persistRuntimeSession(); });
    el.rendererBridgeTemplatePreset.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererDriverTemplatePreset.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererRecoveryPolicy.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.rendererHeartbeatMs.addEventListener("change", function () { syncRendererInputsToState(); renderAll(); persistRuntimeSession(); });
    el.pollingMode.addEventListener("change", function () { syncPollingInputsToState(); renderAll(); });
    el.pollingDwellMs.addEventListener("change", function () { syncPollingInputsToState(); renderAll(); });
    window.addEventListener("beforeunload", function () {
      stopPollingRuntime("page-unload");
      stopRendererHeartbeat("page-unload", { silent: true, persist: false });
    });
  }

  async function maybeAutorun() {
    if (!shouldAutorun() || state.autorunStarted) {
      return;
    }
    state.autorunStarted = true;
    log("warn", "Autorun enabled via query string", {
      bridgeAvailable: state.bridgeAvailable,
      href: window.location.href
    });
    try {
      if (state.mockMode) {
        await runOfflineDemo();
      } else if (state.bridgeAvailable) {
        await runContainerAuthProbe();
      } else {
        await runMinimalChain();
      }
    } catch (error) {
      setTitle("failed");
      log("err", "Autorun failed", String(error && error.message ? error.message : error));
    }
  }

  function renderAll() {
    renderStatus();
    renderPreviewStage();
    renderCameraTable();
    renderTvwallSelectors();
  }

  applyStoredSettings();
  applyStoredAuthProbeSnapshot();
  el.pollingMode.value = state.polling.mode;
  el.pollingDwellMs.value = String(state.polling.dwellMs);
  el.rendererKind.value = state.renderer.kind;
  el.rendererAutoAttach.value = state.renderer.autoAttach ? "1" : "0";
  el.rendererDriverMode.value = state.renderer.driverMode;
  el.rendererProfilePreset.value = state.renderer.profile.preset;
  el.rendererBridgeTemplatePreset.value = state.renderer.templatePresets.bridgePreset;
  el.rendererDriverTemplatePreset.value = state.renderer.templatePresets.driverPreset;
  el.rendererRecoveryPolicy.value = state.renderer.health.recoveryPolicy;
  el.rendererHeartbeatMs.value = String(state.renderer.health.heartbeatIntervalMs);
  syncRendererInputsToState();
  syncTiles(state.layout);
  if (shouldUseMock()) {
    enableMockMode("query-string");
  }
  bindEvents();
  renderAll();
  const existingSnapshot = readRuntimeSessionSnapshot();
  if (existingSnapshot) {
    el.runtimeSessionSnapshot.textContent = pretty(existingSnapshot);
  }
  setTitle(state.mockMode ? "ready-mock" : isBridgeRuntime() ? "ready-container" : "ready-browser");
  log("ok", "POC shell ready", {
    bridgeAvailable: state.bridgeAvailable,
    mockMode: state.mockMode,
    recommendedChain: [
      "GetLoginInfo",
      "GetTickets",
      "/api/resource/v1/cameras",
      "/api/video/v1/cameras/previewURLs",
      "/api/tvms/v1/tvwall/allResources",
      "/api/tvms/v1/public/tvwall/monitor/division",
      "/api/tvms/v1/public/tvwall/floatWnd/zoomIn",
      "/api/tvms/v1/public/tvwall/floatWnd/zoomOut"
    ]
  });
  setTimeout(function () { maybeAutorun(); }, 800);
})();
