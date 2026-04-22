# video_platform_release 项目代码审查与整改方案

## 一、结论

这不是单一的“识别算法不准”问题，核心是 **运行时状态模型设计有缺口**：

1. **观察到的实际状态**（当前现场到底是全屏/窗口、4/6/9/12 宫格、宫格页/放大页）
2. **用户/热键请求的目标状态**（F1/F7/F8 设定的目标）
3. **调度器执行时使用的有效状态**（真正用于点坐标、判断是否继续运行的状态）

这三者在当前实现里被混用了，导致：

- 暂停后切手动，再手工改变客户端宫格/全屏状态，程序**不会把你的手工现场当成“观察到的实际状态”重新接管**；
- 恢复运行和重启运行时，程序有时把“布局同步成功”误当成“已经确认当前页面就是宫格页”；
- 启动后/恢复后，**全屏与窗口识别过度依赖几何尺寸阈值**，现场稍有 DPI、边框、任务栏、屏幕缩放、多显示器差异，就容易错判；
- 当前缓存只覆盖 **windowed 布局**，没有完整保存/回放 **fullscreen + layout** 的运行时画像，所以“关掉再启动”后经常无法恢复真实现场。

因此你现在看到的“各个功能没衔接、看起来像独立的”这个判断是对的，根因不是功能完全没有，而是**状态流没有闭环**。

---

## 二、本次审查覆盖的关键文件

已审查的关键入口与核心模块包括：

- `app.py`
- `scheduler.py`
- `window_manager.py`
- `detector.py`
- `controller.py`
- `grid_mapper.py`
- `layout_switcher.py`
- `status_runtime.py`
- `runtime_guard.py`
- `config.yaml`
- `README.md`
- `HOW_TO_USE.md`
- `LAYOUT_SWITCH_MANUAL.md`
- `self_test.py`

另外，项目自带 `self_test.py` 静态自检通过（109/109 通过），说明当前问题不是“代码跑不起来”，而是 **在线运行状态机与现场状态接管逻辑存在设计/实现问题**。静态自检无法覆盖你描述的现场链路。

---

## 三、与你反馈问题直接对应的根因

### 根因 1：手动模式把“目标状态”直接当成“实际状态”使用

### 代码位置

- `scheduler.py:2065-2105`
- `scheduler.py:2648-2668`
- `scheduler.py:3468-3473`

### 现状

在 `_refresh_window_context()` 中：

- 如果已经是手动控制，并且 `requested_mode` 是 `windowed/fullscreen`，代码直接：
  - `self._current_mode = self._requested_mode`
- 如果已经是手动控制，并且 `requested_layout` 不为空，代码直接：
  - `self._runtime_layout = int(self._requested_layout)`

也就是说：

- 手动模式下，程序**不再保留一份“观察到的当前实际模式/宫格”**；
- 它直接把你请求的目标值当成当前真实值，随后立刻用这个值去建宫格坐标、做动作路径。

在 `_try_sync_runtime_layout()` 里，手动模式下甚至会把 `requested_layout` 当成 `manual_profile_lock` 的确认结果直接返回成功。

在 `_runtime_profile_label()` 里，手动模式下浮窗上显示的“实际档位”，实际上也是请求值，不是观察值。

### 对应你的现象

这正好对应你说的：

- 按 F1 切手动后，再去手工改客户端宫格/全屏状态；
- 程序后续不能按你现场调整后的真实界面继续跑；
- 各个功能像独立的，没有真正衔接。

因为当前实现里：**手动模式并不是“重新接管现场”，而是“停止识别，改为盲信目标值”**。

---

### 根因 2：把“布局同步成功”误当成“当前界面已经确认是宫格页”

### 代码位置

- `scheduler.py:1799-1863`
- `scheduler.py:3133-3188`

### 现状

在 `_ensure_prepare_target_grid()` 中：

- 先识别 `actual_view`
- 如果识别结果不是 GRID，代码执行：
  - `if self._try_sync_runtime_layout(reason="prepare_target_preflight"): return True`

这有逻辑问题：

- `_try_sync_runtime_layout()` 的职责只是**同步/确认布局数**；
- 它**不能证明当前界面一定已经是宫格页**；
- 但当前代码把它的成功，直接当成“可以继续 PREPARE_TARGET”的证据。

同样，在 `_resume_after_pause()` 中：

- 如果 `actual_view != GRID`，但 `_try_sync_runtime_layout()` 返回成功，代码直接：
  - `actual_view = VisualViewState.GRID`

这一步也是错误的：

- “布局数同步成功” ≠ “当前画面已经是宫格页”
- 正确做法应该是：**同步布局后重新分类画面**，而不是直接把 view 改成 GRID。

### 对应你的现象

这会直接造成：

- 暂停后恢复时，程序在放大页/错误页/陌生页上继续按宫格路径点；
- 手动改了布局后，系统以为已经“现场闭环成功”，但实际上并没有回到宫格页；
- 自动识别会错乱，尤其是在暂停、恢复、重启这些状态切换点。

这是本项目里我认为最关键、最确定、最该优先修复的一个运行时 bug。

---

### 根因 3：全屏 / 非全屏识别过度依赖窗口几何阈值，现场稍有偏差就错判

### 代码位置

- `window_manager.py:114-186`
- `config.yaml`
  - `fullscreen_coverage_ratio: 0.96`
  - `client_margin_tolerance_px: 8`

### 现状

`detect_mode()` 当前逻辑是：

1. 先看 client_rect 对 monitor_rect 的覆盖率和左上对齐；
2. 满足阈值才认为可能是 fullscreen；
3. **如果不满足，就直接走几何 fast-path，判成 windowed**。

问题在于：

- 0.96 覆盖率 + 8 px 对齐容差，现场太苛刻；
- Windows 缩放、DPI、边框、任务栏、自定义标题栏、多显示器偏移，都可能导致“真全屏”不满足该几何条件；
- 一旦不满足，代码就**直接返回 windowed**，后面的证据（附属渲染窗体、UIA 状态、全屏按钮状态）根本来不及综合判断。

### 对应你的现象

这正对应：

- 你暂停后手工切成全屏/窗口，程序无法正确识别；
- 你重启程序后，也经常无法识别当前到底是全屏还是窗口。

因为它并不是“综合证据判断”，而是“几何阈值没过就先入为主判成窗口”。

---

### 根因 4：运行时画像缓存只覆盖 windowed，不覆盖 fullscreen

### 代码位置

- `scheduler.py:1305-1321`
- `scheduler.py:1441-1473`

### 现状

`_runtime_layout_cache_payload()` 明确要求：

- `self._current_mode == "windowed"` 才会返回 payload。

也就是说当前缓存只保存：

- windowed 模式
- layout
- client_width/client_height
- monitor_width/monitor_height 等

但没有对应的：

- fullscreen 画像
- fullscreen 下的 runtime layout
- fullscreen 识别置信度
- fullscreen 下的 client/monitor 关系

### 对应你的现象

这会导致：

- 关闭程序再启动后，windowed 可能还能借缓存部分恢复；
- fullscreen 基本只能重新靠一次识别流程判断；
- 一旦识别流程又被上面的几何阈值误导，就会出现“重启后仍然识别不到当前状态”。

---

### 根因 5：热键语义和用户直觉不一致

### 代码位置

- `README.md:183-195`
- `HOW_TO_USE.md:162-170`
- `LAYOUT_SWITCH_MANUAL.md:58-65`
- `self_test.py:2884-2886`

### 现状

文档里明确说明：

- `F1`：切自动/手动
- `F7`：切目标模式
- `F8`：切目标宫格
- 手动锁定后，程序会“直接信任你手动匹配好的模式和宫格”，**不再自动识别**。

`self_test.py` 还显式限制调度器运行时不要调用：

- `self._layout_switcher.switch_runtime_layout(...)`
- `self._layout_switcher.switch_mode(...)`

也就是说当前设计更像：

- F7/F8 是改“程序内部目标”；
- 不是直接驱动视频平台客户端切 UI；
- 程序默认假设“你已经把现场改好了”。

### 对应你的现象

所以你感觉：

- 快捷键、手工切换、自动识别之间没有打通；
- 看起来像几套独立功能。

这是因为产品语义本身就是分裂的：

- 一套是“客户端现场状态”
- 一套是“程序目标状态”
- 但没有明确的“同步当前现场为目标”或“把目标驱动到客户端现场”的中间动作。

---

### 根因 6：状态浮窗 / 状态摘要在手动模式下会误导

### 代码位置

- `scheduler.py:3468-3478`
- `LAYOUT_SWITCH_MANUAL.md:65`

### 现状

操作手册写的是：

- 状态浮窗会显示“实际模式/宫格、目标模式/宫格、是否闭环匹配、当前顺序”。

但真实代码里，手动模式下“实际模式/宫格”来自请求值，不是真实观察值。

### 对应你的现象

这会让你在现场调试时误以为：

- 程序已经正确识别当前状态；
- 实际上只是内部目标被显示出来了。

这也是你会觉得“自动识别错乱”的一部分原因——因为显示层本身就把目标和实际混了。

---

## 四、为什么会导致“图像识别不准、动作路径不准”

你补充的这个问题，核心答案不是“模型不够强”，而是：

### 1）识别上下文被污染了

如果程序把：

- `requested_mode/requested_layout`
- 当成 `current_mode/runtime_layout`

那么后续 detector 和 grid_mapper 接收到的“上下文”就是错的：

- 宫格切分基于错误 layout；
- 预览区域可能套用了错误 profile；
- 当前应该看作 grid 还是 zoomed 的判别基准被污染。

这会让图像识别天然不稳定。

### 2）动作坐标建立在错误布局上

`grid_mapper.py` 按 `preview_rect + runtime_layout` 建 cell。

只要 `runtime_layout` 是错的：

- 第 3 路可能被当成第 5 路；
- 双击位置可能落到分隔线、叠加层或错误视频窗；
- 返回宫格后下一步继续偏移。

### 3）动作前后缺少严格的“状态验证”

虽然当前项目已有一些确认逻辑（select confirm / zoom confirm / grid confirm），但在暂停恢复、布局同步、模式恢复这些关键节点上，存在“把同步结果当成视图结果”的短路逻辑。

这会让动作路径变成：

- 没确认真的回到宫格
- 就开始下一次 click/select/zoom

结果当然容易跑偏。

### 4）识别没有建立“观测状态机”

当前更像是：

- 某一步拿当前帧判断一下
- 然后结合少量历史 probe

但缺一套稳定的、独立的运行时观测状态机，例如：

- `GRID`
- `SELECTED`
- `ZOOMED`
- `UNKNOWN`
- `ERROR_INTERFACE`
- `RECOVERING`

没有这套状态机，暂停/恢复/手动接管/重启时，图像识别和动作路径就很容易各走各的。

---

## 五、整改优先级

建议按下面 4 个阶段整改。

---

## 阶段 A：先修最关键的运行时 bug（立即止血）

### 目标

先解决：

- 暂停后恢复乱跑
- 手工改布局/全屏后恢复乱识别
- 重启后错误继承状态

### 必改项 A1：严格区分“观察值 / 目标值 / 执行值”

### 新增数据结构建议

新增两个 dataclass：

```python
@dataclass
class ObservedRuntimeState:
    mode: Literal["windowed", "fullscreen", "unknown"]
    layout: int | None
    view: VisualViewState
    mode_confidence: float
    layout_confidence: float
    view_confidence: float
    source: str
    updated_at: float

@dataclass
class TargetRuntimeState:
    control_source: Literal["auto", "manual"]
    requested_mode: Literal["auto", "windowed", "fullscreen"]
    requested_layout: int | None
```

调度器里至少要同时持有：

- `observed_state`
- `target_state`
- `effective_state`

其中：

- `observed_state`：永远来自现场检测，**无论是否手动模式都要持续维护**
- `target_state`：F1/F7/F8 或启动参数设定的目标
- `effective_state`：当前这一步真正用于执行的状态（通常由 observed/target 协商得出）

### 必改项 A2：修改 `_refresh_window_context()`

### 当前错误

手动模式下直接：

- `self._current_mode = self._requested_mode`
- `self._runtime_layout = requested_layout`

### 正确改法

`_refresh_window_context()` 必须始终做两件事：

1. **先算 observed_mode / observed_layout**
2. 再根据 control source 决定 effective_mode / effective_layout

伪代码：

```python
def _refresh_window_context(self, *, fast: bool = False) -> None:
    self._window_info = ...

    observed_mode, mode_conf = self._detect_observed_mode(self._window_info)
    observed_layout, layout_conf = self._detect_observed_layout(...)

    self._observed_state.mode = observed_mode
    self._observed_state.layout = observed_layout
    self._observed_state.mode_confidence = mode_conf
    self._observed_state.layout_confidence = layout_conf

    if self._profile_control_manual:
        effective_mode = self._requested_mode if self._requested_mode in {"windowed", "fullscreen"} else observed_mode
        effective_layout = self._requested_layout or observed_layout or self._config.grid.layout
    else:
        effective_mode = observed_mode
        effective_layout = observed_layout or self._config.grid.layout

    self._effective_mode = effective_mode
    self._effective_layout = effective_layout
    self._preview_rect = profile_of(effective_mode).to_rect(...)
    self._cells = self._grid_mapper.build_cells(self._preview_rect, effective_layout, ...)
```

### 必改项 A3：禁止把“布局同步成功”直接当成 GRID

#### 需要修改

- `scheduler.py:_ensure_prepare_target_grid()`
- `scheduler.py:_resume_after_pause()`

### 当前错误示意

```python
if actual_view != GRID and self._try_sync_runtime_layout(...):
    actual_view = GRID
```

### 正确改法

```python
if actual_view != VisualViewState.GRID:
    synced = self._try_sync_runtime_layout(reason="resume_reconcile")
    if synced:
        self._refresh_window_context()
        actual_view, metrics = self._classify_current_view(refresh_context=False)

if actual_view != VisualViewState.GRID:
    # 才允许真正执行 recover_to_grid
```

原则只有一个：

> **布局同步** 只能更新 layout，不能直接证明当前 view=GRID。

### 必改项 A4：手动模式下浮窗必须同时显示“观察 / 目标 / 执行”

建议把状态摘要改成：

- 控制：自动 / 手动
- 观察：全屏 9宫格 / 窗口 12宫格 / 未知
- 目标：全屏 12宫格
- 执行：本轮按全屏 12宫格运行
- 闭环：观察是否匹配目标

而不是现在这种把“目标”伪装成“实际”。

---

## 阶段 B：重构全屏/宫格识别为“多证据打分 + 置信度 + 迟滞”

### 目标

解决：

- 当前全屏/窗口识别容易错
- 宫格数识别在暂停/重启后容易抖动

### 必改项 B1：`detect_mode()` 改成多证据评分，不允许几何 fast-path 直接盖棺定论

### 当前逻辑问题

- 几何条件不满足 → 直接 windowed

### 建议改成

对每种 mode 分别累积分数：

```python
def detect_mode_scored(window_info):
    fullscreen_score = 0.0
    windowed_score = 0.0
    evidence = {}

    if attached_surface:
        fullscreen_score += 0.35
    if fullscreen_toggle_checked:
        fullscreen_score += 0.20
    if fullscreen_geometry_candidate:
        fullscreen_score += 0.25
    else:
        windowed_score += 0.15

    if windowed_ui_markers:
        windowed_score += 0.45

    # 还可加入：顶部栏可见性、侧边收藏夹可见性、标题区高度特征、历史模式惯性

    if abs(fullscreen_score - windowed_score) < 0.15:
        return "unknown", confidence

    return ("fullscreen" if fullscreen_score > windowed_score else "windowed"), confidence
```

### 参数建议（临时止血）

在根治重构前，可先把：

- `fullscreen_coverage_ratio`: `0.96 -> 0.92`（或现场验证后 0.90~0.93）
- `client_margin_tolerance_px`: `8 -> 16`（或现场验证后 16~24）

注意：这只是临时止血，不是根治。

### 必改项 B2：加入识别迟滞 / 稳定窗口

不要单帧切模式。

建议：

- 连续 3 帧里至少 2 帧同结论，才改变 `observed_mode`
- 连续 3 次 layout 候选中同一个 layout 得分领先，才提交 `observed_layout`

这能显著减少暂停恢复、刚切换全屏时的一两帧抖动。

### 必改项 B3：保存完整 runtime profile cache（含 fullscreen）

新增统一缓存格式，例如：

```json
{
  "version": 2,
  "observed_mode": "fullscreen",
  "observed_layout": 9,
  "effective_mode": "fullscreen",
  "effective_layout": 9,
  "mode_confidence": 0.88,
  "layout_confidence": 0.84,
  "source": "runtime_observation",
  "updated_at": 1712345678.123,
  "title": "视频融合赋能平台",
  "process_name": "VideoClient.exe",
  "client_width": 1920,
  "client_height": 1040,
  "monitor_width": 1920,
  "monitor_height": 1080
}
```

启动时：

- 先加载 cache
- 再进行一次轻量 reverify
- reverify 不通过才丢弃缓存

这样重启后就不会完全靠一次冷启动检测盲判。

---

## 阶段 C：把“手动接管”和“客户端实际切换”真正打通

### 目标

解决：

- F1/F7/F8 只改内部目标，不改客户端现场
- 你手工改了客户端，程序又不重新观察现场

### 必改项 C1：明确三种动作语义

建议把热键语义拆清楚：

#### 方案一（更推荐）

- `F1`：切换控制源（自动 / 手动）
- `F7`：只改目标模式
- `F8`：只改目标宫格
- `F3`：**把当前现场同步为目标**（capture current observed -> target）
- `Ctrl+F7`：**驱动客户端切模式**（真正调用 `layout_switcher.switch_mode`）
- `Ctrl+F8`：**驱动客户端切宫格**（真正调用 `layout_switcher.switch_runtime_layout`）

这样用户语义最清楚：

- 我只是改程序目标？按 F7/F8
- 我要让程序真正去切客户端？按 Ctrl+F7/Ctrl+F8
- 我已经手工切好了客户端，要让程序认现场？按 F3

#### 方案二（兼容旧习惯）

保持 F7/F8 不变，但增加配置项：

```yaml
hotkeys:
  f7_f8_apply_to_client: true
```

开启后，F7/F8 除了改内部目标，也会尝试真正切客户端。

### 必改项 C2：暂停恢复时增加“现场重采样”步骤

恢复流程建议改成：

1. 回焦目标客户端
2. 重新采样 observed_mode / observed_layout / observed_view
3. 若手动模式且“观察值 != 目标值”
   - 浮窗明确提示“现场与目标不一致”
   - 不要直接继续点
   - 由配置决定：
     - 要么自动调整客户端到目标
     - 要么停在 `PAUSED_MISMATCH`
4. 只有当 view=GRID 且 effective_layout 有效时，才重走动作路径

伪代码：

```python
def _resume_after_pause(self):
    focus_target_window()
    refresh_window_context()
    observed = self._observed_state

    if self._profile_control_manual:
        mismatch = not self._observed_matches_target()
        if mismatch:
            self._pause_for_detected_issue("manual_target_mismatch")
            return

    actual_view, metrics = self._classify_current_view(refresh_context=False)
    if actual_view != VisualViewState.GRID:
        recover_to_grid()
        refresh_window_context()
        actual_view, metrics = self._classify_current_view(refresh_context=False)
        if actual_view != VisualViewState.GRID:
            self._pause_for_detected_issue("resume_not_grid")
            return

    restart_current_path()
```

---

## 阶段 D：提升图像识别准确率与动作路径准确率

这是你补充的重点，我单独展开。

### 目标

让程序在运行过程中做到：

- 更准确识别当前是不是宫格 / 放大 / 错误页 / 陌生页
- 更准确识别当前是几宫格、是不是全屏
- 更准确执行点击、放大、返回宫格的动作路径

### D1：建立独立的“运行时观测状态机”

建议定义：

```python
class RuntimeViewState(Enum):
    GRID = "grid"
    SELECTED = "selected"
    ZOOMED = "zoomed"
    UNKNOWN = "unknown"
    ERROR_INTERFACE = "error_interface"
    RECOVERING = "recovering"
```

要求：

- 每次动作前后都更新 `observed_view`
- 不是只在部分节点临时判断
- 调度器状态机的跳转必须依赖这个 `observed_view`

例如：

- `PREPARE_TARGET` 前必须确认 `observed_view == GRID`
- `ZOOM_IN` 后必须确认 `observed_view == ZOOMED`
- `ZOOM_OUT` / `RECOVER` 后必须确认 `observed_view == GRID`

### D2：图像识别采用“多信号投票 + 分数制”

当前 `detector.py` 已经有这些好基础：

- probe 对比
- divider 结构估计
- continuity 指标
- low_texture 容错

整改时不要推倒重来，而是要统一为“打分器”。

例如判断 `GRID`：

- `grid_probe` 相似度
- 分隔线行列估计接近目标宫格
- 重复结构强
- active cell 区域与全局结构一致
- 错误页特征分低

判断 `ZOOMED`：

- `zoom_probe` 相似度
- 中央主视图扩张明显
- 分隔线显著减少/消失
- active cell 内容连续性增强

每个状态给一组 score：

```python
scores = {
    "grid": ...,
    "zoomed": ...,
    "error_interface": ...,
    "unknown": ...,
}
```

取最高分，但要求：

- 最高分超过阈值
- 与第二名拉开最小 margin
- 否则进入 `UNKNOWN`

### D3：动作前必须做“落点合法性校验”

当前点位来源主要是 `grid_mapper`。整改时建议在动作前增加：

1. 点位必须落在 `preview_rect` 内
2. 点位距离分隔线要有最小安全边距
3. 若底部 overlay 安全条开启，需重新计算底边有效区域
4. 全屏/窗口切换后必须重新 build cells，不能沿用旧 cells

建议新增：

```python
def validate_action_point(cell, preview_rect, divider_map, safe_margins) -> bool:
    ...
```

### D4：每一步动作都要有“期望变化”和“失败回滚”

动作路径要从“命令式点击”改成“可验证事务”。

#### 选中动作

期望：

- active cell 周边或内容发生局部变化
- 当前 view 仍然应是 GRID 或 SELECTED

失败时：

- 重试一次
- 仍失败则停在 `PREPARE_TARGET`

#### 放大动作

期望：

- 视图从 GRID/SELECTED 进入 ZOOMED
- 中央区域扩张、分隔线减少、zoom probe 得分上升

失败时：

- 再选中一次后重试双击
- 再失败则进入 recover

#### 返回宫格动作

期望：

- 从 ZOOMED/ERROR_INTERFACE 回到 GRID
- grid_probe 接近基准图
- divider 结构恢复

失败时：

- ESC
- 重新 classify
- 仍失败则 pause + 标记 issue

### D5：引入“多帧确认”，不要单帧就下结论

对于以下关键状态：

- 模式（fullscreen/windowed）
- layout（4/6/9/12）
- view（grid/zoomed）

建议都采用：

- 连续 N 帧（通常 3 帧）
- 多数票 + 平均分
- 才改变 stable state

这样能明显改善：

- 刚 pause/resume 时的一帧黑场
- 切全屏动画中的过渡帧
- 双击放大的一过性模糊

### D6：建立“动作路径账本”

建议每一轮 cycle 记录：

```python
{
  "cycle_id": 123,
  "cell_index": 5,
  "before": {"mode": ..., "layout": ..., "view": ...},
  "action": "zoom_in",
  "after": {"mode": ..., "layout": ..., "view": ...},
  "verified": true,
  "retry_count": 0,
  "recovery_used": false
}
```

作用：

- 便于追查到底在哪一步跑偏
- 便于统计哪类动作最容易失败
- 便于后续做重放测试

### D7：建立真实样本库和回放测试

你这个项目不能只靠静态自检。建议新增：

#### 样本维度

- windowed / fullscreen
- 4 / 6 / 9 / 12 宫格
- GRID / ZOOMED / ERROR_INTERFACE / UNKNOWN
- 正常网络 / 黑屏 / 低纹理 / 错误页 / 弹窗遮挡

#### 测试类型

1. **离线识别测试**
   - 输入截图
   - 输出 mode/layout/view
   - 比对标注结果

2. **动作路径回放测试**
   - 输入一组 before/after 截图序列
   - 验证 select/zoom/recover 的状态跳转是否正确

3. **状态机测试**
   - 启动 -> 暂停 -> 手动切全屏/宫格 -> 恢复
   - 启动 -> 重启 -> 读取缓存 -> 复核
   - 手动模式下现场与目标不一致时是否正确停机/提示

---

## 六、建议的详细开发改造步骤

下面给一套更贴近实际落地的改造顺序。

### 第 1 步：先把状态变量拆开

在 `scheduler.py` 中新增：

- `_observed_mode`
- `_observed_layout`
- `_observed_view`
- `_effective_mode`
- `_effective_layout`

保留：

- `_requested_mode`
- `_requested_layout`

然后逐步替换所有原来直接访问：

- `_current_mode`
- `_runtime_layout`

的代码，改为按语义访问。

### 第 2 步：改 `_refresh_window_context()`

要求：

- 永远先更新 observed
- 再计算 effective
- 再 build cells

同时，把 `manual_profile_lock` 的语义改成：

- “锁定目标，不锁定观察值”

### 第 3 步：修复暂停恢复逻辑

先改：

- `_resume_after_pause()`
- `_ensure_prepare_target_grid()`

硬性规则：

- layout sync 后一定重新 classify view
- 未确认 GRID，不准继续点击路径

### 第 4 步：改 `window_manager.detect_mode()`

把当前的几何 fast-path 改成分数式综合判断。

同时把模式识别结果返回为：

```python
(mode, confidence, evidence)
```

便于浮窗和日志显示“为什么判成这个模式”。

### 第 5 步：统一 runtime cache

把现在的 `windowed runtime layout cache` 升级为 `runtime profile cache`，同时支持：

- windowed
- fullscreen
- mode confidence
- layout confidence
- last observed view

### 第 6 步：改浮窗与日志

浮窗显示：

- 观察值
- 目标值
- 执行值
- confidence
- mismatch 标志

日志关键项至少包括：

- observed_mode / observed_layout / observed_view
- requested_mode / requested_layout
- effective_mode / effective_layout
- view classification metrics
- resume reason / recovery reason

### 第 7 步：补自动化测试

新增测试用例至少包括：

1. 自动模式启动，识别 fullscreen + 9 宫格
2. 暂停后手工切到 4 宫格，恢复时重新识别
3. 手动模式下，观察值与目标值不一致，程序不得继续执行
4. 重启后从 cache 恢复 fullscreen + layout
5. layout sync 成功但 view 非 GRID，不得继续执行

---

## 七、临时止血方案（在正式改代码前）

如果你现在就要先尽量跑起来，建议现场先这样用：

### 止血方案 1：优先只用自动模式，不要用 F1 手动锁定后再手工改现场

因为当前版本手动模式本质上是“盲信目标”，不是“重采样现场”。

### 止血方案 2：手工切换全屏/宫格后，先执行只读检查，不要直接继续跑

优先执行：

```bash
python app.py --inspect-runtime --inspect-runtime-candidates
```

先看程序此刻识别出来的是：

- 全屏 / 窗口
- 4 / 6 / 9 / 12 宫格

确认无误后再运行。

### 止血方案 3：先放宽全屏几何阈值

先在 `config.yaml` 试调：

```yaml
window:
  fullscreen_coverage_ratio: 0.92
  client_margin_tolerance_px: 16
```

如果现场还是识别不稳，再逐步试：

- `coverage_ratio`: `0.90 ~ 0.93`
- `margin_tolerance`: `16 ~ 24`

### 止血方案 4：重启前尽量让客户端停在明确的“正常宫格页”

不要让程序停在：

- 放大页
- 黑屏页
- 异常弹窗页
- 错误提示页

否则重启后的冷启动识别更容易误判。

---

## 八、建议的测试矩阵

整改完成后，至少做下面这个矩阵：

### 维度 1：模式

- windowed
- fullscreen

### 维度 2：布局

- 4
- 6
- 9
- 12

### 维度 3：启动方式

- 冷启动
- 暂停 -> 恢复
- 关闭程序 -> 重启
- 手动模式下切换目标
- 手工改客户端现场后恢复

### 维度 4：界面状态

- 正常 GRID
- 放大态 ZOOMED
- 低纹理页
- 黑屏页
- 错误页
- 前台被其他窗口抢焦点

### 验收标准

1. 模式识别准确率 >= 99%（现场采样集）
2. layout 识别准确率 >= 98%
3. 暂停恢复后，不得从非 GRID 状态直接继续点选
4. 手动模式下，观察值与目标值不一致时必须提示并阻止继续执行
5. 重启后能正确恢复 last stable runtime profile，并完成一次 reverify

---

## 九、我对当前项目的整体评价

### 优点

1. 项目结构已经比较模块化：
   - 窗口识别、布局映射、动作控制、运行时保护、浮窗状态都已拆模块
2. `detector.py` 已经有较好的多信号识别基础
3. `grid_mapper.py` 的宫格映射思路清晰
4. `self_test.py` 覆盖了不少策略级约束，说明作者有在做回归控制

### 主要问题

1. **状态模型不干净**：目标/观察/执行混用
2. **关键恢复逻辑存在确定性 bug**
3. **全屏识别过于依赖苛刻几何阈值**
4. **手动模式语义与用户直觉严重不一致**
5. **运行时缓存只做了半套**
6. **大型函数过长，状态机复杂度高，后续很容易再引入回归**

### 总体判断

这个项目不是“做不了”，也不是“识别算法彻底不行”。

它现在最大的问题是：

> **状态闭环设计没有彻底打通，导致识别、热键、恢复、重启、动作路径都在各自工作，但不是围绕同一个真实现场状态源工作。**

只要按上面的顺序整改，先把状态模型拉正，再把恢复逻辑和识别逻辑改成“观察优先、目标协商、动作必验”，这类问题是可以比较彻底解决的。

