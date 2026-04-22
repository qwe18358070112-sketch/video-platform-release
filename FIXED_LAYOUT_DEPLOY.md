# 固定布局多机部署说明

这份说明只覆盖已经确认通过的固定布局程序：

- 非全屏 `4/6/9/12`
- 全屏 `4/6/9/12`

目标是把这 8 套程序部署到其他 Windows 电脑上，并且尽量不要求目标机预装 Python 或 .NET。

## 交付形态

当前固定布局交付有两条线：

### 1. 独立 ZIP 包

每个布局/模式一个独立包，例如：

- `video_platform_release_layout4_windowed_fixed.zip`
- `video_platform_release_layout4_fullscreen_fixed.zip`
- 其他布局同理

特点：

- 解压后直接运行对应 BAT
- 包内自带 `runtime/python/python.exe`
- 包内自带 `runtime/native_runtime/VideoPlatform.NativeProbe.exe`
- 包内自带 `verify_fixed_layout_runtime.cmd`
- 不要求目标机先装 Python 或 .NET

### 2. 固定布局套装包

套装包名称：

- `video_platform_release_fixed_layout_suite.zip`

特点：

- 一次性包含 8 套已验证程序
- 同时包含一键安装脚本和图形安装入口
- 同时包含校验和修复入口
- 适合现场统一安装到固定目录

## 目标机安装方式

### 方式 A：直接使用独立 ZIP

1. 把目标 ZIP 复制到目标 Windows 电脑。
2. 解压到本地目录，例如：

```text
D:\video_platform_release_layout4_fullscreen
```

3. 直接双击对应入口，例如：

```text
fixed_layout_programs\run_layout4_fullscreen_fixed.bat
```

4. 如需停止当前固定布局实例，执行：

```text
fixed_layout_programs\stop_fixed_layout_selector.bat 4 fullscreen
```

### 方式 B：一键安装脚本

1. 解压 `video_platform_release_fixed_layout_suite.zip`
2. 双击：

```text
install_fixed_layout_suite.cmd
```

默认行为：

- 安装到当前用户目录下的固定路径
- 写入开始菜单快捷方式
- 注册卸载入口
- 验证随包 Python 和 NativeProbe 可运行
- 如关键依赖缺失，自动从原始解压目录补齐
- 写入“Verify Fixed Layout Installation”快捷方式，便于目标机定位环境问题
- 写入“Repair Fixed Layout Installation”快捷方式，便于目标机修复缺失依赖

### 方式 C：图形安装入口

1. 解压 `video_platform_release_fixed_layout_suite.zip`
2. 双击：

```text
install_fixed_layout_suite_gui.cmd
```

图形安装器会让操作员选择安装目录，并确认是否创建桌面快捷方式目录。

## 安装完成后的使用入口

套装安装完成后，推荐从下面两个位置启动：

- 开始菜单 `Video Platform Fixed Layouts`
- 桌面快捷方式目录 `Video Platform Fixed Layouts`

快捷方式默认只暴露当前已验证的模式化入口，也就是：

- 非全屏 `4/6/9/12`
- 全屏 `4/6/9/12`

如果安装后程序运行不起来，先运行：

```text
verify_fixed_layout_runtime.cmd
```

如果校验失败，再运行：

```text
repair_fixed_layout_runtime.cmd
```

它会在安装目录下生成：

```text
logs\fixed_layout_runtime_verify_latest.json
```

用于定位是 Python、本地模块、NativeProbe 还是启动链问题。

详细操作步骤和热键说明见：

- `FIXED_LAYOUT_INSTALL_AND_USE.md`

## 卸载

安装版默认通过下面入口卸载：

- 开始菜单中的 `卸载固定布局程序`
- 或直接运行：

```text
uninstall_fixed_layout_suite.cmd
```

默认行为：

- 删除开始菜单和桌面快捷方式
- 注销卸载注册项
- 备份 `logs/` 和 `tmp/` 后再删除安装目录

## 部署前建议

每次准备发给其他 Windows 电脑前，固定做下面三步：

1. 重新生成固定布局程序：

```text
python platform_spike/scripts/generate_fixed_layout_programs.py --include-modes
```

2. 重新打包固定布局分发包：

```text
platform_spike\scripts\package_fixed_layout_programs.cmd --include-modes
```

3. 抽检以下内容：

- 独立 ZIP 能解压并看到 `runtime/python/python.exe`
- 套装包内存在 `install_fixed_layout_suite.cmd`
- 套装包内存在 `install_fixed_layout_suite_gui.cmd`
- 套装包内存在 `runtime/native_runtime/VideoPlatform.NativeProbe.exe`

## 问题收集

目标机现场出现问题时，优先收集：

- 安装目录下 `logs/`
- 安装目录下 `fixed_layout_programs/logs/`
- 安装目录下 `fixed_layout_programs/tmp/runtime_locks/`
- 当前启动的是哪一个布局/模式入口

如果是安装问题，再额外记录：

- 使用的是独立 ZIP 还是套装安装
- 是否从 `install_fixed_layout_suite.cmd` 安装
- 是否从 `install_fixed_layout_suite_gui.cmd` 安装
- 安装目录是什么
