#!/usr/bin/env bash
# Install hooks, subagents and skills into ~/.claude (idempotent).
# Existing files that differ are backed up as <file>.bak-<timestamp> before being replaced.
# Does NOT edit ~/.claude/settings.json: merge settings.example.json by hand.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_HOME:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"
copied=0; unchanged=0; backed=0

install_file() {  # install_file <src> <dest>
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ]; then
    if cmp -s "$src" "$dst"; then
      unchanged=$((unchanged + 1)); return 0
    fi
    cp -p "$dst" "$dst.bak-$TS"
    backed=$((backed + 1))
    echo "  backup  $dst -> $dst.bak-$TS"
  fi
  cp "$src" "$dst"
  copied=$((copied + 1))
  echo "  install $dst"
}

echo "Installing into $DEST"
for f in "$SRC"/hooks/*; do [ -f "$f" ] || continue; install_file "$f" "$DEST/hooks/$(basename "$f")"; done
for f in "$SRC"/agents/*.md; do install_file "$f" "$DEST/agents/$(basename "$f")"; done
for d in "$SRC"/skills/*/; do
  name="$(basename "$d")"
  for f in "$d"*; do [ -f "$f" ] && install_file "$f" "$DEST/skills/$name/$(basename "$f")"; done
done

chmod +x "$DEST"/hooks/ai-kb-recall.py "$DEST"/hooks/ai-kb-status-line.py \
         "$DEST"/hooks/ai-kb-digest.sh "$DEST"/hooks/no-idle-promise.py
chmod +x "$DEST"/skills/session-handoff/save_handoff.py "$DEST"/skills/session-resume/read_latest_handoff.py

echo
echo "Done: $copied installed, $unchanged already up to date, $backed backed up."
echo "Next: merge $SRC/settings.example.json into $DEST/settings.json,"
echo "      and (optional) copy router/ROUTER.example.md to \$FLOWARA_AI_OS_ROOT/ROUTER.md"
echo "      and router/router_synonyms.example.json to \$FLOWARA_AI_OS_ROOT/ops/router_synonyms.json."
