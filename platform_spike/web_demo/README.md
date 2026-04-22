# web_demo

这个目录存放 `platform_spike` 的最小 Web 页面原型。

当前目标不是做最终播放器，而是先验证本机已有的：

- Web 容器桥接
- 客户端会话
- 代理访问
- OpenAPI 资源查询
- 预览 URL 获取

是否能在一个自有页面里闭环。

## 当前文件

- `webcontainer_probe.html`
  最小探针页面
- `webcontainer_probe.js`
  页面逻辑
- `platform_spike_poc.html`
  真正的 POC 壳，开始承载本地宫格状态机和 tvwall 控制桥
- `platform_spike_poc.js`
  POC 页面逻辑
- `implementation_package_harness.html`
  独立的 materialized package 验收页
- `implementation_package_harness.js`
  验收页逻辑
- `../scripts/publish_web_demo.sh`
  把当前页面同步到 Windows 已安装的 `webcontainer` 目录

## 当前验证范围

页面优先验证下面这条链：

1. `GetLoginInfo`
2. `getTickets`
3. `POST /api/resource/v1/unit/getAllTreeCode`
4. `POST /api/resource/v1/regions`
5. `POST /api/resource/v1/cameras`
6. `POST /api/video/v1/cameras/previewURLs`

## 使用方式

### 1. 在客户端 webcontainer 中运行

优先方式是把页面放进客户端内嵌 Web 容器或让容器加载这个页面。

当前仓库已经提供同步脚本：

```bash
./platform_spike/scripts/publish_web_demo.sh
```

默认发布到：

```text
D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\bin\webcontainer\webapp\platform_spike_probe
```

在这种模式下，页面会优先使用：

- `window.cefQuery(...)`
- `POST /proxy`

如果页面 URL 带 `?autorun=1`，它会自动顺序执行：

1. 优先在 `platform_spike_poc.html` 里运行 `Container Auth Probe`
2. `GetLoginInfo`
3. 多组 `getTickets`
4. 通过 `/proxy` 探测 `xres-search` 与 `tvms`
5. 把结果整理成页面内可复制的 `CONTAINER_AUTH_RESULT`

这个模式就是为了减少容器内手工点击。

如果页面 URL 同时带 `?mock=1`，它会切到离线回放模式：

1. 加载本地 mock 登录态 / 票据 / 资源目录 / 点位清单
2. 本地生成 preview URL
3. 加载 mock tvwall 资源
4. 自动回放 `4 宫格 -> 9 宫格 -> 放大 -> 返回 -> 12 宫格`

这个模式不依赖政务网，适合先验证页面状态机和演示闭环。

### 1.5. 在政务网在线窗口外做接口连通性验证

如果当前客户端已经登录过，但你不想手工进联调页，也可以直接用：

```bash
./platform_spike/scripts/platform_live_probe.sh
```

它会直接从 `webcontainer` 日志提取当天最新的 `loginUrl` 和 `TGT`，然后从 Windows 侧直测平台接口，把结果写到：

```text
tmp/platform_live_probe_last.json
```

这一步适合用来快速区分：

- 是“页面桥接没通”
- 还是“当前机器根本没通到政务网/平台网关”

### 2. 在普通浏览器中调试

普通浏览器里没有 `window.cefQuery`，所以：

- 容器桥接相关按钮会失败
- 只能用手工填写的 `Platform Base URL` 和 `Token` 做直接 `fetch`

这个模式主要用于静态调试页面，不用于最终联调。

## 当前限制

- 还没有接入真正的视频播放器内核
- `platform_spike_poc` 目前优先承载：
  - 本地受控 4 / 9 / 12 宫格
  - 绑定监控点
  - 获取预览 URL
  - tvwall 官方接口调试按钮
  - 本地轮询状态机：开始、停止、下一路、全屏轮巡、偏好持久化
  - renderer adapter 策略位和 runtime session 快照
- 所以现在已经不止是“资源查询 + 预览 URL 获取”探针了，而是第一版受控运行壳

## 下一步

如果当前页面能稳定拿到：

- treeCode
- cameraIndexCode
- preview URL

下一步就进入真正的预览承载和电视墙控制联调。

## 当前推荐入口

### 最小探针

- `./webcontainer_probe.html`

用途：

- 验证 `GetLoginInfo`
- 验证 `getTickets`
- 验证 `/proxy`
- 验证基础 OpenAPI 链

### POC 壳

- `./platform_spike_poc.html`

用途：

- 在真实 webcontainer 里自动运行 `Container Auth Probe`，并生成一段可直接复制的 `CONTAINER_AUTH_RESULT`
- 本地 4 / 9 / 12 宫格状态机
- 绑定监控点到 tile
- 批量获取绑定 tile 的预览 URL
- 调用 tvwall 的 `division / zoomIn / zoomOut`
- 支持 `Mock Replay` 离线回放模式
- 支持离线轮询运行时
- 支持 `mock-ws / mock-hls / web-plugin-stub` renderer 切换
- 支持 session snapshot 的保存、恢复、重置
- 每个 tile 会生成 renderer session id、surface type 和 display url，方便后续替换真实播放器实现
- 支持 renderer attach plan 导出、runtime bundle 导出/导入和 diagnostics 快照
- 支持 renderer command queue、selected command preview 和 bridge invocation 骨架
- 支持 renderer driver mode、pending queue 执行和 recent history 回放
- 支持 renderer driver 的 init / dispose 生命周期与 runtime 快照
- 支持 renderer capability matrix 和 host contract 导出，后续可直接映射真实宿主能力
- 支持 renderer health check、heartbeat 和 recovery policy，后续可直接映射真实播放器健康监测与恢复链
- 支持 renderer host preflight 预检，能在离线状态下先识别缺失方法、缺失 artifact 和接入阻塞项
- 支持统一的 renderer admission / attach guard，attach、run queue、recovery 会共用同一套准入决策
- 支持 renderer action policy matrix，能把 attach / refresh / detach / fullscreen route 的许可规则固定成快照
- 支持 driver profile / capability preset，并可一键套用推荐的 driver mode / auto attach / recovery / heartbeat 默认值
- 支持导出 bridge template 和 driver template，后面接真实 web plugin / hls / ws 时可直接按模板填实现
- 支持 bridge / driver template preset，可切换 Webcontainer、WebControl、HTML5、Canvas、HLS.js、WebCodecs 等实现骨架
- 支持导出 implementation package，可直接生成 bridge stub、driver stub、manifest 和接线说明骨架

如果下次在线时不方便执行命令行采集，也可以只进入“视频监控”，等页面自动跑完后，把
`Container Auth Probe` 面板里整段 `CONTAINER_AUTH_RESULT` 原样复制给我。

页面还会把最近一次 `CONTAINER_AUTH_RESULT` 保存到本地浏览器存储里。
也就是说，即使你切回非政务网或页面重开，最近一次探针结果仍然会保留在面板中，后面还能继续复制给我。

仓库里还提供了对应解析器，后面可以直接把这段结果落盘分析：

```bash
python3 platform_spike/scripts/analyze_container_auth_result.py <container_auth_result.txt>
```

如果想直接把这段结果走完整条链，也可以执行：

```bash
bash platform_spike/scripts/ingest_container_auth_result.sh <container_auth_result.txt>
```

### Package Harness

- `./implementation_package_harness.html`

用途：

- 直接加载 `materialized package`
- 显示 manifest / wiring / bridge / driver / health exports
- 在浏览器里执行 `init -> attach -> refresh -> detach -> dispose`
- 导出 harness report，确认 package 本身的最小生命周期已经闭环

如果已经从页面导出了 implementation package JSON，还可以直接落盘成目录文件：

```bash
python3 platform_spike/scripts/materialize_implementation_package.py implementation_package.json --output-root tmp/materialized_packages --force
```

如果手里的是较早导出的 implementation package JSON，也可以先刷新到当前文件骨架再落盘：

```bash
python3 platform_spike/scripts/refresh_implementation_package_export.py implementation_package.json
```

落盘后可以继续校验包结构和 JS 骨架：

```bash
python3 platform_spike/scripts/verify_implementation_package.py tmp/materialized_packages/<package_name>
```

如果要再往前跑一遍最小 runtime 生命周期，可以继续执行：

```bash
python3 platform_spike/scripts/smoke_test_materialized_package.py tmp/materialized_packages/<package_name>
```

如果想在浏览器里直接加载 materialized package，可以先把它 stage 到 `web_demo/harness_packages`：

```bash
python3 platform_spike/scripts/stage_materialized_package_for_harness.py tmp/materialized_packages/<package_name> --force
```

然后打开：

```text
./implementation_package_harness.html
```

如果要做无交互回归，也可以直接带查询参数：

```text
./implementation_package_harness.html?autoload=1&autorun=full
```

如果已经导出或落盘了多份 package，也可以直接批量做 catalog 和 smoke test：

```bash
python3 platform_spike/scripts/catalog_materialized_packages.py tmp/materialized_packages --with-smoke-test --json-output tmp/materialized_packages/catalog.json
```

## 离线回放推荐入口

如果当前不在政务网，直接打开：

```text
./platform_spike_poc.html?mock=1&autorun=1
```

或者发布后打开：

```text
http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?mock=1&autorun=1
```
