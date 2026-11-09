"""题型生成器。

每个 suite 暴露 ``generate(n, seed) -> list[dict]``，返回的每道题都是::

    {"id": "c03", "cat": "charops", "q": "题面", "answer": "标准答案", "check": {...}}

标准答案由脚本直接算出，不手写、不引用外部题库 —— 这是整套测试可信的前提：
模型就算「背」过经典题，也不可能背过一个随机种子生成的串。
"""

from . import arith, charops, constraint

SUITES = {
    "charops": charops.generate,
    "arith": arith.generate,
    "constraint": constraint.generate,
}

DESCRIPTIONS = {
    "charops": "逐字符多步变换（位置漂移、大小写、插入删除）",
    "arith": "链条算术（折扣/加价/税/单位/加权，两位小数）",
    "constraint": "指令硬约束（字数、JSON 字段、分隔符、禁 Markdown）",
}
