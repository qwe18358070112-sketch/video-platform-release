# 从零开始使用这套交付物（详细操作手册）

## 1. 先认识你拿到的文件

你拿到的核心目录就是这个项目文件夹。最重要的文件是：

- `README.md`：总说明，先看这个
- `HOW_TO_USE.md`：你现在正在看的详细操作手册
- `README_DEPLOY.md`：跨电脑部署说明
- `config.yaml`：运行配置，尤其是布局、顺序、停留时间
- `app.py`：主程序入口
- `self_test.py`：自测
- `CODEX_LOCAL_ADMIN_PROMPT.txt`：给 Codex 的完整提示词
- `run_auto.bat`：启动自动轮询
- `calibrate_windowed.bat`：标定非全屏
- `calibrate_fullscreen.bat`：标定全屏
- `inspect_windowed.bat` / `inspect_fullscreen.bat`：检查标定图
- `dump_favorites.bat`：读取左侧收藏夹名称

## 2. 你应该怎么开始

### 第一步：把项目放到固定目录
建议放到：

```text
D:\video_platform_release
```

不要放在临时下载目录里直接运行。

### 第二步：打开管理员终端
因为目标客户端很可能是管理员权限运行，所以你最好：

- 用“管理员身份运行”打开 PowerShell 或 Windows Terminal
- 再进入项目目录

```powershell
cd D:\video_platform_release
```

### 第三步：安装依赖

```powershell
.\install_deps.bat
```

安装完后建议先跑一次项目内静态编译检查：

```powershell
python -m compileall .
```

这条命令只检查项目源码，会自动跳过 `.venv / dist / logs / tmp / __pycache__`。

如果你想看更明确的输出，也可以手工执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果你的默认 `python` 指向 `3.13 RC`，建议后续直接使用：

```powershell
.\.venv\Scripts\python.exe self_test.py
```

原因是当前依赖里的 `pywin32` 在这类预发布解释器上经常没有可用轮子。

完整的宫格切换与自动识别说明见：`LAYOUT_SWITCH_MANUAL.md`

### 第四步：准备客户端界面
在“视频融合赋能平台”客户端里，先手动打开你要测试的宫格页面。

你至少先准备两种界面：
- 非全屏宫格
- 全屏宫格

如果你要切换 `4 / 6 / 9 / 12 / 13`，这次已经现场确认：

- 左侧收藏夹树里的 `9个画面 / 6个画面 / 4个画面` 不是实际布局切换入口
- 真实入口是顶部工具栏里的 `窗口分割`
- 可以直接用项目自带命令切换：

```powershell
python app.py --switch-layout 4
python app.py --switch-layout 6
python app.py --switch-layout 9
python app.py --switch-layout 12
python app.py --switch-layout 13
```

默认映射为：
- `4` -> `平均 / 4`
- `6` -> `水平 / 6`
- `9` -> `平均 / 9`
- `12` -> `其他 / 12`
- `13` -> `其他 / 13`

如果你只是想只读确认当前真实状态，不启动轮询、不切宫格，可以执行：

```powershell
python app.py --inspect-runtime --mode auto
python app.py --inspect-runtime --mode windowed --layout 12
python app.py --inspect-runtime --mode fullscreen --layout 6
```

输出会直接告诉你：
- 当前是全屏还是非全屏
- 当前按几宫格模式在运行
- 当前模式 / 宫格是自动还是手动
- 当前运行档位和轮询顺序

### 第五步：标定非全屏
让客户端停在非全屏宫格状态，然后执行：

```powershell
python app.py --calibrate windowed
```

按照屏幕提示，把预览区域框准。

### 第六步：标定全屏
让客户端停在全屏宫格状态，然后执行：

```powershell
python app.py --calibrate fullscreen
```

### 第七步：检查标定图
这是很关键的一步，很多“点不准”“放大错位”都出在这里。

```powershell
python app.py --inspect-calibration windowed
python app.py --inspect-calibration fullscreen
```

你要检查：
- 宫格区域有没有被完整覆盖
- 左侧收藏夹树有没有被错误框进去
- 顶部工具条有没有被错误框进去

如果框不准，就重新标定。

## 3. 第一次真正跑程序

先跑静态自测：

```powershell
python self_test.py
```

通过后再运行：

```powershell
python app.py --run --mode auto
```

程序启动后，热键是：
- `F1`：切换运行控制（自动识别 / 手动锁定）
- `F7`：切换目标模式（非全屏 / 全屏）；当前若还是自动，会先切到手动锁定
- `F8`：切换目标宫格（12 / 9 / 6 / 4）；当前若还是自动，会先切到手动锁定
- `F2`：启动 / 暂停 / 继续
- `F9`：暂停时选中下一路，但保持暂停
- `F10`：安全停止
- `F11`：紧急恢复到宫格并重走当前路
- `F6`：清除异常冷却；如果当前已经暂停，界面正常时再按 `F2` 继续，界面不正常时再按 `F11` 恢复

如果你已经按 `F1` 切到手动，程序会先重新识别当前现场，再把识别结果锁成手动目标。之后无论你是手工改客户端，还是在暂停态下用 `F7/F8` 改目标，程序恢复前都会再次核对“现场实际状态”与“手动目标”是否一致；不一致就继续保持暂停。

如果你希望暂停态下 `F7/F8` 直接驱动客户端切换，把配置改成：

```yaml
controls:
  runtime_hotkeys_drive_client_ui: true
  runtime_hotkeys_require_paused: true
```

默认配置下，`F7/F8` 只改程序目标，不直接切客户端界面。

### 异常冷却后的继续方式

如果程序提示“异常冷却中”：

- 程序还在运行：直接按一次 `F6`，程序后续会继续按当前路径轮巡
- 程序已经暂停且界面正常：按 `F6 -> F2`
- 程序已经暂停且界面不正常：按 `F6 -> F11`

这里的区别是：

- `F6` 只清冷却，不负责自动继续
- `F2` 负责继续当前路径
- `F11` 负责先做恢复，再重走当前路径

## 4. 你最先该验收什么

不要一上来就同时测所有功能。先按这个顺序：

### 验收 1：动作路径是否正确
你要看的不是“它有没有在动”，而是动作链是否完全正确：

```text
单击选中 -> 双击放大 -> 停留 N 秒 -> 双击返回 -> 停留 N 秒 -> 下一路
```

如果这里不对，先不要继续测其他功能。

### 验收 2：F11 是否正确
在刚放大时按 `F11`，看是否：
- 回宫格
- 重走当前路
- 不跳下一路

### 验收 3：F9 是否能连按
按 `F2` 暂停后，连续按 `F9` 3 次，确认：
- 每次都自动选中下一路
- 但程序仍保持暂停

### 验收 3.5：黑屏 / 预览失败处理是否符合现场语义
如果某一路已经是黑屏、纯色失败页或明显预览失败，确认：
- `black_screen` 仍会按配置安全跳过
- `preview_failure` 不会在选中后直接跳过，而是继续执行完整动作路径
- 整个过程中不会误点到其他窗口

### 验收 4：全屏是否一致
切到全屏再复测同样动作路径。

## 5. 最常改的配置项

### 改布局

```yaml
grid:
  layout: 12
```

可改成 `4 / 6 / 9 / 12`。

但要注意：

- `config.yaml` 里的 `grid.layout` 决定的是“程序怎么理解当前预览区切分”
- 客户端界面本身切到哪种宫格，应该优先使用 `python app.py --switch-layout ...`
- `--switch-layout` 执行后要先看中央宫格是否真的切换成功，再继续后续自动轮询
- 如果你只是想确认“当前实际是全屏/非全屏 + 几宫格”，优先执行 `python app.py --inspect-runtime ...`
- 不要再把左侧收藏夹树当成布局切换入口
- 如果你想直接锁定运行时模式，可以启动时附加 `--layout` 和 `--mode`

```powershell
python app.py --run --mode windowed --layout 9
python app.py --run --mode fullscreen --layout 6
```

### 固定宫格程序

如果你不想在运行时再切宫格，仓库里已经补了 4 套固定布局入口：

- [run_layout4_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout4_fixed.bat)
- [run_layout6_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout6_fixed.bat)
- [run_layout9_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout9_fixed.bat)
- [run_layout12_fixed.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_layout12_fixed.bat)
- [run_fixed_layout_selector.bat](/home/lenovo/projects/video_platform_release/fixed_layout_programs/run_fixed_layout_selector.bat)

这些入口会：

- 启动时固定 `--layout`
- 禁用 `F1 / F7 / F8`
- 只保留 `F2 / F9 / F10 / F11`
- 自带单实例锁，不能并发运行，避免多套程序抢热键

这样做的目标不是更智能，而是把“布局切换”这个变量从运行时直接拿掉，优先把单一布局场景跑通。

说明见：

- [FIXED_LAYOUT_PROGRAMS.md](/home/lenovo/projects/video_platform_release/FIXED_LAYOUT_PROGRAMS.md)
- [fixed_layout_programs/README.md](/home/lenovo/projects/video_platform_release/fixed_layout_programs/README.md)
- [fixed_layout_manifest.json](/home/lenovo/projects/video_platform_release/fixed_layout_programs/fixed_layout_manifest.json)

如果后续发现“全屏 / 窗口”自动识别也会扰动，可以继续拆成 8 套：

```powershell
python platform_spike/scripts/generate_fixed_layout_programs.py --include-modes
```

如果你要把这些固定宫格版本分别发到别的 Windows 电脑上，可以直接独立打包：

```powershell
python platform_spike/scripts/package_fixed_layout_programs.py
python platform_spike/scripts/package_fixed_layout_programs.py --include-modes
```

### 改顺序

从左到右：

```yaml
grid:
  order: row_major
```

从上到下：

```yaml
grid:
  order: column_major
```

自定义：

```yaml
grid:
  order: custom
  custom_sequence: [0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11]
```

### 改停留时间

当前默认值：

```yaml
timing:
  dwell_seconds: 4
  post_restore_dwell_seconds: 4
```

如果你现场还想更慢或更快，再按下面方式覆盖：

```yaml
timing:
  dwell_seconds: 8
  post_restore_dwell_seconds: 5
```

这里建议分开调：
- `dwell_seconds` 决定放大画面停留多久
- `post_restore_dwell_seconds` 决定返回宫格后停多久再切下一路

## 6. 收藏夹名称顺序怎么用

### 第一步：打开左侧收藏夹树
确保左侧收藏夹树已经展开，并且你想排序的名称当前可见。

### 第二步：读取名称

```powershell
python app.py --dump-favorites
```

### 第三步：填写名称映射
在 `config.yaml` 里写：

```yaml
grid:
  order: favorites_name
  cell_labels:
    0: "大厅柱子口"
    1: "法雨寺停车场"
    2: "千步沙入口"
    3: "码头入口"
```

### 第四步：再运行
程序会按左侧收藏夹当前可见顺序，匹配到你定义的物理窗格标签。

## 7. 什么时候需要 Codex 介入

你自己先做下面这几件事：
- 安装依赖
- 标定两套 profile
- 跑一次 self_test
- 跑一次 auto
- 记录问题现象

然后再把项目目录交给 Codex，并把 `CODEX_LOCAL_ADMIN_PROMPT.txt` 内容发给它。

## 8. 你给 Codex 之前要准备什么

你最好把这些信息一次性告诉它：
- 项目目录路径
- 客户端 exe 路径
- 你当前是全屏还是非全屏
- 你当前测的是 4/6/9/12 哪种宫格
- 当前动作路径哪里错了
- 现场是鼠标点不准、双击不生效、还是恢复逻辑不对
- 哪个日志文件记录了问题

## 9. 如果第一次运行不正常，先按这个顺序排查

1. 先看标定图准不准
2. 再看 `grid.click_point_ratio_y` 是否点到了标题栏
3. 再看客户端是不是管理员权限
4. 再看动作路径是不是被客户端版本改了
5. 如果窗口只是最大化，不要直接当成“全屏界面”；现在 `auto` 会优先按 `收藏夹 / 搜索 / 视频监控配置 / 全部收藏` 这些界面控件判定为非全屏
5. 再看日志里是卡在 `SELECT_TARGET`、`ZOOM_IN`、`GRID_CONFIRM` 还是 `ERROR_RECOVERY`

## 10. 这份交付物的边界

这份交付物已经把：
- 代码
- 配置
- 文档
- 自测
- 打包

都准备好了。

但真正的 Windows 桌面点击命中、双击命中、UIA 读取收藏夹，仍然需要在你的目标机最后做现场验证。

## 11. 现在建议你怎么让 Codex 全程代做

你现在最稳的做法不是继续在旧项目目录上直接改，而是：

1. 把新的交付包解压到固定目录，例如 `D:\video_platform_release`
2. 把这个新目录作为 Codex 的唯一工作目录
3. 给 Codex 管理员权限
4. 让 Codex 先阅读：
   - `README.md`
   - `HOW_TO_USE.md`
   - `CALIBRATION_GUIDE.md`
   - `MIGRATION_GUIDE.md`
   - `CODEX_LOCAL_ADMIN_PROMPT.txt`
5. 再让它依次完成：依赖安装 -> 标定 -> 检查标定 -> 自测 -> 运行验收 -> 修复 -> 再自测 -> 再打包

## 12. 标定详细操作步骤（人工也能看懂，Codex 也能照做）

更完整的标定说明在：`CALIBRATION_GUIDE.md`

最短版本如下：

### 非全屏标定
1. 先把客户端切到 **非全屏宫格**
2. 运行：`python app.py --calibrate windowed`
3. 程序提示“把鼠标移到预览区左上角”时，把鼠标放到**第一格左上边界与最外层预览区域左上边界重合的位置**
4. 按一次 `F6`
5. 程序提示“把鼠标移到预览区右下角”时，把鼠标放到**最后一格右下边界与最外层预览区域右下边界重合的位置**
6. 再按一次 `F6`
7. 运行：`python app.py --inspect-calibration windowed`
8. 检查蓝框是不是只包住视频宫格，不要包住左侧收藏夹、顶部导航条、底部状态区

### 全屏标定
步骤完全一样，只是把命令换成：
- `python app.py --calibrate fullscreen`
- `python app.py --inspect-calibration fullscreen`

### 标定常见错误
- 把左侧收藏夹也框进去
- 把顶部工具条也框进去
- 只框到第一排，没有框到全部宫格
- 鼠标点到了格子内部太靠里，导致边界被截掉
- 非全屏和全屏只做了一套标定

## 13. 程序现在新增了什么自我保护

本版新增：
- 错误界面识别
- 错误窗口识别
- 弹窗识别
- 自动 `ESC / Alt+F4 / 回焦 / 回宫格`
- 连续失败自动暂停
- 守卫截图留证

也就是说，程序不再只看“能不能双击放大”，还会看：
- 当前是不是目标窗口
- 当前是不是相关弹窗
- 当前是不是正常宫格 / 正常放大画面
- 当前是不是误点击后跳到陌生界面

## 14. 旧项目文件夹还要不要继续用

建议这样处理：

- **旧项目文件夹**：只作为备份保留，不再直接继续开发
- **新交付目录**：作为你和 Codex 之后唯一继续迭代的主目录

只有两类东西建议从旧目录迁移到新目录：
1. 你过去已经验证过、而且仍然适用的 `config.yaml` 参数
2. 需要比对问题的历史日志 / 截图 / 视频

更完整的迁移说明看：`MIGRATION_GUIDE.md`
