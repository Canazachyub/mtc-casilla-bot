---
description: Reprocesa una notificación ya procesada (re-extrae con IA, regenera nota)
allowed-tools:
  - Bash
argument-hint: <notification-id-o-ruta-pdf>
---

# /reprocess

Vuelve a analizar con IA y regenera la nota Obsidian para una notificación específica. Útil cuando:

- La extracción IA salió mal y querés reintentar (quizás cambió el modelo)
- Editaste el prompt de extracción y querés re-aplicarlo a una notificación vieja
- La nota Obsidian se perdió o corrompió

## Argumentos

- `$1` = ID de la notificación (del index) **o** path del PDF unido

## Comportamiento

```bash
TARGET="${1:?Falta target. Uso: /reprocess <id> o /reprocess <path-al-pdf>}"

uv run mtc-bot reprocess "$TARGET" --regenerate-note
```

## Lo que hace

1. Si recibe un ID: busca en `data/processed/index.json` el path del PDF.
2. Si recibe un path: lo usa directamente.
3. Re-extrae texto del PDF.
4. Llama a la IA (mismo flujo: DeepSeek primero, Gemini fallback).
5. **Hace backup** de la nota actual: `<nombre>.md.bak.<timestamp>`.
6. Regenera la nota con la nueva extracción.
7. Actualiza el índice.

## Output esperado

```
[16:01:00] ▶ Reprocesando: data/merged/20602194958/CARTA-N-000476-...
[16:01:00] ▶ Extrayendo texto del PDF...
[16:01:01] ▶ Llamando a DeepSeek...
[16:01:04] ✓ Extracción OK (confianza: alta)
[16:01:04] ▶ Backup de nota actual...
[16:01:04]   → 2026-04-28_CARTA-N-000476-...md.bak.20260428_160104
[16:01:04] ▶ Regenerando nota...
[16:01:04] ✓ Nota actualizada en bóveda Obsidian
[16:01:04] ▶ Diff de cambios:
            - plazo_dias_habiles: 5 → 5 (sin cambios)
            - resumen: <distinto>
            - acciones_requeridas: 1 → 2 ítems
```
