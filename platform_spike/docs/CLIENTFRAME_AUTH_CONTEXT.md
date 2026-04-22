# `clientframe` 认证上下文分析

这份说明对应脚本：

- [analyze_clientframe_auth_context.py](/home/lenovo/projects/video_platform_release/platform_spike/scripts/analyze_clientframe_auth_context.py)

目标不是直接取代 live probe，而是把 `clientframe` 日志里：

- `GetClientTicket log push back`
- `map_context_token_ insert`
- `getProxyedInfoByType`

这些线索按服务重新整理，回答一个更具体的问题：

> `xres-search` 和 `tvms` 在最近一次真实会话里，更像是拿了哪几个 `context token`？

## 用法

```bash
python3 platform_spike/scripts/analyze_clientframe_auth_context.py \
  "/mnt/d/opsmgr/Infovision Foresight/client/framework/infosightclient.1/logs/clientframe/clientframework.clientframe.debug.log" \
  --date-prefix 2026-04-01 \
  --output tmp/clientframe_auth_context_20260401.json
```

## 当前 2026-04-01 结论

当前这次会话里，脚本已经把大量服务请求和 token 事件重新按时间窗关联了一遍。

最关键的结果不是“有很多 token”，而是：

- `xres:xres-search`
- `tvms:tvms`

这两组都明显收敛到同一对优先候选：

- `C4E7E8C0673248E3c7e2aece94bc4189ad8a234f30e8aa29`
- `C4E7E8C0673248E303AB00892F6FBFA84CE7384499CDDDBE89139D628EB3EC38681F83E0BF20CC0833`

这说明当前 live probe 后续要优先做的，不再是无限扩 header 组合，而是：

1. 继续优先试这两个服务级 token
2. 继续找“容器侧真实票据获取方式”
3. 必要时区分：
   - `TGT`
   - `client_token`
   - `context token`

## 当前价值

这份分析不会直接让认证成功，但会把下次短时政务网窗口里的探测顺序缩小到更可信的一组候选。
