"""Day 4：结构化输出——让模型按指定的 JSON 格式交作业。

运行：python week1/structured.py
过关标准：程序自己解析出任务列表并打印，全程不靠肉眼读模型的文字。

今天是把昨天的规则变成代码：
    输出给人实时看 → 流式（chat.py）
    输出给程序处理 → 同步（今天的 structured.py）

三个新东西：
· json.loads(字符串)：把 JSON 文本变成 Python 的字典/列表（str → dict）
· repr() 体检线：把字符串原样照出来，模型偷藏的 ``` 围栏无处可逃
· 累加器数字版：昨天 full 攒字符串，今天 total 攒分钟数——同一个套路
"""
import json          # 内置库，免费。注意：千万别把变量起名叫 json，会撞车
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    default_headers={
        "x-opencode-session": os.getenv("SESSION_ID", "structured"),
        "User-Agent": "llm-master-journey/0.1",
    },
)
model = os.getenv("MODEL", "deepseek-v4.1-flash")
# 配置区每个脚本复制一份；Day 6 组装 CLI 时会抽成公共模块，别嫌重复

system_prompt = """你是学习计划拆解器。只输出 JSON，不要输出任何其他文字。
格式：{"tasks": [{"name": "任务名", "minutes": 分钟数}]}"""

user_plan = "健身 1 小时，然后学 40 分钟流式输出，最后背 30 个单词。"

# TODO 1：同步调用（你已经敲过两回的搬运）
#   resp = client.chat.completions.create(
#       model=model,
#       messages=[
#           {"role": "system", "content": system_prompt},
#           {"role": "user", "content": user_plan},
#       ],
#   )
resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role":"system","content":system_prompt},
        {"role":"user","content":user_plan},
    ],
)
# TODO 2：取正文存进 text（昨天那条链路，同步版比流式好认：
#   没有 delta，直接 text = resp.choices[0].message.content）
text = resp.choices[0].message.content
#   print(repr(text))    # 体检线：repr 把字符串原样照出来（```、\n 全显形）
                     # 程序稳定跑通后，把这一行注释掉

# TODO 3：让 text 变成字典：data = json.loads(...)
#   试试还没判断 text 什么形状？先跑 TODO 2 的体检线看看它到底给了你什么
data = json.loads(text)
# TODO 4（打印 + 累加）：
#   total = 0                                   ← 放在 for 前面
#   for task in data["tasks"]:
#       print(f"- {task['name']}：{task['minutes']} 分钟")
#       total = total + task["minutes"]
#   print(f"今天共 {len(data['tasks'])} 项任务，合计 {total} 分钟")
total = 0
for task in data["tasks"]:
    print(f"- {task['name']}:{task['minutes']}分钟")
    total = total + task["minutes"]
print(f"今天共 {len(data['tasks'])} 项任务，合计 {total} 分钟")