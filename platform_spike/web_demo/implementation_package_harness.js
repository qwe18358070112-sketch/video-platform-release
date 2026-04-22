const el = {
  packageBaseUrl: document.getElementById("package-base-url"),
  cameraIndexCode: document.getElementById("camera-index-code"),
  previewUrl: document.getElementById("preview-url"),
  btnLoadPackage: document.getElementById("btn-load-package"),
  btnResetRuntime: document.getElementById("btn-reset-runtime"),
  btnRunInit: document.getElementById("btn-run-init"),
  btnRunAttach: document.getElementById("btn-run-attach"),
  btnRunRefresh: document.getElementById("btn-run-refresh"),
  btnRunDetach: document.getElementById("btn-run-detach"),
  btnRunDispose: document.getElementById("btn-run-dispose"),
  btnRunAll: document.getElementById("btn-run-all"),
  btnExportReport: document.getElementById("btn-export-report"),
  loadState: document.getElementById("load-state"),
  runtimeId: document.getElementById("runtime-id"),
  lastAction: document.getElementById("last-action"),
  bridgeKeys: document.getElementById("bridge-keys"),
  driverKeys: document.getElementById("driver-keys"),
  healthKeys: document.getElementById("health-keys"),
  hostBridgeBuffer: document.getElementById("host-bridge-buffer"),
  previewSurfaceStatus: document.getElementById("preview-surface-status"),
  manifestSnapshot: document.getElementById("manifest-snapshot"),
  wiringSnapshot: document.getElementById("wiring-snapshot"),
  lifecycleSnapshot: document.getElementById("lifecycle-snapshot"),
  reportSnapshot: document.getElementById("report-snapshot"),
  terminal: document.getElementById("terminal"),
};

const state = {
  packageBaseUrl: el.packageBaseUrl.value,
  manifest: null,
  wiring: null,
  hostBridge: null,
  hostBridgeCalls: [],
  runtimeId: "",
  runtimeContext: null,
  lifecycleResults: [],
  lastAction: "None",
  report: null,
};

const query = new URLSearchParams(window.location.search);

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function log(kind, label, payload) {
  const line = document.createElement("div");
  line.textContent = "[" + new Date().toLocaleTimeString("zh-CN", { hour12: false }) + "] " + label +
    (payload === undefined ? "" : "\n" + pretty(payload));
  line.style.whiteSpace = "pre-wrap";
  line.style.marginBottom = "10px";
  line.style.color = kind === "err" ? "#ffb4b4" : kind === "warn" ? "#ffd48f" : "#d9e4ff";
  if (el.terminal.textContent === "No events yet.") {
    el.terminal.textContent = "";
  }
  el.terminal.appendChild(line);
  el.terminal.scrollTop = el.terminal.scrollHeight;
}

function buildUrl(relativePath) {
  const base = state.packageBaseUrl.trim() || "./";
  return new URL(relativePath, new URL(base, window.location.href)).href;
}

async function fetchJson(relativePath) {
  const response = await fetch(buildUrl(relativePath), { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch " + relativePath + " (" + response.status + ")");
  }
  return response.json();
}

function buildPayload() {
  return {
    tileIndex: 0,
    tileOrdinal: 1,
    mountSelector: "#preview-surface",
    previewUrl: el.previewUrl.value.trim(),
    cameraIndexCode: el.cameraIndexCode.value.trim(),
  };
}

function buildContext() {
  return {
    runtimePrefix: (state.manifest && state.manifest.runtimePrefix) || "drv-runtime",
    runtimeId: state.runtimeId || undefined,
    mountSelector: "#preview-surface",
    previewUrl: el.previewUrl.value.trim(),
    cameraIndexCode: el.cameraIndexCode.value.trim(),
  };
}

function buildHostBridge(bridgeModule) {
  const calls = [];
  const stub = {};
  Object.keys(bridgeModule || {}).forEach(function (methodName) {
    if (typeof bridgeModule[methodName] !== "function") {
      return;
    }
    stub[methodName] = async function (payload) {
      const callPayload = payload || {};
      const value = await bridgeModule[methodName](callPayload);
      const call = {
        at: new Date().toISOString(),
        methodName: methodName,
        payload: callPayload,
        value: value,
      };
      calls.push(call);
      state.hostBridgeCalls = calls.slice(-40);
      render();
      return value;
    };
  });
  state.hostBridgeCalls = calls;
  return stub;
}

async function loadPackage() {
  state.packageBaseUrl = el.packageBaseUrl.value.trim();
  state.manifest = await fetchJson("manifest.json");
  const wiringModule = await import(buildUrl("runtime/wiring.js"));
  const wiring = wiringModule.createRuntimeWiring();
  state.wiring = wiring;
  state.hostBridge = buildHostBridge(wiring.bridge);
  state.runtimeId = "";
  state.runtimeContext = null;
  state.lifecycleResults = [];
  state.lastAction = "Package loaded";
  state.report = null;
  render();
  log("ok", "Implementation package loaded", {
    packageBaseUrl: state.packageBaseUrl,
    bridgeKeys: Object.keys(wiring.bridge || {}),
    driverKeys: Object.keys(wiring.driver || {}),
    healthKeys: Object.keys(wiring.health || {}),
  });
}

async function runLifecycleAction(action) {
  if (!state.wiring) {
    throw new Error("Package is not loaded");
  }
  const driver = state.wiring.driver || {};
  if (typeof driver[action] !== "function") {
    throw new Error("Driver action is not available: " + action);
  }

  const payload = buildPayload();
  let result;
  if (action === "init") {
    result = await driver.init(buildContext(), state.hostBridge);
    state.runtimeId = result && result.runtimeId ? result.runtimeId : "";
    state.runtimeContext = Object.assign({}, buildContext(), state.runtimeId ? { runtimeId: state.runtimeId } : {});
  } else if (action === "dispose") {
    result = await driver.dispose(state.runtimeContext || buildContext(), state.hostBridge);
    state.runtimeId = "";
    state.runtimeContext = null;
  } else {
    const ctx = state.runtimeContext || buildContext();
    result = await driver[action](ctx, payload, state.hostBridge);
  }

  state.lastAction = action;
  state.lifecycleResults.push({
    action: action,
    at: new Date().toISOString(),
    result: result,
  });
  if (state.lifecycleResults.length > 24) {
    state.lifecycleResults = state.lifecycleResults.slice(-24);
  }
  render();
  log("ok", "Lifecycle action completed", { action: action, result: result });
  return result;
}

async function runFullLifecycle() {
  const actions = ["init", "attach", "refresh", "detach", "dispose"];
  for (const action of actions) {
    await runLifecycleAction(action);
  }
}

function buildHarnessReport() {
  return {
    exportedAt: new Date().toISOString(),
    packageBaseUrl: state.packageBaseUrl,
    manifest: state.manifest,
    wiring: state.wiring ? {
      bridgeKeys: Object.keys(state.wiring.bridge || {}),
      driverKeys: Object.keys(state.wiring.driver || {}),
      healthKeys: Object.keys(state.wiring.health || {}),
    } : null,
    runtimeId: state.runtimeId || "",
    hostBridgeCalls: state.hostBridgeCalls.slice(),
    lifecycleResults: state.lifecycleResults.slice(),
  };
}

function exportReport() {
  state.report = buildHarnessReport();
  render();
  log("ok", "Harness report exported", {
    lifecycleCount: state.report.lifecycleResults.length,
    hostBridgeCalls: state.report.hostBridgeCalls.length,
  });
}

function resetRuntime() {
  state.runtimeId = "";
  state.runtimeContext = null;
  state.lifecycleResults = [];
  state.hostBridgeCalls = [];
  state.hostBridge = state.wiring ? buildHostBridge(state.wiring.bridge) : null;
  state.lastAction = "Runtime reset";
  state.report = null;
  render();
  log("warn", "Harness runtime reset");
}

function render() {
  el.loadState.textContent = state.wiring ? "Loaded" : "Not loaded";
  el.runtimeId.textContent = state.runtimeId || "None";
  el.lastAction.textContent = state.lastAction;
  el.bridgeKeys.textContent = state.wiring ? String(Object.keys(state.wiring.bridge || {}).length) : "0";
  el.driverKeys.textContent = state.wiring ? String(Object.keys(state.wiring.driver || {}).length) : "0";
  el.healthKeys.textContent = state.wiring ? String(Object.keys(state.wiring.health || {}).length) : "0";
  el.hostBridgeBuffer.value = state.hostBridgeCalls.length ? pretty(state.hostBridgeCalls) : "";
  el.previewSurfaceStatus.textContent = state.runtimeId
    ? "Runtime ready: " + state.runtimeId
    : state.wiring
      ? "Package loaded, waiting for lifecycle action."
      : "Waiting for package load.";
  el.manifestSnapshot.textContent = state.manifest ? pretty(state.manifest) : "No manifest loaded yet.";
  el.wiringSnapshot.textContent = state.wiring
    ? pretty({
        bridgeKeys: Object.keys(state.wiring.bridge || {}),
        driverKeys: Object.keys(state.wiring.driver || {}),
        healthKeys: Object.keys(state.wiring.health || {}),
      })
    : "No runtime wiring loaded yet.";
  el.lifecycleSnapshot.textContent = state.lifecycleResults.length ? pretty(state.lifecycleResults) : "No lifecycle results yet.";
  el.reportSnapshot.textContent = state.report ? pretty(state.report) : "No harness report yet.";
}

el.btnLoadPackage.addEventListener("click", function () {
  loadPackage().catch(function (error) {
    log("err", "Loading implementation package failed", String(error && error.message ? error.message : error));
  });
});
el.btnResetRuntime.addEventListener("click", resetRuntime);
el.btnRunInit.addEventListener("click", function () { runLifecycleAction("init").catch(function (error) { log("err", "Init failed", String(error && error.message ? error.message : error)); }); });
el.btnRunAttach.addEventListener("click", function () { runLifecycleAction("attach").catch(function (error) { log("err", "Attach failed", String(error && error.message ? error.message : error)); }); });
el.btnRunRefresh.addEventListener("click", function () { runLifecycleAction("refresh").catch(function (error) { log("err", "Refresh failed", String(error && error.message ? error.message : error)); }); });
el.btnRunDetach.addEventListener("click", function () { runLifecycleAction("detach").catch(function (error) { log("err", "Detach failed", String(error && error.message ? error.message : error)); }); });
el.btnRunDispose.addEventListener("click", function () { runLifecycleAction("dispose").catch(function (error) { log("err", "Dispose failed", String(error && error.message ? error.message : error)); }); });
el.btnRunAll.addEventListener("click", function () { runFullLifecycle().catch(function (error) { log("err", "Full lifecycle failed", String(error && error.message ? error.message : error)); }); });
el.btnExportReport.addEventListener("click", exportReport);

render();

async function autoRunFromQuery() {
  if (query.get("autoload") !== "1") {
    return;
  }
  try {
    await loadPackage();
    const autorun = query.get("autorun");
    if (autorun === "full") {
      await runFullLifecycle();
      exportReport();
    } else if (autorun && ["init", "attach", "refresh", "detach", "dispose"].includes(autorun)) {
      await runLifecycleAction(autorun);
      exportReport();
    }
  } catch (error) {
    log("err", "Harness autorun failed", String(error && error.message ? error.message : error));
  }
}

autoRunFromQuery();
