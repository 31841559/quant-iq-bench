"""字符多步变换：整套测试里唯一能稳定拉开差距的题型。

设计要点（都是踩过的坑）：

1. **必须写明「小写字母」**。只说「交换所有 b 和 c」时，模型会合理地理解成
   不区分大小写，把转大写后的 B/C 也换掉 —— 这是题面歧义，不是模型的错。
2. **必须写明下标起点和「此刻」**。位置操作会让下标随步骤漂移，
   「第 5 个字符」指的是当前字符串的第 5 个，不写清楚就没法判。
3. **必须过滤空操作**。五步里三步不改变字符串，测不出任何东西。
4. **长度要够**。短串太容易靠直觉蒙对，12~22 字符才有区分度。

实测这类题的 token 消耗是普通题的 15 倍，失败模式是「漏步骤、丢字符、错位」，
而且 `temperature=0` 下错法稳定复现 —— 说明是执行精度问题，不是采样抖动。
"""

from __future__ import annotations

import random

POOL = "abcdefgh"
LETTERS_FOR_DELETE = "abcdef"
LETTERS_FOR_SWAP = "abcd"
INSERT_CHARS = "xyz"


def _swap_pos(s: str, i: int, j: int) -> str:
    if max(i, j) > len(s):
        return s
    l = list(s)
    l[i - 1], l[j - 1] = l[j - 1], l[i - 1]
    return "".join(l)


def _insert_after(s: str, k: int, ch: str) -> str:
    return s if k > len(s) else s[:k] + ch + s[k:]


def _delete_pos(s: str, k: int) -> str:
    return s if k > len(s) else s[:k - 1] + s[k:]


KINDS = ["upper", "lower", "reverse", "swapcase", "dup", "take",
         "delete_letter", "swap_letter", "swap_pos", "insert_after", "delete_pos"]


def _apply(kind: str, s: str, rnd: random.Random) -> tuple[str, str]:
    """返回 (新串, 中文描述)。"""
    n = len(s)
    if kind == "upper":
        return s.upper(), "全部转为大写"
    if kind == "lower":
        return s.lower(), "全部转为小写"
    if kind == "reverse":
        return s[::-1], "反转整个字符串"
    if kind == "swapcase":
        return s.swapcase(), "所有字母大小写颠倒"
    if kind == "dup":
        return s + s, "原样复制一份接在后面（变成 s+s）"
    if kind == "take":
        k = rnd.randint(6, 10)
        return s[:k], f"只保留前 {k} 个字符"
    if kind == "delete_letter":
        ch = rnd.choice(LETTERS_FOR_DELETE)
        return s.replace(ch, ""), f"删除所有小写字母 {ch}"
    if kind == "swap_letter":
        a, b = rnd.sample(LETTERS_FOR_SWAP, 2)
        return (s.translate(str.maketrans(a + b, b + a)),
                f"交换所有小写字母 {a} 和 {b}（只换小写的）")
    if kind == "swap_pos" and n >= 6:
        i, j = rnd.sample(range(1, min(n, 12) + 1), 2)
        return _swap_pos(s, i, j), f"把此刻第 {i} 个和第 {j} 个字符互换（从 1 开始数）"
    if kind == "insert_after" and n >= 4:
        k = rnd.randint(1, min(n, 10))
        ch = rnd.choice(INSERT_CHARS)
        return _insert_after(s, k, ch), f"在此刻第 {k} 个字符之后插入小写字母 {ch}"
    if kind == "delete_pos" and n >= 5:
        k = rnd.randint(2, min(n, 10))
        return _delete_pos(s, k), f"删除此刻第 {k} 个字符（从 1 开始数）"
    # 退化分支：保证步骤永远可执行
    return s + "z", "末尾追加小写字母 z"


def generate(
    n: int = 30,
    seed: int = 0,
    steps: int = 5,
    min_len: int = 12,
    max_len: int = 22,
    min_effective: int = 3,
) -> list[dict]:
    """生成 n 道题。

    min_effective 控制「真正改变了字符串的步骤数」下限，低于它的题直接丢掉，
    否则会出现「五步里三步空转」的无效题。
    """
    rnd = random.Random(seed)
    out: list[dict] = []
    guard = 0
    while len(out) < n:
        guard += 1
        if guard > n * 400:
            raise RuntimeError("生成失败：约束太严，放宽 min_effective 或长度范围")

        s0 = "".join(rnd.choice(POOL) for _ in range(rnd.randint(min_len, max_len)))
        s = s0
        descs, effective = [], 0
        for kind in rnd.sample(KINDS, steps):
            before = s
            s, desc = _apply(kind, s, rnd)
            descs.append(desc)
            effective += s != before

        if effective < min_effective:
            continue
        if not (5 <= len(s) <= 40):
            continue

        body = "；".join(f"第{i + 1}步 {d}" for i, d in enumerate(descs))
        q = (f"初始字符串为 “{s0}”。严格按顺序执行以下 {steps} 步"
             f"（每步都在上一步的结果上操作，涉及「第几个字符」均按当时的字符串从 1 开始数）："
             f"{body}。\n最终字符串是什么？最后一行严格输出 `ANSWER: <最终字符串>`，不要加引号。")
        out.append({"id": f"c{len(out) + 1:03d}", "cat": "charops",
                    "q": q, "answer": s})
    return out
