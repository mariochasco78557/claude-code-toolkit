# Router evals: how we know the router helps

A hook that silently adds text to every prompt can quietly get worse: a new keyword steals traffic
from another row, a stemming tweak makes greetings trigger injections, a slow path eats the latency
budget. This folder is a small, stdlib-only harness that measures the `UserPromptSubmit` router
hook (`hooks/ai-kb-recall.py`) against `router/ROUTER.example.md` and fails CI when it regresses.

## What is under test

- Design of the hook: scores `ROUTER.md` rows by keyword overlap, injects the best 1-2 rows,
  **max 1,200 characters** in total, **fails open** (any error or the 2.6 s wall-clock budget
  means "inject nothing", never a blocked prompt), and every real prompt appends one line to a
  local JSONL decision log.
- The harness calls the hook as `hooks/ai-kb-recall.py --router router/ROUTER.example.md --dry-run "<prompt>" --json`
  (`--router` or the `ROUTER_PATH` env var points the hook at any router file). It runs with a throwaway
  `HOME`, so it never reads a real knowledge base, router cache or decision log: the knowledge-base
  search fallback is off and only the router rows are measured.

## Method

| Choice | Why |
|---|---|
| **hit@1 / hit@2 on a golden set** | The hook's job is "put the right pointer in front of the model". hit@1 = the first injected row is an accepted label; hit@2 = either of the (at most) two injected rows is. A labelled set turns "feels right" into a number you can diff between commits. |
| **Separate holdout** | `golden.jsonl` is what you tune against; `holdout.jsonl` was written before tuning and is only for checking that the golden numbers are not overfit. Compare the two: a big gap means you tuned to the examples. |
| **Negatives** | Greetings, thanks, chit-chat, pasted code and slash commands must inject nothing. Without them, "inject something broad on every prompt" would score well on hit@k while costing tokens and distracting the model. |
| **Character budget** | Every injected character is paid on every prompt. We track average (cost) and maximum (hard cap of 1,200 chars) so a router change cannot silently bloat context. |
| **Time budget** | The hook sits in the critical path of each prompt. p95 wall time (including Python start-up) must stay far below the 2.6 s fail-open limit. |
| **Naive baseline** | "Always inject the most frequent row" shows what hit@1 you get for free. A router that is not clearly above it is not helping. |

## Run it

```
python3 evals/router/run_eval.py            # human-readable table, exit 1 below thresholds
python3 evals/router/run_eval.py --json     # machine-readable
python3 evals/router/run_eval.py --no-gate  # always exit 0 (reporting only)
```

Python 3.9+, no dependencies. CI runs it on every push (`.github/workflows/evals.yml`, Python 3.11).
Gates live in `thresholds.json`: hit@1 >= 0.75, hit@2 >= 0.90, average injected chars <= 700, max chars
<= 1200, negatives wrongly injected = 0, p95 latency <= 2600 ms. They are deliberately looser than the
current results so only real regressions trip them; tighten them as the router improves.

## Results

Hook v2.3, `router/ROUTER.example.md` (17 rows), measured with the command above:

| Set | Cases | hit@1 | hit@2 | Avg chars | Max chars | p95 latency |
|---|---|---|---|---|---|---|
| golden | 42 | 0.952 (40/42) | 0.952 | 353 | 409 | 44 ms |
| holdout | 17 | 0.941 (16/17) | 0.941 | 353 | 432 | 47 ms |
| negatives | 12 | n/a | n/a | 0 | 0 | n/a |

- Negatives wrongly injected: **0 / 12**.
- Naive baseline ("always inject R01") hit@1: **0.095** on golden, **0.059** on holdout, so the router is roughly 10-16x better than the free option.
- hit@2 equals hit@1 because this router almost always injects a single row (the second row is added only on a near-tie).
- Known misses, kept in the sets on purpose: a Spanish prompt about "permisos" that scores just under the injection threshold (golden `g23`), a prompt that says "return JSON that matches a schema" without the literal phrase "structured output" (golden `g24`), and a holdout prompt that says "coding rules" instead of "rules file" (`h07`). Each is a keyword-coverage gap, not a bug.
- Latency is wall time of a fresh `python3` process per case on a developer laptop, so it includes interpreter start-up; CI numbers differ. Average chars shifts by a few characters with the checkout path, because the injected header contains the router directory.
- These are numbers for the synthetic example router, not for any private one. They show how to measure, not how your router will score.

## Add a case

Append one JSON line to the right file. Positive cases:

```
{"id": "g43", "prompt": "How do I cache a long system prompt?", "expect": ["R02"]}
```

`expect` lists every row id you would accept as correct (usually one). Negatives only need `id` and `prompt`.
Rules: realistic phrasing, English or Spanish, synthetic, no names of people, clients or private paths.
Only add to `holdout.jsonl` cases you have **not** looked at while tuning keywords. If you add a new router
row, add several golden cases for it and at least one near-miss negative.

## Read a regression

1. The run prints each hit@1 miss as `MISS set/id expect=[...] got=[...] scores=[...]`. `got=[]` with a
   score listed means the right row scored but stayed under the injection threshold (2.0); `got=[Rxx]` means
   another row outranked it.
2. `FALSE INJECT` lines are negatives that received text; check which row fired and which keyword did it.
3. A max-chars or average-chars violation means a row got longer or the second-row tie rule fires too often.
4. A latency violation usually means a new code path (subprocess, file scan) in the hook.
5. Fix the keywords, not the labels. Change a label only when the label was wrong, and say so in the commit.
   Never lower `thresholds.json` to make CI green without recording why.
