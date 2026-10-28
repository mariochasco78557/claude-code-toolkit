#!/usr/bin/env python3
"""
save_handoff.py — "save game" checkpoint writer for the session-handoff skill.

Reads handoff Markdown from stdin and saves it as an idempotent, timestamped
checkpoint inside the current project at:

    PROJECT_ROOT/.claude/handoffs/
        latest.md                                 (overwritten each run)
        index.md                                  (appended each run)
        archive/YYYY-MM-DD_HH-MM_slug.md          (new file each run, never overwritten)

Project root detection (in priority order):
    1. $SESSION_HANDOFF_PROJECT_ROOT   (test/override escape hatch)
    2. git repository root              (git rev-parse --show-toplevel)
    3. current working directory

Safety properties:
    - Never deletes an existing handoff.
    - Never overwrites an existing archive file (adds -2, -3, ... suffix).
    - Reuses the handoffs folder if it already exists; never recreates/resets it.
    - Writes nothing outside PROJECT_ROOT/.claude/handoffs/.

Usage:
    python3 save_handoff.py "short-slug" < handoff.md
    cat handoff.md | python3 save_handoff.py "short-slug"
"""

import os
import re
import subprocess
import sys
from datetime import datetime

HANDOFFS_DIRNAME = ".claude/handoffs"
FALLBACK_SLUG = "session-handoff"
MAX_SLUG_LEN = 60


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


def sanitize_slug(raw: str) -> str:
    """
    Make a safe filename component from arbitrary user input.

    - lowercase
    - spaces / whitespace -> hyphens
    - keep only [a-z0-9_-]
    - collapse repeated hyphens, strip leading/trailing separators
    - block path traversal (no '/', '\\', '..', leading dots)
    - fall back to FALLBACK_SLUG if nothing usable remains
    """
    if not raw:
        return FALLBACK_SLUG

    slug = raw.strip().lower()
    # strip any path components defensively before character filtering
    slug = slug.replace("\\", "/").split("/")[-1]
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-_.")

    if not slug:
        return FALLBACK_SLUG

    return slug[:MAX_SLUG_LEN].strip("-_.") or FALLBACK_SLUG


def unique_archive_path(archive_dir: str, base_name: str) -> str:
    """
    Return a non-colliding path for base_name (without extension) inside
    archive_dir. Adds -2, -3, ... before the .md extension if needed.
    Never returns the path of a file that already exists.
    """
    candidate = os.path.join(archive_dir, base_name + ".md")
    if not os.path.exists(candidate):
        return candidate

    n = 2
    while True:
        candidate = os.path.join(archive_dir, f"{base_name}-{n}.md")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def is_gitignored(project_root: str, handoffs_dir: str) -> str:
    """
    Return 'yes', 'no', or 'unknown (not a git repository)' describing whether
    the handoffs directory appears to be ignored by git.
    """
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
        # exit 0 => ignored, 1 => not ignored, other => error
        if check.returncode == 0:
            return "yes"
        if check.returncode == 1:
            return "no"
        return "unknown (git check-ignore error)"
    except (OSError, subprocess.SubprocessError):
        return "unknown (git unavailable)"


def first_title(content: str, slug: str) -> str:
    """Best-effort human label for the index: first markdown H1, else slug."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return slug


INDEX_HEADER = (
    "# Handoff Checkpoints\n\n"
    "Save-game checkpoints for this project, newest entries appended at the bottom.\n\n"
    "| Saved (local) | Title / Slug | File |\n"
    "|---|---|---|\n"
)


def update_index(index_path: str, when_human: str, title: str, rel_path: str) -> None:
    """Create index.md with a header+table, or append one row to it."""
    safe_title = title.replace("|", "\\|")
    row = f"| {when_human} | {safe_title} | {rel_path} |\n"

    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(INDEX_HEADER + row)
        return

    with open(index_path, "r", encoding="utf-8") as fh:
        existing = fh.read()

    # If the file exists but is missing our table header, rebuild header first.
    if "| Saved (local) |" not in existing:
        sep = "" if existing.endswith("\n") or existing == "" else "\n"
        with open(index_path, "a", encoding="utf-8") as fh:
            fh.write(sep + "\n" + INDEX_HEADER + row)
        return

    sep = "" if existing.endswith("\n") else "\n"
    with open(index_path, "a", encoding="utf-8") as fh:
        fh.write(sep + row)


def main() -> int:
    slug_arg = sys.argv[1] if len(sys.argv) > 1 else ""

    content = sys.stdin.read()
    if not content.strip():
        sys.stderr.write(
            "save_handoff.py: refusing to save — no handoff content on stdin.\n"
        )
        return 2

    if not content.endswith("\n"):
        content += "\n"

    project_root = detect_project_root()
    handoffs_dir = os.path.join(project_root, HANDOFFS_DIRNAME)
    archive_dir = os.path.join(handoffs_dir, "archive")

    # Create or reuse — exist_ok makes this idempotent and non-destructive.
    os.makedirs(archive_dir, exist_ok=True)

    slug = sanitize_slug(slug_arg)
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M")
    base_name = f"{stamp}_{slug}"

    archive_path = unique_archive_path(archive_dir, base_name)
    with open(archive_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    latest_path = os.path.join(handoffs_dir, "latest.md")
    with open(latest_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    index_path = os.path.join(handoffs_dir, "index.md")
    rel_archive = os.path.relpath(archive_path, handoffs_dir)
    when_human = now.strftime("%Y-%m-%d %H:%M")
    title = first_title(content, slug)
    update_index(index_path, when_human, title, rel_archive)

    ignored = is_gitignored(project_root, handoffs_dir)

    print("Handoff checkpoint saved.")
    print(f"  project root : {project_root}")
    print(f"  archive file : {archive_path}")
    print(f"  latest.md    : {latest_path}")
    print(f"  index.md     : {index_path}")
    print(f"  gitignored   : {ignored} (.claude/handoffs/)")
    if ignored == "no":
        print(
            "  note         : .claude/handoffs/ is NOT gitignored — checkpoints "
            "would be committed. Add it to .gitignore if that is not intended."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
