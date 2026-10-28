#!/usr/bin/env python3
"""Stop hook: do not end a turn that ANNOUNCES work without having launched it.

Failure mode it prevents: the assistant says "Now I'm starting the build", closes the
turn without launching anything, and the machine sits idle for hours. If the last message
promises immediate work and nothing was launched in the background during this turn
(Agent, Bash run_in_background, systemd-run, nohup, ...), the stop is blocked once and the
assistant is asked to launch the work now or to say clearly that it has NOT started.
Promise patterns cover English and Spanish.
"""
from __future__ import annotations
import json, re, sys

PROMISE = re.compile(
    r"\b(ahora|ya)\s+(empiezo|arranco|lanzo|monto|me pongo|procedo|sigo con|hago|preparo|grabo|renderizo)\b"
    r"|\b(empiezo|arranco|procedo)\s+(ya|ahora|con|a|el|la|los|las)\b"
    r"|\bvoy a (empezar|arrancar|lanzar|montar|ponerme|proceder|hacer|preparar|grabar|renderizar)\b"
    r"|\b(I'll|I will|let me) (now )?(start|begin|kick off|launch|proceed)\b"
    r"|\b(starting|beginning) (it |this |the \w+ )?now\b",
    re.I,
)
LAUNCH = re.compile(r"systemd-run|bg\.sh start|nohup |\bsetsid\b")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    path = data.get("transcript_path")
    if not path:
        return 0
    try:
        lines = open(path, encoding="utf-8").read().splitlines()[-400:]
    except Exception:
        return 0

    last_text, launched = None, False
    for raw in reversed(lines):
        try:
            e = json.loads(raw)
        except Exception:
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "user":
            if isinstance(content, str) or (
                isinstance(content, list)
                and any(isinstance(c, dict) and c.get("type") == "text" for c in content)
                and not any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content)
            ):
                break  # inicio del turno
            continue
        if e.get("type") != "assistant" or not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and last_text is None and c.get("text", "").strip():
                last_text = c["text"]
            if c.get("type") == "tool_use":
                name, inp = c.get("name", ""), c.get("input") or {}
                if name in ("Agent", "Task", "Workflow", "ScheduleWakeup", "CronCreate"):
                    launched = True
                if inp.get("run_in_background") or LAUNCH.search(str(inp.get("command", ""))):
                    launched = True

    if not last_text or launched:
        return 0
    m = PROMISE.search(last_text)
    if not m:
        return 0
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"Your message announces immediate work ('{m.group(0)}') but the turn is ending "
            "without having launched anything. Rule: never leave the machine idle after promising work. "
            "Launch it NOW (background Agent, Bash run_in_background, or a resource-capped systemd-run) "
            "before finishing; or, if it truly cannot start, rewrite the message saying clearly "
            "that it has NOT started, why, and what is missing."
        ),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
