#!/usr/bin/env bash
# SessionStart: inject compact "what's new" digest from the knowledge feeds (<=1.5KB). Silent on failure.
# KB root: env AI_KB_ROOT, else $HOME/ai-knowledge-feeds. No KB (or no uv) -> skip only the digest;
# the status line still prints.
KB_DIR=""
for c in "${AI_KB_ROOT:-}" "$HOME/ai-knowledge-feeds"; do
  if [ -n "$c" ] && [ -d "$c" ]; then KB_DIR="$c"; break; fi
done
UV="$(command -v uv 2>/dev/null)"
[ -n "$UV" ] || for c in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
  if [ -x "$c" ]; then UV="$c"; break; fi
done
if [ -n "$KB_DIR" ] && [ -n "$UV" ]; then
  timeout 8 "$UV" run --quiet --directory "$KB_DIR" kb whats-new --compact 2>/dev/null || true
fi
timeout 2 python3 "$HOME/.claude/hooks/ai-kb-status-line.py" 2>/dev/null || true
exit 0
