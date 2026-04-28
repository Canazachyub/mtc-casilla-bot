---
description: Arranca el dashboard local FastAPI en 127.0.0.1:8765
allowed-tools:
  - Bash
---

# /serve

Levanta el servidor FastAPI con el dashboard de notificaciones procesadas.

## Comportamiento

```bash
echo "▶ Iniciando dashboard en http://127.0.0.1:8765"
echo "  (Ctrl+C para detener)"
echo ""
uv run mtc-bot serve --host 127.0.0.1 --port 8765
```

## Lo que ofrece el dashboard

- **Lista** de todas las notificaciones procesadas (filtros por RUC, fecha, estado, plazo)
- **Detalle** de cada notificación con PDF embebido
- **Indicador visual** del plazo: 🟢 >5 días | 🟡 3-5 días | 🟠 1-2 días | 🔴 vencido
- **Estado del último run** (logs, errores, tiempos)
- **Botones** para reprocesar o re-descargar
- **Búsqueda** full-text en el contenido de las notificaciones

## Restricciones de seguridad

- ⚠️ El servidor SOLO escucha en `127.0.0.1`. NO es accesible desde la red local.
- ⚠️ NO hay autenticación: queda protegido solo por estar bound a localhost.
- ⚠️ Si se necesita acceso remoto, usar SSH tunnel: `ssh -L 8765:127.0.0.1:8765 usuario@host`.
