# Renderer Implementation Package

- Driver kind: `web-plugin-stub`
- Bridge preset: `webcontrol-local-service`
- Driver preset: `plugin-session-driver`
- Host type: `webcontrol-local-service`
- Runtime prefix: `drv-plugin`

## Next Step

1. Fill the bridge methods in `bridge/webcontrol-local-service.js`.
2. Fill the lifecycle implementation in `driver/plugin-session-driver.js`.
3. Wire the exported functions back into the runtime shell.
4. Validate runtime health and policy using `runtime/health.js` and `runtime/policy.json`.
