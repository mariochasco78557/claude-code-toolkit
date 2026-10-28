---
name: session-handoff
description: Save a structured "checkpoint" of the current Claude Code session into the project (.claude/handoffs/) before /clear, /compact, switching projects, or ending the day, so the next session can resume cleanly. Use when the user says "session handoff", "hand off", "wrap up", "save checkpoint", "before I clear", "before I switch projects", or when context is heavy and a clean restart is near.
argument-hint: "[optional short slug/title]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Grep, Glob, Bash(git status:*), Bash(git diff --stat:*), Bash(git branch:*), Bash(git log --oneline -n 10:*), Bash(git rev-parse:*), Bash(python3 ~/.claude/skills/session-handoff/save_handoff.py:*)
model: sonnet
---

# session-handoff

Produce a structured handoff **and save it as a checkpoint inside the current
project**, so the **next Claude instance** can resume cleanly after `/clear`,
`/compact`, a project switch, or end of day. Think of it as **saving a video-game
checkpoint**: a compact, safe, operational project memory — *not* a transcript of
the whole conversation.

The audience is a future agent with **no memory of this session**.

## What this skill does

1. Generates the structured 8-section handoff summary (below) and prints it in chat.
2. Saves that same Markdown as a timestamped checkpoint, via the companion script
   `~/.claude/skills/session-handoff/save_handoff.py`, into:

   ```
   PROJECT_ROOT/.claude/handoffs/
     latest.md                              # newest handoff (overwritten each run)
     index.md                               # running list of checkpoints (appended)
     archive/
       YYYY-MM-DD_HH-MM_<slug>.md           # one new file per run, never overwritten
   ```

   `PROJECT_ROOT` = git repo root if inside a repo, else the current working
   directory. The script handles all detection, folder creation, sanitization,
   collision suffixes, and idempotency — **do not reimplement that logic in chat.**

## Hard rules (non-negotiable)

- **The script owns the files.** Save ONLY by piping the handoff into
  `save_handoff.py`. Never hand-write into `.claude/handoffs/` with Write/Edit,
  and never `mkdir`/`rm` there yourself. This guarantees idempotency and prevents
  overwriting prior checkpoints.
- **Never invent state.** Report only what actually happened this session. If a
  section has nothing to report, write `none` — never omit the section.
- **Absolute paths always** in the body. No relative paths, no bare filenames.
- **Terse and concrete.** No emojis, no hype, no "what went well / poorly". Facts.
- **No secrets, ever.** Never echo, print, or paste `.env` contents, API keys,
  tokens, passwords, personal data, or private financial/client data
  — neither in chat nor in the saved file. Reference secrets by name /
  placeholder only (e.g. `<API_KEY>`). If sensitive material came up,
  summarize it generically and mark it `[REDACTED]` in the handoff.
- **Background processes MUST be listed.** Any `run_in_background` shell, dev
  server, or live port goes in **Running state** with its ID and a kill command.
- **One "Pick up here" line.** Exactly one most-likely next action (1–2 sentences).
- **Do not touch `.gitignore`.** Only report whether `.claude/handoffs/` appears
  ignored (the script prints this) and recommend adding it if appropriate.

## How to gather state (read-only)

Before writing, gather facts cheaply and read-only:

- Run `git status`, `git diff --stat`, `git branch` to capture changed files,
  staged vs unstaged, and branch — **only if** the working dir is a git repo.
  If not a repo, write `none (not a git repository)` rather than guessing.
- Recall background shell IDs started this session and their kill commands.
- Recall any plan file or memory file touched this session (absolute paths).
- Do **not** open `.env` or any secret file. Do **not** run state-changing
  commands (no installs, migrations, writes).

## Output structure (locked — never vary, never reorder)

Emit exactly these eight `##`/`#` sections as Markdown in chat. This same text is
what gets saved.

```
# Session Handoff — <one-line title>

## Where it started
<2-3 sentences: the objective — what was asked, key constraints>

## Decisions locked + what shipped
- <decision or completed change> — <why; absolute path>
  (write "none" if nothing was decided or shipped)

## Key files for next session
- `<absolute path>` — <why the next agent should read this first>
- Plan file: <absolute path or "none">
- Memory files touched: <absolute paths or "none">

## Running state
- Background processes: <shell ID + what it is + kill command, or "none">
- Dev servers / ports: <url + port, or "none">
- Open worktrees / branches: <branch/path, or "none">
- Git status: <summary from git status / diff --stat, or "none (not a git repo)">

## Verification — how to confirm things still work
- `<command>` — <expected outcome>
  (write "none" if there is nothing to verify yet)

## Open risks + deferred + open questions
- Risk: <open risk> — <why it matters>
- Deferred: <item> — <why pushed>
- Open: <question needing the user's input> — <context>
  (write "none" for any line with nothing to report)

## Pick up here
<1-2 sentences: the single most likely next exact action for a fresh agent>

## Suggested next prompt
<one copy-paste prompt the next session can run to resume — terse, concrete>
```

## How to save (the checkpoint step)

After printing the summary in chat, save it by piping the **exact same Markdown**
into the script. Pass a short slug as the first argument (derive it from the title;
the script will sanitize it). Use a heredoc so the content is passed safely:

```
python3 ~/.claude/skills/session-handoff/save_handoff.py "<short-slug>" <<'HANDOFF_EOF'
# Session Handoff — <title>
... full handoff markdown ...
HANDOFF_EOF
```

Notes:
- The script reads the handoff from **stdin** and the slug from **arg 1**.
- It prints the archive path, `latest.md` path, `index.md` path, and whether
  `.claude/handoffs/` is gitignored. Surface those lines back to the user.
- Re-running is safe: it reuses the folder, writes a **new** archive file, never
  overwrites a previous checkpoint, refreshes `latest.md`, and appends to `index.md`.
- Test/override only: set `SESSION_HANDOFF_PROJECT_ROOT=/path` to redirect where
  it saves (used for testing; not needed in normal use).

If the save command is blocked by the permission prompt or cannot run for any
reason, **do not pretend it saved.** Print the exact heredoc command above
(filled in) and tell the user to run it to save the checkpoint manually.

## After saving — report to the user

Print, in this order:
1. The handoff summary (already shown).
2. Saved archive file path.
3. `latest.md` path.
4. `index.md` path.
5. Whether `.claude/handoffs/` appears gitignored (recommend ignoring if not, but
   do not edit `.gitignore`).
6. Recommended next action (e.g. "safe to `/compact` now").
7. The suggested next prompt (already in the summary).

## When to use

- Before every `/clear` or `/compact`.
- When switching projects mid-sitting.
- At end of day, to leave a clean, resumable entry point for tomorrow.
- After 3–4 compacts in a row, when quality starts to degrade.
- Right after a failed or abandoned task, to record what broke and what's safe.

## When NOT to use

- Mid-task when you are NOT about to clear/compact/switch — it just spends tokens.
- As a client-facing or stakeholder status update — wrong audience, wrong tone.
- When nothing has happened yet this session (no objective, no changes).

## Token economy rules

- Gather git/state facts **once**; do not re-run `git status` repeatedly.
- Keep the handoff terse — it exists to *reduce* what the next session must
  re-read, not to reproduce the whole session. Summarize; do not transcribe.
- Prefer the cheapest model that produces a faithful summary (`sonnet`).
- Canonical workflow: run this (saves the checkpoint), then `/clear` or `/compact`.
  Never `/clear` without saving a handoff first.

## Safety rules (summary)

- All file writes go through `save_handoff.py`, scoped to
  `PROJECT_ROOT/.claude/handoffs/` only. The script never deletes or overwrites
  existing archive checkpoints.
- Read-only state gathering; only read-only git commands plus the save script are
  granted in `allowed-tools`.
- Never echoes or saves secrets / `.env` / personal / client / financial data;
  references them by name and marks sensitive content `[REDACTED]`.
- Never invents state; empty sections say `none`.
- Never edits `.gitignore`; only reports ignore status.
- Defers to any project-level security rules (e.g. a `security-boundaries.md`).

## Rollback / install note

Companion script: `~/.claude/skills/session-handoff/save_handoff.py`.
Timestamped backups of this file are kept as `SKILL.md.bak.<timestamp>` in this
folder. To restore the previous chat-only behavior, copy the desired backup over
`SKILL.md`. To remove the skill entirely:
`rm -rf ~/.claude/skills/session-handoff/` and restart Claude Code.
