"""Day 10：助手 v2.2——会查历史了。

用法：python week2/assistant_v2.py
记录：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟
提问：我上次卧推多少？ / 这周练了几次？

今天的新分工（查历史问答）：
· 模型只做一件事：把问句翻译成查询意图（QUERY_SCHEMA）——它根本不看历史数据；
· 程序做另外两件事：在本地 workouts.jsonl 里查、用模板把答案组装成人话。
· 为什么不把整个文件塞给模型：历史越长，每轮重发的 token 越贵，无关信息还会把回答带偏。
  查数靠代码，理解靠模型——第 3 周 RAG 的骨架就是这个分工。
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

SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成结构化记录。
规则：没提到的数值一律填 null；有氧运动用 minutes；日期用今天（今天是 """ + date.today().isoformat() + """）。
若用户描述含糊（没有具体动作或数量），exercises 返回空列表。"""

QUERY_PROMPT = """你在把健身助手用户的问题翻译成查询意图。
可选意图：
- last_exercise：问某个动作上次的数据（例：「我上次卧推多少」）→ exercise 填动作名，如「卧推」
- week_count：问本周练了几次（例：「这周练了几次」）→ exercise 填 null
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
                # TODO 1：把三种意图的枚举值写进来（照 QUERY_PROMPT 里那三个词抄）
                "enum": ["last_exercise", "week_count", "unknown"],
            },
            # TODO 2（一行）：exercise 要可空——类型改成数组，和昨天 nullable 的写法一样
            "exercise": {"type": ["string", "null"]},
        },
        "required": ["intent", "exercise"],
        "additionalProperties": False,
    },
}


def ask_once(messages: list[dict], schema: dict = WORKOUT_SCHEMA):
    """发一次请求；网络层最多试 3 次。格式合同由调用者选（默认是记训练那张）。"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": schema},
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
        resp = ask_once(messages)
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
                # TODO 3（一行）：把这一行从字符串变成字典，装进 records
                records.append(json.loads(line))
    return records


QUESTION_HINTS = ("多少", "几次", "上次", "最近", "这周", "本周", "历史", "多久")


def is_question(text: str) -> bool:
    """判断一句话是提问还是训练记录。"""
    # TODO 4（一行）：问句的特征——句尾是问号，或包含上面的任一提示词。
    #   提示：str.endswith 可以一次收多个候选：text.rstrip().endswith(("？", "?"))
    #        “包含”判断：any(hint in text for hint in QUESTION_HINTS)
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


def answer_question(text: str, records: list[dict]) -> str:
    """模型理解问题 → 程序查数据 → 模板组装答案。"""
    messages = [
        {"role": "system", "content": QUERY_PROMPT},
        {"role": "user", "content": text},
    ]

    # TODO 5（四行）：让模型把问句翻译成意图。
    #   ① resp = ask_once(messages, QUERY_SCHEMA)      ← 网络重试直接复用昨天那套
    #   ② resp 为 None → return "网络不好，等下再问。"
    #   ③ data = json.loads(resp.choices[0].message.content)
    #   ④ 注意：这里是「理解层」，还不需要 load_records —— 模型没看过任何训练数据。
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

    return "这个问题我还答不了。试试「我上次卧推多少」或「这周练了几次」。"


def main() -> None:
    print("健身记录器 v2.2 —— 练完说一句我帮你记；想问就问（如：我上次卧推多少？）。输入 q 退出。")
    while True:
        text = input("\n你说：").strip()
        if not text or text.lower() in {"q", "quit", "exit"}:
            break

        if is_question(text):
            # TODO 6（两行）：查历史分支——读记录、回答、回到循环顶部。
            #   提示：records = load_records()
            #        print(answer_question(text, records))
            #        continue
            #不懂
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
