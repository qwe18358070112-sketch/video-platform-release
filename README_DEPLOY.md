# 跨电脑部署说明

## 目标
把项目从“当前开发电脑可跑”升级为“换一台电脑也能快速部署、快速验收、快速回退”。

## 一句话先记住
本项目的单路动作路径固定是：

```text
单击选中 -> 双击放大 -> 放大停留 dwell_seconds -> 双击返回 -> 返回后停留 post_restore_dwell_seconds -> 下一路
```

如果现场行为不是这条路径，就先不要继续测其他功能，先回头检查：
- 标定是否正确
- `config.yaml` 的 `timing` 是否符合预期
- 客户端现场版本是否把双击返回改成了别的交互

## 推荐部署步骤

### 1. 准备环境
- Windows 10 / 11
- 安装 Python 3.11 / 3.12（推荐；尽量不要直接用 Python 3.13 RC）
- 若要用 `ahk_controlclick`，安装 AutoHotkey v2
- 如果目标客户端是管理员运行，建议你也用“管理员 PowerShell / 管理员终端”启动本项目

### 2. 解压发布包
把发布包解压到一个独立目录，例如：

```text
D:\video_platform_release
```

### 3. 安装依赖
打开 PowerShell：

```powershell
cd D:\video_platform_release
.\install_deps.bat
```

### 4. 首次标定
先让客户端停在**非全屏宫格状态**：

```powershell
python app.py --calibrate windowed
```

再让客户端停在**全屏宫格状态**：

```powershell
python app.py --calibrate fullscreen
```

### 5. 先检查标定图

```powershell
python app.py --inspect-calibration windowed
python app.py --inspect-calibration fullscreen
```

检查点只有一个：
- 预览区域框线是否准确覆盖宫格区域，而不是把左侧收藏夹树、顶部工具条、底部状态栏也框进去

### 6. 再做自测

```powershell
python -m compileall .
python self_test.py
```

这里的 `python -m compileall .` 只检查项目源码，不会去编译 `.venv / dist / logs / tmp / __pycache__`。

### 7. 再做运行验收

```powershell
python app.py --run --mode auto
```

## 推荐首轮验收场景

### 场景 A：非全屏 + 12 宫格标准模式
检查完整动作路径是否为：
- 单击选中
- 双击放大
- 放大停留
- 双击返回
- 返回后停留
- 下一路

### 场景 B：按 F11
- 在刚放大或返回异常时按 F11
- 预期：回宫格，重走当前路，不直接跳下一路

### 场景 C：按 F9 连续步进
- 暂停后连按 F9 三次
- 预期：每次都自动选中下一路，仍保持暂停

### 场景 C2：黑屏 / 预览失败
- 如果某一路已经是黑屏
- 预期：程序可按配置直接跳过当前路，不继续双击
- 如果某一路是预览失败页
- 预期：程序仍执行完整动作路径，验证放大 / 返回宫格是否闭环

### 场景 D：切到全屏
- 保持相同逻辑复测

### 场景 E：切 9 / 6 / 4 宫格
- 先执行 `python app.py --switch-layout 9`
- 再执行 `python app.py --switch-layout 6`
- 再执行 `python app.py --switch-layout 4`
- 最后再同步检查 `grid.layout`
- 复测完整动作路径
- `--switch-layout` 的成功标准是中央宫格真的切换成功，不是命令返回成功就算通过

注意：
- 左侧收藏夹树里的 `9个画面 / 6个画面 / 4个画面` 不是实际布局切换入口
- 真实入口是顶部工具栏里的 `窗口分割`

### 场景 F：收藏夹名称顺序
- 开启 `favorites.enabled: true`
- 跑 `dump_favorites.bat`
- 核对 `tmp/favorites_cache.json`
- 配置 `grid.order: favorites_name`
- 填写 `grid.cell_labels`
- 观察轮询顺序是否符合左侧收藏夹顺序

## 常见问题

### 1. 点不到画面，总点到上边栏
先检查：
- `grid.click_point_ratio_y`

当前默认已调到：
- `0.45`

若你现场客户端宫格内容更靠下，可继续微调到 `0.48 ~ 0.55`。

### 2. 全屏和非全屏不一致
先确认：
- `profiles.active_mode: auto`
- 两套标定都已完成
- `inspect-calibration` 看起来都覆盖到了正确宫格区域

### 3. 动作太快或太慢
调整：

```yaml
timing:
  select_settle_ms: 220
  dwell_seconds: 4
  post_restore_dwell_seconds: 4
  between_cells_ms: 300
```

### 4. AHK 路径找不到
现在默认不强依赖固定路径；程序会搜索常见安装目录。若你确实要用 AHK 后端，仍可手动填：

```yaml
window:
  control_backend: ahk_controlclick
  autohotkey_path: "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"
```

### 5. 收藏夹名称读取不到
先分两类排查：

#### 类别 A：UIA 读取失败
可能原因：
- 客户端控件不是标准 UIA 树
- 权限级别不一致
- 左侧树控件未展开

#### 类别 B：能读到，但名称映射不上
检查：
- `grid.cell_labels` 是否与收藏夹名称完全一致
- 是否有空格、括号、前后缀差异

## 发布建议
每次准备发给其他电脑前，固定做这三步：
1. `python self_test.py`
2. `python build_release.py --output dist/video_platform_release.zip`
3. 解压 `video_platform_release.zip` 做一次目录抽检

## 新增部署要求：先守卫、后点击

从这一版开始，部署验收不只看“能不能点击”，还要看下面三项是否正常：

1. `runtime_guard.enabled: true`
2. `logs/guard` 目录能正常生成守卫截图
3. 当客户端误弹窗 / 错误界面 / 前台漂移时，程序会优先自动修复，连续失败后自动暂停

## 旧目录与新目录怎么取舍

推荐规则：
- 旧目录保留做备份，不再直接开发
- 新发布包解压后的目录，作为后续唯一主目录
- 只从旧目录迁移：配置、日志、截图、问题视频

详细见：`MIGRATION_GUIDE.md`
