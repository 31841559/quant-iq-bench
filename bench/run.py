"""跑测 CLI。

    export BENCH_BASE_URL=http://192.168.1.10:8080/v1
    export BENCH_MODEL=your-model-name

    python -m bench.run --questions data/questions/charops-20261109.json \
        --out data/results/charops-3bpw.json --thinking

支持断点续跑：结果文件里已有的 id 会跳过，中断后重跑同一条命令即可。
默认串行；`--workers 2` 可以并行，但本地推理机通常 4 路以上就饱和了。
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .client import Client
from .scoring import judge

_lock = threading.Lock()


def _load_done(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    try:
        return {r["id"]: r for r in json.load(open(path, encoding="utf-8"))}
    except Exception:
        return {}


def _save(path: str, done: dict[str, dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(done.values(), key=lambda x: x["id"]), f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description="对当前模型跑一遍题库")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thinking", dest="thinking", action="store_true", default=True)
    ap.add_argument("--no-thinking", dest="thinking", action="store_false",
                    help="关闭思考模式（多数本地栈的默认行为，用于对比）")
    ap.add_argument("--max-tokens", type=int, default=8192,
                    help="输出上限。给到 8192 以下时，长思考题会被截断成空答案")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（冒烟用）")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=300,
                    help="单次请求超时秒数。设太大时，收不住思考的题会长时间阻塞")
    args = ap.parse_args()

    items = json.load(open(args.questions, encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]

    done = _load_done(args.out)
    todo = [x for x in items if x["id"] not in done]
    print(f"共 {len(items)} 题，已完成 {len(items) - len(todo)}，本轮待跑 {len(todo)}")

    client = Client(timeout=args.timeout)
    print(f"模型 {client.model} @ {client.url}  thinking={args.thinking}\n")

    def work(item: dict) -> None:
        t0 = time.time()
        try:
            r = client.chat(item["q"], thinking=args.thinking,
                            max_tokens=args.max_tokens, retries=args.retries)
            got = r.answer
            flags = list(r.flags)
            tokens, secs, rlen = r.tokens, r.seconds, len(r.reasoning)
        except Exception as e:  # 单题失败不该拖垮整轮
            got, flags, tokens, secs, rlen = "", [f"ERR {str(e)[:80]}"], 0, 0, 0

        ok = judge(item, got)
        rec = {"id": item["id"], "cat": item["cat"],
               "std": item.get("answer", ""), "ans": got, "ok": ok,
               "tokens": tokens, "seconds": secs, "reasoning_len": rlen,
               "flags": flags, "q": item["q"]}

        with _lock:
            done[item["id"]] = rec
            _save(args.out, done)
            mark = "PASS" if ok else "FAIL"
            extra = f" {flags}" if flags else ""
            print(f"{item['id']} {item['cat']:10s} {mark}  {tokens:5d}tok "
                  f"{secs:6.1f}s  got={str(got)[:56]!r}{extra}", flush=True)

    try:
        if args.workers > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                list(ex.map(work, todo))
        else:
            for it in todo:
                work(it)
    finally:
        client.close()

    _summary(done, items)


def _summary(done: dict[str, dict], items: list[dict]) -> None:
    rows = [done[x["id"]] for x in items if x["id"] in done]
    if not rows:
        return
    ok = sum(r["ok"] for r in rows)
    tok = sum(r["tokens"] for r in rows)
    sec = sum(r["seconds"] for r in rows)
    print(f"\n{'题集':10s} {'正确':>9s} {'token':>8s} {'耗时':>8s} {'均tok':>7s} {'tok/s':>7s}")
    for cat in sorted({r["cat"] for r in rows}):
        sub = [r for r in rows if r["cat"] == cat]
        s_ok = sum(r["ok"] for r in sub)
        s_tok = sum(r["tokens"] for r in sub)
        s_sec = sum(r["seconds"] for r in sub) or 1e-9
        print(f"{cat:10s} {s_ok:3d}/{len(sub):<4d} {s_tok:8d} {s_sec:7.0f}s "
              f"{s_tok / len(sub):7.0f} {s_tok / s_sec:7.0f}")
    sec = sec or 1e-9
    print(f"{'合计':10s} {ok:3d}/{len(rows):<4d} {tok:8d} {sec:7.0f}s "
          f"{tok / len(rows):7.0f} {tok / sec:7.0f}")

    fails = [r for r in rows if not r["ok"]]
    if fails:
        print("\n失败明细：")
        for r in fails:
            print(f"  {r['id']} {r['cat']:10s} std={r['std'][:30]!r} got={str(r['ans'])[:30]!r} "
                  f"{r['tokens']}tok {r['seconds']}s {r['flags']}")


if __name__ == "__main__":
    main()
