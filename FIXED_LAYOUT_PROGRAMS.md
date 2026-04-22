# 固定宫格程序方案

当平台路线最终因为认证或插件接入原因推进过慢时，这一组固定宫格程序就是桌面自动化兜底方案。

## 方案目标

把当前运行时最容易混乱的“宫格识别 / 运行中切宫格 / 目标状态被热键改写”拆掉。

固定宫格版本只保留：

- 固定布局
- 自动识别全屏 / 窗口
- 轮询
- 放大
- 返回
- 暂停 / 下一路 / 停止 / 紧急恢复

固定宫格版本主动禁掉：

- `F1` 自动/手动切换
- `F7` 模式切换
- `F8` 宫格切换

## 4 套程序

- 4 宫格程序
- 6 宫格程序
- 9 宫格程序
- 12 宫格程序

这些程序在运行时会直接锁定：

```text
python app.py --run --config fixed_layout_programs/config.layoutN.yaml --layout N
```

也就是：

- 宫格不再运行时自动识别
- 每套程序固定只跑自己的 `4 / 6 / 9 / 12`
- 只保留“全屏 / 窗口”自动识别

第一次在 Windows 上使用固定宫格程序前，先执行：

```bat
install_deps.bat
```

## 当前价值

这条路线不能解决平台 API / 插件接入问题，但能明显降低桌面自动化现场的状态混乱概率。

它适合下面这种目标：

- 先把单个固定宫格场景跑通
- 一套程序只验一个布局
- 验收时不要求运行中切布局

## 生成方式

仓库里已经提供生成器：

```bash
python3 platform_spike/scripts/generate_fixed_layout_programs.py
```

Windows 里也可以直接运行：

```bat
platform_spike\scripts\generate_fixed_layout_programs.cmd
```

如果后续实测发现“全屏 / 窗口”自动识别仍然会扰动，可以直接扩成 8 套：

```bash
python3 platform_spike/scripts/generate_fixed_layout_programs.py --include-modes
```

生成后会得到：

- `fixed_layout_programs/config.layout4.yaml`
- `fixed_layout_programs/config.layout6.yaml`
- `fixed_layout_programs/config.layout9.yaml`
- `fixed_layout_programs/config.layout12.yaml`
- `fixed_layout_programs/run_layout4_fixed.bat`
- `fixed_layout_programs/run_layout4_fixed.sh`
- `fixed_layout_programs/run_layout6_fixed.bat`
- `fixed_layout_programs/run_layout6_fixed.sh`
- `fixed_layout_programs/run_layout9_fixed.bat`
- `fixed_layout_programs/run_layout9_fixed.sh`
- `fixed_layout_programs/run_layout12_fixed.bat`
- `fixed_layout_programs/run_layout12_fixed.sh`
- `fixed_layout_programs/run_fixed_layout_selector.bat`
- `fixed_layout_programs/run_fixed_layout_selector.sh`
- `fixed_layout_programs/stop_fixed_layout_selector.bat`
- `fixed_layout_programs/stop_fixed_layout_selector.sh`
- `fixed_layout_programs/fixed_layout_manifest.json`

如果带 `--include-modes`，还会额外生成：

- `fixed_layout_programs/config.layout4.windowed.yaml`
- `fixed_layout_programs/config.layout4.fullscreen.yaml`
- `fixed_layout_programs/run_layout4_windowed_fixed.bat`
- `fixed_layout_programs/run_layout4_fullscreen_fixed.bat`
- 其他布局同理

## 独立打包

为了把这些固定宫格程序分发到其他 Windows 电脑上，仓库里也补了独立打包脚本：

```bash
python3 platform_spike/scripts/package_fixed_layout_programs.py
python3 platform_spike/scripts/package_fixed_layout_programs.py --include-modes
```

Windows 里也可以直接运行：

```bat
platform_spike\scripts\package_fixed_layout_programs.cmd
platform_spike\scripts\package_fixed_layout_programs.cmd --include-modes
```

它会输出：

- `dist/fixed_layout_bundles/video_platform_release_layout4_fixed.zip`
- `dist/fixed_layout_bundles/video_platform_release_layout6_fixed.zip`
- `dist/fixed_layout_bundles/video_platform_release_layout9_fixed.zip`
- `dist/fixed_layout_bundles/video_platform_release_layout12_fixed.zip`
- `dist/fixed_layout_bundles/fixed_layout_bundles_manifest.json`

如果带 `--include-modes`，还会额外输出：

- `video_platform_release_layout4_windowed_fixed.zip`
- `video_platform_release_layout4_fullscreen_fixed.zip`
- 其他布局同理

从这一版开始，如果在 Windows 上执行打包脚本，固定布局 bundle 会优先打成“自带运行时”的可分发包：

- 随包 Python：`runtime/python/python.exe`
- 随包 NativeProbe：`runtime/native_runtime/VideoPlatform.NativeProbe.exe`
- 目标机自检入口：`verify_fixed_layout_runtime.cmd`

也就是说，目标 Windows 电脑不再要求预装 Python 或 `.NET 8`。

## 套装安装

除了每套独立 ZIP，当前还会额外准备一个固定布局套装包，面向其他 Windows 电脑统一安装。

套装安装提供两个入口：

- `install_fixed_layout_suite.cmd`
  一键安装脚本，默认安装到当前用户目录
- `install_fixed_layout_suite_gui.cmd`
  图形安装入口，可选安装目录并创建桌面快捷方式目录
- `verify_fixed_layout_runtime.cmd`
  目标机运行时自检入口，安装后如果程序起不来，先跑它
- `repair_fixed_layout_runtime.cmd`
  目标机运行时修复入口，检测缺失依赖并尝试从原始解压目录补齐

对应详细说明见：

- `FIXED_LAYOUT_DEPLOY.md`
- `FIXED_LAYOUT_INSTALL_AND_USE.md`

如果目标机安装后程序无法启动，先运行：

- `verify_fixed_layout_runtime.cmd`

如果校验失败，再运行：

- `repair_fixed_layout_runtime.cmd`

详细报告会写到：

- `logs/fixed_layout_runtime_verify_latest.json`

## 当前判断

如果平台路线最终还是卡在认证/插件接入，这条固定宫格拆分方案是最现实的桌面自动化 fallback。

## 当前补充

为了减少多机部署和现场切换时的混乱，当前固定宫格路线又补了两层：

- `fixed_layout_manifest.json`
  明确记录当前有哪些入口、各自锁定的布局/模式和独立实例锁名
- `run_fixed_layout_selector.bat`
  作为统一转发入口，便于现场按参数启动；但正式验收仍建议优先直接点独立 BAT
- 同时也生成 `.sh` 入口
  适合当前这台“代码在 WSL、实际程序跑在 Windows 同步目录”的工作方式
- 如果某一套固定宫格程序还在跑，可以先执行 `stop_fixed_layout_selector.sh <layout> [mode]` 或 `stop_fixed_layout_selector.bat <layout> [mode]`
  把对应旧实例停掉，再重新启动该布局程序

## 当前冻结状态

这一版固定布局程序当前冻结矩阵为：

- 全屏 `4/6/9/12`：通过
- 非全屏 `4/6/9/12`：通过

冻结基线见：

- `FIXED_LAYOUT_FREEZE_BASELINE.md`
