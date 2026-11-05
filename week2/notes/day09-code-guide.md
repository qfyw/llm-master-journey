# assistant_v2.py 逐行讲解（Day 9 版）

> 配套文件：`week2/assistant_v2.py`（v2.1，2026-11-05）
> 阅读方式：先看「全景」，再按区块读；每行都标了行号，对得上文件。

```
运行：python week2/assistant_v2.py
作用：你说一句训练，它转成 JSON、验一遍、追加进 data/workouts.jsonl
今天的两处升级：① 格式交给 json_schema(strict) 合同 ② 网络/语义两层重试
```

---

## 一、全景：一个文件，五个角色

| 区块 | 行号 | 职责 |
|---|---|---|
| 文件头 + import | 1-19 | 说明、搬工具 |
| 配置区 | 21-31 | 读 .env、建 client、选模型 |
| 数据路径 | 33 | 指向 `data/workouts.jsonl` |
| SYSTEM_PROMPT | 35-37 | 语义规则 + 日期插槽 |
| WORKOUT_SCHEMA | 39-70 | 机器的合同（JSON Schema） |
| `ask_once()` | 73-88 | 发请求；网络层重试 3 次 |
| `is_valid()` | 91-94 | 语义验收：内容有没有用 |
| `parse_workout()` | 97-128 | 编排两层重试 |
| `save()` | 131-142 | 追加记录、数条数 |
| `main()` | 145-163 | 输入循环、成功落盘、失败人话 |

---

## 二、逐行讲解

### 文件头（1-11）

```python
1  """Day 9：助手 v2.1——把「格式」交给合同，把「重试」分成两层。
...
11 """
```

- **1-11 行**：三引号包起来的是**模块文档字符串**（docstring）。它不是代码，运行时不执行，作用相当于这份文件的「封面」：`python -c "import ..."` 或 help 时能看到。写清楚「这个文件解决什么问题」比写清楚「它怎么实现」更值钱——三个月后回来的人（就是你自己）先看这里。

### import（12-19）

```python
12 import json
13 import os
14 import time
15 from datetime import date
16 from pathlib import Path
18 from dotenv import load_dotenv
19 from openai import APIConnectionError, APIStatusError, OpenAI
```

- **12 `import json`**：标准库。今天用它的两个函数：`json.loads`（字符串→字典，把模型的话变成程序能取的东西）、`json.dumps`（字典→字符串，把记录写成一行文件）。**注意**：变量千万不要起名叫 `json`，会把这把工具盖掉。
- **13 `import os`**：读环境变量用（`os.getenv`）。
- **14 `import time`**：今天只用它的 `time.sleep(2)`——重试前睡两秒，给服务器喘口气。
- **15 `from datetime import date`**：只从 `datetime` 模块里搬一个 `date` 进来。`date.today().isoformat()` → `"2026-11-05"`。**注意**：函数里别再给变量起名 `date`（Day 6 的 UnboundLocalError 就是这么来的）。
- **16 `from pathlib import Path`**：跨平台路径工具。`Path(__file__).parent` 拿到「本文件所在的文件夹」，比手拼反斜杠字符串可靠。
- **18 `from dotenv import load_dotenv`**：读 `.env` 的工具（见 21 行）。
- **19 `from openai import ...`**：`OpenAI` 是建客户端的类；`APIConnectionError` 是「网线/地址不通」那类错；`APIStatusError` 是「服务器回答了但拒绝你」那类错（带状态码 401/402/429…）。**这两个异常类就是今天网络层重试的靶子。**

### 配置区（21-31）

```python
21 load_dotenv()
23 client = OpenAI(
24     api_key=os.getenv("API_KEY"),
25     base_url=os.getenv("BASE_URL"),
26     default_headers={
27         "x-opencode-session": os.getenv("SESSION_ID", "workout"),
28         "User-Agent": "llm-master-journey/0.1",
29     },
30 )
31 model = os.getenv("MODEL", "deepseek-v4.1-flash")
```

- **21 `load_dotenv()`**：「进货」——把 `.env` 里四行倒进环境变量。必须在 24 行之前，否则 `os.getenv` 取到的全是空。
- **23-30 `client = OpenAI(...)`**：按图纸造机器。三个参数：**工牌**（api_key）、**收件地址**（base_url）、**工号牌**（default_headers，其中 `x-opencode-session` 是 opencode go 套餐的强制要求，缺了报 400 MissingSessionID；`SESSION_ID` 取不到时用 `"workout"` 兜底）。`User-Agent` 是「我是谁」的自我介绍，官方要求客户端标明身份。
- **31 `model = os.getenv("MODEL", "deepseek-v4.1-flash")`**：读模型名，`.env` 没配就用括号里第二个参数（**保底值**，和 `os.getenv` 的默认参数思维同源）。换模型只改 `.env` 一行，代码不动。

### 数据路径（33）

```python
33 DATA_FILE = Path(__file__).parent / "data" / "workouts.jsonl"
```

- **33 行**：`__file__` 是「当前这个 py 文件的路径」；`.parent` 取它的文件夹（`week2/`）；`/` 是 Path 的拼接运算符（比字符串加号聪明，自动处理斜杠）。最终指向 `week2/data/workouts.jsonl`。**为什么不用绝对路径**：换台电脑、换个文件夹，代码照样跑。`data/` 在 `.gitignore` 里——公开仓库不放私人训练数据。

### SYSTEM_PROMPT（35-37）——模板与插槽

```python
35 SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成结构化记录。
36 规则：没提到的数值一律填 null；有氧运动用 minutes；日期用今天（今天是 """ + date.today().isoformat() + """）。
37 若用户描述含糊（没有具体动作或数量），exercises 返回空列表。"""
```

- **35-37 行**：一个**用 `+` 拼出来的字符串**。三引号允许换行；中间的 `date.today().isoformat()` 就是**插槽**——拼装时由代码注入今天的日期。模型不知道今天是几号，你知道；模板负责把你的确定信息递过去。
- 注意它现在**只写规则，不写格式**——格式说明退休了，因为 `response_format` 的合同（77-82 行）已经管住形状。prompt 变短 = 输入 token 变少 = 每次请求都省一点。
- **37 行**是语义规则的第三句：含糊就交空表。它让模型的「不知道」有地方安放，而不是编。

### WORKOUT_SCHEMA（39-70）——机器的合同

```python
43 WORKOUT_SCHEMA = {
44     "name": "workout_record",
45     "strict": True,
46     "schema": {
47         "type": "object",
48         "properties": {
49             "date": {"type": "string"},
50             "exercises": {
51                 "type": "array",
52                 "items": {
...
65             "notes": {"type": "string"},
66         },
67         "required": ["date", "exercises", "notes"],
68         "additionalProperties": False,
69     },
70 }
```

- **43 行**：合同装在名叫 `WORKOUT_SCHEMA` 的字典里，三步套娃：外层元信息 → `schema` 条款。
- **44 `"name"`**：合同的标识名，服务端日志/错误里用它指认是哪张合同。
- **45 `"strict": True`**：**管束开关**。关掉它，schema 只是「建议」；打开它，服务端在生成时就把输出约束在条款内（constrained decoding），不合格的输出根本不会产生。
- **46 `"schema"`**：真正的条款。
- **47 `"type": "object"`**：顶层是个对象（对应 Python 字典）。
- **48 `"properties"`**：列举每个字段的规则。
- **49 `"date": {"type": "string"}`**：日期是字符串。注意：schema 只要求「是字符串」，**不要求「是今天的日期」**——事实校验永远是你的活。
- **50-64 `"exercises"`**：数组（`array`）。**52 `"items"`** 规定数组里每一件货的形状——一个对象，含五个字段（55-59 行）。**56-59 的 `["number", "null"]`** 是「可空」的正式写法：字段**必须在**，值可以是数字也可以是 null。这就是你输出里每个动作都带四个 null 的原因。用 `number` 而不是 `integer`，是为了 80.5kg 这种半公斤片也能进。
- **61 `"required"`**：动作对象里五个字段全列——strict 模式要求「可空 ≠ 可省」。
- **62 `"additionalProperties": False`**：这个对象不许出现第六个字段。模型想加 `"mood": "爽"`？被拒。
- **65 `"notes"`**：字符串备注。
- **67 `"required"`**：顶层三件套都要在。
- **68 `"additionalProperties": False`**：顶层也不许多塞。

### ask_once()（73-88）——网络层的药方

```python
73 def ask_once(messages: list[dict]):
74     """发一次请求；网络层最多试 3 次。返回 resp 或 None。"""
75     for attempt in range(3):
76         try:
77             resp = client.chat.completions.create(
78                 model=model,
79                 messages=messages,
82                 response_format={"type": "json_schema", "json_schema": WORKOUT_SCHEMA},
83             )
84             return resp
85         except (APIConnectionError, APIStatusError) as e:
86             print(f"[网络第 {attempt + 1} 次失败] {type(e).__name__}：{e}", flush=True)
87             time.sleep(2)
88     return None
```

- **73 行**：函数签名。`messages: list[dict]` 是类型标注（说明书，不强制）：「给我一个字典列表」；没写返回标注，实际返回 `resp` 或 `None`。**参数名 `messages` 和外层变量的同名没有关系**——函数只认「调用时递进来的东西」。
- **74 行**：docstring。**写清「失败返回什么」比写清「成功返回什么」更重要**——调用方靠它决定怎么兜底。
- **75 行**：`range(3)` 生成 0/1/2，就是三次机会。`attempt` 从 0 数起，所以 86 行打印时要 `+1` 才是人话（第 1 次、第 2 次、第 3 次）。
- **76 行 `try:`**：保险丝开始。「想干的事」放这里。
- **77-83 行**：发请求。四个参数：`model`（模型名）、`messages`（剧本）、`response_format`（**今天的合同**：`"type": "json_schema"` 告诉接口「我要按 schema 约束输出」，`"json_schema"` 里装合同的元信息+条款）。**这行一挂，围栏和字段漂移就变成 API 层的事。**
- **84 `return resp`**：成功就立刻交货。注意它在 `try` 里面——没有异常才会走到；`return` 之后函数结束，`time.sleep` 不会执行。
- **85 行**：两个异常类用**元组**一起捕获——`(A, B) as e` 的写法，哪种发生都进这个分支。`as e` 把异常对象绑给名字 `e`，后面能读 `e.status_code`、`e` 的文本。
- **86 行**：打印人话：第几次失败、异常类型名（`type(e).__name__` → "APIConnectionError"）、错误内容。`flush=True` 让消息立刻上屏（不然可能攒在缓冲里，你以为程序卡死）。
- **87 行**：睡 2 秒再进下一轮。**不睡的话三次会在一瞬间打完**，对限流（429）毫无意义。
- **88 行**：循环走完还没成功 → 返回 `None`。**函数不替上层做主**（不 sys.exit、不重试轰炸），把「认输」的决定权交出去。

### is_valid()（91-94）——语义层的药方

```python
91 def is_valid(data: dict) -> bool:
92     """语义验收：形状由 schema 保证，但「有没有内容」schema 管不了。"""
93     exercises = data.get("exercises")
94     return isinstance(exercises, list) and len(exercises) > 0
```

- **91 行**：`-> bool` 承诺返回布尔值（True/False），调用方可以放心写 `if is_valid(...)`。
- **92 行**：docstring 点破为什么需要这个函数——合同管形状，内容要靠自己验。
- **93 行**：`data.get("exercises")`——用 `.get` 而不是 `data["exercises"]`：键不存在时 `.get` 返回 `None`（不炸），方括号会 `KeyError`。**校验层的代码本身绝不能比被校验的数据更脆。**
- **94 行**：两个条件用 `and` 串起来：是列表（`isinstance(x, list)`）**并且**非空（`len(...) > 0`）。`True and True` 才返回 True。这个表达式就是语义验收的全部：**「有货吗？」**

### parse_workout()（97-128）——编排，今天的心脏

```python
97 def parse_workout(text: str):
98     """解析一句话。网络失败重试 3 次；语义失败纠错重试 1 次。"""
99     messages = [
100        {"role": "system", "content": SYSTEM_PROMPT},
101        {"role": "user", "content": text},
102    ]
104    for round_no in range(2):          # 第一次 + 语义纠错一次
105        resp = ask_once(messages)
106        if resp is None:
107            return None
109        raw = resp.choices[0].message.content
110        print(f"[原文#{round_no + 1}] {raw}")
112        try:
113            data = json.loads(raw)
114        except json.JSONDecodeError:
115            print("strict 模式下出现非法 JSON——异常，原文见上一行")
116            return None
118        if is_valid(data):
119            return data
121        # TODO 2 注释……
126        messages.append({"role": "assistant", "content": raw})
127        messages.append({"role": "user", "content": "上面这次 exercises 是空的。""请根据我最初的话重新解析；确实没有可记录的动作就保持空列表。"})
128    return None
```

- **97 行**：`text: str`——接收用户那句话。
- **98 行**：docstring 交代两层重试的分工。
- **99-102 行**：剧本 = system（规则+日期插槽）+ user（你的话）。**这里就是「上行整包」的起点**：后面每一轮都带着整个剧本重发。
- **104 行**：语义环。`range(2)` = 初问 + 纠错一次。`round_no` 只用于 110 行的编号显示。
- **105 行**：把「发请求」外包给 `ask_once`——网络层重试藏在里面，这里不关心。**分层的好处：改网络策略不用动语义逻辑，反之亦然。**
- **106-107 行**：`ask_once` 三次网络重试全灭 → 返回 `None` → 这里直接认输。**第一道门失守，不进语义流程。**
- **109 行**：从包裹里取正文。链路复习：`resp` → `.choices[0]`（候选列表挑第一件）→ `.message` → `.content`。
- **110 行**：体检线，打印第几轮的原文。`round_no + 1` 让编号从 1 开始。稳定后可以注释掉。
- **112-116 行**：`json.loads` 把字符串变字典。理论上 strict 模式下不该炸，但保留 `try` 是**防御性习惯**：接口行为会变，零成本的保险值得买。真炸了就打一句「异常」并认输（`JSONDecodeError` 是 json 库自带的异常类）。
- **118-119 行**：语义验收通过 → 直接 `return data`，成功路径在这里结束。
- **121-125 行**：TODO 留下的教学注释（可以删，但留着当备忘也行）。
- **126 行**：**先把它的错答留档**（`role: assistant`）。这是 Day 6 的协议：模型要看到「自己说过什么」，才知道下一条纠错是在说谁。
- **127 行**：再放纠错（`role: user`）。内容两件事：**错在哪**（exercises 是空的）+ **要什么**（按最初的话重新解析；确实没有就保持空表）。两个字符串字面量挨着写会**自动拼接**（`"a""b"` == `"ab"`），能用，但推荐合成一个字符串或用 f-string。
- **128 行**：两轮都没过 → 返回 `None`。**诚实的失败。**

### save()（131-142）——落盘

```python
131 def save(record: dict) -> int:
133     DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
134     with open(DATA_FILE, "a", encoding="utf-8") as f:
135         f.write(json.dumps(record, ensure_ascii=False) + "\n")
137     count = 0
138     with open(DATA_FILE, encoding="utf-8") as f:
139         for line in f:
140             if line.strip():
141                 count = count + 1
142     return count
```

- **131 行**：`record: dict` 进，`-> int`（总条数）出。
- **133 行**：`mkdir(parents=True, exist_ok=True)`——`data/` 不存在就建（包括父目录），已存在不报错。**首次运行不炸**靠它。
- **134 行**：`with open(...)` 的 `with`：代码块结束自动关文件（异常也关）。**`"a"` = append**：只往文件末尾追加，绝不覆盖已有记录。
- **135 行**：`json.dumps(record, ensure_ascii=False)` 把字典变一行字符串，`ensure_ascii=False` 让中文原样写出（否则 `\u5367\u63a8`）；末尾补 `"\n"`，这是 **JSON Lines** 的约定——一行一条，下一行开始新记录。
- **137-141 行**：数条数。`open` 默认读模式；`for line in f` 一行行过；`if line.strip()` 跳过空行（防手滑）。这是你从 Day 4 用到现在第 N 次的**累加器**。
- **142 行**：返回总条数，给 main 打印「文件累计 N 条」。

### main()（145-163）——外壳

```python
145 def main() -> None:
146     print("健身记录器 v2.1 —— 练完说一句，我帮你记。输入 q 退出。")
147     while True:
148         text = input("\n你说：").strip()
149         if not text or text.lower() in {"q", "quit", "exit"}:
150             break
152         record = parse_workout(text)
153         if record is None:
154             print("没解析成功，换个说法再试一次。")
155             continue
157         total = save(record)
158         names = "、".join(e["name"] for e in record["exercises"])
159         print(f"已记录 {record['date']} ｜ {names} ｜ 文件累计 {total} 条")
163 if __name__ == "__main__":
163     main()
```

- **145 行**：`-> None`：这个函数不返回东西，它干的是「运行一个循环」。
- **146 行**：开场白。
- **147 行**：`while True`——聊天程序的心跳。退出靠里面的 `break`。
- **148 行**：`input("\n你说：")` 停下等输入，`.strip()` 去掉首尾空格/回车（防止手滑打出的空格被当成内容）。
- **149 行**：两个退出条件：输入为空（`not text`）或（`or`）转小写后命中 `{"q","quit","exit"}` 集合。`.lower()` 让 Q/QT 也能退；集合查找 O(1)，比连写三个 `==` 干净。
- **152 行**：调用解析。注意 `parse_workout` 可能跑几秒（网络 + 可能的纠错），这里同步等待。
- **153-155 行**：`None` = 三种失败之一（网络三次全灭 / 非法 JSON / 语义两轮没救）→ 一句人话 + `continue` 回到循环顶部。
- **157 行**：落盘拿总条数。
- **158 行**：`"、".join(...)` 把动作名用顿号连起来。括号里是**生成器表达式**：`e["name"] for e in record["exercises"]`——边遍历边产出名字，不建中间列表。`join` 只吃字符串，所以元素必须是字符串（都是 `name` 的值）。
- **159 行**：f-string 拼回执：日期、动作、累计条数。
- **163 行**：`if __name__ == "__main__"`：只有直接运行本文件才执行 `main()`；被别的文件 `import` 时不会擅自开聊。**这就是「模块」和「脚本」的分身术。**

---

## 三、两个真实时序（用你今天的运行）

### 成功路径（卧推那句）

```
main → parse_workout("今天卧推80kg …")
  └─ round 0: ask_once → 模型交 JSON
       └─ json.loads → dict
       └─ is_valid → True（exercises 有 3 条）
       └─ return data        ← 一次通过，纠错分支没出场
  └─ save → 追加 1 行 → 返回 2
  └─ print「已记录 2026-11-05 ｜ 卧推、深蹲、跑步 ｜ 文件累计 2 条」
```

### 失败路径（「今天练了一下」）

```
parse_workout("今天练了一下")
  └─ round 0: 原文#1 = 空 exercises → is_valid False
       └─ append 错答 + 纠错消息
  └─ round 1: 原文#2 = 还是空（输入本来没信息）→ is_valid False
       └─ 再 append（这轮的追加用不上了）
  └─ 循环结束 → return None
main →「没解析成功，换个说法再试一次。」
```

**注意第二轮的空不是失败——是模型诚实地承认「你没说」。** 纠错消息救得了「没读懂」，救不了「本来就没有」。

---

## 四、函数速查

| 函数 | 签名 | 参数 | 返回 | 谁调用 | 失败时 |
|---|---|---|---|---|---|
| `ask_once` | `(messages: list[dict])` | 完整剧本 | `resp` 或 `None` | `parse_workout` | 网络重试 3 次后给 `None` |
| `is_valid` | `(data: dict) -> bool` | 解析后的字典 | `True/False` | `parse_workout` | 不抛异常，只回 False |
| `parse_workout` | `(text: str)` | 一句话 | `dict` 或 `None` | `main` | 三种失败统一给 `None` |
| `save` | `(record: dict) -> int` | 合法记录 | 文件总条数 | `main` | 磁盘错误会直接炸（可接受，日志要看得见） |
| `main` | `() -> None` | 无 | 无 | `__main__` | 内部逐层兜底 |

**调用图**：

```
main ──► parse_workout ──► ask_once ──► client.chat.completions.create
  └──► save                       └──► is_valid
```

---

## 五、今天用到的 Python 语法小词典

| 语法 | 例 | 一句话 |
|---|---|---|
| 字典字面量 | `{"role": "user"}` | 键值对，JSON 的 Python 形态 |
| 列表字面量 | `[a, b, c]` | 有顺序的容器 |
| 类型标注 | `x: str`、`-> bool` | 说明书，不强制 |
| f-string | `f"第 {n} 次"` | 花括号里放表达式 |
| `range(n)` | `range(3)` | 0..n-1 |
| `try/except` | 见 76-87 | 保险丝：意外不摔死 |
| 元组捕获 | `except (A, B) as e` | 两种异常一起接 |
| `with open` | 见 134 | 自动关文件 |
| `json.loads/dumps` | str↔dict | JSON 翻译官 |
| `.get(k, 默认)` | `data.get("exercises")` | 拿不到不炸，给保底 |
| `isinstance` | `isinstance(x, list)` | 类型检查 |
| `len()` | `len(list)` | 长度 |
| 生成器表达式 | `for e in xs` 套在 `join` 里 | 边走边产，不建中间表 |
| `__file__` / `Path` | 见 33 | 以文件所在位置为锚做路径 |
| `if __name__ == "__main__"` | 见 163 | 直接运行才执行 |
| 相邻字符串拼接 | `"a""b"` | 自动连成 "ab"（少用） |

---

## 六、自测五题（答案在文末）

1. 如果把 82 行的 `response_format` 删掉，哪两类错误会重新变成概率事件？
2. `is_valid` 为什么用 `data.get("exercises")` 而不是 `data["exercises"]`？
3. 126 行和 127 行的 append 顺序如果颠倒，会发生什么？
4. 为什么 `save` 里用 `"a"` 而不是 `"w"`？两种模式各打一个比方。
5. `parse_workout` 为什么要用两层循环（`range(2)` 套 `ask_once` 里的 `range(3)`）？合成一层行不行？

---

### 自测题答案

1. 围栏（```json 包裹）和字段漂移（少字段/多字段/类型不对）。
2. 键不存在时 `.get` 返回 None（不炸），方括号会抛 KeyError——校验层必须比数据更稳。
3. 剧本里先出现一条孤立的 user 纠错，没有对应的 assistant 错答可指认；轻则模型看不懂，重则接口 400。
4. `"w"` 覆盖全文（像重新买一本本子写第一页），`"a"` 追加（像在本子最后一行续写）。训练记录只能追加。
5. 两层治两种病：网络失败（瞬时，值得睡 2 秒重试）vs 语义失败（值得纠错一次）；合成一层会让「401 重试 3 次」这种无效劳动发生，也分不清该睡还是该纠错。
