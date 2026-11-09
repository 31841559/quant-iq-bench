"""判分器。

整套测试里最容易出错的就是这里。教训很直接：
**判分器不适配模型的输出风格时，你测的是判分器，不是模型。**

实际踩过的坑：
- 模型用 LaTeX 输出 `\\boxed{\\dfrac{99}{100}}`，正则只认文本 `99/100` → 误判为错
- 模型输出 `## 答案：B 说真话`，判分只认开头就是字母 → 误判为错
- 十六进制答案 `DB4` 被当成整数解析 → 误判为错
- 「交换所有 b 和 c」被模型理解成不分大小写，题面本身有歧义 → 该判题目错

所以这里的策略是：能归一化的先归一化，能程序化校验的绝不靠字符串相等。

自带自检：`python -m bench.scoring --self-check`
"""

from __future__ import annotations

import json
import re

_WRAP = "\"'`“”‘’*。 ，,：:"
_ANSWER_PREFIX = re.compile(r"^\s*(?:答案|ANSWER)\s*[:：]\s*", re.I)
_FENCE = re.compile(r"^```(?:json|python|text)?\s*|\s*```$", re.M)
_LATEX_FRAC = re.compile(r"\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}")


def normalize(text: str) -> str:
    """去掉包裹符号、代码围栏、`ANSWER:` 前缀和多余空白。"""
    s = str(text or "")
    s = _FENCE.sub("", s).strip()
    s = _ANSWER_PREFIX.sub("", s)
    return s.strip(_WRAP)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def _numbers(text: str) -> list[float]:
    s = normalize(text).replace(",", "").replace("，", "")
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]


def _hanzi(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fa5]", normalize(text))


def _json_load(text: str):
    s = _FENCE.sub("", normalize(text)).strip()
    try:
        return json.loads(s)
    except Exception:
        # 模型偶尔会包一层讲解，退一步抓第一个 JSON 结构
        m = re.search(r"(\[.*\]|\{.*\})", s, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None


def judge(record: dict, got: str) -> bool:
    """判一条答案。record 需含 cat，可选 check（结构化校验描述）。"""
    cat = record.get("cat", "")
    std = str(record.get("answer", ""))
    check = record.get("check") or {}
    t = check.get("type")

    if cat == "charops":
        # 逐字符结果：不许有任何偏差，但允许外层空白/引号
        return _compact(got) == _compact(std)

    if cat == "arith":
        ns = _numbers(got)
        if not ns:
            return False
        try:
            return abs(ns[-1] - float(std)) < 0.005
        except ValueError:
            return False

    # ---- 指令硬约束：一律程序化校验 ----
    if t == "exact":
        return _compact(got) == _compact(std)

    if t == "hanzi_exact":
        h = _hanzi(got)
        return len(h) == check["n"] and check.get("forbid", "\0") not in normalize(got)

    if t == "char_times_in_range":
        s = normalize(got)
        return (s.count(check["char"]) == check["times"]
                and 0 < len(_hanzi(s)) <= check["max_hanzi"])

    if t == "json_array_of_objects":
        d = _json_load(got)
        if not isinstance(d, list) or len(d) != check["array_len"]:
            return False
        keys = sorted(check["keys"])
        return all(isinstance(x, dict) and sorted(x.keys()) == keys
                   and all(isinstance(v, str) for v in x.values()) for x in d)

    if t == "json_list":
        return _json_load(got) == check["values"]

    if t == "upper_csv":
        raw = normalize(got)
        parts = [p.strip() for p in raw.rstrip(".").split(",")]
        return (len(parts) == check["n"]
                and all(re.fullmatch(r"[A-Z][A-Z' \-]*", p) for p in parts)
                and "。" not in raw and "." not in raw)

    if t == "digits_only":
        return bool(re.fullmatch(r"\d+", normalize(got)))

    if t == "lines":
        lines = [x.strip() for x in normalize(got).splitlines() if x.strip()]
        want = [x.strip() for x in std.splitlines() if x.strip()]
        return lines == want

    if t == "no_markdown":
        s = normalize(got)
        banned = ("#", "*", "`", "```", "- ", "1. ")
        return bool(s) and not any(b in s for b in banned)

    raise ValueError(f"未知的判分类型：cat={cat!r} check={check!r}")


def mcnemar(b_only_a: int, a_only_b: int) -> float:
    """McNemar 精确检验（双侧）。返回 p 值。

    只关心「配对不一致」的格子：A 对 B 错 = b，A 错 B 对 = c。
    样本量小时用二项分布精确计算，不搞卡方近似。
    """
    n = b_only_a + a_only_b
    if n == 0:
        return 1.0
    k = min(b_only_a, a_only_b)
    # 双侧：P(X<=k) * 2，X ~ Bin(n, 0.5)
    tail = sum(_comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _comb(n: int, k: int) -> int:
    from math import comb
    return comb(n, k)


# ---------------- 自检 ----------------

_SELF_CHECK = [
    ("charops", {"cat": "charops", "answer": "CAEADEAAC"},
     ["CAEADEAAC", "ANSWER: CAEADEAAC", "`CAEADEAAC`", " CAEADEAAC\n"],
     ["CAEADAEAC", "", "CAEADEAACX"]),
    ("arith", {"cat": "arith", "answer": "68047.50"},
     ["68047.50", "68047.5", "最终售价 68047.50 元", "$68,047.5"],
     ["68047", "68047.49", "不知道"]),
    ("latex_frac", {"cat": "instr", "answer": "", "check": {"type": "digits_only"}},
     ["7", "7\n"], ["七天", "7 天"]),
    ("exact", {"cat": "instr", "answer": "CEBEEEBB", "check": {"type": "exact"}},
     ["CEBEEEBB", "ANSWER: CEBEEEBB"], ["CEBEEBB"]),
    ("hanzi", {"cat": "instr", "answer": "",
               "check": {"type": "hanzi_exact", "n": 5, "forbid": "的"}},
     ["青金桔很甜"], ["青金桔酸甜可了", "青金桔的酸甜可"]),
    ("json", {"cat": "instr", "answer": "",
              "check": {"type": "json_array_of_objects", "keys": ["name", "code"],
                        "array_len": 2}},
     ['[{"name":"海口","code":"HK"},{"name":"三亚","code":"SY"}]',
      '```json\n[{"name":"海口","code":"HK"},{"name":"三亚","code":"SY"}]\n```'],
     ['{"name":"海口"}']),
    ("csv", {"cat": "instr", "answer": "", "check": {"type": "upper_csv", "n": 3}},
     ["ORANGE, LEMON, LIME"], ["orange, lemon, lime", "ORANGE, LEMON, LIME."]),
    ("lines", {"cat": "instr", "answer": "海南\n广东\n广西", "check": {"type": "lines"}},
     ["海南\n广东\n广西"], ["海南、广东、广西", "1. 海南\n2. 广东\n3. 广西"]),
]


def self_check() -> int:
    bad = 0
    for name, rec, goods, bads in _SELF_CHECK:
        for g in goods:
            if not judge(rec, g):
                print(f"  ✗ [{name}] 应判对却判错: {g!r}")
                bad += 1
        for b in bads:
            if judge(rec, b):
                print(f"  ✗ [{name}] 应判错却判对: {b!r}")
                bad += 1
    total = sum(len(g) + len(b) for _, _, g, b in _SELF_CHECK)
    print(f"判分器自检：{total - bad}/{total} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    import sys
    sys.exit(self_check())
