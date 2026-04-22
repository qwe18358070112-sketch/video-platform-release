# 本地 `platform_spike_probe` 菜单注入

这份说明只针对当前这台机器上已安装的视频平台客户端。

## 背景

当前已经确认：

- 本机 `webcontainer` 自带静态服务，监听 `http://127.0.0.1:36753`
- 已发布联调页：
  - `http://127.0.0.1:36753/platform_spike_probe/index.html`
- 客户端菜单由安装目录下的 `product/META-INF/menus.xml` 驱动
- `type="external"` 的菜单会把 `url` 原样传给 `MainBrowser`

因此，最短联调路径不是继续逆向 LPC，而是直接给客户端菜单增加一个外部页入口。

## 注入脚本

脚本路径：

- [manage_local_probe_menu.sh](/home/lenovo/projects/video_platform_release/platform_spike/scripts/manage_local_probe_menu.sh)

支持五个动作：

- `install`：安装菜单、翻译和图标
- `install-ipoint-slot`：不新增菜单，直接复用已授权的 `ipoint` 外部入口，指向最小探针页
- `install-ipoint-poc-slot`：不新增菜单，直接复用已授权的 `ipoint` 外部入口，指向新的 POC 壳
- `install-video-monitor-poc-slot`：不新增菜单，直接复用已授权的 `client0101`，也就是“视频监控”入口，指向新的 POC 壳
- `remove`：恢复备份，移除菜单
- `status`：查看当前注入状态

默认会修改：

- `/mnt/d/opsmgr/Infovision Foresight/client/product/META-INF/menus.xml`
- `/mnt/d/opsmgr/Infovision Foresight/client/product/META-INF/language/zh_CN/translate.properties`
- `/mnt/d/opsmgr/Infovision Foresight/client/product/META-INF/icon/menu`

首次安装会自动备份到：

- `/mnt/d/opsmgr/Infovision Foresight/client/product/META-INF/.platform_spike_backup`

## 用法

安装：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh install
```

复用 `ipoint` 已授权入口：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh install-ipoint-slot
```

直接复用 `ipoint` 打开 POC 壳：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh install-ipoint-poc-slot
```

直接复用“视频监控”入口打开 POC 壳：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh install-video-monitor-poc-slot
```

查看状态：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh status
```

移除并恢复原配置：

```bash
./platform_spike/scripts/manage_local_probe_menu.sh remove
```

## 注入结果

脚本会新增一个菜单：

- 菜单代码：`platform_spike_probe`
- 页面地址：`http://127.0.0.1:36753/platform_spike_probe/index.html`
- 菜单名称：`平台联调探针`

如果选择 `install-ipoint-slot`：

- 不新增新菜单
- 保留客户端原有的 `点位搜索`
- 只把它背后的外部 URL 改为本地探针页

如果选择 `install-ipoint-poc-slot`：

- 不新增新菜单
- 保留客户端原有的 `点位搜索`
- 直接把它背后的外部 URL 改为 `platform_spike_poc.html?autorun=1`

如果选择 `install-video-monitor-poc-slot`：

- 不新增新菜单
- 不走 `点位搜索`
- 直接复用当前客户端的“视频监控”入口
- 这更符合当前项目真实使用路径：登录客户端后，点击“视频监控”进入轮询/预览工作流

这条路线更适合当前客户端，因为从历史日志看，客户端还会对菜单做授权过滤；直接新增菜单代码，未必会出现在最终可见菜单里。

## 生效条件

客户端通常会在启动时读取 `menus.xml` 和翻译文件。

因此：

- 如果当前客户端已经启动，通常需要重启客户端后新菜单才会显示
- 如果只需要验证静态页是否可访问，可以先直接访问本地地址，不必重启

## 当前新增结论

这次真实联调又确认了一件事：

- 即使本地 `menus.xml` 已经把 `client0101` 改到 `platform_spike_poc.html`
- 当前客户端仍然可能在运行时按服务端返回的 `vsclient_client0101` 菜单去加载原始“视频监控”

也就是说：

- 本地菜单重定向是**尽力而为**
- 不能把它当成唯一可靠入口

如果你重启客户端后，点击“视频监控”仍然没有进入 `platform_spike_poc.html`，不要继续反复改菜单。优先改走：

- `platform_quick_capture_bundle_windows.cmd`
- 或 `platform_quick_capture_bundle.sh`

先把在线窗口里的 `OPERATOR_RESULT` 留下来，再离线分析。

如果要在其他 Windows 电脑上推广，先看：

- [WINDOWS_MULTI_HOST_DEPLOY.md](/home/lenovo/projects/video_platform_release/platform_spike/docs/WINDOWS_MULTI_HOST_DEPLOY.md)

## 风险边界

这一步只是在本机客户端增加一个联调入口，不涉及服务端接口改造。

如果后续确认平台方支持更正规的插件注册或应用中心配置，应优先切回官方配置方式，而不是长期维护本地安装目录补丁。
