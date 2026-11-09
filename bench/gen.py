"""出题 CLI。

设计上有一条硬规则：**默认不回显答案**。

因为这套测试要能拿来做「盲测对照」—— 人（或另一个模型）先答题、模型后跑，
双方都没见过标准答案，测试才站得住。所以答案只写进文件，不打印。

    # 出题（只看题面，不看答案）
    python -m bench.gen --suite charops --n 30 --seed 20261109 \
        --out data/questions/charops-20261109.json

    # 需要核对答案时才加 --show-answers
    python -m bench.gen --suite arith --n 20 --seed 1 --show-answers
"""

from __future__ import annotations

import argparse
import json
import os

from .suites import DESCRIPTIONS, SUITES


def main() -> None:
    ap = argparse.ArgumentParser(description="生成测试题目")
    ap.add_argument("--suite", required=True, choices=sorted(SUITES))
    ap.add_argument("--n", type=int, default=20, help="题目数量")
    ap.add_argument("--seed", type=int, default=0, help="随机种子（决定题目内容）")
    ap.add_argument("--steps", type=int, default=5, help="charops 专用：变换步数")
    ap.add_argument("--min-len", type=int, default=12, help="charops 专用：初始串最短长度")
    ap.add_argument("--max-len", type=int, default=22, help="charops 专用：初始串最长长度")
    ap.add_argument("--out", help="题目输出路径（含答案）")
    ap.add_argument("--blind-out", help="另存一份不含答案的题面，用于盲测")
    ap.add_argument("--show-answers", action="store_true", help="在终端回显答案（会破坏盲测）")
    args = ap.parse_args()

    kwargs = {"n": args.n, "seed": args.seed}
    if args.suite == "charops":
        kwargs.update(steps=args.steps, min_len=args.min_len, max_len=args.max_len)

    items = SUITES[args.suite](**kwargs)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)

    if args.blind_out:
        blind = [{k: v for k, v in x.items() if k != "answer"} for x in items]
        os.makedirs(os.path.dirname(os.path.abspath(args.blind_out)), exist_ok=True)
        with open(args.blind_out, "w", encoding="utf-8") as f:
            json.dump(blind, f, ensure_ascii=False, indent=1)

    print(f"[{args.suite}] {DESCRIPTIONS[args.suite]}")
    print(f"生成 {len(items)} 题，seed={args.seed}"
          + (f"，已写入 {args.out}" if args.out else "")
          + (f"，盲测题面写入 {args.blind_out}" if args.blind_out else ""))
    if not args.show_answers:
        print("（答案未回显，需要时加 --show-answers）\n")

    for x in items:
        line = f"[{x['id']}|{x['cat']}] {x['q']}"
        if args.show_answers:
            line += f"\n    -> {x['answer']!r}"
        print(line)


if __name__ == "__main__":
    main()
