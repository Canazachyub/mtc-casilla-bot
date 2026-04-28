#!/bin/bash
# ──────────────────────────────────────────────────────────
# PreCompact.sh — corre antes de que Claude compacte el contexto
# Guarda un snapshot del estado actual en .claude/state-snapshot.md
# para que la siguiente sesión pueda recuperar contexto rápido.
# ──────────────────────────────────────────────────────────

SNAPSHOT="$CLAUDE_PROJECT_DIR/.claude/state-snapshot.md"

cat > "$SNAPSHOT" <<EOF
# Snapshot — $(date '+%Y-%m-%d %H:%M:%S')

## Último commit
$(git log -1 --oneline 2>/dev/null)

## Branch actual
$(git branch --show-current 2>/dev/null)

## Archivos modificados sin commitear
$(git status --short 2>/dev/null)

## Tests pasando (último run)
$(uv run pytest --tb=no -q 2>/dev/null | tail -3)
EOF

exit 0
