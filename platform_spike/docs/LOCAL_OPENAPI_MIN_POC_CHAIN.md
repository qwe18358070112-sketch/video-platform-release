# 本机 OpenAPI / Web 容器最小闭环

这个文档只整理当前电脑上已经确认存在、并且足够支撑第一版 `platform_spike` POC 的最小接口链。

## 目标

先验证下面这条链能否在自有页面里闭环：

1. 读取客户端登录态
2. 获取票据 / 服务信息
3. 通过容器代理访问平台接口
4. 查询树编码
5. 查询区域或监控点
6. 根据 `cameraIndexCode` 获取预览 URL

只要这条链跑通，后面再做 4 / 9 宫格与放大返回，技术风险就会明显收缩。

## 一、本机已有的容器桥接

来源：

- [main.html](/mnt/d/opsmgr/Infovision%20Foresight/client/components/webcontainer.1/bin/webcontainer/webapp/webappdemo/main.html)

### 1. 获取登录信息

请求：

```json
{
  "request": "GetLoginInfo"
}
```

用途：

- 确认当前内嵌页面是否运行在客户端容器里
- 把当前登录态、会话信息、平台地址等原始返回打印出来

### 2. 读取客户端框架信息

请求模板：

```json
{
  "request": "GetInfoFromFrame",
  "params": {
    "method": "getServiceInfoByType",
    "data": {
      "serviceType": "upm",
      "componentId": "upm"
    }
  }
}
```

本机 Demo 里已确认存在的 `method`：

- `getProxyInfoByType`
- `getServiceInfoByType`
- `getTickets`
- `subscribeEvent`

### 3. 获取票据

请求模板：

```json
{
  "request": "GetInfoFromFrame",
  "params": {
    "method": "getTickets",
    "data": {
      "total": 1,
      "type": 0,
      "tokenType": 1
    }
  }
}
```

本机日志里已确认该调用真实跑过，日志文件：

- [webcontainer.webcontainer.debug.log](/mnt/d/opsmgr/Infovision%20Foresight/client/components/webcontainer.1/logs/webcontainer/webcontainer.webcontainer.debug.log)

### 4. 通过容器代理访问平台接口

Demo 中请求示例：

```json
{
  "method": "POST",
  "timeout": 15,
  "url": "https://10.33.26.198:443/xres-search/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=admin",
  "heads": {
    "Content-Type": "application/json",
    "Token": ""
  },
  "body": {
    "resourceType": "CAMERA",
    "catalogDictionaryCode": [
      "basic_tree",
      "bvideo_basic_tree",
      "imp_tree"
    ]
  }
}
```

发起方式：

- `POST /proxy`

这说明容器可以把页面请求代理到平台服务。

## 二、本机 OpenAPI 文档里已确认的关键接口

来源目录：

- [tmp/openapi_local_docs](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs)

### 1. 获取所有树编码

来源：

- [资源目录服务.docx](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs/资源目录服务.docx)

接口：

- `POST /api/resource/v1/unit/getAllTreeCode`

请求体：

```json
{}
```

关键返回字段：

- `data.list[].treeCode`
- `data.list[].treeName`

### 2. 分页获取区域列表

来源：

- [资源目录服务.docx](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs/资源目录服务.docx)

接口：

- `POST /api/resource/v1/regions`

请求体：

```json
{
  "pageNo": 1,
  "pageSize": 100,
  "treeCode": "0"
}
```

关键返回字段：

- `data.list[].indexCode`
- `data.list[].name`
- `data.list[].parentIndexCode`
- `data.list[].treeCode`

### 3. 分页获取监控点资源

来源：

- [资源目录服务.docx](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs/资源目录服务.docx)

接口：

- `POST /api/resource/v1/cameras`

请求体：

```json
{
  "pageNo": 1,
  "pageSize": 100,
  "treeCode": "0"
}
```

关键返回字段：

- `data.list[].cameraIndexCode`
- `data.list[].name`
- `data.list[].deviceIndexCode`
- `data.list[].unitIndexCode`
- `data.list[].status`

### 4. 获取监控点预览 URL

来源：

- [视频应用服务.docx](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs/视频应用服务.docx)

接口：

- `POST /api/video/v1/cameras/previewURLs`

请求体：

```json
{
  "cameraIndexCode": "camera-uuid",
  "streamType": 0,
  "protocol": "ws",
  "transmode": 1
}
```

关键参数：

- `cameraIndexCode`: 必填
- `streamType`: 0 主码流 / 1 子码流
- `protocol`: `rtsp` / `rtmp` / `hls` / `ws`
- `transmode`: 0 UDP / 1 TCP
- `expand`: 可选扩展字段

关键返回字段：

- `data.url`

文档里明确说明：

- `ws` 适合 H5 视频播放器
- `hls` 适合 H5 页面取流播放
- `rtsp` 既可标准 RTP 方式，也可海康 SDK 方式

## 三、当前最小验证顺序

建议严格按这个顺序做：

1. `GetLoginInfo`
2. `getTickets`
3. `POST /api/resource/v1/unit/getAllTreeCode`
4. `POST /api/resource/v1/cameras`
5. `POST /api/video/v1/cameras/previewURLs`

原因：

- 先判断容器桥接是否可用
- 再判断平台代理是否可用
- 再判断资源目录是否可用
- 最后才判断预览 URL 能否拿到

## 四、当前仍未确认的点

本机资料已经足够让我们开始做测试页，但下面这些点还需要跑页面时确认真实返回：

- `GetLoginInfo` 具体返回字段名
- `getTickets` 返回的是 `ticket` 还是可直接当 `Token` 使用的值
- `/proxy` 是否会自动继承当前客户端会话
- `previewURLs` 返回的 `ws` / `hls` URL 是否可直接在自建页面里播放

## 五、对 POC 的直接意义

只要上面五步里的前四步跑通，`platform_spike` 就已经不再受桌面客户端宫格识别问题限制。

后面再做：

- 4 宫格
- 9 宫格
- 放大一路
- 返回

就只是“自有页面内部状态管理”的问题，而不再是“从外部猜桌面客户端当前是什么状态”的问题。

