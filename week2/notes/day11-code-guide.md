# assistant_v2.py 逐行讲解（Day 11 版）

> 配套文件：`week2/assistant_v2.py`（v2.3，2026-11-09，commit `2cf095f`）
> 阅读方式：先看「全景」和三条线；记录线、查询线的旧部分只标行号（细节见 `day09-code-guide.md` / `day10-code-guide.md`）；今天的重点是**周总结**和**两处上下文清洗**。

```
运行：python week2/assistant_v2.py
记录：今天卧推85kg 5组5次
提问：我上次卧推多少？ / 这周练了几次？ / 这周练得怎么样？
今天的新分工：程序算数，模型写字——RAG 的「生成」那一半
```

---

## 一、全景：一个文件，三条线

| 区块 | 行号 | 职责 | 今天动了吗 |
|---|---|---|---|
| 文件头 + import | 1-21 | 说明、搬工具 | 换了主题 |
| 配置区 | 23-35 | 读 .env、建 client、数据路径 | 没动 |
| SYSTEM_PROMPT | 37-46 | 记录线的规则 + **few-shot 示例** | **加示例** |
| QUERY_PROMPT | 48-54 | 查询线的语义规则：四种意图怎么分 | **加一种** |
| WORKOUT_SCHEMA | 56-87 | 记录线的合同 | 没动 |
| QUERY_SCHEMA | 89-108 | 查询线的合同（枚举多一个词） | **加一词** |
| `ask_once()` | 111-130 | 发请求；网络重试 3 次；**传 schema 才套合同** | **改签名** |
| `is_valid()` / `parse_workout()` | 133-166 | 记录线的语义验收 + 两层重试 | 调用点补参数 |
| `save()` | 169-180 | 追加记录、数条数 | 没动 |
| `load_records()` | 186-196 | 读整个 jsonl，返回字典列表 | 没动 |
| `is_question()` | 199-207 | 规则路由：提问还是记录 | 没动 |
| `find_last()` | 210-216 | 从最新往回找某个动作 | 没动 |
| `count_this_week()` | 219-228 | 数本周（周一起）记录条数 | 没动 |
| `compute_week_stats()` | 231-270 | **本周聚合账本：次数 + 每个动作的累计/最好** | **新增** |
| `SUMMARY_PROMPT` | 273-279 | 给「写总结的模型」立的规则 | **新增** |
| `stats_for_model()` | 282-302 | **给模型的统计副本：去 0、改口径明确的键名** | **新增** |
| `write_summary()` | 305-317 | 程序算好的数字 → 模型组织成人话 | **新增** |
| `answer_question()` | 320-368 | 理解 → 查询/计算 → 表达 | **加分支** |
| `main()` | 371-395 | 输入循环 + 双分支分流 | 横幅改字 |

**调用图**：

```
main
 ├─ is_question? ──True──► load_records ──► answer_question ──► ask_once(QUERY_SCHEMA)
 │                                                ├─ last_exercise → find_last
 │                                                ├─ week_count    → count_this_week
 │                                                └─ week_summary  → compute_week_stats
 │                                                                     ↓
 │                                                                  stats_for_model
 │                                                                     ↓
 │                                                              write_summary → ask_once(不带 schema)
 └──────────────False──► parse_workout ──► ask_once(WORKOUT_SCHEMA) ──► save
```

三条线只共用一个东西：`ask_once` 里的网络层重试。**理解走网络，计算走本地，生成再回网络——但只带清洗过的统计，不带原始记录。**

---

## 二、逐行讲解

### 文件头（1-13）

```python
1  """Day 11：助手 v2.3——会写周报了。
...
7  今天的新分工（周总结 = RAG 的「生成」那一半）：
8  · 数字由程序算：compute_week_stats 在本地把本周记录聚合成一份统计（模型没见过原始记录）；
9  · 措辞由模型写：write_summary 只拿到统计 JSON，规则是「一个数字都不许编」。
...
12 · few-shot 进 SYSTEM_PROMPT：示例教语义（半小时→30、模糊→空），契约管形状。
13 """
```

- **7-11 行**：这一版的主题是「生成」。Day 9 学的是「格式交给合同」，Day 10 学的是「查数交给程序」，今天是最后一块：**数据经过程序加工后，再交给模型说人话**。这正是 RAG 的完整形状——检索/计算在本地，生成在模型，中间那层「交给模型什么」由程序决定。
- **12 行**：few-shot 和 schema 的分工一句话写清。示例教**语义**（怎么换算、什么时候给空），schema 管**形状**（字段齐不齐、类型对不对）。两者不重复。

### import / 配置区（14-35）

没动。`load_dotenv()` 进货 → `client` 按图纸造机器 → `model` / `DATA_FILE` 从环境与路径来。细节见 Day 9 指南。

### SYSTEM_PROMPT（37-46）——few-shot 加进来了

```python
42 SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成结构化记录。
43 规则：没提到的数值一律填 null；有氧运动用 minutes；日期用今天（今天是 """ + date.today().isoformat() + """）。
44 示例（只示范字段怎么填，不示范整张格式）：
45 - 「今天跑了半小时」→ {"name": "跑步", "minutes": 30}，其余数值字段填 null
46 - 「练了一下」→ {"exercises": []}"""
```

- **37-41 行**：注释里的三条要求，也是 few-shot 的三条设计原则：
  1. **只示范字段，不重抄整张 schema**——形状已经由 `WORKOUT_SCHEMA` 管了，示例再抄一遍只是白花 token；
  2. **示例不给日期**——写死哪一天，明天就过期。日期靠 43 行的插槽注入；
  3. **示例要演示「输入 → 输出」**，不是换一种说法讲规则。
- **44-46 行**：这就是 few-shot 的字面意思：给模型看几个「这样进、这样出」的样本。模型靠模式匹配学习，样本比规则句更接近它要产出的东西。
  - 第一条教**口语时间换算**：「半小时」→ `minutes: 30`。这是规则句容易漏、示例一给就懂的地方。
  - 第二条教**什么时候认输**：「练了一下」→ `exercises: []`。它同时给「空列表是合法输出」提供了一个样例，模型不会为了凑内容硬编。
- **你第一版的两个问题**（都在这次对账里修正了）：
  1. 把 `few-shot` 这个词写进了 prompt。那是我们之间的黑话——**prompt 是给模型看的，不是给我们看的**；术语对模型没有意义，只会占 token。
  2. 同一段内容写了两遍（一次接在规则句后面，一次写成「示例：」）。示例区不重复规则区的意思；重复 = 每次记录请求都多付一份钱。
- **成本提醒**：`SYSTEM_PROMPT` 是记录线**每次请求都重发**的固定成本。few-shot 写多长，账单就涨多少——这正是周末 `token_cost_latency.md` 要算的账。

### QUERY_PROMPT（48-54）——第四种意图

```python
52 - week_summary：问本周整体情况（例：「这周练得怎么样」「帮我总结下这周」）→ exercise 填 null
```

- **52 行**：新意图的**语义规则**：什么话算「问周总结」，以及 `exercise` 在这种情况下必须是 `null`。这条跨字段规则 schema 表达不了（schema 只能说「exercise 是字符串或 null」），只能写在 prompt 里 + 程序里兜底。
- **53 行**：`unknown` 仍然是兜底。四种意图的分界靠语义判断，模型负责；**但最终的形状由下一节的 enum 强制。**

### QUERY_SCHEMA（89-108）——枚举多一个词

```python
96             "intent": {
97                 "type": "string",
100                "enum": ["last_exercise", "week_count", "unknown", "week_summary"],
101            },
```

- **100 行**：`enum` 是**允许值清单**。加了 `week_summary`，模型才可能输出这个词；不写进 enum，它再理解也说不出来（只能硬塞进 `unknown`）。**prompt 教语义，enum 管词汇表——两边必须同步。**
- **顺序无所谓**：枚举不是优先级，模型是在四个词里选一个，不是按顺序命中。
- **`exercise` 在第 103 行**仍然可空；`week_summary` 时填 `null` 是语义约定，schema 管不到——所以 `answer_question` 里只用 `intent` 判断，不依赖 `exercise`（355-366 行）。

### ask_once()（111-130）——默认合同撤了

```python
111 def ask_once(messages: list[dict], schema: dict | None = None):
112     """发一次请求；网络层最多试 3 次。传了 schema 才套格式合同——总结是人话，不套。"""
113     for attempt in range(3):
114         try:
115             if schema is not None:
116                 resp = client.chat.completions.create(
117                     model=model,
118                     messages=messages,
119                     response_format={"type": "json_schema", "json_schema": schema},
120                 )
121             else:
122                 resp = client.chat.completions.create(
123                     model=model,
124                     messages=messages,
125                 )
126             return resp
127         except (APIConnectionError, APIStatusError) as e:
...
130     return None
```

- **111 行**：两个变化。
  - `dict | None` 是**类型提示**（Python 3.10+ 的写法，等价于 `Optional[dict]`）：告诉读代码的人「这里可以接一个 dict，也可以接 None」。它不拦运行，是文档。
  - 默认值从 `WORKOUT_SCHEMA` 改成 `None`：**不传第二个参数 = 普通文本请求**。
- **为什么改**：昨天的默认值假设「所有请求都要 JSON」。今天出现了第一种例外——总结是写给人看的，套 schema 反而多一层没用的约束，还可能把长文本塞进字段里变形。**不是所有输出都该结构化：给程序解析的才要合同，给人的要人话。**
- **115-125 行**：为什么写成两个分支而不是搞个 `kwargs`？因为你现在的水平，重复一次调用比多学一个 `**kwargs` 解包更划算。代码有重复，但每个分支一眼看懂。等以后调用点多了，再抽。
- **默认值变更的连带责任**：把默认值从「记录合同」改成「无合同」，**所有靠默认的调用点都会悄悄变语义**。所以 147 行 `parse_workout` 里那次调用必须显式补上 `WORKOUT_SCHEMA`。这就是今天的一课：**改默认值不是改一个函数，是改所有依赖默认值的调用现场。**
- **127-130 行**：网络层原封不动——3 次、睡 2 秒、失败 `None`。三条线共用。

### parse_workout()（139-166）——补一行

```python
146     for round_no in range(2):          # 第一次 + 语义纠错一次
147         resp = ask_once(messages, WORKOUT_SCHEMA)   # 默认合同撤了 → 记录线必须显式点名
```

- **147 行**：只加了第二个参数。含义变了：**合同的选择从函数内部搬到了调用现场**。记录线的人自己声明「我要这张合同」，`ask_once` 不再替谁做主。
- 如果这行忘了补：`ask_once` 会发一个普通文本请求，`resp.choices[0].message.content` 是人话，`json.loads` 立刻炸。**默认值改了但调用点没跟上，就是这种「运行到某条路径才炸」的错。**
- 其余逻辑（网络 3 次 + 语义 1 次 + 纠错消息）没动，见 Day 9 指南。

### save / load_records / is_question / find_last / count_this_week（169-228）

全部没动。逐行解释见 Day 10 指南。今天只需要记住：**周总结没有碰这些函数任何一行**，而它们的回归测试仍然通过——加功能不破坏旧功能的最小实践。

### compute_week_stats()（231-270）——程序侧的账本

```python
231 def compute_week_stats(records: list[dict]) -> dict:
232     """本周（周一起）的汇总：练了几次 + 每个动作的累计数据。只算，不说话。"""
233     today = date.today()
234     monday = today - timedelta(days=today.weekday())
235
236     sessions = 0
237     stats = {}   # 动作名 → {"times": 出现次数, "best_kg": 最重, "sets": 总组数, "reps": 总次数, "minutes": 总分钟}
238
239     for record in records:
240         record_date = date.fromisoformat(record["date"])
241         if record_date < monday:
242             continue
243         sessions = sessions + 1
244
245         for item in record["exercises"]:
246             name = item["name"]
247             # TODO 2（三行）：第一次遇到这个动作 → 开一本空账
248             #   提示：if name not in stats: stats[name] = {...}
249             if name not in stats:
250                 stats[name] = {"times": 0, "best_kg": None, "sets": 0, "reps": 0, "minutes": 0}
251             s = stats[name]
252             s["times"] = s["times"] + 1
...
261             if s["best_kg"] is None or s["best_kg"] < item["weight_kg"]:
262                 s["best_kg"] = item["weight_kg"]
263             if item["sets"]:
264                 s["sets"] = s["sets"] + item["sets"]
...
270     return {"week_start": monday.isoformat(), "sessions": sessions, "exercises": stats}
```

- **233-234 行**：和 `count_this_week` 同一套「本周一」公式。**重复了，但今天先忍**——两处都只有两行，抽成函数反而多一跳；等第三处出现再抽。这是「三次原则」：重复到第三次才值得抽象。
- **236-237 行**：两层累加。`sessions` 数「几条记录」；`stats` 是**嵌套字典**——外层键是动作名，值又是一本小账本。你之前用过的字典都是「键 → 数字」，今天是第一次「键 → 字典」。读法：`stats["卧推"]["best_kg"]`。
- **239-242 行**：先跳过上周。注意这里直接用 `< monday`，没设上界——记录日期由日期插槽保证是今天，不会有未来数据（和 `count_this_week` 同一个假设）。
- **243 行**：`sessions` 在**记录层**加一。一条记录里练三个动作，也只算练了一次——和「这周练了几次」的口径保持一致。
- **245-251 行**：开账本。
  - `if name not in stats`：第一次遇到这个动作（卧推/跑步）才开；之后直接复用。没有这道判断，每次都会把之前累计的账清零。
  - **`s = stats[name]` 是引用别名**：`s` 不是副本，它和 `stats[name]` 指向同一个字典。所以后面 `s["sets"] = ...` 改的就是账本本身，不用再写回 `stats`。这是 Python 的「可变对象按引用传递」——列表、字典都是这样；数字、字符串则是不可变，赋值即新建。
- **252 行**：`times`（出现次数）每次 +1，和 `sessions` 的区别：同一条记录里同一动作出现两次，`times` 也会 +2；`sessions` 始终是记录条数。
- **261-262 行**：最好成绩。**守卫必须在账本这一边**：
  - `s["best_kg"] is None`：第一次给这个动作记重量，还没有最好成绩 → 直接写入；
  - 否则就比较：`s["best_kg"] < item["weight_kg"]` 才更新。
  - 两个分支缺一不可。省略 None 判断，第一条记录就会 `None < 85` → TypeError；判断错了边（写成 `item["weight_kg"] is None`），则在「新数据有值、账本还空」时同样炸。
- **263-268 行**：三个累加。`if item["sets"]:` 用的是**真值判断**：`None` 和 `0` 都是假 → 跳过，不加。在「累加」这个场景里它是安全的——加 0 本来也不改变结果。但要注意区分：**累加可以糊弄 0，展示不行**——342-349 行模板里用 `is not None`，因为「0 分钟」是一个要显示出来的事实，不能被当成「没记」跳过。
- **270 行**：返回三样：本周起点（给模板报日期）、练了几次、每个动作的账本。**注意它返回的是数字，不是句子**——这个函数一个字都不说人话，说话是别人的事。

### SUMMARY_PROMPT（273-279）——写给「写手」的规则

```python
273 SUMMARY_PROMPT = """你是健身教练，要根据程序给出的本周统计写一段 3-4 句的中文总结。
274 规则：
275 1. 只用统计里出现的数字，一个都不许自己编；
276 2. 统计里没有的动作不要提，没出现的数字不要说；
277 3. total_sets / total_reps / total_minutes 是**整周累计**，不是每次的量——别写成「每组 N 次」；
278 4. 不要重复总次数（程序已经报了），直接点评本周表现，最后给一句下周的具体建议；
279 5. 只输出总结正文：不要 JSON、不要标题、不要解释。"""
```

- **275-276 行**：两条都在防同一件事——**编造**。规则 1 管数字，规则 2 管动作名。模型的措辞可以自由，事实必须来自输入。这叫「grounding」（有据可依）：第 3 周 RAG 里，同一句话会变成「只根据检索到的文档回答」。
- **277 行**：这条是**实测加上的**。最初键名叫 `sets` / `reps`，模型把整周累计 8 组 10 次读成「8 组、**每组** 10 次」。改键名（`total_*`）+ 加这条规则，双保险。
- **278 行**：这条**没完全生效**——你在自己那次运行里看到了：「等 1 次」的头部之后，它还是说了「本周共完成 1 次训练」。**规则是说服，不是合同**：模型会大概率遵守，但不是保证。真要保证，只能改结构（比如不把 `sessions` 交给它），那又牺牲了「点评频率」的能力——这就是 prompt 工程的取舍。
- **279 行**：明确输出形态是「人话」。这一条配合 311 行的「不传 schema」，把总结和记录/意图两种结构化输出彻底分开。

### stats_for_model()（282-302）——今天的核心：上下文也要验收

```python
282 def stats_for_model(stats: dict) -> dict:
283     """给模型的统计副本：字段自带口径，0 一律去掉。
...
290     clean = {"week_start": stats["week_start"], "sessions": stats["sessions"], "exercises": {}}
291     for name, s in stats["exercises"].items():
292         item = {"times": s["times"]}
293         if s["best_kg"]:
294             item["best_kg"] = s["best_kg"]
295         if s["sets"]:
296             item["total_sets"] = s["sets"]
297         if s["reps"]:
298             item["total_reps"] = s["reps"]
299         if s["minutes"]:
300             item["total_minutes"] = s["minutes"]
301         clean["exercises"][name] = item
302     return clean
```

- **这段为什么存在**：Day 8 学的「保形状不保语义」一直是指**输出**；今天发现同一个坑在**输入**侧也有。脚手架阶段我拿临时副本实测，两个现场：
  1. 账本里 `minutes: 0`（其实是「没记」）直接交给模型 → 它写「训练时长记录为 0 分钟，单次训练安排偏短」——**数字一个没编，语义编了**；
  2. 键名 `sets` / `reps` 里装的是整周累计 → 模型读成「8 组、每组 10 次」。
  结论：**上下文进模型之前，也要按「模型会怎么读」验收一遍。** 不是把数据库原样倒给它。
- **290 行**：新建 `clean`，不改原 `stats`。**账本是事实来源，展示层不许改账本。** 如果这里直接 `stats["exercises"][name].pop(...)`，后面再想用原始统计就没数据了。分层的第一条纪律：只读上游，写自己的新对象。
- **291 行**：`.items()` 同时拿到键和值——遍历字典的标准姿势。`name` 是动作名，`s` 是那本小账本。
- **293-300 行**：`if s[key]:` 用真值判断，一次排掉 `None` 和 `0`。在健身数据里，重量/组数/次数/分钟都不可能是「真的 0」——`0` 只可能是「这次没记」。所以这里用真值判断是**有业务依据的**，不是偷懒。
- **295-300 行**：键名改成 `total_sets` / `total_reps` / `total_minutes`。**键名就是给模型看的注释**：`sets` 不带口径，模型只能猜；`total_sets` 自带「整周累计」的说明。换一个名字，省掉一段解释，也消掉一类误读。
- **301-302 行**：组装成新字典返回。注意这是**浅拷贝结构**：`clean` 本身是新的，里面的小 `item` 也是新的；源 `stats` 完全不受影响。

### write_summary()（305-317）——程序算数，模型写字

```python
305 def write_summary(stats: dict) -> str:
306     """程序算好的数字 → 模型组织成人话。数字归程序，措辞归模型。"""
307     messages = [
308         {"role": "system", "content": SUMMARY_PROMPT},
309         {"role": "user", "content": json.dumps(stats_for_model(stats), ensure_ascii=False)},
310     ]
311     resp = ask_once(messages)          # 故意不传 schema：总结是写给人看的，不是给程序解析的
312     if resp is None:
313         return "总结没生成出来，网络不好。"
314
315     print(f"[token] 总结 输入 {resp.usage.prompt_tokens} / 输出 {resp.usage.completion_tokens}")
316     # TODO 4（一行）：把总结正文返回给调用者
317     return resp.choices[0].message.content.strip()
```

- **307-310 行**：两条消息，和所有请求一样：system 给规则，user 给材料。材料是 `json.dumps(...)` 后的统计——JSON 比 Python 的 `str(dict)` 更紧凑、更少歧义，模型也见过更多 JSON。
  - `ensure_ascii=False`：中文保持原样。默认的 `True` 会把每个汉字转成 `\uXXXX`，又长又难读。
- **311 行**：**不传 schema**。语义上的理由：这份输出不需要程序解析，它是终点，直接给人看。形状自由，措辞才能自然。
- **312-313 行**：网络三次全灭 → 一句人话兜底。和查询线的兜底同一个设计观：失败要说清楚，不要假装成功。
- **315 行**：顺手把 usage 打出来。你那次是 **215 / 910**，折算约 0.0077 元。屏幕上只有一百多字，输出却记了 910 token——多出来的部分很可能是模型的隐藏推理/内部草稿，也算钱。（精确口径等周末 `token_cost_latency.md` 对账。）
- **317 行**：取正文。和 Day 1 的 `resp.choices[0].message.content` 同一条链，最后多了 `.strip()` 去掉首尾空白。**这一行你第一次写的是「没懂，是返回大模型的输出吗」——返回值是给程序/用户看的，不是提问的地方。**

### answer_question()（320-368）——三个分支

旧的两个分支（336-353）没动。今天加的是：

```python
355     if intent == "week_summary":
362         stats = compute_week_stats(records)
363         if stats["sessions"] == 0:
364             return "这周还没有记录，练完说一句就有了。"
365         header = f"这周（{stats['week_start']} 起）共练了 {stats['sessions']} 次。\n"
366         return header + write_summary(stats)
```

- **362 行**：程序先算。模型在这一步完全没参与，连一次调用都没有。
- **363-364 行**：**空周守卫**。本周一条记录都没有时，直接把「没有记录」告诉用户，**不把空统计交给模型「自由发挥」**。理由：空输入 + 开放任务 = 最容易被编造的场景（它会开始给通用建议或虚构上周数据）。诚实的空状态，好过热闹的空话。
- **365 行**：**总次数由程序打印**。为什么不让模型写进总结？
  1. 总次数是事实，事实的出口越少越好；
  2. 模型可能漏写、改写、或者多写一个「1 次」——你那次就重复了；
  3. 模板拼出来的数字永远准确，且不花 token。
- **366 行**：`header + write_summary(stats)`——程序报事实，模型给点评。两段文本直接拼接，第一段是「硬数据」，第二段是「软评价」。
- **边界提醒**：今天是周一（2026-11-09），`monday` 算出 11-09，你 11-06 那条记录属于**上周**，所以现在问周总结会走空周守卫。这不是 bug，是「这周」的定义在起作用——**词的含义由代码里的日期算术定义，不由感觉定义。**

### main()（371-395）——没变，但有个已知缺口

- 路由仍是两条：`is_question` 为真走查询/总结线，否则走记录线。`answer_question` 内部再按意图分三支。
- **已知缺口**：`is_question` 只认问号和 `QUESTION_HINTS`（199 行）。「帮我总结一下」**不含任何提示词、也没有问号**，会被判成记录 → 送进 `parse_workout`。补法很简单：往 `QUESTION_HINTS` 里加「总结」。今天不改，因为验收用的问法都带「这周」；但这个缺口值得记住——**规则路由的代价就是边角案例，靠真实使用慢慢补。**

---

## 三、真实时序（用你的运行 + 我的验收）

### 时序一：记录（strict + few-shot）

```
你说：今天卧推85kg 5组5次
  → [原文#1] {"date": "2026-11-09", "exercises": [{"minutes": null, "name": "卧推", "reps": 5, "sets": 5, "weight_kg": 85}], "notes": ""}
  → 已记录 2026-11-09 ｜ 卧推 ｜ 文件累计 2 条
```

- `date` 是插槽注入的今天；`minutes` 为 null（这次没提，不是 0）；形状由 strict 合同保证。
- 这条是临时测试记录，验完已删除；`workouts.jsonl` 现在只剩 2026-11-06 那条真实数据。

### 时序二：周总结（你的那次）

```
你说：这周练得怎么样
  → [token] 总结 输入 215 / 输出 910
  → 这周（2026-11-09 起）共练了 1 次。
     本周只完成1次训练，卧推练了1次，周累计5组，最高重量到85公斤。……
```

数字核对：1 次、5 组、85kg——全部来自 `stats`，没有编造。按账本价：

```
215 × 2/1e6 + 910 × 8/1e6 = 0.00043 + 0.00728 ≈ 0.0077 元
```

对比 Day 8 记一条记录的 0.001654 元：**总结贵约 4.7 倍，大头在输出。**

### 时序三：合成两周数据（我的验收，不写文件）

```
上周一条 100kg + 本周两条（85kg 5×5、90kg 3×5、跑步 20 分钟）

compute_week_stats → sessions=2；卧推 times=2, best_kg=90, sets=8, reps=10；跑步 minutes=20
stats_for_model    → {"卧推": {"times":2, "best_kg":90, "total_sets":8, "total_reps":10},
                      "跑步": {"times":1, "total_minutes":20}}
write_summary      → 「最高达到90公斤，整周累计8组；跑步只有1次、累计20分钟……」
```

- 上周的 100kg 被跳过（不参与 best）；`best_kg` 正确取到 90；累计口径正确；模型说的是「累计 8 组」而不是「每组 8 组」。
- 这一组断言全过：**聚合、窗口、清洗、生成，四层都对。**

### 时序四：空周守卫

```
你说：这周练得怎么样（本周 0 条）
  → 这周还没有记录，练完说一句就有了。        ← 没有发生任何模型调用
```

---

## 四、三层分工与 token 账单

```
问句 ──► [理解层] 模型：问句 → {"intent","exercise"}            QUERY_SCHEMA，一次调用
              │
              ▼
         [计算层] 程序：load_records → compute_week_stats         本地文件，0 token
              │
              ▼
         [清洗层] 程序：stats_for_model（去 0、改键名）            0 token
              │
              ▼
         [生成层] 模型：统计 JSON → 3-4 句人话                     SUMMARY_PROMPT，一次调用
              │
              ▼
         [表达层] 程序：header + 正文                             0 token
```

| 调用 | 输入 token | 输出 token | 参考价（元） |
|---|---|---|---|
| 记一条训练 | 171 | 164 | 0.001654 |
| 问「上次卧推多少」 | 204 | 17 | 0.000544 |
| 周总结（你的运行） | 215 | 910 | 0.007710 |

两点值得记住：

1. **输出 token 是总结的成本大头**。屏幕上看到的字远少于 910——隐藏推理也计费。这是周末 `token_cost_latency.md` 的重点。
2. **总结链路没有把历史塞给模型**：输入只有 `SUMMARY_PROMPT`（规则）+ 清洗后的统计（一条动作一行）。历史再长，这份输入也只随**动作种类数**增长，不随记录条数增长——这和 Day 10 的 54 倍实验是同一个设计。

---

## 五、函数速查

| 函数 | 签名 | 参数 | 返回 | 谁调用 | 失败时 |
|---|---|---|---|---|---|
| `ask_once` | `(messages, schema=None)` | 剧本 + 可选合同 | `resp` 或 `None` | 三条线都调 | 网络重试 3 次后给 `None` |
| `parse_workout` | `(text)` | 一句话 | 记录字典或 `None` | `main` | 语义失败纠错 1 次后放弃 |
| `compute_week_stats` | `(records) -> dict` | 记录列表 | 本周账本 | `answer_question` | 日期格式错会 `ValueError`（已知） |
| `stats_for_model` | `(stats) -> dict` | 原始账本 | 清洗后的副本 | `write_summary` | 不抛异常 |
| `write_summary` | `(stats) -> str` | 原始账本 | 总结正文 | `answer_question` | 网络失败 → 一句提示 |
| `answer_question` | `(text, records) -> str` | 问句 + 记录 | 人话答案 | `main` | 网络失败 → 一句提示 |

---

## 六、今天的 6 个坑（都是你真踩过的）

| # | 你写的 | 错在哪 | 正确写法 |
|---|---|---|---|
| 1 | few-shot 写成规则句、还写了两遍 | 示例要「输入→输出」；术语 `few-shot` 不进 prompt；重复内容每次请求都花钱 | 两行示例，无日期，无术语 |
| 2 | `item["weight_kg"] \| s["best_kg"] < item["weight_kg"]` | `\|` 是按位或不是 `or`；且 `\|` 优先级高于比较，先算 `85 \| None` → TypeError | `s["best_kg"] is None or s["best_kg"] < item["weight_kg"]` |
| 3 | 守卫写成 `item["weight_kg"] is None` | 判断错了边：可能为空的是**账本**，不是新数据 | `s["best_kg"] is None or ...` |
| 4 | `return "没懂，是返回大模型的输出吗"` | 返回值是给程序/用户看的，不是提问框 | `return resp.choices[0].message.content.strip()` |
| 5 | 改 `ask_once` 默认值后，调用点忘补参数 | 记录线会收到人话，`json.loads` 炸 | `ask_once(messages, WORKOUT_SCHEMA)` |
| 6 | 以为「总结」不需要考虑路由 | `is_question` 只认问号和提示词；「帮我总结一下」会被当记录 | 已知缺口；往 `QUESTION_HINTS` 加「总结」即可 |

第 2、3 个是同一个知识点的两面：**Python 的 `or` 和 `|` 不是一回事；判空要看对主语。** 第 5、6 个是「改了 A 别忘了 B」——改默认值、加意图词，都要回头检查所有依赖它的地方。

---

## 七、Python 语法小词典

| 语法 | 例 | 一句话 |
|---|---|---|
| 嵌套字典 | `stats[name]["best_kg"]` | 字典的值还可以是字典 |
| 类型提示 union | `dict \| None` | Python 3.10+ 的「dict 或 None」，只是文档 |
| `\|` 按位或 | `85 \| 90` | 把两个整数按二进制位或；**不是逻辑或** |
| 逻辑或 | `a or b` | 前者为真就返回前者，否则返回后者（短路） |
| 运算符优先级 | `a \| b < c` | `\|` 先算，再比较；所以等价于 `(a \| b) < c` |
| 真值判断 | `if s["sets"]:` | `0`、`None`、`""`、`[]` 都算假 |
| `is None` | `if s["best_kg"] is None` | 判断「是不是空」，比 `== None` 更地道 |
| 引用别名 | `s = stats[name]` | 改 `s` 就是改账本里的那本，不复制 |
| `not in` | `if name not in stats` | 键不存在 |
| `.items()` | `for k, v in d.items()` | 同时遍历键和值 |
| `json.dumps` | `json.dumps(obj, ensure_ascii=False)` | 对象 → JSON 字符串；保留中文 |
| `.strip()` | `content.strip()` | 去掉首尾空白/换行 |
| f-string 取键 | `{stats['week_start']}` | 花括号里可以用引号取字典值 |
| `usage` | `resp.usage.prompt_tokens` | 本次请求的输入/输出 token 数 |
| 默认值 | `schema=None` | 不传就当 None；改默认值会波及所有调用点 |

---

## 八、自测五题（答案在文末）

1. 为什么记录和意图都套 `json_schema`，而周总结故意不套？
2. 如果把 `stats_for_model` 删掉、直接把 `stats` 交给 `write_summary`，会出现哪两类具体错误？分别对应今天的哪条证据？
3. 261 行如果写成 `if item["weight_kg"] is None or s["best_kg"] < item["weight_kg"]:`，什么场景会炸？如果写成 `if s["best_kg"] < item["weight_kg"]:` 呢？
4. 周总结的总次数为什么要由程序打印，而不是让模型写？你今天的运行里有什么证据？
5. 「帮我总结一下」这句话会走哪条线？为什么？最小的补法是什么？

---

### 自测题答案

1. 输出交给谁，决定要不要合同：记录和意图是给**程序解析**的，形状必须硬保证；周总结是给**人看**的，形状自由反而更自然，套 schema 只会多一层无用的约束和变形风险。
2. ① `minutes: 0`（其实没记）会被模型读成「训练时长 0 分钟，安排偏短」；② 键名 `sets`/`reps` 装的是整周累计，会被读成「8 组、每组 10 次」。对应 `stats_for_model` docstring 里记的两个实测现场。修法是**去 0 + 键名自带口径**。
3. 第一种（守卫放错边）：新数据有重量、账本还空时，`None < 85` → TypeError——每条动作的第一次记录必炸；跑步这类没重量的动作还会把 `best_kg` 写成 None。第二种（完全不判空）：第一条记录就 `None < 85` → TypeError。**先判「还没有」，再比较。**
4. 总次数是事实，事实只留一个出口：模板拼出来的数字永远准确、不花 token；模型可能漏写、改写或重复。你今天那次运行就是证据——头部已经报了「共练了 1 次」，总结里还是写了「本周只完成 1 次训练」，尽管 `SUMMARY_PROMPT` 第 4 条明确说了不要重复。**规则是说服，结构才是保证。**
5. 会走**记录线**（`parse_workout`），因为 `is_question` 只认问号和 `QUESTION_HINTS`，而这句两者都没有。后果轻则白跑一次 API、重则把问句当训练记进文件。最小补法：把「总结」加进 `QUESTION_HINTS`。
