"""汇总报告：单次跑测统计，或两次跑测的配对比较。

配对比较用 McNemar 精确检验，而不是直接比百分比 —— 因为「差 3 题」
在 n=24 时完全可能是噪声，直接报「差 12 个百分点」会误导人。

    # 单次
    python -m bench.report --run data/results/local.json

    # 两次配对（例如 3bit 跑测 vs 官方跑测）
    python -m bench.report --run data/results/local.json --ref data/results/official.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from .scoring import mcnemar


def _load(path: str) -> dict[str, dict]:
    return {r["id"]: r for r in json.load(open(path, encoding="utf-8"))}


def _table(rows: list[dict], label: str) -> tuple[int, int]:
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["cat"]].append(r)
    print(f"\n{label}")
    print(f"{'题型':12s} {'正确':>8s} {'占比':>6s} {'均token':>8s} {'均秒':>6s}")
    for cat in sorted(by_cat):
        sub = by_cat[cat]
        ok = sum(r["ok"] for r in sub)
        tok = sum(r["tokens"] for r in sub) / len(sub)
        sec = sum(r["seconds"] for r in sub) / len(sub)
        print(f"{cat:12s} {ok:4d}/{len(sub):<3d} {ok / len(sub) * 100:5.0f}% "
              f"{tok:8.0f} {sec:6.1f}")
    ok = sum(r["ok"] for r in rows)
    tok = sum(r["tokens"] for r in rows)
    sec = sum(r["seconds"] for r in rows) or 1e-9
    print(f"{'合计':12s} {ok:4d}/{len(rows):<3d} {ok / len(rows) * 100:5.1f}% "
          f"{tok / len(rows):8.0f} {sec / len(rows):6.1f}")
    print(f"总 token {tok}，总耗时 {sec:.0f}s，吞吐 {tok / sec:.0f} tok/s")
    return ok, len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="汇总跑测结果")
    ap.add_argument("--run", required=True, help="待评估的结果文件")
    ap.add_argument("--ref", help="参照结果文件（做配对比较）")
    args = ap.parse_args()

    run = _load(args.run)
    rows = list(run.values())
    ok, n = _table(rows, f"== {args.run} ==")

    fails = [r for r in rows if not r["ok"]]
    if fails:
        print(f"\n失败 {len(fails)} 题：")
        for r in fails:
            flag = f" {r['flags']}" if r.get("flags") else ""
            print(f"  {r['id']:5s} {r['cat']:10s} std={str(r['std'])[:28]!r:32s} "
                  f"got={str(r['ans'])[:28]!r:32s} {r['tokens']}tok {r['seconds']}s{flag}")

    if not args.ref:
        return

    ref = _load(args.ref)
    common = sorted(set(run) & set(ref))
    print(f"\n== 配对比较：{len(common)} 道重叠题 ==")
    print(f"{'题型':12s} {'本侧':>6s} {'参照':>6s} {'仅本侧对':>9s} {'仅参照对':>9s}")
    by_cat: dict[str, list[str]] = defaultdict(list)
    for i in common:
        by_cat[run[i]["cat"]].append(i)

    tot_b = tot_c = 0
    for cat in sorted(by_cat):
        ids = by_cat[cat]
        a = sum(run[i]["ok"] for i in ids)
        b = sum(ref[i]["ok"] for i in ids)
        b_only = sum(1 for i in ids if run[i]["ok"] and not ref[i]["ok"])
        c_only = sum(1 for i in ids if ref[i]["ok"] and not run[i]["ok"])
        tot_b += b_only
        tot_c += c_only
        print(f"{cat:12s} {a:3d}/{len(ids):<3d} {b:3d}/{len(ids):<3d} "
              f"{b_only:9d} {c_only:9d}")

    a = sum(run[i]["ok"] for i in common)
    b = sum(ref[i]["ok"] for i in common)
    print(f"{'合计':12s} {a:3d}/{len(common):<3d} {b:3d}/{len(common):<3d} "
          f"{tot_b:9d} {tot_c:9d}")

    p = mcnemar(tot_b, tot_c)
    print(f"\n不一致配对 {tot_b + tot_c} 组，McNemar 精确检验 p = {p:.4f}")
    if p >= 0.05:
        print("→ 统计上不显著：这点差距还在噪声范围内，加题量才谈得上结论。")
    else:
        print("→ 统计显著：差距不太可能由采样波动解释。")

    if tot_b != tot_c:
        alone = [i for i in common if run[i]["ok"] != ref[i]["ok"]]
        print("\n不一致题号：" + "、".join(alone))


if __name__ == "__main__":
    main()
