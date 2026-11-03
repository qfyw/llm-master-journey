# Day 6 笔记

1. Function Calling 里，模型真的「调用」了工具吗？**没有**——它输出的是一张**举手条**（`tool_calls` 数组：工具名 + JSON 参数 + 编号），真正执行的是我的 Python 程序。

2. 模型的「举手」藏在 `resp.choices[0].message.tool_calls`。注意它和取答案的 `.content` **是同一层**：同一个 message 包裹，平时装台词（content），举手时装举手条（tool_calls）。

3. 工具跑完后，结果用 `role="tool"` 塞回剧本；`tool_call_id` 是**快递单号**——一次可能举好几只手（同时要日期和天气），每个回执靠编号对上自己那只手。

4. 为什么必须先 `messages.append(msg)` 再回填结果：**顺序是协议，不是礼仪**。回执必须紧跟在举手记录后面；反了的话，剧本里出现一条孤立的 tool 消息、引用的编号在剧本里找不到对应的举手——轻则模型看不懂，重则接口 400 拒收。

5. 【合体清单】assistant.py 继承了：chat.py → **多轮剧本结构（messages）**；structured.py → **`json.loads` 解析工具参数**（arguments 是一段 JSON 字符串）；cost_log.py → **`ask()` 重试 + token 账本**。

## 今天真正记住的一件事

模型只举手，执行的人永远是我——工具能力是程序的，不是模型的。
