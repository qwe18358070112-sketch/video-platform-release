# 审查与修复报告

## 1. 我实际核对了什么

- 项目压缩包 `video_platform_release.zip`
- 测试视频 `程序测试视频.mp4`
- 现有说明 `codex当前输出.txt`
- 代码主链路：`app.py`、`window_manager.py`、`scheduler.py`、`layout_switcher.py`、`detector.py`、`grid_mapper.py`、`runtime_guard.py`、`self_test.py`

## 2. 代码审查结论

### 2.1 自动识别“全屏 / 非全屏”

当前代码里**已经实现**，主链路在：

- `window_manager.py -> WindowManager.detect_mode()`

它的判定顺序不是只看窗口大小，而是：

1. 先检查是否存在真实附属渲染面
2. 再检查非全屏界面标记，例如 `收藏夹 / 搜索 / 全部收藏 / 打开文件夹 / 视频监控配置`
3. 最后才用几何覆盖率兜底

这说明当前程序**具备自动识别全屏 / 非全屏的能力**。

### 2.2 自动识别“当前是几宫格”

当前代码里**已经实现**，主链路在：

- `scheduler.py -> _try_sync_runtime_layout()`
- `layout_switcher.py -> detect_current_layout()`

它会优先读“窗口分割”面板当前勾选的布局，失败时再回落到视觉同步，因此当前程序**具备自动识别 4 / 6 / 9 / 12 宫格的能力**。

注意：

- `13` 目前仍是“可切换、可核对”
- 自动轮询主流程仍按 `4 / 6 / 9 / 12` 正式支持

## 3. 我在当前环境真正复现到的实质问题

### 问题 1：`self_test.py` 在当前环境无法运行

原因不是主流程语法错误，而是 `layout_switcher.py` 在模块顶层硬导入 `pywinauto.Desktop`。

这会导致：

- 只要当前环境没装 `pywinauto`
- 或当前环境不是 Windows/UIA 环境
- `self_test.py` 还没开始执行测试就直接 `ModuleNotFoundError`

这会直接破坏“先静态验证，再上真机”的流程。

### 问题 2：`self_test.py` 自身有一条回归测试写错了

`zoom_probe_precedence_over_grid_probe` 这条测试原来没有把伪造预览图传入 `Detector.classify_runtime_view()`，而是间接触发了真实截图路径。

结果是：

- 测试本来想验证 probe 优先级
- 实际却意外走到了屏幕抓图逻辑
- 在无桌面环境下直接失败

### 问题 3：已有自测对 `layout_switcher.py` 的实现细节卡得过死

原测试把 `self._desktop.window(...)` 的具体写法当成唯一正确实现。为了让 `layout_switcher.py` 能在非 Windows 环境下被安全导入，我改成了“延迟要求 Desktop”的写法后，功能没变，但自测会误判失败。

### 问题 4：缺少一份单独的“宫格切换与自动识别操作手册”

项目虽然在 `README.md` 和 `HOW_TO_USE.md` 里分散写了不少内容，但对现场最常问的两件事还不够集中：

- 程序现在到底会不会自动识别全屏/非全屏、会不会自动识别 4/6/9/12
- 我手工切宫格到底该怎么做

## 4. 我实际做的修复

### 已修改文件

- `layout_switcher.py`
- `self_test.py`
- `README.md`
- `HOW_TO_USE.md`
- `build_release.py`
- `提示词.txt`
- `提示词_增强版.txt`
- `CODEX_LOCAL_ADMIN_PROMPT.txt`
- 新增：`LAYOUT_SWITCH_MANUAL.md`

### 修复内容

#### A. 修复 `layout_switcher.py` 的硬依赖导入问题

- 将 `pywinauto.Desktop` 改为可降级导入
- 新增 `_require_desktop()`
- 只有真正执行 UIA 相关操作时才要求 Desktop 可用

效果：

- `self_test.py` 可以在当前环境正常跑起来
- 运行时在目标 Windows 机上仍保留原有 UIA 功能

#### B. 修复 `self_test.py` 的两处错误

- 修正 `zoom_probe_precedence_over_grid_probe`，不再误走真实抓图路径
- 放宽 `runtime_layout_sync_prefers_uia_detected_layout` 对实现写法的限制，改为检查“有效实现路径”，而不是死卡某一行文本

#### C. 补齐“自动识别 + 手动切宫格”文档链路

- 新增 `LAYOUT_SWITCH_MANUAL.md`
- `README.md` 明确写入“自动识别当前宫格数”的说明
- `HOW_TO_USE.md` 增加对独立手册的引用
- 三份提示词都追加了“自动识别与手动切布局要求”

#### D. 更新发布包清单

- `build_release.py` 已把 `LAYOUT_SWITCH_MANUAL.md` 一起纳入发布包

## 5. 测试视频观察

从 `程序测试视频.mp4` 的抽帧看，视频里主要展示的是：

- 非全屏 6 宫格下的轮询
- 全屏 6 宫格下的轮询
- 动作路径表现为：单击选中 -> 双击放大 -> 停留 -> 双击返回 -> 下一路
- 黑屏/预览失败占位图存在，但程序仍在继续完成动作路径

也就是说：

- 这份视频里**没有直接显示出“自动识别功能完全缺失”**
- 更像是“这轮代码改动后，验证链条本身不稳，导致后续修复结果不够可信”

## 6. 我在当前环境完成的验证

### 静态检查

- `python3 -m compileall .`：通过
- `python3 self_test.py`：通过，`74/74`
- `python3 build_release.py --output dist/video_platform_release_fixed.zip`：通过

## 7. 当前环境无法替你伪造的事情

这里必须说清楚：

我当前能做的是**容器里的静态审查、代码修复、视频复核、打包验证**。

我**不能在这个 Linux 容器里假装完成你 Windows 现场的真实 GUI 自动化复测**，包括：

- 非全屏 `12 / 9 / 6 / 4` 真机点击
- 全屏 `12 / 9 / 6 / 4` 真机点击
- 真正的 UIA 控件读取
- `VSClient` 附属渲染面前台切换
- F8 / F9 / F10 / F11 对目标客户端的真实热键回归

所以这次我给你的结果是：

- **静态链路已修好**
- **文档 / 提示词 / 打包链路已补齐**
- **自动识别相关代码已审清，确认主链路存在**
- **Windows 真机复测仍要在目标机上继续执行**

## 8. 你接下来在目标机上的最短复测顺序

1. `python app.py --switch-layout 12`
2. 人工确认中央宫格真的变成 12
3. `python app.py --run --mode auto`
4. 先测非全屏 12
5. 再测非全屏 9 / 6 / 4
6. 再测全屏 12
7. 再测全屏 9 / 6 / 4
8. 再测 `F9 / F11 / favorites_name / custom_sequence`

## 9. 当前交付物

- 修复后发布包：`dist/video_platform_release_fixed.zip`
- 独立操作手册：`LAYOUT_SWITCH_MANUAL.md`
- 本报告：`AUDIT_AND_FIX_REPORT.md`
