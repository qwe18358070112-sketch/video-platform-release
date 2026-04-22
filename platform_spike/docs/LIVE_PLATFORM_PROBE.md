# LIVE_PLATFORM_PROBE

这个文档说明 `platform_spike/scripts/platform_live_probe.sh` 的用途和当前结论。

## 目的

把“当前客户端已经登录，但现场网络环境不稳定”这种情况标准化成一个固定探针，而不是每次重新手工：

- 找 `webcontainer` 日志
- 抠 `loginUrl`
- 抠最新 `TGT`
- 手工拼 `resource` / `previewURLs` / `tvms` 请求

## 脚本入口

```bash
./platform_spike/scripts/platform_live_probe.sh
```

Windows 侧实际执行的是：

```text
platform_spike/scripts/platform_live_probe.ps1
```

## 当前行为

脚本会：

1. 读取：

```text
D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\logs\webcontainer\webcontainer.webcontainer.debug.log
```

2. 提取当天最新的：

- `loginUrl`
- `portalAddress`
- `userIndexCode`
- `TGT`

3. 从 Windows 侧直接探测：

- `POST /api/resource/v1/unit/getAllTreeCode`
- `POST /api/resource/v1/cameras`
- `POST /api/video/v1/cameras/previewURLs`
- `POST /api/tvms/v1/tvwall/allResources`

4. 结果写入：

```text
tmp/platform_live_probe_last.json
```

当前版本还额外做了两件事：

- 会从 `clientframe` 日志里提取最近的 `context token`
- 会按服务做优先级排序：
  - `xres-search` 优先试更接近 `xres-search` 请求时刻的 token
  - `tvms` 优先试更接近 `tvms` 请求时刻的 token
- quick capture bundle 现在会顺手把 `clientframe_auth_context.json` 和 `clientframe_tail.log` 一起打进 bundle

这样下一次短时在线窗口里，probe 不再只是“全局乱试 header”，而是优先走更像当前服务刚拿到的 token。

## 当前推荐的两种模式

### 1. 快速模式

适合你只能给我一个很短的在线窗口时先跑：

```bash
./platform_spike/scripts/platform_live_probe.sh -ProbePreset quick -TimeoutSec 2 -SkipLocalProxy
```

这个模式只测：

- `/api/resource/v1/unit/getAllTreeCode`
- `/api/tvms/v1/tvwall/allResources`

优点是更快，适合先判断“平台接口是不是已经开始返回真实数据”。

如果还想顺手把日志和摘要一起打包，可以直接运行：

```bash
bash platform_spike/scripts/platform_quick_capture_bundle.sh
```

它会在 `tmp/live_probe_bundles/bundle_时间戳/` 下生成：

- `platform_live_probe_last.json`
- `webcontainer_tail.log`
- `bundle_summary.json`
- `bundle_analysis.json`
- `bundle_analysis.md`
- `operator_packet.txt`
- `operator_review.json`
- `operator_review.txt`

并刷新：

- `tmp/live_probe_bundles/latest_bundle.txt`
- `tmp/live_probe_bundles/latest_bundle_zip.txt`

这样即使你只告诉我“已经执行完 bundle”，我也可以直接读取最新那一份结果。

同目录下还会自动生成：

- `latest_operator_review.json`
- `latest_operator_review.txt`
- `latest_operator_packet.txt`

bundle 本身也会被自动打成：

- `tmp/live_probe_bundles/bundle_时间戳.zip`

这两份文件会把“当前 recommendation / nextStep / operatorStep”直接写出来，减少再手工翻 JSON 的时间。

现在 `platform_quick_capture_bundle.sh` 在执行结束后，还会直接打印一个：

```text
=== OPERATOR_RESULT ===
```

里面会包含：

- `LATEST_BUNDLE_DIR=...`
- `LATEST_BUNDLE_ZIP=...`
- `operator_packet`
- `operator_review`

现在 `operator_packet / operator_review` 里还会带：

- `xresSearchContext`
- `tvmsContext`

所以后面短时在线配合时，优先只需要把这个结果块原样发回即可。

### 2. 完整模式

如果快速模式已经开始返回真实数据，再跑完整模式：

```bash
./platform_spike/scripts/platform_live_probe.sh -ProbePreset full -TimeoutSec 5
```

这个模式会补齐：

- `/api/resource/v1/cameras`
- `/api/video/v1/cameras/previewURLs`
- 本地 `/proxy`

并且现在会按阶段增量落盘：

- `session_loaded`
- `connectivity_checked`
- `probe_completed:/api/...`
- `complete`

所以即使中途换网络、超时或手动中断，文件里也至少会留下本次最新：

- `loginUrl`
- `portalAddress`
- `userIndexCode`
- `TGT`
- 已完成到哪一步

## 当前已确认的现场结论

在 2026-04-01 这次会话里，日志已经明确包含：

- `loginUrl = https://10.25.7.171:443`
- 最新 `TGT`

但对 `https://10.25.7.171:443` 的直接连通性探测会超时。

这说明当前机器虽然保留了客户端登录态，但当前网络环境并没有真正连通平台网关。

所以这类现场下，阻塞点不是：

- OpenAPI 不存在
- `tvms` 不存在
- `resource` 不存在

而是：

- 当前网络没有打通到平台网关

## 用法建议

- 在非政务网 / 未连 VPN 时，用这个脚本确认“环境阻塞”。
- 在政务网在线时，先跑这个脚本。
  如果 `resource` 和 `tvms` 开始返回真实数据，再继续推进 `platform_spike_poc` 的受控宫格和放大返回闭环。
- 如果现场网络可能随时切换，优先看 `tmp/platform_live_probe_last.json` 里的 `stage` 和 `updatedAt`，不要只看脚本进程是否完整结束。
- 如果在线时间很短，优先跑 `quick` 模式；只有快速模式开始返回真实数据，再切到 `full`。
