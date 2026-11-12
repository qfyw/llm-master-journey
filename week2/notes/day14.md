# Day 14 笔记：第 2 周复盘

## 本周复盘（4 问）

1. 这周我学到了什么、能一句话讲清的概念？
（待补）

2. 这周留下了什么能看的东西？
（待补：v2.5 能记录 / 查询 / 周总结 / 记账 / 出账单；Day 8-13 笔记；一串 commit）

3. 下周只改一件事，改什么？
（待补）

4. 助手 v2 这周你真的在用吗？如果没有，是哪一步碍事？
（待补。`workouts.jsonl` 现在只有 2 条记录——这是最诚实的指标，不用美化）

## 阅读补档：function_calling.md（10 分钟）

对照 Day 6 的 `week1/assistant.py`，回答四句：

- Tool / Function 本质是什么？模型自己执行吗？
  （待补）
- 一次工具调用里，哪一步是「控制权交接」？为什么这一步必须在程序里？
  （待补）
- 为什么工具执行结果要作为一条 message 塞回 `messages`？
  （待补）
- 工具说明书每轮都要重发，这对输入 token 和成本意味着什么？
  （待补：Day 12 账本里带工具的请求输入 339 token，比普通对话贵得多）

## 本周交付检查

- [ ] `week2/assistant_v2.py` 正常跑通记录 / 查询 / 周总结
- [ ] `python week2/bill_summary.py` 用真实账本生成 `week2/bill-summary.md`（现在有 2 条真实记录）
- [ ] 第 2 周复盘写进 `README.md`
- [ ] `function_calling.md` 对账完成，勾掉阅读队列
- [ ] `git push` 到 GitHub（本地领先 origin 8 个 commit）
- [ ] （可选）算法日：704 二分查找手写 + `algo/NOTES.md` 记卡点

## 第 3 周准备

- 主题：RAG 最小闭环——用 `study-materials` 当语料：切块 → embedding → 检索 → 带引用回答
- 第一件事：（待补）
