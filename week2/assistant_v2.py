"""Day 8：助手 v2 第一版——健身记录器。

用法：python week2/assistant_v2.py
然后输入（自然语言）：今天卧推80kg 5组5次，深蹲100kg 5x5，跑步20分钟

流程：你的话 → 模型转成 JSON（Day 4 技能）→ 追加进 week2/data/workouts.jsonl

旧技能回收：structured.py 的 JSON 合同 / cost_log.py 的重试 / chat.py 的剧本结构
新砖一块：JSON Lines 文件——一行一条记录，追加不覆盖，永久保存。
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

# 数据放本地，不进公开仓库（这是你的身体数据，隔壁 .gitignore 已挡住）
DATA_FILE = Path(__file__).parent / "data" / "workouts.jsonl"

SYSTEM_PROMPT = """你是健身记录解析器。把用户的话解析成 JSON，只输出 JSON，不要其他文字。
格式：
{"date": "YYYY-MM-DD", "exercises": [{"name": "动作名", "weight_kg": 数字或null, "sets": 数字或null, "reps": 数字或null, "minutes": 数字或null}], "notes": "备注或空字符串"}
规则：没提的数值写 null；有氧用 minutes；日期没提就用今天（今天是 """ + date.today().isoformat() + """）。"""


def parse_workout(text: str):
    """把一句话解析成记录字典；失败返回 None。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    resp = None
    for attempt in range(3):
        try:
            # TODO 1（纯搬运，Day 4 原样）：同步 create，参数 model 和 messages
            resp = ...
            break
        except (APIConnectionError, APIStatusError) as e:
            print(f"[第 {attempt + 1} 次失败] {type(e).__name__}：{e}", flush=True)
            time.sleep(2)

    if resp is None:
        return None

    raw = resp.choices[0].message.content
    print(f"[原文] {raw}")    # 体检线：看模型交的形状；稳定后注释掉

    # TODO 2（半搬运 + 今天的第二层）：
    #   data = json.loads(raw)
    #   然后校验（Day 4 的教训：保形状不保语义，程序要自己验）：
    #   · data 里有 "exercises" 这个键，且它的值是列表、不为空
    #   · 不合法 → print 一句人话提示 → return None
    ...


def save(record: dict) -> int:
    """追加一条记录到 workouts.jsonl，返回文件里的总条数。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    # TODO 3（今天唯一的新砖）：追加模式写一行
    #   with open(DATA_FILE, "a", encoding="utf-8") as f:
    #       f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # 注意 "a" = append：只往末尾加，不覆盖老记录；ensure_ascii=False 让中文可读

    # 数条数——老套路：打开文件，for 一行行数，非空的就 +1
    count = 0
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count = count + 1
    return count


def main() -> None:
    print("健身记录器 v1 —— 练完说一句，我帮你记。输入 q 退出。")
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
