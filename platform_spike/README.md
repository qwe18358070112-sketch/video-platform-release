# platform_spike

这个目录是“脱离桌面客户端自动化”的替代路线原型。

目标不是继续修当前 Python + OpenCV + UIA 的识别链，而是把后续实现收束成：

- 资源发现
- 预览承载
- 宫格控制
- 轮询状态机

四层独立契约。

## 当前结论

根据这次真实客户端探针结果：

- [tmp/native_uia_probe.json](/home/lenovo/projects/video_platform_release/tmp/native_uia_probe.json)
- [native_runtime/PROBE_RESULT_2026-03-31.md](/home/lenovo/projects/video_platform_release/native_runtime/PROBE_RESULT_2026-03-31.md)

当前桌面客户端不适合继续作为主控制面。

所以 `platform_spike/` 只做两条可持续路线：

1. `HCNetSDK / 平台 SDK` 直连预览
2. `视频 WEB 插件 / WebControl` 受控预览页

## 子目录

- `docs/`
  迁移设计、技术选型、实施顺序
- `docs/LOCAL_WINDOWS_DISCOVERY_2026-03-31.md`
  当前电脑 Windows 环境里已经找到的本地资料清单
- `docs/LOCAL_OPENAPI_MIN_POC_CHAIN.md`
  用本机文档和本机容器能力拼出来的最小接口闭环
- `docs/LOCAL_TVWALL_API_SHORTLIST.md`
  从本机 OpenAPI 文档里抽出的电视墙最小动作接口清单
- `docs/LOCAL_WEBCONTAINER_MENU_INJECTION.md`
  把本地联调页挂进已安装客户端菜单的做法
- `docs/CLIENT_MENU_SOURCE_DIAGNOSIS.md`
  判断“视频监控”当前到底落到了本地重定向、探针菜单，还是服务端 `vsclient`
- `docs/PLATFORM_VENDOR_CONFIRMATION_CHECKLIST.md`
  需要平台方确认的能力清单
- `docs/PLATFORM_VENDOR_MESSAGE_TEMPLATE.md`
  可直接发给平台方/实施方的确认消息模板
- `contracts/`
  新运行时的最小领域契约，不绑定具体 SDK 或 Web 插件
- `web_demo/`
  当前同时包含：
  - 最小 webcontainer 探针页
  - 第一版 platform POC 壳
  - 离线 `mock replay` 回放模式，可在不连政务网时演示 `4 / 9 / 12` 宫格、放大、返回
- `scripts/`
  本地发布和菜单注入脚本
  现在也包含“从 webcontainer 日志提取当前 TGT 并直接探测平台接口”的联调脚本
  以及面向其他 Windows 电脑的 PowerShell 自检、部署和打包脚本

## 推荐优先级

## 当前本机已进入的阶段

这台机器上已经找到：

- WebControl / WebControlActiveX
- webcontainer 组件
- 本地内嵌页面 Demo
- 本地 OpenAPI 文档
- 组件包和升级包

所以接下来的优先工作不再是“等资料”，而是：

1. 先用 `web_demo/` 验证最小桥接闭环
2. 再把预览 URL 承载成真正的预览页
3. 同时验证本机文档里已经存在的 `tvwall` 官方接口
4. 最后决定走“自建预览宫格”还是“直接调 tvwall”

## 当前联调脚本

当前仓库已经提供：

```bash
./platform_spike/scripts/platform_live_probe.sh
```

它会在 Windows 侧完成这些动作：

1. 从 `webcontainer.webcontainer.debug.log` 提取当天最新的 `loginUrl`
2. 提取同一会话的最新 `TGT`
3. 直接探测：
   - `/api/resource/v1/unit/getAllTreeCode`
   - `/api/resource/v1/cameras`
   - `/api/video/v1/cameras/previewURLs`
   - `/api/tvms/v1/tvwall/allResources`
4. 把结果写到：

```text
tmp/platform_live_probe_last.json
```

这个脚本的意义是把“政务网在线时段”的有效信息固化下来，避免每次都靠手工抓日志和手工拼请求。

如果在线时间很短，优先用：

```bash
./platform_spike/scripts/platform_live_probe.sh -ProbePreset quick -TimeoutSec 2 -SkipLocalProxy
```

先判断 `resource + tvms` 是否已经开始返回真实数据，再决定要不要继续跑完整探针。

如果需要把 quick probe 结果和最新日志片段一次性留给离线分析，也可以直接运行：

```bash
bash platform_spike/scripts/platform_quick_capture_bundle.sh
```

这个命令会自动补一层分析，额外生成：

- `bundle_analysis.json`
- `bundle_analysis.md`
- `operator_packet.txt`
- `operator_review.json`
- `operator_review.txt`
- `tmp/live_probe_bundles/latest_bundle_zip.txt`
- `tmp/live_probe_bundles/latest_operator_packet.txt`
- `tmp/live_probe_bundles/latest_bundle.txt`
- `tmp/live_probe_bundles/latest_operator_review.json`
- `tmp/live_probe_bundles/latest_operator_review.txt`

并且会把本次 bundle 自动打成：

- `tmp/live_probe_bundles/bundle_时间戳.zip`

脚本结束时还会直接打印一个：

```text
=== OPERATOR_RESULT ===
```

后面在线配合时，优先只需要把这整个结果块原样发回即可；如果不方便，也至少发：

- `LATEST_BUNDLE_DIR=...`
- 或 `LATEST_BUNDLE_ZIP=...`

如果当时不方便开终端，也可以直接进入“视频监控”，等待 `platform_spike_poc.html` 自动跑完
页面内的 `Container Auth Probe`，然后把其中整段 `CONTAINER_AUTH_RESULT` 原样发回。
这条路径不依赖额外脚本参数，只依赖当前 webcontainer 页面和客户端会话本身。

仓库里也已经补了对应解析器：

```bash
python3 platform_spike/scripts/analyze_container_auth_result.py <container_auth_result.txt>
```

它会把你发回来的 `CONTAINER_AUTH_RESULT` 落盘到：

- `tmp/container_auth_results/container_auth_result_时间戳/`

并自动生成：

- `container_auth_result.json`
- `analysis.json`
- `analysis.md`
- `latest_container_auth_result.txt`

如果要把这段结果继续走成和 live bundle 对称的 `review + package + operator result`，也可以直接执行：

```bash
bash platform_spike/scripts/ingest_container_auth_result.sh <container_auth_result.txt>
```

它会额外生成：

- `operator_review.json`
- `operator_review.txt`
- `operator_packet.txt`
- `tmp/container_auth_results/container_auth_result_时间戳.zip`
- `latest_container_auth_result_zip.txt`
- `latest_container_auth_operator_packet.txt`

如果当时人在 Windows 终端，也可以直接执行：

```bat
platform_spike\scripts\platform_quick_capture_bundle_windows.cmd
```

## 多台 Windows 电脑支持

如果这条方案最终走通，后续要在其他 Windows 电脑上复用，当前仓库已经补了三件关键工具：

1. Windows 环境自检：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\check_windows_platform_spike_env.ps1
```

或者：

```bat
platform_spike\scripts\check_windows_platform_spike_env.cmd
```

2. Windows 侧发布/菜单部署：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File platform_spike\scripts\deploy_platform_spike_windows.ps1 -MenuMode publish-only
```

3. Windows 分发包打包：

```bash
python3 platform_spike/scripts/package_platform_spike_windows.py
```

完整说明见：

- [WINDOWS_MULTI_HOST_DEPLOY.md](/home/lenovo/projects/video_platform_release/platform_spike/docs/WINDOWS_MULTI_HOST_DEPLOY.md)

如果需要单独判断“视频监控”当前到底在吃哪套菜单，还可以直接运行：

```bat
platform_spike\scripts\inspect_client_menu_sources.cmd
```

当前真实联调还说明了一点：

- 本地 `menus.xml` 的 `client0101` 重定向，不一定总能盖过服务端下发菜单。

因此，多机推广时要把：

- `quick capture bundle`

作为第一优先级；

把：

- 页面侧 `Container Auth Probe`

作为第二优先级的增强入口。

## 当前离线演示入口

如果当前机器没有切到政务网，但仍要继续推进页面状态机和演示闭环，可以直接打开：

```text
http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?mock=1&autorun=1
```

这个入口会直接切到本地 mock 数据源，自动完成：

1. 资源目录加载
2. 点位加载
3. preview URL 解析
4. tvwall 资源加载
5. `4 -> 9 -> 放大 -> 返回 -> 12` 离线回放
6. 本地轮询运行时，可验证 `下一路 / 全屏轮巡 / 停留时间 / 偏好持久化`
7. renderer adapter 与 runtime session 快照，可提前验证承载层恢复语义
8. renderer attach payload / diagnostics / runtime bundle 导入导出，可提前固定真实播放器接入边界
9. renderer command queue 与 bridge invocation 预览，可提前固定真实播放器生命周期调用顺序
10. renderer driver mode 与 queue 执行骨架，可提前固定真实播放器 driver 责任边界
11. renderer driver init / dispose 生命周期，可提前固定真实播放器 runtime 管理边界
12. renderer capability matrix 与 host contract，可提前固定真实播放器宿主接口边界
13. renderer health check / heartbeat / recovery policy，可提前固定真实播放器健康监测与恢复边界
14. renderer host preflight 预检，可提前固定真实接入前缺失的方法、artifact 和阻塞项
15. renderer admission / attach guard，可提前固定 attach、run、recovery 共用的准入规则
16. renderer action policy matrix，可提前固定 attach / refresh / detach / fullscreen route 的许可规则
17. driver profile / capability preset，可提前固定不同真实接入路线的动作策略配置，并一键套用推荐运行参数
18. bridge template / driver template 导出，可提前固定真实实现接入骨架
19. bridge / driver template preset，可提前固定真实 host bridge 和 renderer driver 的实现路线
20. implementation package 导出，可提前固定 bridge stub、driver stub 与 manifest 的落地骨架
21. `scripts/materialize_implementation_package.py`，可把 implementation package JSON 直接落盘成真实目录文件
22. `scripts/verify_implementation_package.py`，可校验 materialized package 的 manifest、runtime support 与 JS 骨架
23. `scripts/catalog_materialized_packages.py`，可批量扫描和校验 materialized package 目录，并输出 catalog JSON 方便做 preset 级 smoke test
24. `scripts/smoke_test_materialized_package.py`，可对单个 materialized package 实际 import wiring 并执行最小 driver lifecycle
25. `scripts/refresh_implementation_package_export.py`，可把旧版 implementation package export JSON 刷新成当前 bridge / driver / runtime 文件骨架
26. `scripts/stage_materialized_package_for_harness.py`，可把 materialized package 复制到 `web_demo/harness_packages`，供浏览器 harness 直接加载
27. `web_demo/implementation_package_harness.html`，可在浏览器里直接加载 staged package，执行最小 driver lifecycle 并导出 harness report

### 第一优先级

优先验证平台是否能提供：

- 组织查询
- 设备资源查询
- 直播管理
- 预览能力

如果这些能力能通过平台 OpenAPI + SDK/插件拿到，就不再操作当前桌面客户端。

### 第二优先级

如果拿不到平台级能力，再考虑直接使用 HCNetSDK 面向设备侧构建预览墙。

但这会带来：

- 设备登录态管理
- 通道号发现
- 权限和账号分发
- 平台资源模型与设备资源模型映射

所以只有在平台侧能力不够时才作为备选。
