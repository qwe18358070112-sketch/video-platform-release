# native_runtime 原型

这个目录不是新运行时的正式实现，而是第一阶段的原生 Windows 探针。

现在它同时承担第二阶段的“原生自动化引擎 sidecar”角色：

- `probe`：一次性探测 UIA 能力
- `serve`：常驻 JSON line sidecar，供 Python 主程序调用 Win32 原生窗口/输入能力

目标只有一个：

- 验证当前视频客户端的关键控件，是否能通过 `FlaUI + UIA3` 稳定枚举

重点验证对象：

- 主窗口
- 附属 `VSClient` 渲染窗
- 顶部 `窗口分割`
- `全屏 / 退出全屏`
- 布局面板里的 `平均 / 水平 / 其他 / 4 / 6 / 9 / 12 / 13`
- 左侧 `收藏夹 / 搜索 / 全部收藏 / 视频监控配置`

## 运行要求

- 必须在 Windows 上安装 `.NET SDK 8`
- 运行机器必须装有当前客户端
- 建议先把客户端切到目标界面，再执行探针

## 从当前仓库直接运行

优先使用现有桥接：

```bash
./windows_bridge.sh native-probe --open-layout-panel
```

如果要输出到指定文件：

```bash
./windows_bridge.sh native-probe --open-layout-panel --output tmp/native_uia_probe.json
```

如果要手工启动 sidecar 服务模式：

```powershell
dotnet run --project native_runtime/VideoPlatform.NativeProbe --framework net8.0-windows -- serve --repo-root D:\video_platform_release
```

当前 sidecar 负责的原生能力主要是：

- 主窗口发现与聚焦
- 相关窗口枚举
- 原生鼠标单击 / 双击
- ESC / Alt+F4 恢复类按键
- 运行时布局状态读取
- 运行时布局项原生点选
- UIA 信号作为可选增强，而不是唯一真相源

## 在 Windows 里直接运行

```powershell
cd 你的仓库目录
dotnet run --project native_runtime/VideoPlatform.NativeProbe --framework net8.0-windows -- --open-layout-panel --output tmp/native_uia_probe.json
```

## 输出怎么看

输出 JSON 里最重要的是：

- `targets[*].capabilities.foundWindowSplitControl`
- `targets[*].capabilities.foundFullscreenToggle`
- `targets[*].capabilities.foundLayoutSections`
- `targets[*].capabilities.foundLayoutOptions`
- `targets[*].capabilities.relatedRenderSurfaceCount`
- `targets[*].capabilities.renderSurfaceInterestingElementCount`
- `decision.recommendedPath`

判定原则：

- 如果 `窗口分割`、`全屏/退出全屏`、布局面板项都能稳定枚举，说明可以继续推进原生 UIA 迁移
- 如果顶部工具栏能读到，但 `VSClient` 渲染窗没有稳定 UIA 回读，就只能把 UIA 用在工具栏和面板，不再把视频内容识别当主状态源
- 如果布局面板主动展开后仍读不到布局项，说明应优先转平台 SDK / Web 插件路线
- 如果 UIA 信号稀缺，但 Win32 窗口与输入链稳定，仍可走“Python 调度层 + .NET 原生自动化引擎”的混合路线
