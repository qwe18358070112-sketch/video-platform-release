# 视频平台自动轮询控制器（修复增强版）

这是一个用于“视频融合赋能平台 / 视频监控客户端”的自动轮询辅助项目，目标是实现：

- 宫格模式下按既定顺序自动轮询
- **单击选中 -> 双击放大 -> 停留 N 秒 -> 双击返回 -> 停留 N 秒 -> 下一路**
- 支持人工监管介入、暂停、步进、紧急恢复
- 同时兼容非全屏与全屏
- 允许跨电脑部署，而不是只绑死在开发机上

## 动作路径定义（最终以此为准）

本项目的标准单路动作路径不是“直接双击放大后就切下一路”，而是下面这条完整路径：

```text
单击选中
-> 等待 select_settle_ms
-> 双击放大
-> 放大停留 dwell_seconds
-> 双击返回宫格
-> 返回后停留 post_restore_dwell_seconds
-> 下一路
```

对应配置项：

- `timing.select_settle_ms`：单击选中后的稳定等待
- `timing.dwell_seconds`：放大后的停留秒数
- `timing.post_restore_dwell_seconds`：双击返回宫格后的停留秒数

如果你现场想改节奏，只需要改 `config.yaml`：

```yaml
timing:
  select_settle_ms: 220
  dwell_seconds: 4
  post_restore_dwell_seconds: 4
```

## 这次重点修复了什么

### 1. F11 紧急恢复逻辑修复
历史错误行为：
- F11 曾被错误处理成“返回宫格后直接跳过当前路”

新逻辑：
- F11 = 返回宫格并**重走当前未完成动作路径**
- 适用于：刚放大就返回、人工觉得画面没看够、按 F11 后希望继续检查当前路

### 2. F9 连续步进逻辑修复
旧逻辑：
- 暂停时 F9 只能有限排队，常被 `max_queued_next_steps=1` 卡住

新逻辑：
- `controls.max_queued_next_steps: 0` 表示不限制
- `hotkeys.next_cell_debounce_ms` 单独控制 F9，避免连续步进时被 F2/F11 共用防抖吞键
- 暂停状态下，F9 每按一次就：
  - 计算下一路
  - 自动鼠标点击选中下一路
  - 仍保持暂停，等待你继续按 F9 或按 F2 恢复

### 3. 黑屏 / 预览失败安全策略修复
- 现在默认 `detection.skip_on_detected_issue: true`
- `black_screen` 仍可按配置直接跳过，避免在纯黑 / 空白 tile 上反复乱点
- `preview_failure` 不再在 `SELECT_CONFIRM` 阶段直接跳过，而是继续执行完整动作路径
- 这样非政务网或低纹理失败页也能完成 `单击 -> 双击放大 -> 停留 -> 双击返回宫格`

### 4. 状态浮窗干扰修复
- 状态浮窗会自动短暂显示后隐藏，且信息提示会比之前停留更久，便于人工确认
- 提示栏现在会同步显示 `message / details / meta / hotkey`，并随程序阶段实时刷新，不再出现“功能变了但提示词没变”
- 浮窗改成了更轻量的多行卡片样式，视觉更清晰，同时保持点击穿透，不影响程序正常运行
- 即使关闭回调失效，浮窗也会按 stale 超时自毁，不再长时间卡在屏幕上
- 守卫会忽略程序自己的状态浮窗，不再把它误判成“前台窗口漂移”

### 5. 轮询顺序扩展
支持：
- `row_major` / `left_to_right`：从左到右、从上到下
- `column_major` / `top_to_bottom`：从上到下、从左到右
- `custom`：自定义物理编号顺序
- `favorites_name`：按左侧收藏夹的名称顺序映射到轮询顺序

### 5. 宫格布局扩展
支持：
- 4 宫格
- 6 宫格
- 9 宫格
- 12 宫格
- 其他类型的 12 宫格（通过 `layout_template` 实现，例如 `twelve_3x4`）

### 5. 全屏 / 非全屏统一
- 默认 `profiles.active_mode: auto`
- 启动后自动识别当前窗口是全屏还是非全屏
- 启动后自动识别当前窗口更像 4 / 6 / 9 / 12 中的哪一种宫格，并在运行时同步点击坐标
- 非全屏自动识别现在只走多信号闭环，不再在主流程里打开顶部 `窗口分割` 面板
- 非全屏自动识别同时参考视觉候选、分隔线结构、宫格几何估计这 3 类信号
- 支持运行时手动锁定 `全屏 / 非全屏` 和 `4 / 6 / 9 / 12 宫格`
- 状态浮窗会同步显示：当前模式、当前宫格、当前运行档位、当前顺序
- `auto` 会优先看界面控件是否仍是非全屏宫格（如 `收藏夹 / 搜索 / 视频监控配置 / 全部收藏`），再用窗口几何兜底
- 统一走同一套调度逻辑、热键逻辑、异常恢复逻辑

### 6. 跨电脑部署增强
- 配置里不再写死某一台电脑的 AHK 路径
- `controller.py` 会自动尝试常见 AutoHotkey 安装路径
- 提供 `.bat` 启动脚本、自测脚本、打包脚本

## 工程结构说明

核心模块：
- `app.py`：程序入口
- `scheduler.py`：状态机与热键调度核心
- `detector.py`：画面状态检测（放大 / 返回 / 黑屏 / 异常）
- `grid_mapper.py`：宫格切分与轮询顺序映射
- `layout_switcher.py`：顶部“窗口分割”布局切换
- `favorites_reader.py`：读取左侧收藏夹可见名称顺序
- `controller.py`：鼠标 / 双击 / ESC 恢复等输入执行
- `window_manager.py`：窗口发现与全屏/非全屏识别
- `common.py`：配置、数据结构、枚举
- `native_runtime/`：Windows 原生 UIA3 探针原型，用于验证是否值得迁移到原生自动化

辅助文件：
- `config.yaml`：当前运行配置
- `config.example.yaml`：完整示例配置
- `HOW_TO_USE.md`：从零开始的详细操作手册
- `CODEX_LOCAL_ADMIN_PROMPT.txt`：发给 Codex 的本机管理员执行提示词
- `self_test.py`：静态自测
- `build_release.py`：生成精简发布包
- `提示词_增强版.txt`：用于提升 Codex / vibe coding 修复效率

## 最短使用路径（第一次跑起来）

### 1. 安装依赖
推荐先打开 PowerShell，再进入项目目录执行：

```powershell
cd 你的项目目录
.\install_deps.bat
```

### 2. 标定窗口区域
先做非全屏标定：

```powershell
python app.py --calibrate windowed
```

再做全屏标定：

```powershell
python app.py --calibrate fullscreen
```

### 3. 检查标定结果是否画对

```powershell
python app.py --inspect-calibration windowed
python app.py --inspect-calibration fullscreen
```

也可以直接双击：
- `inspect_windowed.bat`
- `inspect_fullscreen.bat`

### 4. 跑静态自测

```powershell
python self_test.py
```

### 5. 启动自动轮询

```powershell
python app.py --run --mode auto
```

如果你想直接以“手动模式 + 手动宫格”启动，也可以：

```powershell
python app.py --run --mode windowed --layout 9
python app.py --run --mode fullscreen --layout 6
```

如果你想把程序直接拆成“固定宫格版本”，仓库里已经补了 4 套独立入口：

- [run_layout4_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout4_fixed.bat)
- [run_layout6_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout6_fixed.bat)
- [run_layout9_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout9_fixed.bat)
- [run_layout12_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout12_fixed.bat)
- [run_fixed_layout_selector.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_fixed_layout_selector.bat)

这些固定宫格版本会：

- 启动时直接锁定 `--layout`
- 禁用 `F1 / F7 / F8`
- 只保留 `F2 / F9 / F10 / F11`

说明见：

- [FIXED_LAYOUT_PROGRAMS.md](/home/lenovo/projects/video_platform_release/FIXED_LAYOUT_PROGRAMS.md)
- [fixed_layout_programs/README.md](/home/lenovo/projects/video_platform_release/fixed_layout_programs/README.md)
- [fixed_layout_manifest.json](/home/lenovo/projects/video_platform_release/fixed_layout_programs/fixed_layout_manifest.json)

固定宫格版本还加了单实例保护：

- `4 / 6 / 9 / 12` 这 4 套程序不会允许并发运行
- 如果前一套还没退出，就会直接提示实例锁冲突，避免多套程序抢热键

如果后续实测发现“全屏 / 窗口”自动识别也还会扰动，可以继续扩成 8 套：

```bash
python3 platform_spike/scripts/generate_fixed_layout_programs.py --include-modes
```

如果要把这些固定宫格版本分别发到其他 Windows 电脑上，可以直接独立打包：

```bash
python3 platform_spike/scripts/package_fixed_layout_programs.py
python3 platform_spike/scripts/package_fixed_layout_programs.py --include-modes
```

## 热键说明

- `F1`：切换 `自动识别 / 手动锁定`
- `F7`：切换 `非全屏 / 全屏` 目标；如果当前还是自动识别，会先切到手动锁定再切模式
- `F8`：切换 `12 / 9 / 6 / 4` 宫格目标；如果当前还是自动识别，会先切到手动锁定再切宫格
- `F2`：启动 / 暂停 / 继续
- `F9`：暂停时预选下一路；可连续多次按
- `F10`：安全停止并退出
- `F11`：紧急恢复到宫格，并重走当前未完成路径
- `F6`：清除异常冷却；暂停后界面正常时再按 `F2`，界面不正常时再按 `F11`

手动锁定的语义也改了：

- 当你按 `F1` 切到手动后，程序会先连续重识别当前现场，再把观察到的模式和宫格锁成手动目标
- 手动锁定状态下，程序仍会持续观测现场；只有“现场实际状态”和“手动目标”一致时才会恢复动作路径
- 暂停后如果你手工改了宫格或全屏状态，恢复前程序会重新核对，不再继续沿用旧宫格或旧模式
- 可选配置 `controls.runtime_hotkeys_drive_client_ui: true` 后，暂停态下的 `F7/F8` 可以直接驱动客户端切换；默认仍是“只改目标、恢复前校验”
- 异常冷却后如果程序仍在运行，直接按 `F6` 清冷却即可；如果已经暂停，界面正常用 `F6 -> F2`，界面不正常用 `F6 -> F11`
- 提示栏会同步显示 `控制 / 实际 / 目标 / 闭环`，让当前运行语义和界面提示保持一致

## 推荐的最小验收顺序

1. 先测动作路径：单击选中 -> 双击放大 -> 停留 -> 双击返回 -> 停留 -> 下一路
2. 再测 F11：确认不再直接跳下一路
3. 再测 F9 连按 3 次：确认能连续选中下一路
4. 再测人工暂停 / 继续 / 接管恢复
5. 再切到全屏测试
6. 再切到 9 / 6 / 4 宫格测试
7. 最后再测 `custom_sequence` 或 `favorites_name`

## 收藏夹名称排序怎么用

### 第一步：读取当前可见收藏夹名称

```powershell
python app.py --dump-favorites
```

如果你只是想只读确认当前真实状态，不启动轮询、不切宫格，可以直接执行：

```powershell
python app.py --inspect-runtime --mode auto
python app.py --inspect-runtime --mode windowed --layout 9
python app.py --inspect-runtime --mode fullscreen --layout 4
```

如果目标机上 UIA 能读取成功，会输出左侧收藏夹的名称列表，并缓存到：

- `tmp/favorites_cache.json`

## 原生 UIA3 探针

如果你要验证“这个客户端是否值得迁移到 Windows 原生自动化”，优先运行：

```bash
./windows_bridge.sh native-probe --open-layout-panel
```

它不会替代当前 Python 运行时，而是额外输出一份 JSON，回答下面这些问题：

- `窗口分割` 能不能被 UIA 稳定读到
- `全屏 / 退出全屏` 能不能被 UIA 稳定读到
- 布局面板展开后，`平均 / 水平 / 其他 / 4 / 6 / 9 / 12 / 13` 能不能被 UIA 枚举
- `VSClient` 渲染窗有没有暴露出可用的 UIA 信息

如果这条探针仍证明关键布局项无法稳定枚举，就不再继续堆 OpenCV 识别规则，直接转平台 SDK / Web 插件路线。

### 第二步：把名称写进 `grid.cell_labels`
把物理槽位与实际监控名称对应起来，例如：

```yaml
grid:
  order: favorites_name
  cell_labels:
    0: "大厅柱子口"
    1: "法雨寺停车场"
    2: "千步沙入口"
    3: "码头入口"
```

### 第三步：切到 `favorites_name`

```yaml
grid:
  order: favorites_name
```

程序会按左侧收藏夹可见顺序去匹配 `cell_labels`，生成轮询顺序。

> 注意：这一步是“按名称映射物理槽位”，不是直接去控制收藏夹树本身的展开收起。

## 自定义顺序怎么用

```yaml
grid:
  order: custom
  custom_sequence: [0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11]
```

这表示：
- 先轮询第一列
- 再轮询第二列
- 最后轮询第三列

## 切换 12 宫格类型怎么用

标准 12 宫格：

```yaml
grid:
  layout: 12
  layout_template: ""
```

切换到另一种 12 宫格（3 行 4 列）：

```yaml
grid:
  layout: 12
  layout_template: twelve_3x4
```

## 切换 4 / 6 / 9 / 12 / 13 布局怎么用

完整步骤见：`LAYOUT_SWITCH_MANUAL.md`


这次现场已经确认：

- 左侧收藏夹树里的 `9个画面 / 6个画面 / 4个画面` 不是实际布局切换入口
- 真实入口是顶部工具栏里的 `窗口分割`
- 本项目已经把这条路径固化成 CLI：

```powershell
python app.py --switch-layout 4
python app.py --switch-layout 6
python app.py --switch-layout 9
python app.py --switch-layout 12
python app.py --switch-layout 13
```

当前默认映射为：

- `4` -> `平均 / 4`
- `6` -> `水平 / 6`
- `9` -> `平均 / 9`
- `12` -> `其他 / 12`
- `13` -> `其他 / 13`

注意：

- `13` 仅用于现场切换与核对画面形态，当前自动轮询主流程仍按 `4 / 6 / 9 / 12` 支持
- 如果你只是想跑自动轮询，请先把客户端手动或通过 `--switch-layout` 切到目标宫格，再执行 `--run`
- `--switch-layout` 执行后要核对中央宫格是否真的切换成功，不能只看命令返回成功
- 如果你只是想确认当前真实状态，不要切宫格，优先执行 `python app.py --inspect-runtime ...`

## 自测

```powershell
python -m compileall .
python self_test.py
```

当前自测覆盖：
- `python -m compileall .`，并自动跳过 `.venv / dist / logs / tmp / __pycache__`
- 配置加载
- 4/6/9/12 宫格数量
- 自定义顺序
- 上到下顺序
- 收藏夹名称排序映射
- 12 宫格模板切换
- 运行时动作路径状态检查
- README / 部署说明 / 提示词 的动作路径语义检查
- `F11/F9` 语义文本检查

## 发布打包

```powershell
python build_release.py --output dist/video_platform_release.zip
```

输出的是精简后的发布包，不会把：
- `.git`
- `.venv`
- 大视频
- 历史备份
- 日志截图

一起塞进去。

## 当前仍需目标机实测的内容

由于当前开发容器不是 Windows 桌面环境，以下内容只能在目标机最终验收：
- 实际鼠标点击与双击是否命中客户端
- UIA 是否能稳定读取左侧收藏夹名称
- 目标客户端在你现场版本下的 ESC / 双击 / 返回宫格响应

纯 Python 逻辑、配置、顺序、模板、自测、打包流程已在当前环境完成静态验证。

## 这次新增的高风险防护：错误界面 / 错误窗口 / 错误点击自我修复

为了解决“客户端卡顿导致误点击，弹出新窗口或切到错误界面，但程序还在继续点击”的问题，本版新增了独立的 `runtime_guard.py` 守卫层。

它会做四件事：

1. **前台窗口漂移检测**
   - 检查前台窗口是否仍然是目标客户端
   - 若跳到同进程弹窗 / 相关窗口，优先自动处理
   - 若跳到其他窗口，先尝试回焦，不乱关别的程序

2. **错误界面检测**
   - 在普通网格 / 放大态判断之外，再额外检测“低纹理、整块纯色、明显不属于正常宫格/放大画面”的异常界面
   - 重点拦截：误点标题栏、误点空白区、卡顿后进入错误页面、弹窗遮挡后继续点击

3. **自动修复**
   - 对同进程弹窗：先 `ESC`，仍存在则尝试 `Alt+F4`
   - 对错误界面：回焦到客户端，再执行回宫格恢复
   - 自动修复成功后，**重走当前路径**，不直接跳下一路

4. **自动暂停留证**
   - 若连续触发错误达到阈值，程序会自动暂停，而不是继续乱点
   - 同时保存守卫截图到 `logs/guard`

推荐先看：
- `runtime_guard.py`
- `config.yaml` 里的 `runtime_guard`
- `CALIBRATION_GUIDE.md`
- `MIGRATION_GUIDE.md`

## 公开仓库说明

这是用于展示项目能力的公开代码仓库版本，已移除运行日志、发布产物、现场截图、运行时目录和本地配置文件。
