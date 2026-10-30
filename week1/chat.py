"""Day 3：流式输出——让回复一个字一个字蹦出来。

运行：python week1/chat.py
过关标准：回复像打字机一样逐字往外蹦。

今天改的只有 chat() 内部，main() 和昨天一模一样。
这就是昨天架构的回报：状态归 main 管，"怎么说"归 chat 管。

核心认知（昨天你自己悟的）：模型本来就是一个字一个字写剧本。
昨天是 SDK 等它全部写完、装订成 resp 才交卷；
今天是改成边写边收——服务器每写一个字就快递一个字。
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
    """流式版：边生成边打印，最后仍然 return 完整回复文本。

    返回值没变——main 还要用它写回剧本；变的是"怎么给你看"。
    """
    full = ""  # 累加器：把蹦出来的字一块块攒成完整台词
    print("助手：", end="", flush=True)

    # TODO 1（一个参数的事）：在下面 create 的参数末尾加一行 stream=True
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
    )

    # TODO 2（逐块收货）：把下面这五行从注释敲成真代码——
    #   for piece in stream:
    #       text = piece.choices[0].delta.content
    #       if text is None:
    #           continue
    #       print(text, end="", flush=True)
    #       full = full + text
    # 边敲边记三个新知识：
    #   · piece.choices[0].delta —— 注意是 delta 不是 message！
    #     delta = 这一集里"新增的字"，不是完整台词
    #   · end="" —— print 打完默认自动换行；不让它换行，字才连成一句话
    #   · flush=True —— 强制立刻上屏；没有它终端会攒一攒再吐，打字机就卡死了

    # TODO 3（收尾）：字蹦完之后，print() 单独一行换行，然后 return full
    # （full 交给 main，它要按昨天的 TODO 5 写回剧本）

def main() -> None:
    messages = [
        {"role": "system", "content": "你是一个简洁的中文助手。"},
    ]
    print("输入 q 退出")
    while True:
        user_input = input("\n你：").strip()
        if not user_input or user_input.lower() in {"q", "quit", "exit"}:
            break

        messages.append({"role": "user", "content": user_input})
        reply = chat(messages)  # 打字机在这一行的里面现场表演
        # 昨天的 TODO 5 原样保留：模型说过的话写回剧本
        messages.append({"role": "assistant", "content": reply})
        # 注意：昨天这里的 print(f"助手：{reply}") 搬进 chat() 里去了——
        # 字是在流出来的时候打的，不是等回来以后再打印


if __name__ == "__main__":
    main()
