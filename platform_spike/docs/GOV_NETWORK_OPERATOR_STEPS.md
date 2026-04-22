# GOV_NETWORK_OPERATOR_STEPS

这个文档给现场操作用，目标是把“什么时候必须切政务网”和“切完以后怎么最小成本配合联调”固定下来。

## 结论

不切政务网，我仍然可以继续做一部分工作，但只能做离线部分：

- 完善 `platform_spike_poc` 页面状态机
- 完善日志、错误提示、超时处理、重试策略
- 完善 `tvms` / `resource` / `previewURLs` 请求封装
- 完善“从本地日志提取当前 `TGT` 与 `loginUrl`”的自动探测脚本
- 用本地文档和假数据继续推进页面与接口适配层

但是下面这些步骤，必须在政务网或等效可达平台网关的网络环境里做：

- 验证 `resource` 接口真实返回
- 验证 `previewURLs` 真实返回
- 验证 `tvms` 真实返回
- 验证真实预览承载
- 验证 `4 / 9 / 12` 宫格和放大返回的真实控制闭环

## 当前已经准备好的脚本

仓库里已经有这个脚本：

```bash
./platform_spike/scripts/platform_live_probe.sh
```

它会自动：

1. 从 `webcontainer` 日志提取当天最新的 `loginUrl`
2. 提取同一会话的最新 `TGT`
3. 直测：
   - `/api/resource/v1/unit/getAllTreeCode`
   - `/api/resource/v1/cameras`
   - `/api/video/v1/cameras/previewURLs`
   - `/api/tvms/v1/tvwall/allResources`
4. 再补测一次本地 `http://127.0.0.1:36753/proxy`
5. 把结果写到：

```text
tmp/platform_live_probe_last.json
```

## 你需要手动配合的最小步骤

只有在我明确告诉你“现在需要切政务网”时，再做下面这些动作。

### 步骤 1：不要关闭客户端

- 保持“视频融合赋能平台客户端”已经登录
- 保持客户端窗口存在，最小化也可以
- 不要退出客户端，不要切换用户

### 步骤 2：连接政务网或等效 VPN

- 连上你平时能正常看到视频监控画面的那条网络
- 如果需要开 VPN，就开到能访问平台网关的状态
- 不需要手工再点任何业务按钮，先保持客户端原样

### 步骤 3：告诉我一句话

你只需要回复：

```text
已连政务网，客户端未关闭
```

到这里为止，其他操作都先不要做。

### 步骤 4：等待我先跑自动探测

我会先跑：

```bash
./platform_spike/scripts/platform_live_probe.sh
```

如果在线时间很短，我会优先跑：

```bash
./platform_spike/scripts/platform_live_probe.sh -ProbePreset quick -TimeoutSec 2 -SkipLocalProxy
```

这一步的作用是先确认：

- 当前网关能不能连通
- 当前 `TGT` 是否可用
- `resource` / `previewURLs` / `tvms` 是否开始返回真实数据

### 步骤 5：只有我明确要求时，再做 UI 配合

只有在我确认接口已通后，我才会让你做下一步，比如：

- 进入“视频监控”
- 点一次“点位搜索”
- 切一次某个宫格
- 手工放大一路

每次我都会给你单独一句非常明确的操作指令。

## 我发给你时，会用的标准指令

如果后面需要你操作，我会只发下面这种格式：

### 网络切换类

```text
现在请连政务网，保持客户端不要关闭。连好后回复：已连政务网，客户端未关闭
```

### 快速在线采集类

```text
现在请保持客户端不要关闭，在政务网环境下执行快速探针。执行完后回复：快速探针已执行
```

如果我要求你做“一键 bundle 采集”，你只需要执行：

```bash
bash platform_spike/scripts/platform_quick_capture_bundle.sh
```

如果你当时在 Windows 终端里操作，也可以直接执行：

```bat
platform_spike\scripts\platform_quick_capture_bundle_windows.cmd
```

它会自动生成一个目录，里面至少包含：

- `platform_live_probe_last.json`
- `webcontainer_tail.log`
- `bundle_summary.json`
- `bundle_analysis.json`
- `bundle_analysis.md`
- `operator_packet.txt`
- `operator_review.json`
- `operator_review.txt`

同时还会在 `tmp/live_probe_bundles/` 下额外生成：

- `bundle_时间戳.zip`
- `latest_bundle_zip.txt`
- `latest_operator_packet.txt`

同时还会刷新：

- `tmp/live_probe_bundles/latest_bundle.txt`
- `tmp/live_probe_bundles/latest_operator_review.json`
- `tmp/live_probe_bundles/latest_operator_review.txt`

执行结束后，终端最后会出现一个：

```text
=== OPERATOR_RESULT ===
```

你后面优先只需要把这整个 `OPERATOR_RESULT` 块原样发给我即可。
如果你当时更方便发路径，也可以只发：

- `LATEST_BUNDLE_DIR=...`
- 或 `LATEST_BUNDLE_ZIP=...`

结果块里如果出现：

- `xresSearchContext=...`
- `tvmsContext=...`

也一并保留原样发给我，不要手工删改。

如果当时不方便开终端，也可以走页面内采集：

1. 保持客户端已登录并进入“视频监控”
2. 什么都不要再点，等页面自动运行 `Container Auth Probe`
3. 把页面里 `Container Auth Probe` 面板中的整段 `CONTAINER_AUTH_RESULT` 原样复制给我

这条路的目标和 quick capture bundle 一样，都是把：

- 当前容器会话是否可用
- `xres-search` 是否已命中真实 service context
- `tvms` 是否已命中真实 service context
- 当前更像“网络不稳”还是“认证头不对”

固定成一段可以离线分析的结果。

补充一点：

- 页面会把最近一次 `CONTAINER_AUTH_RESULT` 保存在本地存储里
- 所以即使你切回非政务网、页面重开，最近一次探针结果通常还在，不需要你当场重复操作

### 页面进入类

```text
现在请在客户端里进入“视频监控”，进入后不要再点别的，回复：已进入视频监控
```

### 手工动作类

```text
现在请手工切到 9 宫格，切完后不要再操作，回复：已切到 9
```

```text
现在请手工放大一路，放大后不要再操作，回复：已放大
```

```text
现在请从单画面返回宫格，返回后不要再操作，回复：已返回宫格
```

## 不切政务网时，我还能继续做什么

即使你暂时不切政务网，我仍然可以继续推进这些离线工作：

1. 给 `platform_spike_poc` 增加假数据回放模式
2. 让页面在没有真实接口时也能完整跑本地宫格、放大、返回状态机
3. 把真实接口返回结构适配成统一的运行时数据模型
4. 继续补充日志、失败提示和恢复策略
5. 把“联调时只需要你做一次最小操作”的流程压缩到最少

## 当前最推荐的协作方式

- 平时不切政务网时，我继续做离线部分
- 只有当我要验证真实接口时，你再临时切一次政务网
- 你每次只需要做我当下明确要求的那一步，不要多点

这样可以把你手工参与的次数压到最少。
