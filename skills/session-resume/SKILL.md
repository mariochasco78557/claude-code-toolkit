---
name: session-resume
description: Load the latest saved session checkpoint for the current project and resume cleanly. Counterpart to /session-handoff. Reads PROJECT_ROOT/.claude/handoffs/latest.md, summarizes the saved state, and points to the next action. Use after /clear, /compact, reopening Claude Code, or returning to a project, or when the user says "session resume", "resume", "load checkpoint", "where was I", "pick up where I left off", "continue last session".
argument-hint: ""
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Grep, Glob, Bash(git status:*), Bash(git branch:*), Bash(git rev-parse:*), Bash(python3 ~/.claude/skills/session-resume/read_latest_handoff.py:*)
model: sonnet
---

# session-resume

Load the most recent **saved checkpoint** for the current project and help the
user continue from it. This is the **"load game"** counterpart to
`/session-handoff` (the "save game"):

- `/session-handoff` → saves `PROJECT_ROOT/.claude/handoffs/latest.md` + an archive copy.
- `/session-resume` → reads that `latest.md` and resumes from it.

The audience for your output is **the user returning to this project** with little
or no memory of the last session.

## What this skill does

1. Detects the project root: git repo root if inside a repo, else current working
   directory.
2. Reads **only** `PROJECT_ROOT/.claude/handoffs/latest.md`.
3. If found: summarizes the saved state and recommends exactly how to continue.
4. If not found: says so cleanly, shows the expected path, and suggests running
   `/session-handoff` after a meaningful work session. Creates nothing.

All detection + reading is done by the companion script
`~/.claude/skills/session-resume/read_latest_handoff.py`. **Do not reimplement
that logic.** Do not go hunting through the project for state — `latest.md` is the
single source of truth for this skill.

## How to run it

Invoke the script and use its output:

```
python3 ~/.claude/skills/session-resume/read_latest_handoff.py
```

The script prints, in order:

```
PROJECT_ROOT=<absolute path>
LATEST_PATH=<absolute path to latest.md>
CHECKPOINT_FOUND=yes|no
GITIGNORED=yes|no|unknown (...) (.claude/handoffs/)
```

…then, **only if found**, the verbatim file between:

```
----- BEGIN LATEST.MD -----
<contents>
----- END LATEST.MD -----
```

…or, **only if missing**, two status lines (`STATUS=...`, `HINT=...`).

Test/override only: set `SESSION_HANDOFF_PROJECT_ROOT=/path` to redirect which
project root is read (used for testing; not needed in normal use).

If the script is blocked by a permission prompt or cannot run, fall back to
reading `PROJECT_ROOT/.claude/handoffs/latest.md` directly with the Read tool —
**only that file**, nothing else in the project.

## Hard rules (non-negotiable)

- **Read-only. Always.** This skill never creates, edits, or deletes any file —
  not in the project, not in `.claude/handoffs/`. If the user wants to save, that
  is `/session-handoff`, a separate command.
- **Read ONLY `latest.md`.** Do not open other handoff archives, source files,
  `.env`, configs, or anything else unless the user explicitly asks afterward.
  Do not search or glob the project.
- **No secrets, ever.** If `latest.md` contains anything that looks like a secret
  (API key, token, password, `.env` contents, personal data, private financial or
  client data), do **not** echo it. Summarize generically and mark it `[REDACTED]`.
- **Absolute paths** when you reference files in your summary.
- **Don't invent state.** Report only what `latest.md` actually says. If a field
  is absent, say "not recorded in checkpoint" rather than guessing.
- **Don't touch `.gitignore`.** Only report the ignore status the script prints.

## How to summarize when a checkpoint is found

Read the checkpoint and produce a tight resume briefing. Extract whatever the
checkpoint provides for:

- **Goal** — the project/session objective ("Where it started").
- **Current status** — what state things are in now.
- **Completed work / decisions** — "Decisions locked + what shipped".
- **Relevant files** — "Key files for next session" (absolute paths).
- **Risks / constraints / blockers** — "Open risks + deferred + open questions".
- **Running state** — any background processes, dev servers, branches still live.
- **Next recommended action** — the "Pick up here" line.
- **Suggested next prompt** — surface it clearly and verbatim (it is copy-paste).

Keep it terse. The point is to rebuild context fast, not to re-narrate the
checkpoint line by line. If the next action is clear from the checkpoint, state it
and offer to proceed — **do not ask unnecessary questions.**

## How to report (always, at the end)

Print, in this order:

1. **Detected project root** (absolute).
2. **latest.md path** (absolute).
3. **Checkpoint found?** yes / no.
4. **Resume summary** (the briefing above) — or the not-found message.
5. **Recommended next action** (one concrete step).
6. **Suggested next prompt** (verbatim from the checkpoint if present).

## When no checkpoint is found

- State plainly: no handoff checkpoint was found for this project.
- Show the expected path: `PROJECT_ROOT/.claude/handoffs/latest.md`.
- Recommend running `/session-handoff` after a meaningful work session to create
  the first checkpoint.
- Do **not** create any handoff files. Do **not** modify the project.

## When to use

- Right after `/clear` or `/compact`, to reload context.
- When reopening Claude Code on a project from a previous day.
- When returning to a project after working on a different one.
- Any time you ask "where was I?" on a project that uses session-handoff.

## When NOT to use

- Mid-session when you already have full context — it just spends tokens.
- To save state — that is `/session-handoff`.
- On a project that has never had a handoff saved (it will simply report none).

## Safety rules (summary)

- Strictly read-only; `allowed-tools` grants no Write/Edit, only read-only git and
  the read script.
- Reads only `latest.md`; never searches the project or opens secret files.
- Redacts anything secret-like found in the checkpoint.
- Never edits `.gitignore`; only reports ignore status.
- Defers to any project-level security rules (e.g. a `security-boundaries.md`).

## Rollback / install note

Companion script: `~/.claude/skills/session-resume/read_latest_handoff.py`.
To remove this skill entirely:
`rm -rf ~/.claude/skills/session-resume/` and restart Claude Code.
This skill is self-contained and does not modify `session-handoff`.
