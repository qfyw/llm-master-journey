"""Day 6：Function Calling + 组装命令行助手。

运行：python assistant.py "今天几号？"
过关：普通问题能答；问到日期时，助手先「查工具」再回答。

今天三位老朋友的技能合体：
· chat.py 的多轮结构（messages 剧本）
· structured.py 的 json.loads（解析模型给的参数）
· cost_log.py 的账本（token / 成本 / 重试）
真正的新东西只有一个：Function Calling——
模型不再只写台词；它会举手说「我需要查一次日期」，
你的程序替它查完，把结果塞回剧本，它才接着演。
"""
import json
import os
import sys
import time
from datetime import date       # TODO 1 要用

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    default_headers={
        "x-opencode-session": os.getenv("SESSION_ID", "assistant"),
        "User-Agent": "llm-master-journey/0.1",
    },
)
model = os.getenv("MODEL", "deepseek-v4.1-flash")

PRICE_IN = 2 / 1_000_000
PRICE_OUT = 8 / 1_000_000


def get_date() -> str:
    """查今天的日期。真实项目里这可能是数据库、天气 API、公司内部系统。"""
    # TODO 1：返回今天日期，格式 2026-11-02。提示：date.today().isoformat()
    ...


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "查询今天的日期。用户问今天几号、当前日期时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def ask(messages: list[dict]):
    """同步请求 + 重试——这招你 Day 5 亲手写过，从 cost_log.py 照抄即可。"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,        # ← 今天唯一的新参数：把工具箱递给模型
            )
            return resp
        except (APIConnectionError, APIStatusError) as e:
            TRANSLATE = {401: "key 无效", 402: "余额不足", 404: "地址或模型名不对", 429: "限流"}
            hint = TRANSLATE.get(getattr(e, "status_code", None), "网络问题或未知错误")
            print(f"[第 {attempt + 1} 次失败] {type(e).__name__}：{hint}（{e}）", flush=True)
            time.sleep(2)
    return None


def main() -> None:
    # ── CLI：python assistant.py "你的问题" ──
    # sys.argv 是命令行参数列表：argv[0] 是文件名，argv[1] 才是你写的第一个参数
    question = sys.argv[1] if len(sys.argv) > 1 else input("问题：")
    messages = [
        {"role": "system", "content": "你是一个简洁的中文助手。需要工具时就用它。"},
        {"role": "user", "content": question},
    ]

    resp = ask(messages)
    if resp is None:
        sys.exit("接口连不上，三次重试失败。")

    msg = resp.choices[0].message

    # ── 今天的心脏：模型举手要工具 ──
    if msg.tool_calls:
        # TODO 2：替模型干活，再把工具结果塞回剧本。照这张图敲（顺序就是剧情）：
        #
        #   messages.append(msg)                                  ① 它举手的记录，原样留档
        #   for call in msg.tool_calls:
        #       args = json.loads(call.function.arguments or "{}") ② 参数是一段 JSON 字符串
        #       result = get_date()                                ③ 执行（眼下只有这一个工具）
        #       print(f"[工具] {call.function.name}({args}) → {result}")
        #       messages.append({"role": "tool", "tool_call_id": call.id, "content": result})  ④ 结果回填
        #   resp = ask(messages)                                   ⑤ 带着工具结果再问一次
        #   msg = resp.choices[0].message                          ⑥ 这次拿到的才是最终答案
        ...

    print(f"\n助手：{msg.content}")

    usage = resp.usage
    cost = usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT
    print(f"[token] 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens} ｜ 约 {cost:.6f} 元")


if __name__ == "__main__":
    main()
