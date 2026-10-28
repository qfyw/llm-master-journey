"""Day 1：让模型响一声。

跑之前：把 DeepSeek 的 key 填进 .env 的 API_KEY=
运行：python week1/day01_hello.py
"""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

# deepseek-flash 的峰值价（元 / token），用于估算这次对话花了多少钱
PRICE_IN = 2 / 1_000_000
PRICE_OUT = 8 / 1_000_000

load_dotenv()

api_key = os.getenv("API_KEY", "").strip()
if not api_key:
    sys.exit("API_KEY 是空的：打开 .env，把 key 粘到 API_KEY= 后面再保存")

client = OpenAI(
    api_key=api_key,
    base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
)
model = os.getenv("MODEL", "deepseek-flash")

resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "你是一个简洁的助手。"},
        {"role": "user", "content": "用一句话解释什么是大语言模型。"},
    ],
)

print(resp.choices[0].message.content)

usage = resp.usage
cost = usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT
print(
    f"\n[token] 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens} "
    f"｜ 约 {cost:.6f} 元（≈ 这样聊 1000 次 {cost * 1000:.2f} 元）"
)
