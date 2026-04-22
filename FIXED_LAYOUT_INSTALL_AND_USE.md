# 固定布局程序安装与使用说明

这份文档给“另一台新 Windows 电脑”的安装和现场使用人员看，目标是装完就能跑，不需要额外装 Python 或 .NET。

## 安装前结论

当前固定布局安装包已经自带运行依赖：

- 便携 Python：`runtime\python\python.exe`
- NativeProbe：`runtime\native_runtime\VideoPlatform.NativeProbe.exe`
- 固定布局运行脚本
- 校验脚本
- 修复脚本

正常情况下，目标机不需要另外安装：

- Python
- `.NET 8 SDK`
- `.NET Runtime`

## 推荐安装包

推荐优先使用套装安装包：

```text
video_platform_release_fixed_layout_suite.zip
```

它同时包含：

- 非全屏 `4/6/9/12`
- 全屏 `4/6/9/12`
- 一键安装入口
- 图形安装入口
- 校验入口
- 修复入口

## 安装步骤

### 方式一：图形安装

1. 把 `video_platform_release_fixed_layout_suite.zip` 复制到目标电脑。
2. 解压到一个本地目录。
3. 双击：

```text
install_fixed_layout_suite_gui.cmd
```

4. 选择安装目录。
5. 等安装完成。

### 方式二：命令行一键安装

1. 把 `video_platform_release_fixed_layout_suite.zip` 复制到目标电脑。
2. 解压到一个本地目录。
3. 双击：

```text
install_fixed_layout_suite.cmd
```

安装器会自动：

- 复制整套固定布局程序
- 写入开始菜单快捷方式
- 可选写入桌面快捷方式目录
- 校验便携 Python 是否可运行
- 校验 NativeProbe 是否可运行
- 校验关键模块和状态栏依赖是否完整
- 若安装目录缺少关键依赖，尝试从原始解压目录自动补齐

## 安装后先做什么

安装完成后，先运行一次校验：

```text
verify_fixed_layout_runtime.cmd
```

如果校验通过，说明当前电脑上的固定布局程序运行依赖已经完整。

如果校验失败，再运行：

```text
repair_fixed_layout_runtime.cmd
```

修复脚本会：

- 检测当前安装目录缺少哪些关键文件
- 尝试从原始安装包解压目录补回缺失文件
- 重新执行运行时验证

如果原始解压目录已经被删掉，修复脚本会明确提示；这时重新用最新 ZIP 重新安装即可。

## 怎么启动程序

安装完成后，可以从以下位置启动：

- 开始菜单 `Video Platform Fixed Layouts`
- 桌面快捷方式目录 `Video Platform Fixed Layouts`
- 或安装目录下 `fixed_layout_programs\`

## 选哪个程序

按当前视频客户端的实际状态选：

- 当前客户端是非全屏宫格：启动 `*_windowed_fixed.bat`
- 当前客户端是全屏宫格：启动 `*_fullscreen_fixed.bat`

例如：

- 非全屏 12 宫格：`run_layout12_windowed_fixed.bat`
- 全屏 9 宫格：`run_layout9_fullscreen_fixed.bat`

## 常用热键

- `F2`：运行 / 暂停 / 继续
- `F8`：切换轮巡顺序
- `F9`：暂停时切到下一路
- `F10`：安全停止并退出
- `F11`：紧急回宫格并重启当前路

## 现场建议操作顺序

1. 先打开视频客户端，并切到目标布局。
2. 再启动对应固定布局程序。
3. 正常情况下不要在运行中手动改宫格。
4. 需要人工查看某一路时：
   - 先按 `F2` 暂停
   - 再按 `F9` 切到目标路
   - 看完后按 `F2` 继续
5. 如果只是顺序不满意：
   - 按 `F8`
6. 如果状态明显乱了：
   - 先按 `F11`
   - 还不行再按 `F10` 停止重开

## 首次安装后的验收建议

每台新电脑至少做一次下面的通过确认：

- 正常轮巡一整轮
- `F2 -> F2`
- `F2 -> F9 x6 -> F2`
- `F2 -> F8 -> F2`

## 还需要标定吗

固定布局程序不是完全“无标定概念”，而是已经内置了经过验证的固定比例点击/预览区域。

这意味着：

- 如果目标电脑的客户端版本、窗口形态、显示缩放、全屏/非全屏 chrome 结构和当前验收环境一致，通常不需要再单独标定。
- 如果换到新电脑后出现以下现象，就需要重新标定：
  - 点击点位明显偏移
  - 选中路和实际放大的路不一致
  - 预览区域采样位置不对
  - 相同布局下总是误判

所以结论是：

- 大多数同类环境下，固定布局安装后可以直接用，不需要先标定。
- 只有当新电脑的显示环境或客户端表现和当前验收环境差异明显时，才需要重新标定。

## 出现问题先收什么

先收这些目录和信息：

- 安装目录下 `logs\`
- 安装目录下 `fixed_layout_programs\logs\`
- 安装目录下 `fixed_layout_programs\tmp\runtime_locks\`
- 当前启动的是哪个入口
- `verify_fixed_layout_runtime.cmd` 的结果
- `repair_fixed_layout_runtime.cmd` 的结果

最新运行时校验报告在：

```text
logs\fixed_layout_runtime_verify_latest.json
```
