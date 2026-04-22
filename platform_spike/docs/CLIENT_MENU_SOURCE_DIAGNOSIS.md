# 视频监控菜单来源诊断

当本地 `menus.xml` 已经把 `client0101` 重定向到 `platform_spike_poc.html`，但客户端实际点“视频监控”后仍然进入原始 `vsclient`，问题通常不是页面文件没发布，而是当前会话仍然吃了服务端菜单。

## 诊断命令

Windows 上直接执行：

```bat
platform_spike\scripts\inspect_client_menu_sources.cmd
```

或者：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\inspect_client_menu_sources.ps1
```

它会先复用：

- `check_windows_platform_spike_env.ps1`

再输出一段简化结果：

```text
=== CLIENT_MENU_SOURCE_RESULT ===
...
CLIENT_MENU_SOURCE_RESULT_END
```

## 关键字段

- `videoMonitorMenuSourceAssessment`
  当前判定的“视频监控”来源：
  - `server-vsclient`
  - `local-client0101-redirect`
  - `local-probe-menu-only`
  - `unknown`
- `latestClient0101Component`
  最近一次 `AddAppTab:AppID=client0101` 对应的组件
- `latestVideoPermissionCode`
  最近一次和“视频监控”相关的 `permissionCode`
- `latestProbeMenuSignal`
  日志里最近一次与 `platform_spike_probe` / `platform_spike_poc.html` 相关的命中

## 如何理解结果

### `server-vsclient`

说明当前会话里，“视频监控”仍然来自服务端或组件层的 `vsclient_client0101`。

这时不要再把：

- 本地 `menus.xml` 的 `client0101` 重定向

当作唯一入口。

优先级应改成：

1. `quick capture bundle`
2. 本地 `probe-menu` / `ipoint-poc`
3. 页面侧 `Container Auth Probe`

### `local-client0101-redirect`

说明本地 `menus.xml` 的重定向已经更可能在生效。

这时再去验证：

- “视频监控”是否进入了 `platform_spike_poc.html`
- 页面里是否出现 `Container Auth Probe`

### `local-probe-menu-only`

说明本地探针菜单已发布，但当前没有证据表明“视频监控”真的落到了本地 POC。

这种情况下更适合让操作员点：

- 单独的 `平台联调探针`

而不是依赖“视频监控”。

## 当前建议

在多机部署时，把“菜单来源诊断”放到 `quick capture bundle` 之前做一次，可以更快判断：

- 该优先走页面侧探针
- 还是继续走命令行采集
