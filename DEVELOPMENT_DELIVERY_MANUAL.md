# 程序开发文档、功能逻辑说明、操作手册与验收用例

## 1. 文档范围

这份文档用于说明当前版本“视频平台自动轮询控制器”的：

- 项目目标与边界
- 核心模块职责
- 全部主要功能的运行逻辑
- 配置、启动、切换、日常使用方法
- 本次验收可直接执行的测试用例

适用对象：

- 开发人员
- 现场实施人员
- 验收人员
- 后续继续让 Codex / 其他工程师接手维护的人

## 2. 项目目标

项目目标是对“视频融合赋能平台 / 视频监控客户端”的宫格页面进行稳定的自动轮询，保证以下动作路径成立：

```text
单击选中
-> 等待 select_settle_ms
-> 双击放大
-> 放大停留 dwell_seconds
-> 双击返回宫格
-> 返回后停留 post_restore_dwell_seconds
-> 下一路
```

核心要求：

- 支持非全屏与全屏
- 支持 4 / 6 / 9 / 12 宫格
- 支持自动识别当前模式与当前宫格
- 支持手动锁定模式与宫格
- 支持从左到右、自定义顺序、收藏夹顺序
- 支持人工监管、暂停、单步预选、恢复、停止
- 支持异常检测、界面守卫、自动恢复

## 3. 当前版本的功能清单

当前版本已实现并现场验证过的能力：

- 自动识别当前是非全屏还是全屏
- 自动识别当前更像 4 / 6 / 9 / 12 中的哪一种宫格
- 手动锁定 `windowed / fullscreen`
- 手动锁定 `4 / 6 / 9 / 12`
- 非全屏 12 / 9 / 6 / 4 轮询
- 全屏 12 / 9 / 6 / 4 轮询
- 行优先顺序 `row_major`
- 列优先顺序 `column_major`
- 自定义顺序 `custom`
- 收藏夹名称顺序 `favorites_name`
- 状态提示栏同步显示运行态
- 热键：
  - `F7` 模式切换
  - `F8` 启动 / 暂停 / 继续
  - `F9` 暂停态预选下一路
  - `F10` 安全停止
  - `F11` 返回宫格并重走当前路
  - `F12` 宫格切换
- 黑屏 / 预览失败软告警
- 异常界面守卫
- 前台漂移回焦
- 同进程弹窗自动关闭
- 失败恢复与自动暂停

## 4. 核心模块说明

### 4.1 入口与配置

- `app.py`
  - 解析命令行参数
  - 创建窗口管理、控制器、检测器、调度器等对象
  - 支持 `--run / --calibrate / --inspect-runtime / --dump-favorites / --switch-layout`

- `common.py`
  - 定义 `AppConfig`
  - 定义 `TimingConfig / HotkeyConfig / FavoritesConfig / DetectionConfig`
  - 定义调度状态枚举 `SchedulerState`

### 4.2 调度与状态机

- `scheduler.py`
  - 主状态机核心
  - 负责单路动作路径推进
  - 负责热键注册与运行时响应
  - 负责运行时模式 / 宫格同步
  - 负责状态浮窗内容同步

主要状态：

- `PREPARE_TARGET`
- `SELECT_TARGET`
- `SELECT_CONFIRM`
- `ZOOM_IN`
- `ZOOM_CONFIRM`
- `ZOOM_DWELL`
- `ZOOM_OUT`
- `GRID_CONFIRM`
- `GRID_DWELL`
- `NEXT`
- `PAUSED`
- `ERROR_RECOVERY`
- `STOPPED`

### 4.3 宫格切分与顺序

- `grid_mapper.py`
  - 先生成物理槽位
  - 再按顺序策略重排输出
  - 支持：
    - `row_major`
    - `column_major`
    - `custom`
    - `favorites_name`

### 4.4 画面检测

- `detector.py`
  - 判断当前更像宫格还是放大
  - 识别黑屏 / 预览失败
  - 校验双击放大、双击返回是否成功
  - 为全屏场景提供视觉布局候选信息

### 4.5 客户端模式与窗口管理

- `window_manager.py`
  - 找主窗口
  - 识别是否全屏 / 非全屏
  - 处理附属渲染窗口
  - 处理前台窗口一致性

### 4.6 宫格切换与读取

- `layout_switcher.py`
  - 通过顶部 `窗口分割` 入口切换宫格
  - 在非全屏下读取当前选中的布局
  - 读取时采用安全 UIA 路径，避免误点布局按钮

- `favorites_reader.py`
  - 读取左侧收藏夹当前可见名称
  - 提供给 `favorites_name` 顺序映射使用

### 4.7 输入与守卫

- `controller.py`
  - 鼠标单击、双击、ESC、Alt+F4 等输入动作

- `runtime_guard.py`
  - 前台窗口守卫
  - 同进程弹窗处理
  - 异常界面检测与自动回收

- `input_guard.py`
  - 人工输入监管
  - 避免运行中被意外操作打乱状态

### 4.8 状态提示栏

- `status_runtime.py`
  - 写入运行时状态文件

- `status_overlay.py`
  - 读取状态文件并显示浮窗
  - 同步显示模式、宫格、档位、顺序与热键提示

## 5. 全部主要功能的逻辑说明

### 5.1 自动识别全屏 / 非全屏

逻辑链路：

1. 先找目标主窗口与附属渲染窗口
2. 优先检查非全屏界面的结构性证据，例如：
   - `收藏夹`
   - `搜索`
   - `全部收藏`
   - `打开文件夹`
   - `视频监控配置`
3. 再用窗口几何覆盖率做兜底

结论：

- 最大化窗口不等于真正全屏
- 右上角按钮状态不单独作为全屏证据
- 只有界面结构也符合全屏，才会判定为 `fullscreen`

### 5.2 自动识别当前宫格

#### 非全屏

非全屏下优先读取顶部 `窗口分割` 面板里当前被选中的布局。

当前实现要点：

- 只走安全 UIA 打开 / 关闭路径
- 禁止坐标热区兜底
- 如果面板读取失败，则放弃本次安全识别，不再冒险误点

这样做的原因：

- 非全屏下右上工具栏存在真实布局入口
- 但误点到 `2宫格`、`1宫格` 等其他布局会直接把现场带偏

#### 全屏

全屏下不再强行打开 `窗口分割`。

当前实现要点：

- 通过视觉特征判断更像 4 / 6 / 9 / 12
- 引入分隔线峰值、内容纹理、稀疏宫格特征等辅助评分
- 如果自动判断不稳定，可以人工锁定当前宫格

### 5.3 手动模式与手动宫格

手动模式有两层：

- 手动模式：锁定当前运行态是 `windowed` 还是 `fullscreen`
- 手动宫格：锁定当前运行态是 `4 / 6 / 9 / 12`

触发方式：

- 启动参数：
  - `--mode auto|windowed|fullscreen`
  - `--layout 4|6|9|12`
- 运行时热键：
  - `F7` 切模式
  - `F12` 切宫格

行为规则：

- 自动态下，程序会根据现场实时同步
- 手动态下，程序不再自动改动该维度，直到你切回自动

### 5.4 单路动作路径

当前标准动作路径为：

```text
单击选中
-> 等待 select_settle_ms
-> 双击放大
-> 放大停留 dwell_seconds
-> 双击返回宫格
-> 返回后停留 post_restore_dwell_seconds
-> 下一路
```

注意：

- 不是“双击放大后立刻下一路”
- 不是“返回宫格后立刻下一路”
- 两段停留是独立可配置的

### 5.5 轮询顺序

支持 4 种顺序：

- `row_major`
  - 从左到右、从上到下
- `column_major`
  - 从上到下、从左到右
- `custom`
  - 直接使用 `grid.custom_sequence`
- `favorites_name`
  - 读取左侧收藏夹当前可见顺序
  - 再映射到 `grid.cell_labels` 对应的物理槽位

### 5.6 收藏夹顺序

逻辑步骤：

1. 左侧收藏夹树读取当前可见名称
2. 用这些名称去匹配 `grid.cell_labels`
3. 匹配成功后得到“名称顺序 -> 物理槽位顺序”
4. 调度器按映射后的物理槽位顺序轮询

重要前提：

- 收藏夹树必须可见
- 名称必须真实可读
- `cell_labels` 必须和现场名称一致

### 5.7 黑屏 / 预览失败处理

当前版本的语义是：

- `black_screen`
  - 作为单路内容异常
  - 记录软告警
  - 不把它当成客户端整体界面错误
- `preview_failure`
  - 也是软告警
  - 不在 `SELECT_CONFIRM` 阶段直接跳过

当前结果：

- 黑屏 / 预览失败不会导致程序崩溃
- 程序仍继续执行完整动作路径
- 日志里会记录 `PRECHECK soft anomaly ... continuing action path`

### 5.8 人工监管与恢复

#### F8

- 启动
- 暂停
- 继续

#### F9

- 仅在暂停态有意义
- 每按一次，就预选下一路
- 自动选中该路，但保持暂停
- 支持连续按多次

#### F10

- 安全停止
- 程序退出前会尽量把现场回收到可控状态

#### F11

语义是：

```text
返回宫格 -> 重走当前未完成路径
```

不是：

```text
返回宫格 -> 跳过当前路
```

#### F7 / F12

- `F7` 切运行模式
- `F12` 切运行宫格
- 切换结果会同步显示到提示栏

### 5.9 状态提示栏

提示栏会同步显示：

- 当前模式
- 当前宫格
- 当前运行档位
- 当前顺序
- 当前主提示消息
- 热键提示

典型显示示例：

```text
模式: 非全屏(自动) | 宫格: 4宫格(自动) | 运行档位: 非全屏 4宫格 | 顺序: 收藏夹顺序
```

## 6. 常用命令与详细操作步骤

### 6.1 命令执行方式

#### 方式 A：从 WSL / Linux 侧桥接到 Windows

```bash
./windows_bridge.sh <command>
```

#### 方式 B：直接在 Windows 里执行

```powershell
python app.py <command>
```

下文默认写桥接命令；如果你在 Windows 里直接操作，把前缀替换掉即可。

### 6.2 安装依赖

```bash
./windows_bridge.sh install-deps
```

或在 Windows 里：

```powershell
.\install_deps.bat
```

### 6.3 标定

非全屏：

```bash
./windows_bridge.sh calibrate windowed
```

全屏：

```bash
./windows_bridge.sh calibrate fullscreen
```

### 6.4 检查标定

```bash
./windows_bridge.sh inspect-calibration windowed
./windows_bridge.sh inspect-calibration fullscreen
```

### 6.5 只读查看当前运行态

自动判断：

```bash
./windows_bridge.sh inspect-runtime --mode auto
```

手动锁定查看：

```bash
./windows_bridge.sh inspect-runtime --mode windowed --layout 9
./windows_bridge.sh inspect-runtime --mode fullscreen --layout 6
```

### 6.6 切宫格

```bash
./windows_bridge.sh switch-layout 4
./windows_bridge.sh switch-layout 6
./windows_bridge.sh switch-layout 9
./windows_bridge.sh switch-layout 12
./windows_bridge.sh switch-layout 13
```

建议：

1. 切完后人工看一眼中央宫格是否真的变了
2. 确认成功后再启动自动轮询

### 6.7 启动自动轮询

自动识别：

```bash
./windows_bridge.sh run --mode auto
```

手动锁定模式与宫格：

```bash
./windows_bridge.sh run --mode windowed --layout 9
./windows_bridge.sh run --mode fullscreen --layout 6
```

### 6.8 读取收藏夹

```bash
./windows_bridge.sh dump-favorites
```

### 6.9 日常运行步骤

推荐现场步骤：

1. 打开客户端
2. 先确认当前是全屏还是非全屏
3. 先确认当前宫格数
4. 如果要主动切宫格，优先使用 `switch-layout`
5. 再用 `inspect-runtime --mode auto` 只读确认一次
6. 再执行 `run --mode auto`
7. 观察提示栏是否和现场一致
8. 再开始验动作路径、热键与顺序

## 7. 配置说明

最常用的配置位于 `config.yaml`。

### 7.1 模式相关

```yaml
profiles:
  active_mode: auto
```

可选：

- `auto`
- `windowed`
- `fullscreen`

### 7.2 宫格与顺序

```yaml
grid:
  layout: 12
  order: row_major
```

常用可选值：

- `layout`
  - `4 / 6 / 9 / 12`
- `order`
  - `row_major`
  - `column_major`
  - `custom`
  - `favorites_name`

### 7.3 自定义顺序

```yaml
grid:
  order: custom
  custom_sequence: [0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11]
```

### 7.4 收藏夹顺序

```yaml
grid:
  order: favorites_name
  cell_labels:
    0: "大厅柱子口"
    1: "法雨寺停车场"
    2: "千步沙入口"
    3: "码头入口"
```

### 7.5 动作节奏

```yaml
timing:
  select_settle_ms: 220
  dwell_seconds: 4
  post_restore_dwell_seconds: 4
```

### 7.6 热键

当前默认：

- `F7`：模式切换
- `F8`：启动 / 暂停 / 继续
- `F9`：下一路
- `F10`：停止
- `F11`：恢复
- `F12`：宫格切换

## 8. 本次验收测试用例

### 8.1 验收前准备

1. 客户端可正常打开
2. 目标宫格页面可稳定显示
3. 验收中尽量不要切去别的窗口
4. 主要观察：
   - 状态提示栏
   - `logs/video_auto_poll.log`
   - `tmp/runtime_status.json`

### 8.2 用例 A：8 个模式全覆盖

需要覆盖的 8 个模式：

- 非全屏 12
- 非全屏 9
- 非全屏 6
- 非全屏 4
- 全屏 12
- 全屏 9
- 全屏 6
- 全屏 4

每个模式的步骤完全相同：

1. 先手动把客户端切到目标模式与目标宫格
2. 执行：

```bash
./windows_bridge.sh inspect-runtime --mode auto
```

3. 预期：
   - `mode` 与现场一致
   - `layout` 与现场一致
   - `runtime_profile` 与现场一致

4. 再执行手动锁定确认，例如：

```bash
./windows_bridge.sh inspect-runtime --mode windowed --layout 9
./windows_bridge.sh inspect-runtime --mode fullscreen --layout 6
```

5. 预期：
   - 识别仍正确
   - 来源变成手动锁定

6. 启动自动轮询：

```bash
./windows_bridge.sh run --mode auto
```

7. 预期：
   - 提示栏显示当前模式、宫格、档位、顺序
   - 动作路径为：
     - 单击选中
     - 双击放大
     - 停留
     - 双击返回
     - 再停留
     - 下一路

8. 按 `F8`
   - 预期进入暂停

9. 再按 `F8`
   - 预期继续

10. 按 `F10`
   - 预期安全停止

### 8.3 用例 B：提示栏与手动切换

建议在 `非全屏 4 宫格` 下做。

步骤：

1. 启动：

```bash
./windows_bridge.sh run --mode auto
```

2. 提示栏出现后先按 `F8` 暂停
3. 连按 `F12`
4. 预期提示栏里的 `宫格` 依次切换：
   - `4宫格(手动)`
   - `6宫格(手动)`
   - `9宫格(手动)`
   - `12宫格(手动)`
   - `自动识别(自动)`

5. 连按 `F7`
6. 预期提示栏里的 `模式` 依次切换：
   - `非全屏(手动)`
   - `全屏(手动)`
   - `自动识别(自动)`

7. 按 `F10` 结束

### 8.4 用例 C：F11 恢复

步骤：

1. 任意选择一种稳定模式，建议 `非全屏 4 宫格`
2. 启动自动轮询
3. 等程序已经放大某一路时按 `F11`
4. 预期：
   - 返回宫格
   - 重走当前路
   - 不直接跳下一路
   - 不崩溃

### 8.5 用例 D：收藏夹顺序

使用测试配置：

- `favorites_order_test.yaml`

步骤：

1. 把客户端切到 `非全屏 4 宫格`
2. 确认左侧收藏夹树可见
3. 先执行：

```bash
./windows_bridge.sh dump-favorites
```

4. 再执行：

```bash
./windows_bridge.sh run --config favorites_order_test.yaml --mode auto
```

5. 等第一路开始后按 `F8` 暂停
6. 预期首路是：
   - `第2行第1列 [浙江舟山普陀山-大厅柱子北面球机]`

7. 连按 `F9` 三次
8. 预期提示栏依次出现：
   - 第 1 次：`第1行第1列 [49K+800M舟山西龙门架球机]`
   - 第 2 次：`第2行第2列 [浙江舟山普陀山-码头广场鹰眼细节]`
   - 第 3 次：`第1行第2列 [浙江舟山普陀山-南海观音上广场]`

结论：

- 该用例通过时，说明 `favorites_name` 的 4 宫格映射为 `2 -> 0 -> 3 -> 1`

### 8.6 用例 E：自定义顺序

使用测试配置：

- `custom_order_test.yaml`

步骤：

1. 把客户端切到 `非全屏 4 宫格`
2. 执行：

```bash
./windows_bridge.sh run --config custom_order_test.yaml --mode auto
```

3. 等第一路开始后按 `F8` 暂停
4. 预期首路是：
   - `第2行第2列 [自定义槽位D]`

5. 连按 `F9` 三次
6. 预期提示栏依次出现：
   - 第 1 次：`第1行第2列 [自定义槽位B]`
   - 第 2 次：`第1行第1列 [自定义槽位A]`
   - 第 3 次：`第2行第1列 [自定义槽位C]`

结论：

- 该用例通过时，说明 `custom_sequence` 的 4 宫格顺序为 `3 -> 1 -> 0 -> 2`

### 8.7 用例 F：黑屏 / 预览失败

步骤：

1. 找一条已知容易黑屏或预览失败的路
2. 启动自动轮询
3. 观察该路行为

预期：

- 程序不会崩溃
- 日志里可能出现：
  - `PRECHECK soft anomaly ... result=black_screen`
  - `PRECHECK soft anomaly ... result=preview_failure`
- 程序仍继续完整动作路径

## 9. 本次现场验收结论

本轮已经实机通过的项目：

- 非全屏 12 / 9 / 6 / 4
- 全屏 12 / 9 / 6 / 4
- 自动识别全屏 / 非全屏
- 自动识别当前宫格
- 手动锁定模式与宫格
- 提示栏同步
- `F7 / F8 / F9 / F10 / F11 / F12`
- 收藏夹顺序
- 自定义顺序

已验证的关键顺序结果：

- 收藏夹顺序 4 宫格：`2 -> 0 -> 3 -> 1`
- 自定义顺序 4 宫格：`3 -> 1 -> 0 -> 2`

## 10. 当前版本边界

当前版本明确边界：

- 正式自动识别与轮询支持 `4 / 6 / 9 / 12`
- `13` 目前主要用于切换与核对，不作为正式轮询主布局
- 黑屏 / 预览失败当前策略是软告警后继续动作路径
- 非全屏的宫格自动识别依赖顶部 `窗口分割` 面板的安全读取
- 如果现场界面结构变化很大，需要重新标定并重新验收

## 11. 推荐你现在怎么用

最推荐的现场范式只有两句：

1. 切宫格优先用 `switch-layout`
2. 自动运行优先用 `run --mode auto`

如果你只是想看当前真实状态，不要直接跑自动轮询，先执行：

```bash
./windows_bridge.sh inspect-runtime --mode auto
```

如果你要验收藏夹顺序和自定义顺序，直接使用：

```bash
./windows_bridge.sh run --config favorites_order_test.yaml --mode auto
./windows_bridge.sh run --config custom_order_test.yaml --mode auto
```
