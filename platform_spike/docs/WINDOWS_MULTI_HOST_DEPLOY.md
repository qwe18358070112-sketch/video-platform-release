# `platform_spike` 多台 Windows 电脑部署说明

这份说明的目标不是只让当前这台电脑可用，而是把 `platform_spike` 的联调页、采集脚本和部署动作整理成可复制到其他 Windows 电脑上的做法。

另外，当前也补了一个“视频监控菜单来源诊断”工具，用来判断本机当前会话到底在吃：

- 本地 `client0101` 重定向
- 本地探针菜单
- 还是服务端下发的 `vsclient_client0101`

对应说明见：

- [CLIENT_MENU_SOURCE_DIAGNOSIS.md](/home/lenovo/projects/video_platform_release/platform_spike/docs/CLIENT_MENU_SOURCE_DIAGNOSIS.md)

## 当前结论

已经确认两件事：

- 平台联调页、quick capture bundle、live probe 不再依赖当前这台机器的单次在线窗口才能准备。
- 但“视频监控”入口是否会真的切到本地 `platform_spike_poc.html`，不能只看本地 `menus.xml`。当前客户端在部分会话里仍会吃服务端下发的 `vsclient_client0101` 菜单，所以本地 `client0101` 重定向只能算“尽力而为”的入口，不是唯一可靠入口。

因此，多机部署建议按两层做：

1. **先保证采集链可用**
   也就是：
   - `platform_quick_capture_bundle.ps1`
   - `platform_live_probe.ps1`
   - `quick capture bundle` / `OPERATOR_RESULT`
2. **再尝试页面侧入口**
   也就是：
   - 发布 `platform_spike_probe` 页面到本地 `webcontainer`
   - 尝试 `probe-menu` / `ipoint-poc` / `video-monitor-poc`
   - 如果“视频监控”仍然没有进入 POC 页，就退回 quick bundle 路线

另外，桌面自动化兜底路线现在也支持多机分发：

- 固定宫格版本优先按独立 zip 分发，每台机器只部署需要的那一套
- 如果现场继续被“全屏 / 窗口”识别扰动，再把 4 套扩成 8 套

对应打包命令：

```bash
python3 platform_spike/scripts/package_fixed_layout_programs.py
python3 platform_spike/scripts/package_fixed_layout_programs.py --include-modes
```

Windows 上也可以直接执行：

```bat
platform_spike\scripts\package_fixed_layout_programs.cmd
platform_spike\scripts\package_fixed_layout_programs.cmd --include-modes
```

## 一、先做环境自检

在目标 Windows 电脑上，先运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\check_windows_platform_spike_env.ps1
```

或者直接运行：

```bat
platform_spike\scripts\check_windows_platform_spike_env.cmd
```

它会输出一段：

```text
=== WINDOWS_ENV_RESULT ===
...
WINDOWS_ENV_RESULT_END
```

并在仓库 `tmp/windows_env_reports/` 下生成一份 JSON 和 TXT 报告。

它会检查这些关键项：

- `client\product\META-INF\menus.xml`
- `client\components\webcontainer.1`
- `client\framework\infosightclient.1`
- `WebControl.exe`
- `MainBrowser.exe`
- `SimpleWebServer.exe`
- `webcontainer` 和 `clientframe` 日志
- 本地静态页 `http://127.0.0.1:36753/platform_spike_probe/index.html`
- 当前日志里是否已经出现：
  - `xres-search`
  - `tvms`
  - 服务端 `vsclient_client0101`

如果要专门诊断“视频监控”当前菜单来源，可直接运行：

```bat
platform_spike\scripts\inspect_client_menu_sources.cmd
```

或者：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\inspect_client_menu_sources.ps1
```

## 二、部署本地联调页

如果只是把页面和脚本部署到目标电脑，不改菜单，运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode publish-only
```

如果要新增一个本地探针菜单：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode probe-menu
```

如果要直接复用 `ipoint`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode ipoint-poc
```

如果要直接复用“视频监控”：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode video-monitor-poc
```

如果要恢复：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode restore
```

也可以直接用：

```bat
platform_spike\scripts\deploy_platform_spike_windows.cmd
```

## 三、不要把菜单重定向当成唯一入口

当前真实客户端已经证明：

- 本地 `menus.xml` 被改了，不代表当前会话一定会吃这份菜单。
- 客户端仍可能按服务端菜单加载 `vsclient_client0101`。

所以在其他 Windows 电脑上，要优先保证这条链能用：

```bat
platform_spike\scripts\platform_quick_capture_bundle_windows.cmd
```

只要这个命令能跑，`OPERATOR_RESULT` 就能留给离线分析。

页面侧 `Container Auth Probe` 是加分项，不是唯一依赖。

## 四、打包给其他 Windows 电脑

如果需要把当前联调页和 Windows 脚本打成一个可拷贝包，运行：

```bash
python3 platform_spike/scripts/package_platform_spike_windows.py
```

它会生成：

- `tmp/windows_probe_packages/platform_spike_windows_bundle_时间戳/`
- `tmp/windows_probe_packages/platform_spike_windows_bundle_时间戳.zip`

包里包含：

- `web_demo/` 核心页面
- `deploy_platform_spike_windows.ps1`
- `check_windows_platform_spike_env.ps1`
- `platform_quick_capture_bundle_windows.cmd`
- 相关联调说明文档

## 五、建议的多机推广顺序

1. 在目标电脑上跑环境自检。
2. 只做 `publish-only`。
3. 先验证 quick capture bundle 能否出结果。
4. 再尝试 `probe-menu` 或 `ipoint-poc`。
5. 最后才尝试 `video-monitor-poc`。

这样做的原因是：`video-monitor-poc` 最贴近真实入口，但也最容易受服务端菜单覆盖影响。
