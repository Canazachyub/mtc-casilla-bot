---
description: Ejecuta el bot end-to-end con dry-run primero, luego procesamiento real
allowed-tools:
  - Bash
---

# /run-bot

Ejecuta el flujo completo del bot MTC siguiendo la secuencia segura:

1. Validar configuración (`.env` y `data/credentials/rucs.csv`)
2. Correr `--dry-run` y mostrar resumen
3. **Esperar confirmación del usuario**
4. Si confirma, ejecutar el run real
5. Mostrar resumen de resultados

## Pasos

```bash
# 1. Verificar config
echo "▶ Verificando configuración..."
uv run mtc-bot doctor

# 2. Dry run
echo ""
echo "▶ Dry run: qué se procesaría..."
uv run mtc-bot run --dry-run --since today

# 3. PAUSA — preguntar al usuario si quiere proceder
echo ""
echo "═════════════════════════════════════════════════"
echo "  ¿Procedés con el run real? (responde sí/no)"
echo "═════════════════════════════════════════════════"
```

> Después de mostrar el dry-run, **NO ejecutar el run real automáticamente**. Esperar respuesta explícita del usuario. Si dice sí, correr `uv run mtc-bot run --since today`.

## Output esperado del dry-run

```
[12:34:56] ▶ Cargando configuración...
[12:34:56]   ✓ DEEPSEEK_API_KEY presente
[12:34:56]   ✓ GEMINI_API_KEY presente
[12:34:56]   ✓ Bóveda Obsidian: C:\...\RESOLVE (escribible)
[12:34:56]   ✓ 12 RUCs cargados (10 activos)
[12:34:57] ▶ DRY RUN — no se descargará ni escribirá nada
[12:34:57]   Procesando RUC 20602194958 (CITV ESPINAR)...
[12:35:02]   ✓ 2 notificaciones nuevas detectadas:
[12:35:02]     - CARTA N° 000476-CR-2026-SUTRAN (28-04-2026)
[12:35:02]     - OFICIO N° 1234-2026-MTC/DGAT (28-04-2026)
...
[12:36:15] ▶ Resumen total:
[12:36:15]   RUCs procesados: 10
[12:36:15]   Notificaciones nuevas: 7
[12:36:15]   Ya procesadas (skip): 3
[12:36:15]   Errores: 0
```
