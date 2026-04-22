# 本机电视墙 API 最小清单

这份清单来自本机已解开的 OpenAPI 文档：

- [tmp/openapi_local_docs/视频应用服务.docx](/home/lenovo/projects/video_platform_release/tmp/openapi_local_docs/视频应用服务.docx)

它的用途不是做完整接口手册，而是把当前最能替代“桌面客户端宫格/放大/返回”动作的那一小组接口固定下来，直接服务 `platform_spike` POC。

## 目标动作映射

### 1. 电视墙资源发现

- 获取电视墙大屏信息
  - `POST /api/tvms/v1/tvwall/allResources`
  - 用途：
    - 找 `tvwall_id`
    - 找 `dlp_id`
    - 找 `pos`
    - 找窗口相关 `wnd_uri`

- 获取电视墙场景列表
  - `POST /api/tvms/v1/tvwall/scenes`

- 获取电视墙窗口信息列表
  - `POST /api/tvms/v1/tvwall/wnds/get`
  - 请求体：
    - `dlp_id` 可选
  - 返回重点字段：
    - `wnd_id`
    - `wnd_uri`
    - `status`
    - `camera.index_code`
    - `stream_url`

### 2. 宫格切换

- 非开窗设备窗口分割
  - `POST /api/tvms/v1/public/tvwall/monitor/division`
  - 请求体：
    - `dlp_id`
    - `monitor_pos`
    - `div_num`
  - `div_num` 文档支持：
    - `1`
    - `2`
    - `4`
    - `6`
    - `8`
    - `9`
    - `12`
    - `16`
    - `25`
    - `36`

- 浮动窗口分割
  - `POST /api/tvms/v1/public/tvwall/floatWnd/division`
  - 请求体：
    - `dlp_id`
    - `floatwnd_id`
    - `div_num`

### 3. 放大与返回

- 窗口放大
  - `POST /api/tvms/v1/public/tvwall/floatWnd/zoomIn`
  - 请求体：
    - `dlp_id`
    - `floatwnd_id`
    - `wnd_uri`
    - `type`
  - `type` 说明：
    - `full_screen` 表示放大到全屏
    - 不填或 `normal` 表示普通放大

- 窗口还原
  - `POST /api/tvms/v1/public/tvwall/floatWnd/zoomOut`
  - 请求体：
    - `dlp_id`
    - `floatwnd_id`

### 4. 其他可选补充

- 窗口批量创建
  - `POST /api/tvms/v1/public/tvwall/floatWnds/addition`

- 窗口批量删除
  - `POST /api/tvms/v1/public/tvwall/floatWnds/deletion`

- 窗口漫游
  - `POST /api/tvms/v1/public/tvwall/floatWnd/move`

- 窗口置顶/置底
  - `POST /api/tvms/v1/public/tvwall/floatWnd/layerCtrl`

## 对当前 POC 的直接意义

如果这些接口在当前部署环境可用，那么用户原本依赖桌面客户端快捷键完成的：

1. `4 宫格`
2. `9 宫格`
3. `12 宫格`
4. `放大一路`
5. `返回宫格`

就可以被平台 API 直接替代，而不再需要：

- 猜当前桌面客户端处于几宫格
- 猜当前是否全屏
- 靠 OpenCV 识别宫格线
- 靠 UIA 猜按钮

## 当前仓库对应实现

这组接口已经接入到：

- [platform_spike_poc.html](/home/lenovo/projects/video_platform_release/platform_spike/web_demo/platform_spike_poc.html)
- [platform_spike_poc.js](/home/lenovo/projects/video_platform_release/platform_spike/web_demo/platform_spike_poc.js)

页面里对应按钮包括：

- `Monitor Divide 4 / 9 / 12`
- `Float Divide 4 / 9 / 12`
- `Zoom Normal`
- `Zoom Fullscreen`
- `Zoom Out`

下一步只要客户端容器会话能起来，就可以直接验证这组官方接口能不能覆盖你原来依赖桌面客户端的动作链。
