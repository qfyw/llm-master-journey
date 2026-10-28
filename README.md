# llm-master-journey

LLM 应用开发 · 渐进负荷版的执行记录。
内容地图：[llm-master](https://github.com/youngyangyang04/llm-master)

## 第 1 周目标

一个**能跑、能解释、在 GitHub 上**的 AI 命令行助手 v1。

## 运行环境

接口是 OpenCode Go 的 OpenAI 兼容端点 `https://opencode.ai/zen/go/v1`，key 在 https://opencode.ai/auth 管理。
`.env` 里四个值：

| 字段 | 含义 |
|---|---|
| `API_KEY` | `oc_` 开头的 key，不提交、不外发 |
| `BASE_URL` | `https://opencode.ai/zen/go/v1` |
| `MODEL` | 当前用 `deepseek-v4.1-flash` |
| `SESSION_ID` | 本客户端的稳定会话 ID，go 套餐要求请求头带它 |

换模型只改 `MODEL` 一行；换服务商只改 `BASE_URL` + `MODEL` 两行，代码不用动。

## 跑

```bash
python week1/day01_hello.py   # 发一次对话，打印回复和 token
python week1/probe.py         # 出问题时先跑这个，它会指出是哪一环坏了
```

## Day 1 记录

- [x] 第一次对话跑通（2026-10-28）
- [ ] 改一句 prompt 再跑一次
- [ ] 5 行笔记（`week1/notes/day01.md`）

## 本周复盘（Day 7 填在最上面）

1. 这周我学到了什么、能一句话讲清的概念？
2. 这周留下了什么能看的东西？
3. 下周只改一件事，改什么？
