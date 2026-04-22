# Windows 本机资料盘点（2026-03-31）

本文件记录在当前电脑 Windows 环境中已确认存在、且可直接用于 `platform_spike` 方案推进的本地资料。

## 结论

当前机器上已经具备继续推进 Web 插件 / OpenAPI / SDK 路线所需的第一批本地资料，不需要再从桌面客户端 UI 自动化继续硬顶。

已确认存在：

- 已安装的视频平台客户端
- 已安装的 Web 控件 / Web 容器
- 客户端内置的本地嵌入页 Demo
- 本地 OpenAPI 开发指南压缩包
- 本地 JS SDK 压缩包
- 客户端组件安装包 / 升级包

## 一、已安装客户端与关键进程

真实运行中的关键进程路径：

- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\ClientFrame.exe`
- `D:\opsmgr\Infovision Foresight\client\components\vsclient.1\bin\VSClient.exe`
- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\containocx\ChromeContainer\WebControl.exe`

这说明当前环境不是只有桌面客户端，还同时装有 WebControl 容器。

## 二、已安装 Web 控件 / Web 容器

### 1. WebControl 与 ActiveX

目录：

- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\containocx\ChromeContainer\WebControl.exe`
- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\containocx\ChromeContainer\WebControlActiveX.ocx`
- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\containocx\ChromeContainer\LocalServiceConfig.xml`

安装/升级脚本：

- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\script\clientframe\postinstall.bat`
- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\script\clientframe\upgrade.bat`

从脚本可确认：

- 注册了 `InfoSightWebControlPlugin` URL Protocol
- 开机自启动了 `WebControl.exe`
- 运行时以 `HIGHDPIAWARE` 启动

### 2. LocalServiceConfig 关键信息

文件：

- `D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\bin\ClientFrame\containocx\ChromeContainer\LocalServiceConfig.xml`

关键信息：

- `SingleInstanceName = InfoSightWebControl.lock`
- WebSocket 端口范围：`14600-14609`
- `RunAdmin = true`
- `AutoLog = true`

这说明 WebControl 本地服务具备固定端口范围和单实例锁，后续可以优先从本地 WebSocket / 本地桥接能力入手验证。

## 三、webcontainer 组件

目录：

- `D:\opsmgr\Infovision Foresight\client\components\webcontainer.1`

关键可执行文件：

- `bin\webcontainer\MainBrowser.exe`
- `bin\webcontainer\SimpleWebServer.exe`
- `bin\webcontainer\BrowserSubProcess.exe`

组件元数据：

- `META-INF\component.xml`
- `META-INF\config.xml`
- `META-INF\menus.xml`
- `META-INF\language\zh_CN\function_description.txt`
- `META-INF\language\zh_CN\changelog.txt`

已确认信息：

- `component.xml` 标记该组件为 `id="webcontainer"`，`frameworkType="client"`
- `function_description.txt` 文案为“根据URL生成对应的web页面，该页面可被客户端框架集成为菜单并展示”
- `changelog.txt` 提到“修复未接收到客户端全屏模式消息的问题”

这说明 webcontainer 不是无关组件，而是客户端官方内嵌页面承载能力。

## 四、客户端内置本地嵌入页 Demo

Demo 页面：

- `D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\bin\webcontainer\webapp\webappdemo\main.html`

页面标题：

- `客户端本地嵌入页面Demo`

页面内直接展示了以下容器桥接请求：

- `GetLoginInfo`
- `GetInfoFromFrame`
- `getProxyInfoByType`
- `getServiceInfoByType`
- `getTickets`
- `subscribeEvent`

页面内还包含一个代理访问接口示例：

- `https://10.33.26.198:443/xres-search/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=admin`

并且带有：

- `Token` 请求头
- `/proxy` 代理转发示例
- `window.cefQuery(...)` 容器桥接调用

这说明当前机器上已经存在一个官方风格的“客户端内嵌 Web 页面 + 容器桥接 + 取票据 + 服务寻址 + 代理访问后端接口”的完整样例。

## 五、webcontainer 日志中的直接证据

日志文件：

- `D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\logs\webcontainer\webcontainer.webcontainer.debug.log`

日志中可直接看到：

- `method":"getTickets"`
- 返回 `ticket`

这说明容器桥接的取票据调用在这台机器上真实跑过，不只是 Demo 静态页面。

## 六、本机已有安装包 / 组件包

组件包目录：

- `D:\opsmgr\Infovision Foresight\client\packages\components`
- `D:\opsmgr\Infovision Foresight\client\packages\framework`

已确认包：

- `D:\opsmgr\Infovision Foresight\client\packages\framework\infosightclient_2.1.3.20220721212420.zip`
- `D:\opsmgr\Infovision Foresight\client\packages\components\webcontainer_2.0.2.20220121161552_Win.zip`
- `D:\opsmgr\Infovision Foresight\client\packages\components\vsclient_1.100.2.20230711224241.zip`
- `D:\opsmgr\Infovision Foresight\client\packages\components\vsclient_1.2.0004.20220823125534_Win.zip`
- `D:\opsmgr\Infovision Foresight\client\packages\components\videoplay_1.17.0.20230722171427.zip`

这意味着如果后面需要做组件级逆向梳理、样例提取或版本对照，本机材料已经够用。

## 七、本机已有 OpenAPI 文档

桌面上发现两份相同压缩包：

- `C:\Users\lenovo\Desktop\平时文件\项目\平安法制一体化\Infovision Foresight V1.3.1 OpenAPI 开发指南 (4).zip`
- `C:\Users\lenovo\Desktop\平时文件\各类说明书\Infovision Foresight V1.3.1 OpenAPI 开发指南 (4).zip`

压缩包内文件：

- `资源目录服务.docx`
- `视频应用服务.docx`
- `智能基础服务.docx`
- `智能应用服务.docx`
- `通用服务.docx`
- `智能分析服务.docx`

从文档正文已确认的关键能力：

- `资源目录服务.docx`
  - 获取所有树编码
  - 分页获取区域列表
- `视频应用服务.docx`
  - 根据监控点编号获取预览 URL
  - 根据监控点编号和时间获取回放 URL
  - 文档明确写到监控点编号可通过“分页获取监控点资源”获取
- `通用服务.docx`
  - 用户分页查询

这已经足够支撑第一版 POC 的基础链路：

- 查询资源树 / 区域 / 监控点
- 根据监控点取预览 URL
- 用自控播放器或官方能力承载预览

## 八、本机已有 SDK 压缩包

桌面上确认存在：

- `C:\Users\lenovo\Desktop\open-js-sdk-xslink1.7.1-20260302.7z`
- `C:\Users\lenovo\Desktop\三方指令配置_20260228121853\open-js-sdk-xslink1.7.1-20241014.7z`

已进一步确认 `open-js-sdk-xslink1.7.1-20260302.7z` 可展开，内容包括：

- `socket.js`
- `testSocket.vue`
- `说明文档.docx`
- `第三方对接nlp做文字分析说明.docx`

从源码和说明文档可确认：

- 它通过 `wss://127.0.0.1:20192/hibot/v1/testApp` 建立本地 WebSocket 长连接
- 示例联动应用名为 `bvoicectrl`
- 示例主题事件为 `switch_point_mode`
- 主要用于 `hibot` 语音 / NLP 联动，而不是视频预览控件

所以它不是本项目最想要的“视频预览 Web 插件 SDK”，但它证明了这台机器上已经存在“本地服务 + 前端 SDK + 事件回调”的正式对接模式。

## 九、对当前项目的实际意义

结合以上本机资料，后续不应再以“识别桌面客户端当前到底是几宫格/是否全屏”为主问题。

更合理的路线是：

1. 先基于本机 OpenAPI 文档确认“资源查询 + 预览 URL 获取”闭环。
2. 再基于本机 WebControl / webcontainer Demo 验证“登录态 / token / proxy / 服务寻址 / 事件订阅”闭环。
3. 最后做 `platform_spike` POC，优先实现：
   - 打开 4 宫格
   - 切 9 宫格
   - 放大一路
   - 返回

如果 WebControl / open-js-sdk 可直接承载预览控件，则优先走 Web 路线；如果本地 SDK 更稳，再补 SDK 播放壳。

## 十、建议的下一步

优先顺序：

1. 结构化提取 OpenAPI 文档中的“资源查询 / 监控点查询 / 预览 URL / 鉴权”接口
2. 把 `webappdemo` 的桥接调用改造成最小测试页
3. 继续查找本机是否还留有真正的视频预览 Web SDK / Web 插件开发包
4. 在仓库内搭建真正的 `platform_spike` POC 壳
