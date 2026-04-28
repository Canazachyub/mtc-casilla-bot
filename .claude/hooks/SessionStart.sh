#!/bin/bash
# ──────────────────────────────────────────────────────────
# SessionStart.sh — corre al iniciar Claude Code
# Imprime un resumen breve del estado del proyecto.
# ──────────────────────────────────────────────────────────

echo "════════════════════════════════════════════════"
echo "  MTC Casilla Bot — sesión iniciada"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════"

# Mostrar última línea del decision log si existe
if [ -f "CLAUDE.md" ]; then
    echo ""
    echo "Estado actual (de CLAUDE.md sección 9):"
    awk '/## 9\. Estado actual/,/## 10\./' CLAUDE.md | head -20 | tail -n +2
fi

# Mostrar último commit
if [ -d ".git" ]; then
    echo ""
    echo "Último commit:"
    git log -1 --oneline 2>/dev/null
fi

echo "════════════════════════════════════════════════"
exit 0
