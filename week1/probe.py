"""检查 .env 里的 key / 接口地址 / 模型名是否可用。

运行：python week1/probe.py
只发一个极短的请求，失败时会告诉你是哪一环出了问题。
"""
import os
import sys

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

load_dotenv()

api_key = os.getenv("API_KEY", "").strip()
base_url = os.getenv("BASE_URL", "").strip()
model = os.getenv("MODEL", "").strip()


def mask(key: str) -> str:
    return f"{key[:6]}...{key[-4:]}" if len(key) >= 12 else "（太短，可能没复制全）"


if not api_key:
    sys.exit("API_KEY 是空的：先把 key 填进 .env，再跑这个脚本")

print(f"key      : {mask(api_key)}")
print(f"base_url : {base_url}")
print(f"model    : {model}\n")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=20.0,
    default_headers={
        # opencode go 要求客户端带稳定的会话 ID，并标明自己是谁
        "x-opencode-session": os.getenv("SESSION_ID", "probe"),
        "User-Agent": "llm-master-journey/0.1",
    },
)

# 1) 鉴权 + 连接 + 看服务端有哪些模型
#    有些中转站没实现 /models 接口，这一步失败不代表不能用，接着试对话
model_ids = []
try:
    model_ids = [m.id for m in client.models.list().data]
    print(f"[1/2] 鉴权/连接：通过，可用模型 {len(model_ids)} 个")
    print(f"      {', '.join(model_ids[:15])}")
except APIConnectionError as e:
    sys.exit(
        f"[1/2] 连不上 {base_url}\n"
        f"      网络或代理问题。如果这是 api.openai.com，需要能访问境外的网络。\n"
        f"      {e}"
    )
except APIStatusError as e:
    if e.status_code == 401:
        sys.exit(
            "[1/2] key 被拒绝（401）\n"
            "      三种可能：key 复制不全 / key 已被删除 / 这是网页版订阅账号，根本没有 API"
        )
    print(f"[1/2] /models 返回 {e.status_code}（中转站常见，忽略，直接试对话）")

# 2) 真正发一次对话，这一步决定能不能用
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "只回复两个字：通了"}],
    )
except APIConnectionError as e:
    sys.exit(f"[2/2] 对话时连不上：{e}")
except APIStatusError as e:
    hint = {
        400: "请求格式或模型名不被接受",
        401: "key 无效",
        402: "余额不足",
        403: "没有权限，或地区限制",
        404: "模型名或接口路径不存在",
        429: "限流或额度用完",
    }.get(e.status_code, "")
    detail = e.message
    if "MissingSessionID" in str(detail):
        hint = "缺少 x-opencode-session 头（检查 .env 里的 SESSION_ID）"
    sys.exit(f"[2/2] 对话失败 {e.status_code} {hint}：{detail}")
except Exception as e:  # noqa: BLE001 - 把未知错误也翻译成人话
    sys.exit(f"[2/2] 未预期的错误：{type(e).__name__}: {e}")

print(f"[2/2] 对话：通过 → {resp.choices[0].message.content!r}")

if model_ids and model not in model_ids:
    print(f"      注意：{model} 不在上面列表里，但调用成功了（有些服务做了别名映射）")
print("\nDay 1 及格线达成，可以回到计划继续了。")
