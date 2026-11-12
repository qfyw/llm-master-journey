# Day 13 笔记

1. 错误分类：`RETRYABLE_STATUS` 里的 408/429/5xx 可以重试，401/402/400 不能。
   为什么「能修的错才重试」？如果一个 401（key 错）也重试 3 次，用户实际要等多久、日志里会多出什么？
   （把 Day 5 的「常见错误 → 处理方式」清单翻出来对照）

2. 两层重试叠在一起：OpenAI SDK 默认自己会重试 2 次，我们的 `ask_once` 又循环 3 次。
   最坏情况下一次操作实际发了几次 HTTP 请求？为什么今天要把 `max_retries` 设为 0？
   另外，固定等 2 秒 vs 2s → 4s 的指数退避，区别在哪？生产环境为什么还要加 jitter（随机抖动）？

3. 今天的账本只记成功调用：失败/重试的成本去哪了？
   `bill-summary.md` 的合计和供应商真实账单可能差在哪？（至少说两个原因）

4. 账单按「日期」和「调用点」两个维度汇总，各能回答什么问题？
   用你生成的账单看一眼：哪条线最贵？如果下个月要把花费降一半，你先动哪条线、怎么动？

5. `usage.jsonl` 不进 Git，而 `bill-summary.md` 和 `usage.example.jsonl` 进 Git——
   三者的边界分别是什么？如果 example 文件里直接复制了真实账本，会泄露什么？

## 今日验收

- [ ] `python week2/bill_summary.py week2/usage.example.jsonl week2/bill-summary.example.md` 能出两张表
- [ ] 合计对得上：6 次调用 / 输入 1732 / 输出 442 / 0.007000 元（示例数据）
- [ ] 坏 key 只尝试 1 次就停（不再傻等 3 轮）
- [ ] 断网/BASE_URL 指向坏端口时，能看到 2s → 4s 的退避重试
- [ ] `python week2/assistant_v2.py` 正常记录/查询/总结，退出时能看到失败/重试次数

> 坏 key 测试：`API_KEY=sk-bad python week2/assistant_v2.py`
> （`load_dotenv()` 默认不覆盖已存在的环境变量，所以命令行传的值会赢）
>
> 断网测试：`BASE_URL=http://127.0.0.1:9/v1 python week2/assistant_v2.py`
> 然后随便说一句「今天卧推80kg 5组5次」，观察 2s → 4s 的等待。

## 今天真正记住的一件事

（待补）
