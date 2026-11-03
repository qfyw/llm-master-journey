"""Day 5：错误处理 + 成本统计——把「世界会坑你」写进代码。

运行：python week1/cost_log.py
过关标准：
① 把 .env 的 BASE_URL 换成断线假地址 → 程序不崩：重试 3 次后礼貌退出
   （试完必须改回来！）
② 每轮对话结束打印本轮花费；输入 q 退出时打印全程总账单

三块新东西：
· try/except——保险丝：try 身上装「想干的事」，except 身上装「出事别崩，怎么办」。
  没有 try 的程序遇到意外会当场摔死、甩一屏天书。
· 重试——但先分类：能修的错（网络抖动、429 限流）睡 2 秒再试；
  修不好的错（401 key 错）重试不叫坚持，叫固执。
· 账本——累加器四连（次数、输入 token、输出 token、花费），退出时结算。
  Day 1 那一行 [token] 今天正式升级成账本。
"""
import os
import time

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    default_headers={
        "x-opencode-session": os.getenv("SESSION_ID", "costlog"),
        "User-Agent": "llm-master-journey/0.1",
    },
)
model = os.getenv("MODEL", "deepseek-v4.1-flash")

PRICE_IN = 2 / 1_000_000     # deepseek-flash 官方峰值价（元/token），参考账
PRICE_OUT = 8 / 1_000_000


# TODO 1：把下面注释里的函数逐行敲成真代码（try/except 是今天的新语法，
# 边敲边读注释）——
#
# def ask(messages: list[dict]):
#     """同步发一次请求；最多试 3 次；全失败返回 None（调用方收拾残局）。"""
#     for attempt in range(3):
#         try:
#             resp = client.chat.completions.create(
#                 model=model,
#                 messages=messages,
#             )
#             return resp
#         except (APIConnectionError, APIStatusError) as e:
#             # 翻译表：状态码 → 人话。两种错误的体质不同：
#             #   断网（APIConnectionError）没有状态码，只是"没通"
#             #   被拒（APIStatusError）有状态码：401/402/404/429...
#             TRANSLATE = {
#                 401: "key 无效——重试也没用，先修配置",
#                 402: "余额不足——去充值",
#                 404: "地址或模型名不对",
#                 429: "限流——睡一下再试是对的",
#             }
#             hint = TRANSLATE.get(getattr(e, "status_code", None), "网络问题或未知错误")
#             # .get(键, 保底) 的第二个参数就是 Day 2 学过的 os.getenv 思维：
#             # 拿不到就给保底值，不炸
#             print(f"[第 {attempt + 1} 次失败] {type(e).__name__}：{hint}（{e}）", flush=True)
#             time.sleep(2)
#     return None
def ask(messages: list[dict]):
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return resp
        except (APIConnectionError,APIStatusError) as e:
            TRANSLATE = {
                401:"key无效——重试也没用，先修配置",
                402: "余额不足——去充值",
                404: "地址或模型名不对",
                429: "限流——睡一下再试是对的",
            }
            hint = TRANSLATE.get(getattr(e, "status_code", None),"网络问题或未知错误")
            print(f"[第 {attempt + 1} 次失败] {type(e).__name__}：{hint}（{e}）", flush=True)
            time.sleep(2)
    return None


def main() -> None:
    messages = [{"role": "system", "content": "你是一个简洁的中文助手。"}]
    calls = 0
    in_tokens = 0
    out_tokens = 0
    total_cost = 0.0
    print("输入 q 退出")
    while True:
        user_input = input("\n你：").strip()
        if not user_input or user_input.lower() in {"q", "quit", "exit"}:
            break

        messages.append({"role": "user", "content": user_input})

        resp = ask(messages)
        if resp is None:
            print("助手联系不上，本轮没有回复。")
            continue

        # TODO 2：三件旧活——取正文、打印、把台词写回剧本（昨天你会的全套）
        reply = resp.choices[0].message.content
        print(f"助手：{reply}")
        messages.append({"role": "assistant", "content": reply})

        # TODO 3：记账（累加器四连）+ 本轮结算
        #   usage = resp.usage
        #   round_cost = usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT
        #   四个累加器各进账多少？再说一句本轮的账：
        #   print(f"[账本] 累计 {calls} 次请求 ｜ 本轮 输入 {..} / 输出 {..} ｜ 参考价 .. 元（累计 .. 元）")
        usage = resp.usage
        round_cost = usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT
        calls = calls + 1
        in_tokens = in_tokens + usage.prompt_tokens
        out_tokens = out_tokens + usage.completion_tokens
        total_cost = total_cost + round_cost
        print(f"[账本] 累计 {calls} 次 ｜ 本轮 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens}"
              f" ｜ 本轮约 {round_cost:.6f} 元，累计约 {total_cost:.6f} 元")
    # TODO 4：总账单（退出时结算）
    #   print(本次会话：N 次请求 / 输入 X / 输出 Y / 参考总价 Z 元)
    print(f"本次会话：{calls} 次请求 ｜ 输入 {in_tokens} / 输出 {out_tokens} ｜ 参考总价 {total_cost:.6f} 元")

if __name__ == "__main__":
    main()
