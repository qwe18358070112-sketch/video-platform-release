(function () {
  const state = {
    bridgeAvailable: typeof window !== "undefined" && typeof window.cefQuery === "function",
    loginInfo: null,
    ticketInfo: null,
    serviceInfo: null,
    lastCameraList: null,
    lastPreviewUrl: null,
    autorunStarted: false
  };

  const el = {
    bridgeMode: document.getElementById("bridge-mode"),
    ticketValue: document.getElementById("ticket-value"),
    cameraValue: document.getElementById("camera-value"),
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
    terminal: document.getElementById("terminal"),
    btnLogin: document.getElementById("btn-login"),
    btnTicket: document.getElementById("btn-ticket"),
    btnService: document.getElementById("btn-service"),
    btnClearState: document.getElementById("btn-clear-state"),
    btnTreeCodes: document.getElementById("btn-tree-codes"),
    btnRegions: document.getElementById("btn-regions"),
    btnCameras: document.getElementById("btn-cameras"),
    btnPreviewUrl: document.getElementById("btn-preview-url"),
    btnFillFromResponse: document.getElementById("btn-fill-from-response"),
    btnRunFullChain: document.getElementById("btn-run-full-chain"),
    btnClearLog: document.getElementById("btn-clear-log")
  };

  function setStatus() {
    el.bridgeMode.textContent = state.bridgeAvailable ? "webcontainer bridge detected" : "browser mode only";
    el.ticketValue.textContent = extractTicket(state.ticketInfo) || "Not loaded";
    el.cameraValue.textContent = el.cameraIndexCode.value || "Not selected";
  }

  function getSearchParam(name) {
    const search = new URLSearchParams(window.location.search || "");
    return search.get(name);
  }

  function shouldAutorun() {
    return getSearchParam("autorun") === "1";
  }

  function setTitle(status) {
    document.title = "Platform Spike Probe - " + status;
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

  function normalizeBaseUrl() {
    return (el.platformBaseUrl.value || "").trim().replace(/\/+$/, "");
  }

  function normalizeToken() {
    return (el.platformToken.value || "").trim() || extractTicket(state.ticketInfo);
  }

  function invokeCef(requestObject) {
    return new Promise((resolve, reject) => {
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
    const request = { request: "GetLoginInfo" };
    log("ok", "Container request: GetLoginInfo", request);
    const result = await invokeCef(request);
    state.loginInfo = result;
    log("ok", "Container response: GetLoginInfo", result);
    return result;
  }

  async function getTickets() {
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
    setStatus();
    return result;
  }

  async function getServiceInfo() {
    const result = await callContainerMethod("getServiceInfoByType", {
      serviceType: el.serviceType.value.trim(),
      componentId: el.componentId.value.trim()
    });
    state.serviceInfo = result;
    return result;
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
      headers: {
        "Content-Type": "application/json"
      },
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
    const headers = {
      "Content-Type": "application/json"
    };
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
    const baseUrl = normalizeBaseUrl();
    if (!baseUrl && state.bridgeAvailable) {
      return proxyRequest({
        method: "POST",
        url: path,
        heads: buildProxyHeaders(),
        body: body
      });
    }
    if (!baseUrl) {
      throw new Error("Platform Base URL is required in browser mode");
    }
    return directRequest({
      method: "POST",
      url: baseUrl + path,
      body: body
    });
  }

  function buildProxyHeaders() {
    const headers = {
      "Content-Type": "application/json"
    };
    const token = normalizeToken();
    if (token) {
      headers.Token = token;
    }
    return headers;
  }

  async function listTreeCodes() {
    return callPlatformApi("/api/resource/v1/unit/getAllTreeCode", {});
  }

  async function listRegions() {
    return callPlatformApi("/api/resource/v1/regions", {
      pageNo: 1,
      pageSize: Number(el.regionPageSize.value || 50),
      treeCode: el.treeCode.value.trim() || "0"
    });
  }

  async function listCameras() {
    const result = await callPlatformApi("/api/resource/v1/cameras", {
      pageNo: Number(el.cameraPageNo.value || 1),
      pageSize: Number(el.cameraPageSize.value || 20),
      treeCode: el.treeCode.value.trim() || "0"
    });
    state.lastCameraList = result;
    return result;
  }

  async function getPreviewUrl() {
    const body = {
      cameraIndexCode: el.cameraIndexCode.value.trim(),
      streamType: Number(el.streamType.value),
      protocol: el.protocol.value,
      transmode: Number(el.transmode.value)
    };
    if (el.expand.value.trim()) {
      body.expand = el.expand.value.trim();
    }
    const result = await callPlatformApi("/api/video/v1/cameras/previewURLs", body);
    state.lastPreviewUrl = result;
    return result;
  }

  function fillFirstCamera() {
    const list = (((state.lastCameraList || {}).data || {}).list || []);
    if (!list.length) {
      throw new Error("No camera list in previous response");
    }
    const first = list[0];
    el.cameraIndexCode.value = first.cameraIndexCode || "";
    setStatus();
    log("ok", "Filled first camera from last response", first);
  }

  function clearState() {
    state.loginInfo = null;
    state.ticketInfo = null;
    state.serviceInfo = null;
    state.lastCameraList = null;
    state.lastPreviewUrl = null;
    el.platformToken.value = "";
    el.cameraIndexCode.value = "";
    setStatus();
    log("warn", "State cleared");
  }

  function clearLog() {
    el.terminal.textContent = "";
  }

  async function runFullChain() {
    log("warn", "Running full chain");
    setTitle("running");
    if (state.bridgeAvailable) {
      await getLoginInfo();
      await getTickets();
    } else {
      log("warn", "Skipping container-only steps in browser mode");
    }
    await listTreeCodes();
    await listCameras();
    fillFirstCamera();
    await getPreviewUrl();
    log("ok", "Full chain completed");
    setTitle("success");
  }

  async function withLog(label, fn) {
    try {
      const result = await fn();
      setStatus();
      return result;
    } catch (error) {
      log("err", label + " failed", String(error && error.message ? error.message : error));
      throw error;
    }
  }

  function bindEvents() {
    el.btnLogin.addEventListener("click", function () {
      withLog("GetLoginInfo", getLoginInfo);
    });
    el.btnTicket.addEventListener("click", function () {
      withLog("GetTickets", getTickets);
    });
    el.btnService.addEventListener("click", function () {
      withLog("GetServiceInfo", getServiceInfo);
    });
    el.btnClearState.addEventListener("click", function () {
      clearState();
    });
    el.btnTreeCodes.addEventListener("click", function () {
      withLog("Tree codes", listTreeCodes);
    });
    el.btnRegions.addEventListener("click", function () {
      withLog("Regions", listRegions);
    });
    el.btnCameras.addEventListener("click", function () {
      withLog("Cameras", listCameras);
    });
    el.btnPreviewUrl.addEventListener("click", function () {
      withLog("Preview URL", getPreviewUrl);
    });
    el.btnFillFromResponse.addEventListener("click", function () {
      try {
        fillFirstCamera();
      } catch (error) {
        log("err", "Fill camera failed", String(error.message || error));
      }
    });
    el.btnRunFullChain.addEventListener("click", function () {
      withLog("Full chain", runFullChain);
    });
    el.btnClearLog.addEventListener("click", function () {
      clearLog();
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
      await runFullChain();
    } catch (error) {
      setTitle("failed");
      log("err", "Autorun failed", String(error && error.message ? error.message : error));
    }
  }

  setStatus();
  bindEvents();
  setTitle(state.bridgeAvailable ? "ready-container" : "ready-browser");
  log("ok", "Probe page ready", {
    bridgeAvailable: state.bridgeAvailable,
    recommendedChain: [
      "GetLoginInfo",
      "GetTickets",
      "/api/resource/v1/unit/getAllTreeCode",
      "/api/resource/v1/cameras",
      "/api/video/v1/cameras/previewURLs"
    ]
  });
  setTimeout(function () {
    maybeAutorun();
  }, 800);
})();
