# UIA3 探针结果（2026-03-31）

本次通过：

```bash
./windows_bridge.sh native-probe --open-layout-panel
```

对真实客户端做了 Windows 原生 UIA3 探针。

对应 JSON 输出：

- [tmp/native_uia_probe.json](/home/lenovo/projects/video_platform_release/tmp/native_uia_probe.json)

## 结果摘要

- 主窗口可附着到 UIA，窗口类名为 `Qt5QWindowIcon`
- 相关渲染窗 `VSClient.exe` 可被识别为独立顶层窗
- 但主窗口和渲染窗都没有暴露出关键运行控件

本次真实结果：

- `foundWindowSplitControl = false`
- `foundFullscreenToggle = false`
- `foundLayoutOptions = 0`
- `relatedRenderSurfaceCount = 1`
- `renderSurfaceInterestingElementCount = 0`
- `recommendedPath = sdk_or_web_plugin`

## 结论

当前客户端不适合继续作为 `FlaUI.UIA3` 主运行时来重构。

原因不是代码没写完，而是真实客户端没有把关键控件稳定暴露给 UIA：

1. 顶部 `窗口分割` 没有被枚举到
2. `全屏 / 退出全屏` 没有被枚举到
3. 主动尝试布局面板验证后，仍未枚举到布局项
4. `VSClient` 渲染窗存在，但没有暴露可用于状态回读的 UIA 信息

因此下一阶段应直接转：

- 平台 SDK
- Web 插件
- 平台接口驱动的自建预览页

而不是继续把桌面客户端自动化作为主方案。
