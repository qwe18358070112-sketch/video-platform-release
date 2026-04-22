# Fixed Layout Programs

这一组是兜底路线：把程序按固定宫格拆成 4 套独立入口。

设计目标：

- 每套程序只负责一种布局：4 / 6 / 9 / 12
- 运行时直接锁定 `--layout`，不再依赖布局热键切换
- 禁用最容易把状态搅乱的 `F1 / F7`
- 保留 `F2 / F8 / F9 / F10 / F11`，继续支持暂停、顺序切换、下一路、停止、紧急恢复

对应入口：

- `run_layout4_fixed.bat`：固定 4 宫格程序
- `run_layout4_fixed.sh`：在当前 WSL 仓库里启动固定 4 宫格程序
- `run_layout4_windowed_fixed.bat`：固定 4 宫格 + 固定 windowed 程序
- `run_layout4_windowed_fixed.sh`：在当前 WSL 仓库里启动固定 4 宫格 + 固定 windowed 程序
- `run_layout4_fullscreen_fixed.bat`：固定 4 宫格 + 固定 fullscreen 程序
- `run_layout4_fullscreen_fixed.sh`：在当前 WSL 仓库里启动固定 4 宫格 + 固定 fullscreen 程序
- `run_layout6_fixed.bat`：固定 6 宫格程序
- `run_layout6_fixed.sh`：在当前 WSL 仓库里启动固定 6 宫格程序
- `run_layout6_windowed_fixed.bat`：固定 6 宫格 + 固定 windowed 程序
- `run_layout6_windowed_fixed.sh`：在当前 WSL 仓库里启动固定 6 宫格 + 固定 windowed 程序
- `run_layout6_fullscreen_fixed.bat`：固定 6 宫格 + 固定 fullscreen 程序
- `run_layout6_fullscreen_fixed.sh`：在当前 WSL 仓库里启动固定 6 宫格 + 固定 fullscreen 程序
- `run_layout9_fixed.bat`：固定 9 宫格程序
- `run_layout9_fixed.sh`：在当前 WSL 仓库里启动固定 9 宫格程序
- `run_layout9_windowed_fixed.bat`：固定 9 宫格 + 固定 windowed 程序
- `run_layout9_windowed_fixed.sh`：在当前 WSL 仓库里启动固定 9 宫格 + 固定 windowed 程序
- `run_layout9_fullscreen_fixed.bat`：固定 9 宫格 + 固定 fullscreen 程序
- `run_layout9_fullscreen_fixed.sh`：在当前 WSL 仓库里启动固定 9 宫格 + 固定 fullscreen 程序
- `run_layout12_fixed.bat`：固定 12 宫格程序
- `run_layout12_fixed.sh`：在当前 WSL 仓库里启动固定 12 宫格程序
- `run_layout12_windowed_fixed.bat`：固定 12 宫格 + 固定 windowed 程序
- `run_layout12_windowed_fixed.sh`：在当前 WSL 仓库里启动固定 12 宫格 + 固定 windowed 程序
- `run_layout12_fullscreen_fixed.bat`：固定 12 宫格 + 固定 fullscreen 程序
- `run_layout12_fullscreen_fixed.sh`：在当前 WSL 仓库里启动固定 12 宫格 + 固定 fullscreen 程序

- `run_fixed_layout_selector.bat`：统一转发入口，按参数选择具体独立 BAT

同时会生成：

- `fixed_layout_manifest.json`：当前固定宫格入口清单，可用于多机分发和验收记录

注意：

- 这 4 套程序只保留“全屏 / 窗口”自动识别；宫格不再运行时自动识别，而是固定锁到各自程序对应的布局。
- 但它们不再允许运行中切换宫格，也不会通过 F1/F7/F8 改目标。
- 每套程序现在使用独立实例锁；4 宫格不会再被 12 宫格的旧锁挡住。
- 如果目录里存在 `runtime/python/python.exe`，固定宫格 BAT 会优先使用随包 Python 运行时，不再依赖目标机预装 Python。
- 如果现场继续被“全屏 / 窗口”识别扰动，可以执行 `python3 platform_spike/scripts/generate_fixed_layout_programs.py --include-modes`，直接扩成 8 套程序。
- 也可以用 `run_fixed_layout_selector.bat <layout> [mode]` 作为统一入口；它只是转发到对应独立 BAT，不替代独立程序。

