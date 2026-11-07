"""Day 11：助手 v2.3——会写周报了。

用法：python week2/assistant_v2.py
记录：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟
提问：我上次卧推多少？ / 这周练了几次？ / 这周练得怎么样？

今天的新分工（周总结 = RAG 的「生成」那一半）：
· 数字由程序算：compute_week_stats 在本地把本周记录聚合成一份统计（模型没见过原始记录）；
· 措辞由模型写：write_summary 只拿到统计 JSON，规则是「一个数字都不许编」。
· 昨天是「程序查、程序答」；今天是「程序算、模型写」——检索之后的生成，
  第 3 周 RAG 缺的最后一块。
· few-shot 进 SYSTEM_PROMPT：示例教语义（半小时→30、模糊→空），契约管形状。
"""
import json
import os
import time
from datetime import date, timedelta
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

# TODO 0（今天的 few-shot，两行）：在下面 SYSTEM_PROMPT 的规则后面加两条示例。
#   只示范「字段怎么填」，不用重抄整张 schema（形状已经由 WORKOUT_SCHEMA 管了，示例只教语义）：
#   ① 「今天跑了半小时」→ 跑步的 minutes 填 30（口语时间要换算）
#   ② 「练了一下」→ exercises 返回空列表
#   提示：示例里不必写日期——写死哪一天，明天就过期了；只示范字段。
SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成结构化记录。
规则：没提到的数值一律填 null；有氧运动用 minutes；日期用今天（今天是 """ + date.today().isoformat() + """）。
若用户描述含糊（没有具体动作或数量），exercises 返回空列表。"""

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
                # TODO 1：第四种意图加进枚举（照 QUERY_PROMPT 里新加的那个词抄）。
                #   昨天 lesson：enum 是「只能从这几个词里选」，不是 properties 的字段表。
                "enum": ["last_exercise", "week_count", "unknown"],
            },
            # 可空写法：["string", "null"] 是「字符串或 null」，不是 "string,null"
            "exercise": {"type": ["string", "null"]},
        },
        "required": ["intent", "exercise"],
        "additionalProperties": False,
    },
}


def ask_once(messages: list[dict], schema: dict | None = None):
    """发一次请求；网络层最多试 3 次。传了 schema 才套格式合同——总结是人话，不套。"""
    for attempt in range(3):
        try:
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
        resp = ask_once(messages, WORKOUT_SCHEMA)   # 默认合同撤了 → 记录线必须显式点名
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
            # TODO 2（三行）：第一次遇到这个动作 → 在 stats 里给它开一本空账（全是 0，best_kg 是 None）
            #   提示：if name not in stats: stats[name] = {"times": 0, "best_kg": None, "sets": 0, "reps": 0, "minutes": 0}
            s = stats[name]          # ← 先留着这行；TODO 2 写完，它才有东西可取
            s["times"] = s["times"] + 1

            # TODO 3（四段 if）：把这次的数据并进账本——
            #   ① 重量：item["weight_kg"] 不是 None 时，跟 s["best_kg"] 比，更大（或还没有）就更新；
            #      None 表示「这次没记重量」，不是 0kg
            #   ② 组数：有值才累加 → s["sets"] = s["sets"] + item["sets"]
            #   ③ 次数：同上，累加 reps
            #   ④ 分钟：同上，累加 minutes
            #   提示：没值就跳过，否则 None + 1 会 TypeError——「没记」和「记了 0」是两件事。

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
    resp = ask_once(messages)          # 故意不传 schema：总结是写给人看的，不是给程序解析的
    if resp is None:
        return "总结没生成出来，网络不好。"

    print(f"[token] 总结 输入 {resp.usage.prompt_tokens} / 输出 {resp.usage.completion_tokens}")
    # TODO 4（一行）：把总结正文返回给调用者
    return ""


def answer_question(text: str, records: list[dict]) -> str:
    """模型理解问题 → 程序查数据 → 模板组装答案。"""
    messages = [
        {"role": "system", "content": QUERY_PROMPT},
        {"role": "user", "content": text},
    ]

    # 模型只做翻译：问句 → {"intent", "exercise"}；数据查询一行都还没开始
    resp = ask_once(messages, QUERY_SCHEMA)
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
        # TODO 5（五行）：本周总结分支——
        #   ① stats = compute_week_stats(records)
        #   ② stats["sessions"] == 0 → return "这周还没有记录，练完说一句就有了。"
        #   ③ header = f"这周（{stats['week_start']} 起）共练了 {stats['sessions']} 次。\n"
        #   ④ return header + write_summary(stats)
        #   想一想：总次数为什么让程序报，不让模型报？
        return ""

    return "这个问题我还答不了。试试「我上次卧推多少」或「这周练了几次」。"


def main() -> None:
    print("健身记录器 v2.3 —— 练完说一句我帮你记；想问就问（如：我上次卧推多少？这周练得怎么样？）。输入 q 退出。")
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


if __name__ == "__main__":
    main()
