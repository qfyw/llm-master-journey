"""Day 12：助手 v2.4——每次请求都有小票。

用法：python week2/assistant_v2.py
记录：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟
提问：我上次卧推多少？ / 这周练了几次？ / 这周练得怎么样？

今天的主题（可观测性）：
· 三条模型调用线（记录解析 / 意图翻译 / 周总结）都从 ask_once 过路，
  统一记账：输入、输出、参考花费、耗时——按调用点分开算，不再各打各的。
· 每次成功调用追加一行到 week2/data/usage.jsonl；退出时打印本次会话总账。
· 「输出 token 为什么贵」不再靠感觉：账本直接告诉你钱花在哪条线、哪一段。
· 顺手补掉 Day 11 的已知缺口：让「帮我总结一下」走到查询线（一个词的事）。
"""
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    default_headers={
        "x-opencode-session": os.getenv("SESSION_ID", "workout"),
        "User-Agent": "llm-master-journey/0.1",
    },
)
model = os.getenv("MODEL", "deepseek-v4.1-flash")

DATA_FILE = Path(__file__).parent / "data" / "workouts.jsonl"
USAGE_FILE = Path(__file__).parent / "data" / "usage.jsonl"

# 参考单价（元/token）：deepseek-flash 的峰值价。价格会变，只在这里改。
# 账本算的是「参考价」不是发票——缓存、峰谷、隐藏推理都可能让实际账单不同。
PRICE_IN = 2 / 1_000_000
PRICE_OUT = 8 / 1_000_000

# 本次会话的总账：每成功调用一次就累加，退出时结算。
SESSION = {"calls": 0, "input": 0, "output": 0, "cost": 0.0}

# few-shot 设计（Day 11）：只示范字段，不重抄整张 schema（形状归 WORKOUT_SCHEMA 管）；
# 示例不写日期——写死哪一天，明天就过期；日期靠下面的插槽注入。
SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成结构化记录。
规则：没提到的数值一律填 null；有氧运动用 minutes；日期用今天（今天是 """ + date.today().isoformat() + """）。
示例（只示范字段怎么填，不示范整张格式）：
- 「今天跑了半小时」→ {"name": "跑步", "minutes": 30}，其余数值字段填 null
- 「练了一下」→ {"exercises": []}"""

QUERY_PROMPT = """你在把健身助手用户的问题翻译成查询意图。
可选意图：
- last_exercise：问某个动作上次的数据（例：「我上次卧推多少」）→ exercise 填动作名，如「卧推」
- week_count：问本周练了几次（例：「这周练了几次」）→ exercise 填 null
- week_summary：问本周整体情况（例：「这周练得怎么样」「帮我总结下这周」）→ exercise 填 null
- unknown：其它问题 → exercise 填 null
只输出 JSON，不要解释。"""

# —— JSON Schema 军规（strict 模式要求）——
# · 每个字段都要列进 required（"可空"用 ["number", "null"] 表达，而不是不写）
# · 每个 object 都要 additionalProperties: false（不许多塞字段）
# · array 必须给出 items 的形状
WORKOUT_SCHEMA = {
    "name": "workout_record",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "date": {"type": "string"},
            "exercises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "weight_kg": {"type": ["number", "null"]},
                        "sets": {"type": ["number", "null"]},
                        "reps": {"type": ["number", "null"]},
                        "minutes": {"type": ["number", "null"]},
                    },
                    "required": ["name", "weight_kg", "sets", "reps", "minutes"],
                    "additionalProperties": False,
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["date", "exercises", "notes"],
        "additionalProperties": False,
    },
}

# —— 查历史的意图合同：比 WORKOUT_SCHEMA 小得多，只有「一个枚举 + 一个可空字符串」——
QUERY_SCHEMA = {
    "name": "query_intent",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                # enum 是「只能从这几个词里选」：prompt 教语义，enum 管词汇表，两边必须同步
                "enum": ["last_exercise", "week_count", "unknown", "week_summary"],
            },
            # 可空写法：["string", "null"] 是「字符串或 null」，不是 "string,null"
            "exercise": {"type": ["string", "null"]},
        },
        "required": ["intent", "exercise"],
        "additionalProperties": False,
    },
}


def track_usage(label: str, resp, latency: float) -> None:
    """一次成功调用的账：打印小票 + 追加账本 + 累加会话总账。"""
    usage = resp.usage

    # TODO 1（一行）：花费 = 输入 token × 输入单价 + 输出 token × 输出单价。
    #   单价在文件顶部 PRICE_IN / PRICE_OUT；先乘 token 再乘单价，别反过来。
    cost = 0.0

    print(f"[账本] {label} 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens}"
          f" ｜ 约 {cost:.6f} 元 ｜ 耗时 {latency:.2f}s")

    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "input": usage.prompt_tokens,
        "output": usage.completion_tokens,
        "cost": round(cost, 6),
        "latency_s": round(latency, 3),
    }
    # TODO 2（三行）：把 record 追加到 USAGE_FILE，一行一个 JSON。
    #   提示：文件所在目录可能还不存在；追加用的模式是 "a"。
    #   USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    #   with open(...) as f: f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # TODO 3（四行）：累加会话总账——调用次数、输入、输出、花费。
    #   提示：SESSION 是文件顶部那个字典；用法和 Day 5 的四个累加器一样。
    pass


def ask_once(messages: list[dict], schema: dict | None = None, label: str = "请求"):
    """发一次请求；网络层最多试 3 次。成功后退场前自动记账（带调用点标签）。"""
    for attempt in range(3):
        try:
            # TODO 4（两行）：给这一次调用掐表。
            #   ① started = time.perf_counter()          ← 放在 if schema 判断之前
            #   ② latency = time.perf_counter() - started ← 放在拿到 resp 之后
            #   提示：perf_counter 是单调秒表，比 time.time() 更适合量耗时（系统改时间它不跳）。
            if schema is not None:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_schema", "json_schema": schema},
                )
            else:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
            latency = 0.0   # ← 用上面 ② 的结果替换这一行
            track_usage(label, resp, latency)
            return resp
        except (APIConnectionError, APIStatusError) as e:
            print(f"[网络第 {attempt + 1} 次失败] {type(e).__name__}：{e}", flush=True)
            time.sleep(2)
    return None


def is_valid(data: dict) -> bool:
    """语义验收：形状由 schema 保证，但「有没有内容」schema 管不了。"""
    exercises = data.get("exercises")
    return isinstance(exercises, list) and len(exercises) > 0


def parse_workout(text: str):
    """解析一句话。网络失败重试 3 次；语义失败纠错重试 1 次。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    for round_no in range(2):          # 第一次 + 语义纠错一次
        label = "记录解析" if round_no == 0 else "记录纠错"
        resp = ask_once(messages, WORKOUT_SCHEMA, label)   # 合同显式点名；label 让账本分清首次还是纠错
        if resp is None:
            return None

        raw = resp.choices[0].message.content
        print(f"[原文#{round_no + 1}] {raw}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("strict 模式下出现非法 JSON——异常，原文见上一行")
            return None

        if is_valid(data):
            return data

        # 语义失败 → 纠错重试。顺序是协议：先留档它的错答，再指出错在哪 + 要什么。
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": "上面这次 exercises 是空的。""请根据我最初的话重新解析；确实没有可记录的动作就保持空列表。"})
    return None


def save(record: dict) -> int:
    """追加一条记录到 workouts.jsonl，返回文件里的总条数。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    count = 0
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count = count + 1
    return count


# ———————————————— 查询线：模型理解问题，程序查数据 ————————————————


def load_records() -> list[dict]:
    """读整个 workouts.jsonl，返回记录列表（文件不存在就是空列表）。"""
    records = []
    if not DATA_FILE.exists():
        return records
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                # 每行是 JSON 字符串 → json.loads 变成字典，才能取 record["date"]
                records.append(json.loads(line))
    return records


# TODO 5（一个词）：Day 11 的已知缺口——「帮我总结一下」不含问号，也不含下面任何提示词，
#   会被当成训练记录送进解析线。往元组里加一个词，让这句话走查询线（提示：加在最后）。
QUESTION_HINTS = ("多少", "几次", "上次", "最近", "这周", "本周", "历史", "多久")


def is_question(text: str) -> bool:
    """判断一句话是提问还是训练记录。"""
    # 问句特征：句尾问号，或含任一提示词（「多少」「几次」「上次」……）
    if text.rstrip().endswith(("？", "?")) or any(hint in text for hint in QUESTION_HINTS):
        return True
    return False


def find_last(records: list[dict], exercise: str):
    """从最新一条往回找：第一条含有该动作的记录。返回 {"date":..., "item":...} 或 None。"""
    for record in reversed(records):
        for item in record["exercises"]:
            if exercise in item["name"]:
                return {"date": record["date"], "item": item}
    return None


def count_this_week(records: list[dict]) -> int:
    """数本周（周一起到今天）有几条记录。"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())   # weekday(): 周一=0 … 周日=6
    count = 0
    for record in records:
        record_date = date.fromisoformat(record["date"])   # "2026-11-05" → date 对象
        if record_date >= monday:
            count = count + 1
    return count


def compute_week_stats(records: list[dict]) -> dict:
    """本周（周一起）的汇总：练了几次 + 每个动作的累计数据。只算，不说话。"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    sessions = 0
    stats = {}   # 动作名 → {"times": 出现次数, "best_kg": 最重, "sets": 总组数, "reps": 总次数, "minutes": 总分钟}

    for record in records:
        record_date = date.fromisoformat(record["date"])
        if record_date < monday:
            continue
        sessions = sessions + 1

        for item in record["exercises"]:
            name = item["name"]
            # 第一次遇到这个动作 → 开一本空账；s 是 stats[name] 的别名，改 s 就是改账本
            if name not in stats:
                stats[name] = {"times": 0, "best_kg": None, "sets": 0, "reps": 0, "minutes": 0}
            s = stats[name]
            s["times"] = s["times"] + 1
            
            # 重量先判「账本还没有」，再比较；组数/次数/分钟有值才累加（None 不能参与加法）
            if s["best_kg"] is None or s["best_kg"] < item["weight_kg"]:
                s["best_kg"] = item["weight_kg"]
            if item["sets"]:
                s["sets"] = s["sets"] + item["sets"]
            if item["reps"]:
                s["reps"] = s["reps"] + item["reps"]
            if item["minutes"]:
                s["minutes"] = s["minutes"] + item["minutes"]
            
    return {"week_start": monday.isoformat(), "sessions": sessions, "exercises": stats}


SUMMARY_PROMPT = """你是健身教练，要根据程序给出的本周统计写一段 3-4 句的中文总结。
规则：
1. 只用统计里出现的数字，一个都不许自己编；
2. 统计里没有的动作不要提，没出现的数字不要说；
3. total_sets / total_reps / total_minutes 是**整周累计**，不是每次的量——别写成「每组 N 次」；
4. 不要重复总次数（程序已经报了），直接点评本周表现，最后给一句下周的具体建议；
5. 只输出总结正文：不要 JSON、不要标题、不要解释。"""


def stats_for_model(stats: dict) -> dict:
    """给模型的统计副本：字段自带口径，0 一律去掉。

    Day 11 实测的两个坑：
    · 直接把 minutes: 0 交给模型 → 它写「训练时长记录为 0 分钟，安排偏短」；
    · 键名叫 sets / reps → 累计 8 组 10 次被读成「8 组、每组 10 次」。
    账本里的 0 是「没记」；给模型看的键名要自带「这是整周累计」的说明。
    """
    clean = {"week_start": stats["week_start"], "sessions": stats["sessions"], "exercises": {}}
    for name, s in stats["exercises"].items():
        item = {"times": s["times"]}
        if s["best_kg"]:
            item["best_kg"] = s["best_kg"]
        if s["sets"]:
            item["total_sets"] = s["sets"]
        if s["reps"]:
            item["total_reps"] = s["reps"]
        if s["minutes"]:
            item["total_minutes"] = s["minutes"]
        clean["exercises"][name] = item
    return clean


def write_summary(stats: dict) -> str:
    """程序算好的数字 → 模型组织成人话。数字归程序，措辞归模型。"""
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": json.dumps(stats_for_model(stats), ensure_ascii=False)},
    ]
    resp = ask_once(messages, label="周总结")   # 故意不传 schema：总结是写给人看的，不是给程序解析的
    if resp is None:
        return "总结没生成出来，网络不好。"

    # 记账统一在 ask_once → track_usage 里做了，这里不再自己打印 token（避免两本账）
    return resp.choices[0].message.content.strip()


def answer_question(text: str, records: list[dict]) -> str:
    """模型理解问题 → 程序查数据 → 模板组装答案。"""
    messages = [
        {"role": "system", "content": QUERY_PROMPT},
        {"role": "user", "content": text},
    ]

    # 模型只做翻译：问句 → {"intent", "exercise"}；数据查询一行都还没开始
    resp = ask_once(messages, QUERY_SCHEMA, label="意图翻译")
    if resp is None:
        return "网络不好，等下再问。"
    data = json.loads(resp.choices[0].message.content)

    intent = data["intent"]
    exercise = data["exercise"]

    if intent == "last_exercise" and exercise:
        found = find_last(records, exercise)
        if found is None:
            return f"没有找到「{exercise}」的记录。"
        item = found["item"]
        parts = [found["date"]]
        if item["weight_kg"] is not None:
            parts.append(f"{item['weight_kg']}kg")
        if item["sets"] is not None:
            parts.append(f"{item['sets']}组")
        if item["reps"] is not None:
            parts.append(f"×{item['reps']}次")
        if item["minutes"] is not None:
            parts.append(f"{item['minutes']}分钟")
        return f"上次{exercise}是 " + " ".join(parts) + "。"

    if intent == "week_count":
        return f"这周（周一起）练了 {count_this_week(records)} 次。"

    if intent == "week_summary":
        # 空周守卫：没有记录就直接说，不把空统计交给模型；总次数由程序报，模型只写点评
        stats = compute_week_stats(records)
        if stats["sessions"] == 0:
            return "这周还没有记录，练完说一句就有了。"
        header = f"这周（{stats['week_start']} 起）共练了 {stats['sessions']} 次。\n"
        return header + write_summary(stats)

    return "这个问题我还答不了。试试「我上次卧推多少」或「这周练了几次」。"


def main() -> None:
    print("健身记录器 v2.4 —— 练完说一句我帮你记；想问就问（如：我上次卧推多少？这周练得怎么样？）。输入 q 退出。")
    while True:
        text = input("\n你说：").strip()
        if not text or text.lower() in {"q", "quit", "exit"}:
            break

        if is_question(text):
            # 查历史分支：读记录 → 回答 → 回到循环顶部（continue）
            records = load_records()
            print(answer_question(text, records))
            continue
        else:
            record = parse_workout(text)
            if record is None:
                print("没解析成功，换个说法再试一次。")
                continue

            total = save(record)
            names = "、".join(e["name"] for e in record["exercises"])
            print(f"已记录 {record['date']} ｜ {names} ｜ 文件累计 {total} 条")

    # 退出时结算本次会话（Ctrl+C 直接走的话不会执行到这里——已知边界）
    if SESSION["calls"] == 0:
        print("本次会话：没有发生模型调用。")
    else:
        print(f"本次会话：{SESSION['calls']} 次调用 ｜ 输入 {SESSION['input']} / 输出 {SESSION['output']}"
              f" ｜ 参考总价 {SESSION['cost']:.6f} 元")


if __name__ == "__main__":
    main()
