#!/usr/bin/env python3
"""SessionStart: ONE status line for the AI knowledge base + vault (files only, no network, <1 s).
last KB sync · pending items · promotion candidates + candidates/* branch · canon age.
Roots: env FLOWARA_AI_OS_ROOT (default $HOME/vault) / AI_KB_ROOT (default $HOME/ai-knowledge-feeds).
Silent on failure."""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import subprocess



def root(env: str, default: str) -> pathlib.Path | None:
    for c in (os.environ.get(env, ""), os.path.join(str(pathlib.Path.home()), default)):
        if c and os.path.isdir(c):
            return pathlib.Path(c)
    return None


def main() -> None:
    kb, fl = root("AI_KB_ROOT", "ai-knowledge-feeds"), root("FLOWARA_AI_OS_ROOT", "vault")
    parts = []
    today = dt.date.today()
    if kb:
        try:
            lr = json.loads((kb / "state/last_run.json").read_text())
            fin = (lr.get("finished") or "?")[:16].replace("T", " ")
            parts.append(f"sync {fin} UTC {lr.get('status', '?')} ({len(lr.get('errors') or [])} err)")
        except Exception:
            parts.append("sync ?")
        try:
            seen = json.loads((kb / "state/seen.json").read_text())
            pend = sum(1 for src in seen.values() if isinstance(src, dict)
                       for v in src.values() if isinstance(v, dict) and v.get("status") == "pending")
            parts.append(f"pending items {pend}")
        except Exception:
            pass
        try:
            cpath = next(p for p in (kb / "index/VAULT_CANDIDATES.md", kb / "index/FLOWARA_CANDIDATES.md")
                         if p.exists())
            cand = cpath.read_text(encoding="utf-8")
            try:
                done = json.loads((kb / "state/promote_done.json").read_text())
            except Exception:
                done = {}
            ids = [m.group(1) for m in (re.match(r"^- `(?:canonical|practice)` .* \(`([^`]+)`\)\s*$", ln)
                                        for ln in cand.splitlines()) if m]
            n = sum(1 for i in ids if i not in done)
            week = re.search(r"(?:week to|semana hasta) (\d{4}-\d{2}-\d{2})", cand)
            wk = week.group(1) if week else "?"
            branch = ""
            if fl:
                heads = fl / ".git/refs/heads/candidates"
                names = sorted(p.name for p in heads.iterdir()) if heads.is_dir() else []
                if not names:
                    try:
                        out = subprocess.run(["git", "-C", str(fl), "branch", "--list", "candidates/*"],
                                             capture_output=True, text=True, timeout=0.5).stdout.split()
                        names = [o.split("/", 1)[-1] for o in out if o != "*"]
                    except Exception:
                        names = []
                branch = f", branch candidates/{names[-1]}" if names else ", branch merged"
            if n == 0:
                parts.append(f"candidates: all {len(ids)} handled (week to {wk}{branch})")
            else:
                parts.append(f"candidates {n} unpromoted (week to {wk}{branch})")
        except Exception:
            pass
    if fl:
        dates = []
        for f in (fl / "wiki/sources").glob("src-anthropic-*.md"):
            m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", f.read_text(encoding="utf-8")[:600], re.M)
            if m:
                dates.append(m.group(1))
        if dates:
            newest = max(dates)
            age = (today - dt.date.fromisoformat(newest)).days
            parts.append(f"canon updated {newest} ({age} d)")
    if parts:
        print("[AI KB status] " + " · ".join(parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
