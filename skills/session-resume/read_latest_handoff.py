#!/usr/bin/env python3
"""
read_latest_handoff.py — "load game" reader for the session-resume skill.

Counterpart to session-handoff's save_handoff.py. It locates and prints the most
recent saved checkpoint for the current project:

    PROJECT_ROOT/.claude/handoffs/latest.md

Project root detection (in priority order):
    1. $SESSION_HANDOFF_PROJECT_ROOT   (test/override escape hatch)
    2. git repository root              (git rev-parse --show-toplevel)
    3. current working directory

Strictly read-only:
    - Reads ONLY latest.md. Never searches the project, never opens any other file.
    - Never creates, modifies, or deletes anything.

Output is delimited so the calling agent can parse it reliably:
    PROJECT_ROOT=<path>
    LATEST_PATH=<path>
    CHECKPOINT_FOUND=yes|no
    GITIGNORED=yes|no|unknown (...)
    ----- BEGIN LATEST.MD -----   (only when found)
    <verbatim contents>
    ----- END LATEST.MD -----

Usage:
    python3 read_latest_handoff.py
"""

import os
import subprocess
import sys

HANDOFFS_REL = ".claude/handoffs"
LATEST_NAME = "latest.md"


def detect_project_root() -> str:
    """Return the project root using override -> git root -> cwd."""
    override = os.environ.get("SESSION_HANDOFF_PROJECT_ROOT", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        root = out.stdout.strip()
        if out.returncode == 0 and root:
            return os.path.abspath(root)
    except (OSError, subprocess.SubprocessError):
        pass

    return os.path.abspath(os.getcwd())


def is_gitignored(project_root: str, handoffs_dir: str) -> str:
    """Return 'yes', 'no', or an 'unknown (...)' reason for the handoffs dir."""
    try:
        inside = subprocess.run(
            ["git", "-C", project_root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return "unknown (not a git repository)"

        check = subprocess.run(
            ["git", "-C", project_root, "check-ignore", "-q", handoffs_dir],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode == 0:
            return "yes"
        if check.returncode == 1:
            return "no"
        return "unknown (git check-ignore error)"
    except (OSError, subprocess.SubprocessError):
        return "unknown (git unavailable)"


def main() -> int:
    project_root = detect_project_root()
    handoffs_dir = os.path.join(project_root, HANDOFFS_REL)
    latest_path = os.path.join(handoffs_dir, LATEST_NAME)

    found = os.path.isfile(latest_path)
    gitignored = is_gitignored(project_root, handoffs_dir)

    print(f"PROJECT_ROOT={project_root}")
    print(f"LATEST_PATH={latest_path}")
    print(f"CHECKPOINT_FOUND={'yes' if found else 'no'}")
    print(f"GITIGNORED={gitignored} (.claude/handoffs/)")

    if not found:
        print("STATUS=No handoff checkpoint found for this project.")
        print(
            "HINT=Run /session-handoff after a meaningful work session to create one."
        )
        return 0

    try:
        with open(latest_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        print(f"STATUS=Found latest.md but could not read it: {exc}")
        return 1

    print("----- BEGIN LATEST.MD -----")
    sys.stdout.write(content)
    if not content.endswith("\n"):
        sys.stdout.write("\n")
    print("----- END LATEST.MD -----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
