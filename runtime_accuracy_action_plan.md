# 运行过程中如何实现准确的图像识别、准确的动作路径

## 1. 总原则

程序要想在运行过程中稳定工作，不能只依赖“单次截图 + 单次点击”。
必须把整个过程改成：

1. 先确认现场真实状态
2. 再决定本轮要执行的目标状态
3. 点击前校验一次
4. 点击后确认一次
5. 失败就恢复到宫格再重走当前路径

也就是：

观测 -> 决策 -> 执行 -> 确认 -> 纠偏

## 2. 图像识别要怎么做才准

### 2.1 不要单帧判定
至少连续采样 3 帧：
- mode: fullscreen / windowed
- layout: 4 / 6 / 9 / 12
- view: GRID / ZOOMED / UNKNOWN

最后做多数投票，只有置信度足够高才提交结果。

### 2.2 观测状态与目标状态必须彻底分开
运行时至少维护三套状态：
- observed_mode / observed_layout / observed_view
- requested_mode / requested_layout
- effective_mode / effective_layout

observed 只描述现场真实界面。
requested 只描述用户或热键要求。
effective 才是当前动作真正采用的状态。

### 2.3 模式识别要多信号融合
不要只看几何尺寸，也不要只看 UIA。
建议同时用：
- 几何覆盖率
- 顶层窗口与附属渲染窗
- windowed 特征控件
- fullscreen 开关状态
- 最近 3 帧投票结果

### 2.4 宫格识别要带置信度和证据
布局识别结果不应只返回“9 宫格”，还应该返回：
- confidence
- source
- evidence

例如：

```python
{
  "layout": 9,
  "confidence": 0.84,
  "source": "visual+uia",
  "evidence": {
    "divider_rows": 3,
    "divider_cols": 3,
    "uia_layout": 9,
    "grid_probe_score": 0.11
  }
}
```

### 2.5 缓存只能当候选，不能当事实
启动时如果用了缓存：
- 只能先临时使用
- 第一轮动作前必须 quick verify
- 验证失败立刻废弃缓存

## 3. 动作路径要怎么做才准

### 3.1 每一步动作都要有前置校验
例如点击前先确认：
- 当前界面仍是 GRID
- 当前 mode / layout 与 effective state 一致
- 当前 point 仍在可点击区域
- 窗口仍在前台

### 3.2 每一步动作都要有后置确认
例如：
- select 后，仍应是 GRID，且当前选中格合理变化
- zoom_in 后，应确认进入 ZOOMED
- zoom_out 后，应确认回到 GRID

### 3.3 失败后不能直接跳下一路
必须这样处理：
1. retry once
2. recover to grid
3. 重新识别当前状态
4. 如果状态已匹配，就重走当前格
5. 如果状态不匹配，就暂停并提示人工处理

### 3.4 动作路径要有事务感
每次点击前记录一份 action snapshot：
- mode
- layout
- cell index
- cell rect
- select_point
- zoom_point
- 当前 cycle id

动作成功后才 commit；否则回滚并重试当前路径。

## 4. 你这个项目里最该先改的点

### 4.1 scheduler.py
先拆状态模型，不要再把：
- _current_mode
- _runtime_layout
- _requested_mode
- _requested_layout
混在一起。

### 4.2 window_manager.py
重点改：
- windowed marker 缓存 TTL
- 模式切换后主动失效缓存
- marker 不只看 exists，还要看 visible / rect / center point
- 模式识别增加多帧投票

### 4.3 detector.py
重点改：
- 所有 classify 结果增加 confidence
- 所有 confirm 结果增加 evidence
- pause / resume / startup / recover 后强制重建 probe
- 关键时刻允许低频 UIA 只读校验

### 4.4 grid_mapper.py
不要只保留一个固定点击点。
建议为每个 cell 预计算：
- primary_point
- backup_point_left
- backup_point_right
- backup_point_lower

如果首点失败，第二次重试优先换备选点，而不是重复点同一个点。

### 4.5 controller.py
动作层要记录：
- 实际发送的点
- 发送前窗口句柄
- 发送后 guard 结果
- 双击间隔
- backend

## 5. 运行过程中要加的闭环

### 5.1 Pause -> 手工调整 -> Resume
恢复前必须先做一次现场重识别：
- 连续 3 帧识别 mode/layout/view
- 与目标状态比对
- 匹配才继续
- 不匹配就保持暂停

### 5.2 F1 切手动
不能直接把当前内存状态锁成手动。
应该先做高置信度重识别，再把 observed 状态锁进 requested 状态。

### 5.3 F7/F8 修改目标
推荐做成两种模式：
- 默认：只改目标，不直接切客户端，恢复前先校验
- 可选：暂停态下直接调用 switch_mode / switch_runtime_layout 切客户端 UI

### 5.4 重启后
不能直接信任上次 layout cache。
必须在首轮 PREPARE_TARGET 前做一次 quick verify。

## 6. 参数层面的建议

先不要大范围乱调阈值。
建议按这个顺序调：

1. 先修状态闭环
2. 再修 probe 重建时机
3. 再修多帧投票
4. 最后再微调 threshold

如果只调阈值，不改状态模型，现场仍会继续出现：
- 暂停后衔接不上
- 手工改宫格后识别错乱
- 重启后沿用旧布局

## 7. 最务实的落地顺序

第一周先做：
- 拆 observed/requested/effective state
- pause-resume 前三帧重识别
- startup cache quick verify
- mode/layout mismatch 时保持暂停，不继续乱点

第二周再做：
- mode/layout 多信号投票
- detector confidence/evidence
- grid cell 备选点击点
- action snapshot / retry / rollback

第三周做：
- 现场日志结构化输出
- 自动导出 mismatch 现场截图
- 针对黑屏页、失败页、低纹理页单独调参

## 8. 最终验收标准

达到下面 5 条，才算真正“准确”：

1. 暂停后手工改宫格，再恢复，程序能按新宫格继续。
2. 暂停后手工切全屏/窗口，再恢复，程序能识别对。
3. 程序重启后不会盲信旧缓存，能重新识别当前现场。
4. 单击/双击失败时不会直接跳下一路，而是先恢复并重走当前路径。
5. 黑屏页/失败页/低纹理页不会被误判成错误界面而乱点。
