"""Day 9：助手 v2.1——把「格式」交给合同，把「重试」分成两层。

用法：python week2/assistant_v2.py
输入：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟

今天的两处升级（来自 Day 8 笔记的对账结论）：
① response_format 上 json_schema(strict)：格式从「说服」变成「管束」——
   API 层保证输出符合 schema，裹围栏、字段漂移从「概率问题」变成「不可能事件」。
   于是 prompt 里的格式说明退休，prompt 变短，输入 token 省下来。
② 双层重试：网络失败（3 次 + sleep）和语义失败（1 次 + 纠错消息）是两类病，两份处方。
"""
import json
import os
import time
from datetime import date
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


def ask_once(messages: list[dict]):
    """发一次请求；网络层最多试 3 次。返回 resp 或 None。"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                # TODO 1（两行）：把格式从「说服」升级成「管束」——
                #   response_format={"type": "json_schema", "json_schema": WORKOUT_SCHEMA},
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

        # TODO 2（今天的核心四行）：语义失败 → 纠错重试。顺序是协议：
        #   messages.append({"role": "assistant", "content": raw})   ← 把它的错答留档
        #   messages.append({"role": "user", "content": "上面这次 exercises 是空的。"
        #                                            "请根据我最初的话重新解析；确实没有可记录的动作就保持空列表。"})
        # 提示：纠错消息必须说清「错在哪」+「要什么」，否则它第二次还会这么答。

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


def main() -> None:
    print("健身记录器 v2.1 —— 练完说一句，我帮你记。输入 q 退出。")
    while True:
        text = input("\n你说：").strip()
        if not text or text.lower() in {"q", "quit", "exit"}:
            break

        record = parse_workout(text)
        if record is None:
            print("没解析成功，换个说法再试一次。")
            continue

        total = save(record)
        names = "、".join(e["name"] for e in record["exercises"])
        print(f"已记录 {record['date']} ｜ {names} ｜ 文件累计 {total} 条")


if __name__ == "__main__":
    main()
