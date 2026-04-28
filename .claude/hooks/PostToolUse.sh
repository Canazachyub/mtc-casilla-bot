#!/bin/bash
# ──────────────────────────────────────────────────────────
# PostToolUse.sh — corre tras cada Edit/Write
# Aplica ruff format + ruff check --fix solo a archivos Python
# en src/ y tests/. No falla la operación si ruff no está.
# ──────────────────────────────────────────────────────────

set +e  # no fallar el hook por errores menores

# Solo correr si hay cambios recientes en .py dentro de src/ o tests/
if [ -d "src" ] || [ -d "tests" ]; then
    if command -v uv &> /dev/null; then
        uv run ruff format src tests 2>/dev/null
        uv run ruff check --fix src tests 2>/dev/null
    elif command -v ruff &> /dev/null; then
        ruff format src tests 2>/dev/null
        ruff check --fix src tests 2>/dev/null
    fi
fi

exit 0
