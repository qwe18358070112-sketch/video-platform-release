export async function launchLocalService(ctx) { return { port: 14600, lockName: 'InfoSightWebControl.lock' }; }

export async function createPluginWindow(ctx) { return { windowId: 'wc-' + Date.now(), mountSelector: ctx.mountSelector }; }

export async function invokePreview(ctx) { return { previewStarted: true, cameraIndexCode: ctx.cameraIndexCode, servicePort: ctx.servicePort || 14600 }; }

export async function stopPreview(ctx) { return { previewStopped: true, sessionId: ctx.sessionId }; }

export async function disposePluginWindow(ctx) { return { disposed: true, windowId: ctx.windowId }; }