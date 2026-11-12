"""Day 13：账单汇总——把本机账本变成一份可提交的「派生数据」。

用法：
    python week2/bill_summary.py                                      # 真账本 → week2/bill-summary.md
    python week2/bill_summary.py week2/usage.example.jsonl week2/bill-summary.example.md
                                                                      # 假数据试跑，不碰真账单

为什么提交汇总、不提交原始账本：
· usage.jsonl 是运行时数据：时间戳、调用习惯都在里面，已被 .gitignore 排除；
· bill-summary.md 只保留「日期 / 次数 / token / 参考花费」这类聚合结果，可以公开。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "usage.jsonl"
OUT_FILE = Path(__file__).parent / "bill-summary.md"


def load_rows(path: Path) -> list[dict]:
    """读 jsonl 账本；文件不存在就当空账本。"""
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict], key_fn) -> dict:
    """按 key_fn(row) 分组累计：calls / input / output / cost。

    key_fn 是一个函数：传 lambda row: row["label"] 就按调用点汇总，
    传 lambda row: row["ts"][:10] 就按日期汇总。
    """
    # TODO 1（六行）：把 rows 聚合成分组字典。
    #   目标形状：{"2026-11-10": {"calls": 3, "input": 786, "output": 223, "cost": 0.003356}, ...}
    #   提示：
    #   groups = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0})
    #   for row in rows:
    #       g = groups[key_fn(row)]
    #       g["calls"] += 1
    #       g["input"] += row["input"]
    #       ...（output、cost 同理）
    #   最后 return dict(groups)
    pass


def render_table(title: str, groups: dict, first_col: str) -> str:
    """把一组汇总渲染成 markdown 表：表头 + 每个分组一行 + 合计一行。"""
    # TODO 2（十行左右）：拼表格。
    #   表头：  | 键 | 调用 | 输入 | 输出 | 参考花费（元） |
    #   对齐：  |---:|---:|---:|---:|---:|
    #   数据：  | 2026-11-10 | 3 | 786 | 223 | 0.003356 |
    #   合计：把每组 calls/input/output/cost 再加一遍；花费保留 6 位小数。
    #   提示：lines 列表 + "\n".join(lines)；行内花费 f"{cost:.6f}"。
    pass


def render(rows: list[dict]) -> str:
    """按日期 + 按调用点各出一张表。"""
    by_date = summarize(rows, lambda row: row["ts"][:10])
    by_label = summarize(rows, lambda row: row["label"])
    return ("# 账单汇总（派生数据）\n\n"
            "> 由 `week2/bill_summary.py` 从本机 `usage.jsonl` 生成；原始账本不入库。\n\n"
            + render_table("按日期", by_date, "日期") + "\n\n"
            + render_table("按调用点", by_label, "调用点"))


def main() -> None:
    usage_file = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_FILE
    out_file = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_FILE

    rows = load_rows(usage_file)
    if not rows:
        print(f"没有账本数据：{usage_file}")
        print("先用假数据试跑：python week2/bill_summary.py week2/usage.example.jsonl week2/bill-summary.example.md")
        return

    markdown = render(rows)
    out_file.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\n已写入 {out_file}")


if __name__ == "__main__":
    main()
