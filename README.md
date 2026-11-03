# llm-master-journey

LLM 应用开发 · 渐进负荷版的执行记录。
内容地图：[llm-master](https://github.com/youngyangyang04/llm-master)

> **第 1 周成品**：一个能跑、能解释的 AI 命令行助手——多轮记忆、流式输出、结构化输出、成本账本、函数调用。

## 运行环境

- 接口：OpenCode Go 的 OpenAI 兼容端点 `https://opencode.ai/zen/go/v1`（key 管理：https://opencode.ai/auth）
- `.env`（已被 .gitignore 排除）：`API_KEY` / `BASE_URL` / `MODEL` / `SESSION_ID`
- 换模型只改 `MODEL`；换服务商只改 `BASE_URL` + `MODEL`，代码不用动

## 五个脚本，五级台阶

| 脚本 | 能力 | 一句话原理 |
|---|---|---|
| `week1/day01_hello.py` | 让模型响一声 | 一次请求 = SDK 发 HTTPS → 推理服务端 → 逐 token → SDK 拼装 |
| `week1/chat.py` | 多轮记忆 + 打字机 | 模型无状态：每次把**整个 messages 历史**重发，记忆在程序手里 |
| `week1/structured.py` | 结构化输出 | 提示词立合同 + `json.loads` 验收；保形状不保语义 |
| `week1/cost_log.py` | 重试 + 账本 | 错误分类：能修的睡 2 秒再试，修不好的别固执 |
| `week1/assistant.py` | 函数调用 CLI | 模型只「举手」，程序执行工具并把回执塞回剧本 |

## 跑

```bash
python week1/chat.py                          # 交互聊天（打字机效果）
python week1/structured.py                    # 学习计划 → JSON 任务列表
python week1/cost_log.py                      # 带重试与账单的对话
python week1/assistant.py "今天几号？"         # 触发 get_date 工具
```

样例（assistant.py 的真实输出）：

```
[工具] get_date({}) → 2026-11-03
助手：今天是 2026 年 11 月 3 日。
[token] 输入 339 / 输出 16 ｜ 约 0.000806 元
```

`week1/probe.py` 是体检脚本：key、网络、模型名哪个坏了，它指给你看。

## 进度

- Day 1-6 完成：五个脚本 + 每日笔记（`week1/notes/`）+ 阅读队列（`week1/reading-queue.md`）
- 待办：Day 7 推送 GitHub + 写本周复盘三问

## 本周复盘（Day 7 填）

1. 这周我学到了什么、能一句话讲清的概念？
2. 这周留下了什么能看的东西？
3. 下周只改一件事，改什么？
