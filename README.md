# claude-code-toolkit

A small, stdlib-only set of Claude Code building blocks: a per-prompt knowledge router,
a four-tier subagent team, session save/load checkpoints, and a Stop hook that stops the
assistant from promising work it never starts.

## What is inside

| Piece | One line |
|---|---|
| `hooks/ai-kb-recall.py` | UserPromptSubmit hook: injects the 1-2 best `ROUTER.md` lines (or a KB search) as context. |
| `hooks/ai-kb-status-line.py` | SessionStart: one status line (last KB sync, pending items, canon age). |
| `hooks/ai-kb-digest.sh` | SessionStart: compact "what's new" digest from the KB, then the status line. |
| `hooks/no-idle-promise.py` | Stop hook: blocks ending a turn that announces work without launching it. |
| `agents/{junior,plumber,senior,verifier}.md` | Four subagents, one per model tier. |
| `skills/session-handoff/` | `/session-handoff`: save a structured checkpoint into the project. |
| `skills/session-resume/` | `/session-resume`: load the latest checkpoint and continue. |
| `router/` | Example `ROUTER.md` and synonyms file. |
| `settings.example.json` | The hook wiring to merge into `~/.claude/settings.json`. |
| `install.sh` | Idempotent installer into `~/.claude` (timestamped backups). |

## The per-prompt router

Instead of dumping a whole knowledge base into context, the hook looks at each prompt and
injects a pointer: "for this topic, open these pages / these KB ids". It runs in about
0.25 s, injects at most 1200 characters, and never blocks the prompt (any failure is silent).

`ROUTER.md` is a plain file with one line per topic, 7 columns separated by ` | `:

```
R02 | Prompt caching | !caching,prompt cache,cache_control | [[prompt-caching]] | pf:en/build-with-claude/prompt-caching.md | - | can
id  | topic          | keywords (!strong, x* prefix, phrases) | vault pages | KB ids | owner | authority
```

Scoring is keyword overlap with light ES/EN stemming and a synonyms file
(`ops/router_synonyms.json`). If no line reaches the threshold, the hook falls back to a
search of the knowledge base ([`ai-knowledge-feeds`](https://github.com/mariochasco78557/ai-knowledge-feeds),
companion repo) and injects up to two hits. Short prompts, slash commands and notifications
get nothing. Every real prompt appends one line to `~/.cache/ai-kb-recall/decisions.jsonl`
(local only, mode 0600) so you can review routing decisions.

Try it without Claude Code:

```
FLOWARA_AI_OS_ROOT=/path/to/vault python3 hooks/ai-kb-recall.py --dry-run "How do I add a SessionStart hook?"
```

Environment variables (names kept for compatibility):

- `FLOWARA_AI_OS_ROOT`: vault containing `ROUTER.md` (default `$HOME/vault`).
- `AI_KB_ROOT`: checkout of the knowledge feeds (default `$HOME/ai-knowledge-feeds`).

Without either, the hooks print nothing and exit 0.

## The four-tier subagent team

Rule: **the main session orchestrates, agents write.** The main session reads, decides,
delegates and verifies; code and long documents are produced by subagents.

- `junior` (Haiku): read-only discovery, search, summaries.
- `plumber` (Sonnet): routine implementation once design is decided.
- `senior` (Opus): architecture, hard bugs, security, anything hard to reverse.
- `verifier` (Sonnet): runs after every meaningful change; returns PASS / PASS WITH WARNINGS / FAIL and never edits.

Pick the tier by task complexity: do not downgrade judgment work, do not upgrade mechanical work.

## Session checkpoints

- `/session-handoff` writes a fixed eight-section Markdown summary to
  `<project>/.claude/handoffs/` (`latest.md`, `index.md`, timestamped `archive/`). Run it before `/clear` or `/compact`.
- `/session-resume` reads only `latest.md` and gives a short briefing plus the next action.

Think "save game" and "load game". The scripts own the files and never overwrite an archive.

## no-idle-promise

A Stop hook. If the last assistant message says things like "now I'm starting..." (English or
Spanish) and nothing was launched in the turn (background Agent, `run_in_background`,
`systemd-run`, `nohup`...), it blocks the stop once and asks the assistant to launch the work
or state plainly that it has not started.

## Install

```
git clone <this repo> && cd claude-code-toolkit
bash install.sh
```

The installer copies hooks, agents and skills into `~/.claude` (override with `CLAUDE_HOME`),
backs up any differing file as `<file>.bak-<timestamp>`, sets executable bits and prints what
it did. It does not touch `settings.json`: merge `settings.example.json` yourself. To use the
router, copy `router/ROUTER.example.md` to `$FLOWARA_AI_OS_ROOT/ROUTER.md` and
`router/router_synonyms.example.json` to `$FLOWARA_AI_OS_ROOT/ops/router_synonyms.json`,
then edit them to your topics.

## Requirements

Python 3.9+ (standard library only), bash. `uv` is optional and only needed for the KB search
fallback and digest.

## License

MIT, see `LICENSE`.

Author: Mario Chasco, [flowaraai.com](https://flowaraai.com), [youtube.com/@mariochasco_AI](https://youtube.com/@mariochasco_AI)
