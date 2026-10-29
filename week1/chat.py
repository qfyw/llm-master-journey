"""Day 2：多轮对话。

目标：写一个 chat(messages) 函数，让程序"记得"你上一句说了什么。
运行：python week1/chat.py
过关标准：告诉它一个信息，下一句问它，它答得出来。

提示：昨天的 day01_hello.py 里你已经写过一次"发请求 + 取回复"，
今天 TODO 1、2 就是把那段搬进来。真正的新东西是 TODO 3、4、5。
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    default_headers={
        "x-opencode-session": os.getenv("SESSION_ID", "chat"),
        "User-Agent": "llm-master-journey/0.1",
    },
)
model = os.getenv("MODEL", "deepseek-v4.1-flash")


def chat(messages: list[dict]) -> str:
    """发一轮对话，返回模型回复的文本。messages 就是程序的"记忆"。"""
    # TODO 1: 调用 client.chat.completions.create，参数是 model 和 messages
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    # TODO 2: 从 resp 里取出回复文本并 return（链路的最后一环，
    #         昨天你 print 的是 .choices[0].message.content）
    return resp.choices[0].message.content

def main() -> None:
    messages = [
        {"role": "system", "content": "你是一个简洁的中文助手。"},
    ]
    print("输入 q 退出")
    while True:
        user_input = input("\n你：").strip()
        if not user_input or user_input.lower() in {"q", "quit", "exit"}:
            break

        # TODO 3: 把用户这句话放进 messages（用什么 role？）
        messages.append({"role": "user", "content": user_input})
        # TODO 4: 调用 chat(messages) 拿到回复，打印成「助手：xxx」
        reply = chat(messages)
        print(f"助手：{reply}")
        # TODO 5（今天的题眼）: 把模型的回复也放回 messages。
        #         不写这行会发生什么？先跑一遍看看，再写上它对比。
        messages.append({"role": "assistant", "content": reply})

if __name__ == "__main__":
    main()
