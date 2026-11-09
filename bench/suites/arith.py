"""链条算术：测的是「多步数值推理 + 精度保持」。

这类题量化几乎不掉点（实测两边都是满分），放进来是当对照组用的：
如果一个模型在这里也崩，说明问题不在量化，而在服务配置（最常见就是
没开思考模式，模型跳过推理直接猜数）。

所有答案都是两位小数，由 Python 直接算出。
"""

from __future__ import annotations

import random

CATEGORIES = ["markup", "double_discount", "tax_fee", "unit_price",
              "weighted_mix", "growth", "three_stage", "fx_fee"]


def _one(kind: str, rnd: random.Random) -> tuple[str, float]:
    if kind == "markup":
        cost = rnd.randint(200, 900)
        up = rnd.choice([15, 20, 25, 30, 35, 40])
        off = rnd.choice([10, 15, 20, 25])
        v = cost * (1 + up / 100) * (1 - off / 100)
        q = (f"某商品成本 {cost} 元。先按成本加价 {up}% 定价，再按定价打 {100 - off} 折出售。"
             f"最终售价是多少元？保留两位小数，只回答数字。")

    elif kind == "double_discount":
        price = rnd.randint(300, 1200)
        d1 = rnd.choice([10, 15, 20])
        d2 = rnd.choice([5, 10, 15])
        v = price * (1 - d1 / 100) * (1 - d2 / 100)
        q = (f"一件商品标价 {price} 元。先降价 {d1}%，在此基础上再降价 {d2}%。"
             f"最终价格是多少元？保留两位小数，只回答数字。")

    elif kind == "tax_fee":
        base = rnd.randint(500, 3000)
        r1 = rnd.choice([3, 5, 6, 9, 13])
        r2 = rnd.choice([2, 4, 7])
        v = base * (1 + r1 / 100) * (1 + r2 / 100)
        q = (f"某服务不含税价 {base} 元。先加收 {r1}% 的增值税，再对含税总额加收 {r2}% 的平台服务费。"
             f"最终应付多少元？保留两位小数，只回答数字。")

    elif kind == "unit_price":
        n = rnd.randint(20, 90)
        g = rnd.choice([350, 420, 500, 680])
        price = rnd.choice([12.5, 18.8, 24.6, 33.4])
        v = n * g / 1000 * price
        q = (f"某批货共 {n} 箱，每箱 {g} 克。按每公斤 {price} 元计价，总价是多少元？"
             f"保留两位小数，只回答数字。")

    elif kind == "weighted_mix":
        a1, p1 = rnd.randint(20, 60), rnd.randint(40, 80)
        a2, p2 = rnd.randint(20, 60), rnd.randint(50, 90)
        v = (a1 * p1 + a2 * p2) / (a1 + a2)
        q = (f"把 {a1} 公斤单价 {p1} 元的原料与 {a2} 公斤单价 {p2} 元的原料混合。"
             f"混合后的平均单价是多少元/公斤？保留两位小数，只回答数字。")

    elif kind == "growth":
        start = rnd.randint(1000, 5000)
        g1 = rnd.choice([8, 12, 15, -6, -9])
        g2 = rnd.choice([5, 10, 20, -7])
        v = start * (1 + g1 / 100) * (1 + g2 / 100)
        q = (f"某项收入第一年变化 {g1:+d}%，第二年在第一年基础上再变化 {g2:+d}%。"
             f"若初始为 {start} 元，两年后是多少元？保留两位小数，只回答数字。")

    elif kind == "three_stage":
        cost = rnd.randint(100, 500)
        up = rnd.choice([30, 40, 50, 60])
        off = rnd.choice([10, 20, 25])
        cut = rnd.choice([5, 10, 15])
        v = cost * (1 + up / 100) * (1 - off / 100) * (1 - cut / 100)
        q = (f"进货价 {cost} 元。先加价 {up}% 作为标价，再打 {100 - off} 折，"
             f"最后在成交价上再让利 {cut}%。实际成交价是多少元？保留两位小数，只回答数字。")

    else:  # fx_fee
        amount = rnd.randint(2000, 20000)
        rate = rnd.choice([0.0482, 0.0513, 0.0476, 0.0531])
        fee = rnd.choice([0.5, 1.0, 1.5])
        v = amount * rate * (1 - fee / 100)
        q = (f"用 {amount} 元人民币按汇率 {rate} 换汇，再扣除 {fee}% 的手续费。"
             f"最终到账多少外币？保留两位小数，只回答数字。")

    return q, float(f"{v:.2f}")


def generate(n: int = 20, seed: int = 0) -> list[dict]:
    rnd = random.Random(seed)
    out: list[dict] = []
    seen: set[str] = set()
    guard = 0
    while len(out) < n:
        guard += 1
        if guard > n * 200:
            raise RuntimeError("生成失败：题面重复率过高")
        q, v = _one(rnd.choice(CATEGORIES), rnd)
        if q in seen:
            continue
        seen.add(q)
        out.append({"id": f"a{len(out) + 1:03d}", "cat": "arith",
                    "q": q, "answer": f"{v:.2f}"})
    return out
