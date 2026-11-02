#!/usr/bin/env python3
"""Eval harness for the UserPromptSubmit router hook (stdlib only).

Runs hooks/ai-kb-recall.py in `--dry-run --json` mode against router/ROUTER.example.md for every
case in golden.jsonl, holdout.jsonl and negatives.jsonl and reports hit@1, hit@2, injected size and
latency. Exit code 1 if any metric violates thresholds.json (CI gate).

    python3 evals/router/run_eval.py [--json] [--router PATH] [--thresholds PATH] [--no-gate]

The hook runs with a throwaway HOME so it can neither see a real knowledge base nor touch the real
router cache or decision log: only the router file is under test (the KB-search fallback is off).
"""
from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HOOK = REPO / "hooks" / "ai-kb-recall.py"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run_case(prompt: str, router: Path, env: dict) -> dict:
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, str(HOOK), "--router", str(router), "--dry-run", prompt, "--json"],
                       capture_output=True, text=True, env=env, timeout=10)
    wall = (time.perf_counter() - t0) * 1000
    d = json.loads(p.stdout)
    d["wall_ms"] = wall
    return d


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)] if xs else 0.0


def score_positive(name: str, cases: list[dict], router: Path, env: dict, details: list) -> dict:
    h1 = h2 = 0
    chars, lat = [], []
    for c in cases:
        r = run_case(c["prompt"], router, env)
        got = r.get("routes", [])
        ok1 = bool(got) and got[0] in c["expect"]
        ok2 = any(g in c["expect"] for g in got[:2])
        h1 += ok1
        h2 += ok2
        chars.append(r["chars"])
        lat.append(r["wall_ms"])
        if not ok1:
            details.append({"set": name, "id": c["id"], "expect": c["expect"], "got": got,
                            "scores": r.get("scores", [])[:3], "prompt": c["prompt"]})
    n = len(cases)
    # Baseline: always inject the single row that is expected most often.
    ids = sorted({e for c in cases for e in c["expect"]})
    best = max(ids, key=lambda i: sum(i in c["expect"] for c in cases)) if ids else ""
    base = sum(best in c["expect"] for c in cases) / n if n else 0.0
    return {"n": n, "hit_at_1": h1 / n if n else 0.0, "hit_at_2": h2 / n if n else 0.0,
            "avg_chars": sum(chars) / n if n else 0.0, "max_chars": max(chars, default=0),
            "p95_latency_ms": p95(lat), "baseline_always_row": best, "baseline_hit_at_1": base}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--router", default=str(REPO / "router" / "ROUTER.example.md"))
    ap.add_argument("--thresholds", default=str(HERE / "thresholds.json"))
    ap.add_argument("--no-gate", action="store_true", help="always exit 0")
    a = ap.parse_args()
    router = Path(a.router).resolve()
    th = json.loads(Path(a.thresholds).read_text(encoding="utf-8"))

    home = tempfile.mkdtemp(prefix="router-eval-home-")
    env = {k: v for k, v in os.environ.items() if k not in ("FLOWARA_AI_OS_ROOT", "AI_KB_ROOT", "ROUTER_PATH",
                                                            "ROUTER_SYNONYMS", "AI_KB_RECALL_LOG")}
    env["HOME"] = home

    details: list = []
    res = {"sets": {}}
    for name in ("golden", "holdout"):
        cases = load(HERE / f"{name}.jsonl")
        if cases:
            res["sets"][name] = score_positive(name, cases, router, env, details)

    neg = load(HERE / "negatives.jsonl")
    bad, nlat, nchars = [], [], []
    for c in neg:
        r = run_case(c["prompt"], router, env)
        nlat.append(r["wall_ms"])
        nchars.append(r["chars"])
        if r["chars"] > 0:
            bad.append({"id": c["id"], "prompt": c["prompt"], "chars": r["chars"], "routes": r.get("routes", [])})
    res["negatives"] = {"n": len(neg), "wrongly_injected": len(bad), "cases": bad}
    res["failures"] = details

    allpos = list(res["sets"].values())
    res["overall"] = {
        "max_chars": max([s["max_chars"] for s in allpos] + nchars, default=0),
        "p95_latency_ms": p95([x for x in nlat]) if not allpos else max(s["p95_latency_ms"] for s in allpos),
    }

    viol = []
    for name, s in res["sets"].items():
        if s["hit_at_1"] < th["hit_at_1_min"]:
            viol.append(f"{name}: hit@1 {s['hit_at_1']:.3f} < {th['hit_at_1_min']}")
        if s["hit_at_2"] < th["hit_at_2_min"]:
            viol.append(f"{name}: hit@2 {s['hit_at_2']:.3f} < {th['hit_at_2_min']}")
        if s["avg_chars"] > th["avg_chars_max"]:
            viol.append(f"{name}: avg chars {s['avg_chars']:.0f} > {th['avg_chars_max']}")
        if s["p95_latency_ms"] > th["p95_latency_ms_max"]:
            viol.append(f"{name}: p95 latency {s['p95_latency_ms']:.0f} ms > {th['p95_latency_ms_max']}")
    if res["overall"]["max_chars"] > th["max_chars_max"]:
        viol.append(f"max chars {res['overall']['max_chars']} > {th['max_chars_max']}")
    if len(bad) > th["negatives_injected_max"]:
        viol.append(f"negatives injected {len(bad)} > {th['negatives_injected_max']}")
    res["violations"] = viol
    res["passed"] = not viol

    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"{'set':<10}{'n':>4}{'hit@1':>8}{'hit@2':>8}{'avg ch':>8}{'max ch':>8}{'p95 ms':>8}{'baseline@1':>12}")
        for name, s in res["sets"].items():
            print(f"{name:<10}{s['n']:>4}{s['hit_at_1']:>8.3f}{s['hit_at_2']:>8.3f}{s['avg_chars']:>8.0f}"
                  f"{s['max_chars']:>8}{s['p95_latency_ms']:>8.0f}{s['baseline_hit_at_1']:>8.3f} ({s['baseline_always_row']})")
        print(f"negatives: {len(bad)} wrongly injected of {len(neg)}")
        for f in details:
            print(f"  MISS {f['set']}/{f['id']} expect={f['expect']} got={f['got']} scores={f['scores']} :: {f['prompt'][:70]}")
        for b in bad:
            print(f"  FALSE INJECT {b['id']} {b['routes']} :: {b['prompt'][:60]!r}")
        print("PASS" if not viol else "FAIL: " + "; ".join(viol))
    return 0 if (a.no_gate or not viol) else 1


if __name__ == "__main__":
    sys.exit(main())
