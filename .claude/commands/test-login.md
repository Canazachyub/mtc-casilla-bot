---
description: Prueba el login MTC para un RUC específico sin descargar nada
allowed-tools:
  - Bash
argument-hint: <ruc>
---

# /test-login

Smoke test del login. Útil para verificar que las credenciales de un RUC funcionan antes de un run completo.

## Argumentos

- `$1` = RUC a probar (ej: `20602194958`)

## Comportamiento

```bash
RUC="${1:?Falta el RUC. Uso: /test-login 20602194958}"

echo "▶ Probando login para RUC $RUC..."
echo ""

# Modo headed para ver qué pasa visualmente
MTC_BOT_HEADED=1 uv run mtc-bot test-login --ruc "$RUC"
```

## Resultado esperado

Si todo OK:
```
[15:42:01] ▶ Login para RUC 20602194958 (CITV ESPINAR)
[15:42:01]   método: direct
[15:42:01] ▶ Lanzando Chromium en modo headed...
[15:42:03] ▶ Llenando formulario...
[15:42:05] ▶ Submit...
[15:42:08] ✓ Login exitoso. URL post-login: .../recibidos
[15:42:08] ✓ Inbox visible con N notificaciones (sin procesarlas)
[15:42:09] ✓ Logout y cierre limpio
```

Si falla:
```
[15:42:08] ✗ Login falló: 'Usuario o contraseña incorrectos'
[15:42:08]   Trace guardada: playwright-traces/20602194958_20260428_154208.zip
[15:42:08]   Para revisarla: playwright show-trace playwright-traces/...
```

## Cuándo usarlo

- Después de actualizar credenciales en el CSV
- Cuando el portal MTC parece haber cambiado
- Al onboardear un RUC nuevo
- Cuando el run completo falla y querés aislar si es problema de auth o de otra etapa
