const REQUIRED_BRIDGE_METHODS = [
  "launchLocalService",
  "createPluginWindow",
  "invokePreview",
  "stopPreview",
  "disposePluginWindow"
];
const ATTACH_BRIDGE_METHODS = [
  "launchLocalService",
  "createPluginWindow",
  "invokePreview"
];
const DETACH_BRIDGE_METHODS = [
  "stopPreview"
];
const DISPOSE_BRIDGE_METHODS = [
  "disposePluginWindow"
];

function buildResult(action, extra) {
  return Object.assign({ action: action, ok: true, at: new Date().toISOString() }, extra || {});
}

async function callBridge(hostBridge, methodName, payload) {
  if (!hostBridge || typeof hostBridge[methodName] !== 'function') {
    return buildResult('bridge-skip', { methodName: methodName, skipped: true, payload: payload || null });
  }
  const value = await hostBridge[methodName](payload || {});
  return buildResult('bridge-call', { methodName: methodName, value: value });
}

export async function init(ctx, hostBridge) {
  const runtimeId = String((ctx && ctx.runtimePrefix) || "drv-plugin") + '-' + Date.now();
  const bootstrap = REQUIRED_BRIDGE_METHODS.length ? await callBridge(hostBridge, REQUIRED_BRIDGE_METHODS[0], Object.assign({}, ctx || {}, { runtimeId: runtimeId })) : null;
  return buildResult('init', { runtimeId: runtimeId, bootstrap: bootstrap, steps: ["prepare runtime context", "validate host bridge", "return runtime id"] });
}

export async function attach(ctx, payload, hostBridge) {
  const calls = [];
  for (const methodName of ATTACH_BRIDGE_METHODS) {
    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));
  }
  const sessionId = String((ctx && ctx.runtimeId) || "drv-plugin") + '-session-' + String((payload && payload.tileIndex) || 0);
  return buildResult('attach', { sessionId: sessionId, calls: calls, payload: payload || null, steps: ["initialize plugin runtime", "bind plugin container", "request preview session", "cache session descriptor"] });
}

export async function refresh(ctx, payload, hostBridge) {
  const methodName = ATTACH_BRIDGE_METHODS.length > 1 ? ATTACH_BRIDGE_METHODS[ATTACH_BRIDGE_METHODS.length - 1] : ATTACH_BRIDGE_METHODS[0];
  const refreshResult = methodName ? await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { refresh: true })) : null;
  return buildResult('refresh', { payload: payload || null, refreshResult: refreshResult, steps: ["reuse session", "refresh preview source", "confirm renderer health"] });
}

export async function detach(ctx, payload, hostBridge) {
  const calls = [];
  for (const methodName of DETACH_BRIDGE_METHODS) {
    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));
  }
  return buildResult('detach', { calls: calls, payload: payload || null, steps: ["stop preview or close stream", "release tile session", "keep runtime alive if needed"] });
}

export async function dispose(ctx, hostBridge) {
  const calls = [];
  for (const methodName of DISPOSE_BRIDGE_METHODS) {
    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));
  }
  return buildResult('dispose', { calls: calls, steps: ["drain queue", "dispose host resources", "release runtime context"] });
}