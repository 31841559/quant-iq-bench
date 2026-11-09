"""指令硬约束：测「听话」，不是测「聪明」。

一个模型可能算得全对，却在「恰好 14 个汉字」「只输出数字」「每行一个」上翻车。
这类失败在业务里最贵 —— 解析器拿到一坨 Markdown 就崩了。

所有校验都程序化，不靠肉眼比对。
"""

from __future__ import annotations

import random

TOPICS = ["海南青金桔", "云南小粒咖啡", "赣南脐橙", "广西沃柑", "福建蜜柚"]
REGIONS = [("海南", "广东", "广西"), ("湖南", "湖北", "江西"),
           ("江苏", "浙江", "安徽"), ("山东", "山西", "河北")]
PROVINCE_CITIES = {
    "海南": [("海口", "HK"), ("三亚", "SY"), ("儋州", "DZ")],
    "广东": [("广州", "GZ"), ("深圳", "SZ"), ("珠海", "ZH")],
    "浙江": [("杭州", "HZ"), ("宁波", "NB"), ("温州", "WZ")],
}
FRUIT_GROUPS = ["柑橘类水果", "热带水果", "核果类水果"]


def generate(n: int = 15, seed: int = 0) -> list[dict]:
    rnd = random.Random(seed)
    out: list[dict] = []

    def add(q: str, answer: str, check: dict) -> None:
        out.append({"id": f"i{len(out) + 1:03d}", "cat": "instr",
                    "q": q, "answer": answer, "check": check})

    templates = ["reverse", "hanzi", "json", "csv", "char_times",
                 "digits", "lines", "no_markdown"]

    guard = 0
    while len(out) < n:
        guard += 1
        if guard > n * 50:
            break
        kind = templates[len(out) % len(templates)]

        if kind == "reverse":
            s = rnd.choice(TOPICS) + rnd.choice(["种植基地", "分拣中心", "冷链仓"])
            add(f"把字符串「{s}」倒序输出。只输出结果，不要解释。",
                s[::-1], {"type": "exact"})

        elif kind == "hanzi":
            topic = rnd.choice(TOPICS)
            k = rnd.randint(12, 18)
            add(f"用一句话介绍{topic}，要求：整句必须恰好包含 {k} 个汉字（不计标点），"
                f"且不得出现「的」字。只输出这一句话，不要解释。",
                "", {"type": "hanzi_exact", "n": k, "forbid": "的"})

        elif kind == "json":
            prov = rnd.choice(list(PROVINCE_CITIES))
            add(f"以 JSON 数组输出{prov}的三个地级市，每个对象字段必须恰好是 name 和 code，"
                f"值均为字符串。只输出 JSON，不要 markdown 代码块，不要解释。",
                "", {"type": "json_array_of_objects",
                     "keys": ["name", "code"], "array_len": 3})

        elif kind == "csv":
            group = rnd.choice(FRUIT_GROUPS)
            add(f"用英文输出三种{group}的名称，全部字母大写，用逗号加空格分隔，"
                f"不要句号，不要解释。", "", {"type": "upper_csv", "n": 3})

        elif kind == "char_times":
            topic = rnd.choice(TOPICS)
            add(f"写一句话描述{topic}的味道，整句不超过 20 个汉字，且必须恰好出现两次「酸」字。"
                f"只输出这句话。", "",
                {"type": "char_times_in_range", "char": "酸", "times": 2, "max_hanzi": 20})

        elif kind == "digits":
            a, b = rnd.randint(20, 90), rnd.randint(20, 90)
            add(f"计算 {a} 加 {b} 等于多少？要求：只输出阿拉伯数字，不要任何文字、标点或单位。",
                str(a + b), {"type": "digits_only"})

        elif kind == "lines":
            trio = rnd.choice(REGIONS)
            add(f"列出「{'」「'.join(trio)}」三个地区，每行一个，行首不加任何符号或编号，"
                f"不要解释。", "\n".join(trio), {"type": "lines"})

        else:  # no_markdown
            add("用不超过 40 个汉字的纯文本说明冷链运输对水果保鲜的作用。"
                "不得使用任何 Markdown 标记：不要井号标题、不要星号加粗、不要反引号、"
                "不要列表符号或编号。只输出正文。", "", {"type": "no_markdown"})

    return out
