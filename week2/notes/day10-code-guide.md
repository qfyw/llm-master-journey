# assistant_v2.py 逐行讲解（Day 10 版）

> 配套文件：`week2/assistant_v2.py`（v2.2，2026-11-06）
> 阅读方式：先看「全景」，再读查询线；记录线昨天没动，只标行号（细节见 `day09-code-guide.md`）。

```
运行：python week2/assistant_v2.py
记录：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟
提问：我上次卧推多少？ / 这周练了几次？
今天的新分工：模型只理解问题，程序查数据，模板组答案
```

---

## 一、全景：一个文件，两条线

| 区块 | 行号 | 职责 | 今天动了吗 |
|---|---|---|---|
| 文件头 + import | 1-20 | 说明、搬工具（新增 `timedelta`） | 微调 |
| 配置区 | 22-34 | 读 .env、建 client、数据路径 | 没动 |
| SYSTEM_PROMPT | 36-38 | 记录线的语义规则 + 日期插槽 | 没动 |
| QUERY_PROMPT | 40-45 | 查询线的语义规则：三种意图怎么分 | **新增** |
| WORKOUT_SCHEMA | 47-78 | 记录线的合同 | 没动 |
| QUERY_SCHEMA | 80-98 | 查询线的合同（一个枚举 + 一个可空字符串） | **新增** |
| `ask_once()` | 101-114 | 发请求；网络重试 3 次；**合同由调用者选** | **改签名** |
| `is_valid()` / `parse_workout()` | 117-150 | 记录线的语义验收 + 两层重试 | 没动 |
| `save()` | 153-164 | 追加记录、数条数 | 没动 |
| `load_records()` | 170-180 | 读整个 jsonl，返回字典列表 | **新增** |
| `is_question()` | 183-193 | 规则路由：这句话是提问还是记录 | **新增** |
| `find_last()` | 196-202 | 从最新往回找某个动作 | **新增** |
| `count_this_week()` | 205-214 | 数本周（周一起）记录条数 | **新增** |
| `answer_question()` | 217-256 | 理解 → 查询 → 表达的总编排 | **新增** |
| `main()` | 259-283 | 输入循环 + 双分支分流 | **改了** |

**调用图**：

```
main
 ├─ is_question? ──True──► load_records ──► answer_question ──► ask_once(QUERY_SCHEMA)
 │                                                └──► find_last / count_this_week
 └──────────────False──► parse_workout ──► ask_once(WORKOUT_SCHEMA) ──► save
```

两条线共用的只有一样东西：`ask_once` 里的网络层重试。**理解走网络，查数走本地。**

---

## 二、逐行讲解

### 文件头（1-12）

```python
1  """Day 10：助手 v2.2——会查历史了。
...
11   查数靠代码，理解靠模型——第 3 周 RAG 的骨架就是这个分工。
12 """
```

- **1-12 行**：docstring 换了主题。上一版的主题是「格式交给合同」，这一版是「分工」。文档字符串的价值就在这：三个月后回来，先看封面就知道这版解决了什么问题。

### import（13-20）

```python
13 import json
14 import os
15 import time
16 from datetime import date, timedelta
17 from pathlib import Path
```

- **16 行**：今天多搬了一个 `timedelta`——它是「一段时间」的类型，用来算「本周一」：`今天 - 7 天 × 星期几`。`date` 是「一个日期」，`timedelta` 是「日期的差值」，两个配合才能做日期算术。

### 配置区（22-34）

没动。`load_dotenv()` 进货 → `client` 按图纸造机器 → `model` 从 `.env` 读。细节见 Day 9 指南 21-31 行。

### QUERY_PROMPT（40-45）——查询线的语义规则

```python
40 QUERY_PROMPT = """你在把健身助手用户的问题翻译成查询意图。
41 可选意图：
42 - last_exercise：问某个动作上次的数据（例：「我上次卧推多少」）→ exercise 填动作名，如「卧推」
43 - week_count：问本周练了几次（例：「这周练了几次」）→ exercise 填 null
44 - unknown：其它问题 → exercise 填 null
45 只输出 JSON，不要解释。"""
```

- **40-45 行**：它和 `SYSTEM_PROMPT` 是一对镜像：一个教模型「怎么把训练话变成记录」，一个教模型「怎么把问题变成查询」。注意两者的分工变了——记录线要求模型**产出数据**（重量、组数），查询线只要求模型**指路**（问的是哪类事、哪个动作），数据它一个字都不用碰。
- **42-44 行**：`exercise` 的含义跟着 `intent` 走：只有 `last_exercise` 要填动作名，另外两种填 `null`。这条**跨字段规则**写在 prompt 里，schema 表达不了（下一节会看到）。
- **45 行**：`只输出 JSON` 和 schema 的 `strict` 有一点重复，但没有坏处：prompt 管语义（三个意图怎么分），合同管形状（输出只能是这三个词）。**事前规矩，事中合同**——Day 9 的口诀在这里原样复用。

### QUERY_SCHEMA（80-98）——查询线的合同

```python
81 QUERY_SCHEMA = {
82     "name": "query_intent",
83     "strict": True,
84     "schema": {
85         "type": "object",
86         "properties": {
87             "intent": {
88                 "type": "string",
89                 # TODO 1：……
90                 "enum": ["last_exercise", "week_count", "unknown"],
91             },
92             # TODO 2（一行）：……
93             "exercise": {"type": ["string", "null"]},
94         },
95         "required": ["intent", "exercise"],
96         "additionalProperties": False,
97     },
98 }
```

- **81-83 行**：和 `WORKOUT_SCHEMA` 同款三层套娃：元信息（`name`）+ 管束开关（`strict`）+ 条款（`schema`）。
- **87-91 行 `intent`**：`type: "string"` 说「值是个字符串」，`enum` 说「但只能是这三串之一」。**`enum` 是允许值清单，不是字段表**——你第一次写的 `properties` 是「对象有哪些栏」用的，这里 `intent` 的右边不是对象，是一根字符串。
- **93 行 `exercise`**：`["string", "null"]` 是「可空字符串」的正式写法，和昨天 `weight_kg` 的 `["number", "null"]` 同源。你第一版写成 `"array,null"`，问题有两层：① 类型必须是字符串或**字符串列表**，逗号要写在列表里；② exercise 是动作名，基础类型本来就是字符串，不是数组。
- **95-96 行**：`required` 两个都要在（可空 ≠ 可省）；`additionalProperties: false` 不许加第三个字段。
- **合同管不到的地方**：schema 允许 `{"intent": "week_count", "exercise": "卧推"}` 这种**语义矛盾**的组合——形状全合法。所以 237 行还要用 `and exercise` 再验一道。这就是「契约保形状，事实靠插槽/代码」的又一次现身。

### ask_once()（101-114）——一层药方，两处复用

```python
101 def ask_once(messages: list[dict], schema: dict = WORKOUT_SCHEMA):
102     """发一次请求；网络层最多试 3 次。格式合同由调用者选（默认是记训练那张）。"""
103     for attempt in range(3):
104         try:
105             resp = client.chat.completions.create(
106                 model=model,
107                 messages=messages,
108                 response_format={"type": "json_schema", "json_schema": schema},
109             )
110             return resp
111         except (APIConnectionError, APIStatusError) as e:
112             print(f"[网络第 {attempt + 1} 次失败] {type(e).__name__}：{e}", flush=True)
113             time.sleep(2)
114     return None
```

- **101 行**：今天唯一的签名改动。`schema: dict = WORKOUT_SCHEMA` 是**默认参数**：调用时不写第二个参数，就用记录线的合同；写了，就用你递进来的那张。
  - 默认值在**函数定义那一刻**求值一次，之后一直用这个对象——所以别把「会变的东西」当默认值。
  - 两个调用点：131 行 `ask_once(messages)` 走记录线；229 行 `ask_once(messages, QUERY_SCHEMA)` 走查询线。
- **为什么这么改**：网络层的病（断连、限流、超时）和业务无关，两份处方完全一样。**复制粘贴重试代码 = 以后修 bug 要修两处**；把「格式合同」抽成参数，重试逻辑只此一份。这叫分层：变化的（合同）下沉为参数，不变的（重试）留在函数里。
- **103-114 行**：和 Day 9 一字不差——3 次、睡 2 秒、失败返回 `None`。查询线直接继承这套网络保险，不用重写。

### 记录线（117-164）——今天没动

`is_valid`（语义验收）、`parse_workout`（网络 3 次 + 语义 1 次）、`save`（追加、数条数）全部保持 Day 9 状态。逐行解释见 `day09-code-guide.md` 的 168-245 行。今天只要记住：**查询线没有碰记录线任何一行**，而回归测试（记录一句）照样通过——这是「加功能不破坏旧功能」的最小实践。

### load_records()（170-180）——把文件读成字典列表

```python
170 def load_records() -> list[dict]:
171     """读整个 workouts.jsonl，返回记录列表（文件不存在就是空列表）。"""
172     records = []
173     if not DATA_FILE.exists():
174         return records
175     with open(DATA_FILE, encoding="utf-8") as f:
176         for line in f:
177             if line.strip():
178                 # TODO 3（一行）：……
179                 records.append(json.loads(line))
180     return records
```

- **170 行**：`-> list[dict]` 承诺「返回一个列表，里面每个元素是字典」。这个承诺很重要：调用方（`find_last`）拿到后直接 `record["exercises"]`，靠的就是「元素是字典」。
- **172 行**：`records = []` 新建空列表——**累加器**的容器版。你从 Day 4 的 `total`、Day 5 的四个计数器一路走到今天：累加的是数字，今天是「把每条记录收进列表」。
- **173-174 行**：文件不存在就直接返回空列表。**第一次提问时 data/ 可能还没有文件**（还没记录过任何训练）——没有这道门，`open` 会 `FileNotFoundError`。`Path.exists()` 返回 True/False。
- **175 行**：`with open(...)` 读模式（没写 `"r"` 就是读），块结束自动关文件。
- **176-177 行**：逐行遍历；`if line.strip()` 跳过空行（防手滑、防文件末尾多一个换行）。
- **179 行**：**今天的核心一行**。文件里的 `line` 是**字符串**（`'{"date": "2026-11-06", ...}\n'`），`json.loads` 把它变回**字典**。你第一版写的是 `records.append(line)`，等于把一串字符串当记录收进来——`find_last` 里 `record["exercises"]` 会立刻炸 `TypeError: string indices must be integers`（字符串只认数字下标，不认键名）。**文件是字符串的仓库，程序要的是字典——`loads` 就是那道转换门。**
- **180 行**：返回列表。每次提问都重新读一遍文件，所以「刚刚记录的那条」立刻能查到，不用重启程序。

### QUESTION_HINTS + is_question()（183-193）——不用模型的路由

```python
183 QUESTION_HINTS = ("多少", "几次", "上次", "最近", "这周", "本周", "历史", "多久")

186 def is_question(text: str) -> bool:
187     """判断一句话是提问还是训练记录。"""
191     if text.rstrip().endswith(("？", "?")) or any(hint in text for hint in QUESTION_HINTS):
192         return True
193     return False
```

- **183 行**：提示词元组（tuple）。用元组而不是列表，因为这是一份**常量清单**，运行中不会改；圆括号还有个附带好处：`endswith` 恰好收元组。
- **191 行**，两个条件用 `or` 连接，任一边 True 就进查询线：
  - **左半**：`text.rstrip().endswith(("？", "?"))`——先去掉尾部空白，再看句尾是不是中文问号或英文问号。`endswith` 的参数放元组 = 「以其中任意一个结尾」，一次判断多个候选。
  - **右半**：`any(hint in text for hint in QUESTION_HINTS)`——读作「只要有一个提示词出现在这句话里」。`hint in text` 是子串判断；`any(...)` 拿到第一个 True 就停（短路）。
  - **为什么两半缺一不可**：「我上次卧推多少」**没有问号**，只靠左半会被判成记录，然后被送进 `parse_workout` 当训练存下来——问句变成假数据，这是最坏的一种 bug。右半的「上次」「多少」就是为它准备的。
- **为什么不用模型判意图**：这是纯规则、零 token、零延迟、结果稳定。代价是「这周卧推多少」这类同时含记录词和提问词的句子可能误判——规则路由的取舍，先接受。真到误判频繁，再把路由也交给模型（多一次调用）。
- **192-193 行**：命中就 True，否则落到 193 行的 False（记录线）。

### find_last()（196-202）——倒着找最近一次

```python
196 def find_last(records: list[dict], exercise: str):
197     """从最新一条往回找：第一条含有该动作的记录。返回 {"date":..., "item":...} 或 None。"""
198     for record in reversed(records):
199         for item in record["exercises"]:
200             if exercise in item["name"]:
201                 return {"date": record["date"], "item": item}
202     return None
```

- **198 行**：`reversed(records)` 把列表**从后往前**遍历，不复制、不改原列表。文件是追加写的（`save` 永远往末尾加），所以**越靠后越新**；「上次」= 最新 = 从后往前第一条命中的。
  - 如果去掉 `reversed` 正着找，返回的会是**最早**那次卧推（样例里的 11-02 75kg），问题问「上次」，答案却是「第一次」——逻辑反了。
- **199 行**：嵌套循环。外层一条条记录，内层看这条记录里的每个动作（一条记录可能有卧推、深蹲、跑步三件）。
- **200 行**：`exercise in item["name"]` 是**子串**匹配，方向不能反：`"卧推" in "哑铃卧推"` 为 True，所以模型把动作名归成「卧推」也能匹配到你记的「哑铃卧推」。
- **201 行**：找到就**立刻 return**，不再往下扫——早退（early return）。返回值是个小字典：哪天 + 哪个动作的完整字段。
- **202 行**：全扫完没找到 → 返回 `None`。调用方据此说「没有找到」，而不是硬编一个数字。**函数的「找不到」要有个正规出口，`None` 就是它。**
- **语义提醒**：「上次」包含今天——如果你今天刚记了卧推，`find_last` 返回的就是今天这条。这是刻意选的语义（最近一次），不是 bug。你第一次跑（记录前）得到 11-04 80kg，记完再跑得到 11-06 85kg，变的不是代码，是数据。

### count_this_week()（205-214）——本周从周一起

```python
205 def count_this_week(records: list[dict]) -> int:
206     """数本周（周一起到今天）有几条记录。"""
207     today = date.today()
208     monday = today - timedelta(days=today.weekday())   # weekday(): 周一=0 … 周日=6
209     count = 0
210     for record in records:
211         record_date = date.fromisoformat(record["date"])   # "2026-11-05" → date 对象
212         if record_date >= monday:
213             count = count + 1
214     return count
```

- **207 行**：`date.today()` 拿到今天（2026-11-06）。
- **208 行**：`today.weekday()` 返回**0-6**，周一=0、周日=6。今天是周五 → 4；`timedelta(days=4)` 表示 4 天；`今天 - 4 天` = **本周一 11-02**。周一当天减 0 天，还是它自己——公式不用特判。
- **209 行**：又一个累加器，这次数「条数」。
- **211 行**：`date.fromisoformat("2026-11-05")` 把字符串变**日期对象**。为什么不直接拿字符串比大小？ISO 格式（`YYYY-MM-DD`）碰巧能按字典序比，但那是「碰巧」：`"2026-1-5"` 这种不补零的写法会排错；日期对象还能做减法、取星期。**让类型承担规则，别让字符串的巧合承担。**（顺带：格式不对的字符串会抛 `ValueError`——这是目前已知的脆弱点，等真遇到再补护栏。）
- **212 行**：`>= 周一` 就算本周。不设上界（`<= 今天`），因为记录日期由日期插槽保证是今天，不会出现未来。
- **语义提醒**：数的是**记录条数**，一条记录里练三个动作也只算一次「练了」。这和「这周练了几次」的日常语义一致。

### answer_question()（217-256）——理解 → 查询 → 表达

```python
217 def answer_question(text: str, records: list[dict]) -> str:
218     """模型理解问题 → 程序查数据 → 模板组装答案。"""
219     messages = [
220         {"role": "system", "content": QUERY_PROMPT},
221         {"role": "user", "content": text},
222     ]
```

- **217 行**：注意参数：`records` 进了函数，但**没有进 `messages`**。这就是今天的全部秘密——数据在程序手里，模型只看得到问题。`messages` 只有两条：规则 + 问句，204 个 token，和历史长度无关。
- **224-232 行**：

```python
229     resp = ask_once(messages, QUERY_SCHEMA)
230     if resp is None:
231         return "网络不好，等下再问。"
232     data = json.loads(resp.choices[0].message.content)
```

  - **229 行**：复用网络重试，只是换成查询合同。`ask_once` 内部仍然最多试 3 次。
  - **230-231 行**：三次全灭 → 回一句人话。查询线不需要「语义纠错重试」——意图只有三种，模型答不出来就是 unknown，没有「再劝一次」的价值。
  - **232 行**：同一个取包裹链路（`resp → choices[0] → message → content`）再走一遍。这里没套 `try/except JSONDecodeError`，因为 strict 合同保证形状；但接口行为会变，想和记录线保持一致的话，可以补一层同样的保险（一行 `try`，可选打磨项）。
- **234-235 行**：按 key 取值。**不要按位置猜**——JSON 的 key 顺序不保证（Day 9 就见过 `minutes` 跑最前面）。
- **237 行**：`intent == "last_exercise" and exercise`——第二个条件防的是「schema 允许、语义矛盾」的组合：intent 说查动作，exercise 却是 null。没这个 `and`，`find_last(records, None)` 会拿 None 去和动作名做子串判断，直接 TypeError。
- **241-251 行**：

```python
241         item = found["item"]
242         parts = [found["date"]]
243         if item["weight_kg"] is not None:
244             parts.append(f"{item['weight_kg']}kg")
...
251         return f"上次{exercise}是 " + " ".join(parts) + "。"
```

  - **242 行**：`parts` 是「答案零件」列表，先放日期。
  - **243-250 行**：四个 `if ... is not None` 逐个决定要不要加零件。**为什么不用 `if item["minutes"]:` 这种简写**——因为 `0` 是假值：如果某天记了「跑步 0 分钟」（或体重 0），简写会把它当「没有」漏掉。`is not None` 只排除真正的空值，0 会被保留。**判空用 `is None`，判真假才用 `if x`。**
  - **251 行**：`" ".join(parts)` 用空格把零件串成一句话。`join` 只吃字符串——`found["date"]` 是记录里的字符串（不是 date 对象），所以能直接拼。
- **253-254 行**：`week_count` 分支——把 `count_this_week` 算出的数字塞进模板。**模型只提供了「意图」两个字，数字是程序数出来的。**
- **256 行**：兜底。unknown 不硬答，给出两个能用的问法——**诚实的边界提示**，和 Day 9 的「没解析成功」是同一个设计观。

### main()（259-283）——分流

```python
266         if is_question(text):
272             records = load_records()
273             print(answer_question(text, records))
274             continue
275         else:
276             record = parse_workout(text)
...
```

- **266 行**：路由用规则函数，不用模型——零成本、零延迟。
- **272-274 行**：查历史分支：读全量 → 回答 → `continue` 跳回 `while` 顶部，**跳过 else 的记录流程**。`continue` 就是「这一轮到此为止，下一轮请早」。
- **275 行起**：记录分支原样保留。这就是回归测试能过、功能没被破坏的结构原因：两条线在 `main` 里分开，只在 `ask_once` 里共享网络层。
- **小清理**：271 行 `#不懂` 和 272 行尾的空格现在可以删了（已经懂了）；`continue` 后面不再有代码，所以没有死代码。

---

## 三、真实时序（用你今天的运行）

### 时序一：「我上次卧推多少？」（记录前）

```
main：is_question("我上次卧推多少？")
  ├─ 句尾是「？」→ True（其实「上次」「多少」也命中右半）
  └─ load_records() → 3 条样例
answer_question(text, records)
  ├─ ask_once(QUERY_PROMPT + 问题, QUERY_SCHEMA)   ← 204 token，模型没看历史
  │    └─ {"intent": "last_exercise", "exercise": "卧推"}
  ├─ find_last(reversed) → 11-04 的 80kg 5组5次
  └─ 模板 → 「上次卧推是 2026-11-04 80kg 5组 ×5次。」
```

### 时序二：同一条问题（记录后）

```
先把「今天卧推85kg 5组5次」走记录线存进文件（累计 4 条）
再问同一个问题：
  find_last 从后往前，第一条命中就是 11-06 的 85kg
  → 「上次卧推是 2026-11-06 85kg 5组 ×5次。」
```

**代码一个字没改，答案变了——因为「上次」的定义包含今天，数据变了。**

### 时序三：「这周练了几次？」与边界

```
count_this_week：周一 = 11-06 - 4 天 = 11-02
  11-02 ✓  11-04 ✓  11-06 ✓  11-06（真实记录）✓  → 4 次
「我上次跑步多久？」 → minutes 分支 → 20分钟
「我上次硬拉多少？」 → find_last 返回 None → 「没有找到「硬拉」的记录。」
```

---

## 四、三层分工与 token 账单

```
问句 ──► [理解层] 模型：问句 → {"intent": ..., "exercise": ...}    204 token/次，不看历史
              │
              ▼
         [查询层] 程序：load_records → find_last / count_this_week   本地文件，0 token
              │
              ▼
         [表达层] 模板：日期 + 数字 + 单位 → 人话                     0 token
```

同一问题「我上次卧推多少？」的对照实验（200 条历史）：

| 方案 | 模型看到什么 | 输入 token |
|---|---|---|
| A：整包历史 | 200 条 JSON 全塞进 prompt | 11,072 |
| B：今天这条链路 | 只有规则 + 问句 | 204 |

- 差 **54 倍**，而且 A 每问一次都要重发整包；B 的 204 与历史长度**无关**。
- 按每条约 55 token 估算：两年 730 条约 4 万 token/问；2,000 条约 11 万 token——贴上上下文窗口。
- 这就是为什么第 3 周学 RAG 时要「先检索、再生成」：**检索留在程序侧，模型只拿得到和问题相关的那几条。**

---

## 五、函数速查

| 函数 | 签名 | 参数 | 返回 | 谁调用 | 失败时 |
|---|---|---|---|---|---|
| `ask_once` | `(messages, schema=WORKOUT_SCHEMA)` | 剧本 + 合同 | `resp` 或 `None` | 两条线都调 | 网络重试 3 次后给 `None` |
| `load_records` | `() -> list[dict]` | 无 | 记录列表 | `main` | 文件不存在 → 空列表 |
| `is_question` | `(text) -> bool` | 一句话 | 真/假 | `main` | 不抛异常 |
| `find_last` | `(records, exercise)` | 记录列表 + 动作名 | `{"date","item"}` 或 `None` | `answer_question` | 没找到 → `None` |
| `count_this_week` | `(records) -> int` | 记录列表 | 次数 | `answer_question` | 日期格式错会 `ValueError`（已知） |
| `answer_question` | `(text, records) -> str` | 问句 + 记录 | 人话答案 | `main` | 网络失败 → 一句提示 |

---

## 六、今天的 6 个坑（都是你真踩过的）

| # | 你写的 | 错在哪 | 正确写法 |
|---|---|---|---|
| 1 | `intent` 里塞 `properties` | `properties` 是对象字段表；`intent` 的值是字符串，允许值用 `enum` | `"enum": ["last_exercise", "week_count", "unknown"]` |
| 2 | `"type": "array,null"` | 类型是「字符串或字符串列表」，逗号要写在列表里；且基础类型选错 | `"type": ["string", "null"]` |
| 3 | `records.append(line)` | `line` 是字符串，查询要字典 | `records.append(json.loads(line))` |
| 4 | `if text.rstrip().endswith(...) #不懂` | 少冒号；`if` 行末必须有 `:` | 行末补 `:` |
| 5 | 只判断句尾问号 | 「我上次卧推多少」没有问号，会被当记录存进去 | `or any(hint in text for hint in QUESTION_HINTS)` |
| 6 | `if resp==None` | 少冒号；判 None 的惯用写法是 `is None` | `if resp is None:` |

前 3 个是「合法 Python / 非法语义」，编译器拦不住，靠运行和 schema 拦；第 4、6 个是纯语法，编译器在第一行就拦住你。**两种错要分清：语法错看 traceback，语义错看输出。**

---

## 七、Python 语法小词典

| 语法 | 例 | 一句话 |
|---|---|---|
| 元组字面量 | `("多少", "几次")` | 不可变的序列，适合常量清单 |
| `endswith(元组)` | `text.endswith(("？", "?"))` | 以其中任意一个结尾即为真 |
| 生成器 + `any` | `any(h in text for h in HINTS)` | 逐个试，中一个就返回 True |
| 短路 `or` | `A or B` | A 为真时 B 不求值 |
| 默认参数 | `schema=WORKOUT_SCHEMA` | 不传就用默认值；默认值在定义时求值一次 |
| `reversed()` | `for r in reversed(xs)` | 倒序遍历，不复制列表 |
| 嵌套循环 + 早退 | 见 198-201 | 找到即 return，不再扫 |
| `is None` | `if resp is None` | 判断「是不是空」，比 `== None` 更地道 |
| `date.today()` | 今天 | 拿当前日期 |
| `weekday()` | 周五 → 4 | 周一 0 … 周日 6 |
| `timedelta(days=n)` | `today - timedelta(days=4)` | 日期加减「一段时间」 |
| `date.fromisoformat()` | `"2026-11-05"` → date | 字符串转日期对象 |
| `.exists()` | `DATA_FILE.exists()` | 路径是否存在 |
| `intent == "x" and exercise` | 见 237 | 用真值判断顺带挡 None |

---

## 八、自测五题（答案在文末）

1. 把 198 行的 `reversed(records)` 改成 `records`，问「我上次卧推多少」会答成哪一次？为什么？
2. `answer_question` 的 `messages` 里没有历史数据，可它又收了一个 `records` 参数——谁在用这个参数？模型能看到它吗？
3. 「这周练了几次」里，如果某条记录的日期是 `"2026-1-5"`，`date.fromisoformat` 会怎样？如果当初直接用字符串比大小，会发生什么？
4. 把 243 行的 `if item["weight_kg"] is not None:` 改成 `if item["weight_kg"]:`，什么数据会漏掉？
5. `is_question` 的 `or` 右半（提示词）删掉后，`我上次卧推多少` 会走哪条线？后果是什么？

---

### 自测题答案

1. 会答成**最早**那次（样例里的 11-02 75kg）。文件是追加写的，越靠后越新；去掉 `reversed` 就变成从旧到新扫，第一个命中的是第一次。
2. 模型看不到。`records` 只喂给 `find_last` / `count_this_week`，在本地查完直接把结果交给模板；进 `messages` 的只有 `QUERY_PROMPT` 和问句。**数据留在本地，问题才上网。**
3. `ValueError: Invalid isoformat string`（格式不补零不合规）。字符串比较则会「碰巧」按字典序排，`"2026-1-5"` 会被排到很后面，周计数悄悄算错——不报错的错更危险。
4. 数值为 `0` 的字段（例如「跑步 0 分钟」）。`0` 是假值，简写会把它当成「没有」跳过；`is not None` 只排除真正的空值。
5. 会走**记录线**：`parse_workout` 把「我上次卧推多少」当训练描述去解析，模型可能返回空 exercises（被语义验收拦下）或编出一条假记录存进文件。前者只是白跑一次 API，后者是**问句污染了数据**。
