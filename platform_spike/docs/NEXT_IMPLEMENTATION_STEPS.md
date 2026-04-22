# 下一阶段实施步骤

## 第 1 步：先用本机资料做最小闭环

本机已确认存在：

- Web 容器 Demo
- OpenAPI 文档
- WebControl 本地服务

所以当前第一步不再是停在“等待资料”，而是先验证：

1. `GetLoginInfo`
2. `getTickets`
3. `POST /api/resource/v1/unit/getAllTreeCode`
4. `POST /api/resource/v1/cameras`
5. `POST /api/video/v1/cameras/previewURLs`

对应文件：

- [LOCAL_WINDOWS_DISCOVERY_2026-03-31.md](/home/lenovo/projects/video_platform_release/platform_spike/docs/LOCAL_WINDOWS_DISCOVERY_2026-03-31.md)
- [LOCAL_OPENAPI_MIN_POC_CHAIN.md](/home/lenovo/projects/video_platform_release/platform_spike/docs/LOCAL_OPENAPI_MIN_POC_CHAIN.md)
- [web_demo/README.md](/home/lenovo/projects/video_platform_release/platform_spike/web_demo/README.md)

## 第 2 步：向平台方补齐未确认项

必须确认下面这些问题：

1. 是否有平台 OpenAPI 能列出组织、设备、通道
2. 是否有 Web 插件或 WebControl 能承载实时预览
3. 是否有平台级鉴权 token 或会话机制
4. 是否必须直连设备，还是可以经平台转发
5. 是否支持在页面或 SDK 中直接切分 4 / 6 / 9 / 12 宫格

## 第 3 步：做一个只含 4 个动作的 POC

第一版 POC 先做这 4 个动作：

1. 打开资源列表
2. 打开 4 宫格
3. 切 9 宫格
4. 放大其中一路再返回

只要这 4 步能在自有程序里闭环，就证明已经脱离桌面客户端自动化主路线。

当前离线 POC 已经额外补上：

1. 本地 mock 资源目录 / 点位清单
2. 本地 preview URL 解析占位
3. `4 -> 9 -> 放大 -> 返回 -> 12` 自动回放
4. 本地轮询状态机：开始、停止、下一路、全屏轮巡、持久化
5. renderer adapter 策略位：`mock-ws / mock-hls / web-plugin-stub`
6. runtime session 快照：导出、恢复、重置
7. renderer attach plan / runtime bundle / diagnostics 快照，后面可直接映射到真实播放器 adapter
8. renderer command queue / bridge invocation 预览，后面可直接映射到真实播放器 attach / refresh / detach 生命周期
9. renderer driver mode / queue 执行 / history replay，后面可直接映射到真实播放器驱动实现
10. renderer driver init / dispose 生命周期，后面可直接映射到真实播放器 runtime host 管理
11. renderer capability matrix / host contract，后面可直接映射到真实播放器宿主接口清单
12. renderer health check / heartbeat / recovery policy，后面可直接映射到真实播放器健康监测与恢复链
13. renderer host preflight 预检，后面可直接映射到真实接入前的 host contract 阻塞检查
14. renderer admission / attach guard，后面可直接映射到真实 attach、run、recovery 的统一准入决策
15. renderer action policy matrix，后面可直接映射到真实 attach / refresh / detach / fullscreen route 的动作许可矩阵
16. driver profile / capability preset，后面可直接映射到不同真实接入路线的策略配置，并自动落推荐运行参数
17. bridge template / driver template 导出，后面可直接映射到真实 host bridge 和 renderer driver 实现骨架
18. bridge / driver template preset，后面可直接映射到真实 Webcontainer、WebControl、HTML5、Canvas、HLS.js、WebCodecs 等实现路线
19. implementation package 导出，后面可直接生成 bridge stub、driver stub、manifest 和接线说明骨架
20. materialize implementation package，后面可直接把导出 JSON 落盘成真实目录文件再接实现
21. verify implementation package，后面可直接做离线结构验收，减少政务网联调前的无效往返
22. catalog materialized packages，后面可直接批量扫目录、逐个 smoke test，并沉淀 preset 级 catalog 结果
23. smoke test materialized package，后面可直接 import wiring 并执行最小 lifecycle，提前发现 bridge/driver 导出断点
24. refresh implementation package export，后面可直接把旧版 export JSON 升级到当前文件骨架，减少重复开页面导出的依赖
25. stage materialized package for harness，后面可直接在浏览器壳里加载 package，做可视化 wiring/lifecycle 验收
26. implementation package harness，后面可直接做浏览器侧 `autoload=1&autorun=full` 回归，补齐页面级验收
27. quick capture bundle + analysis，后面可直接把短时在线窗口压缩成一次 bundle 采集，再离线读结论

所以后续切回政务网时，重点已经不是“先做轮询 UI”，而是把真实平台返回接到这套既有状态机上。

## 第 4 步：迁移现有调度语义

迁移时只复用现有动作语义，不复用现有识别链。

保留：

- 暂停
- 继续
- 下一路
- 手动切布局
- 放大停留
- 返回停留

移除：

- 当前宫格识别
- 当前全屏识别
- 当前客户端窗口状态识别

## 第 5 步：验收标准

必须满足：

1. 切布局不再需要截图确认
2. 放大/返回不再需要图片分类
3. 程序重启后状态由自身会话恢复，不靠旧截图缓存
4. 手工切布局后，程序能直接按内部状态机会话继续
