# Apps Script — MTC Casilla Bot API

Web App de **solo lectura** que sirve los datos del Sheet "MTC Casilla DB" al frontend del bot. Diseñada para ser pública (`ANYONE_ANONYMOUS`) pero con la URL como secreto-ish (no googleable).

## Archivos

- **`Code.gs`** — endpoints `doGet` y handlers
- **`appsscript.json`** — manifest

## Setup paso a paso

### 1. Preparar el Sheet "MTC Casilla DB"

Crear un Google Sheet nuevo con tres tabs:

#### Tab `notificaciones`

Headers obligatorios en la **fila 1** (en este orden o cualquier orden, pero con estos nombres exactos):

```
id | timestamp_proceso | fecha_notificacion | ruc | empresa | documento | emisor | asunto | resumen | requiere_respuesta | plazo_dias_habiles | plazo_vencimiento | confianza_ia | modelo_ia | drive_file_id | drive_view_url | estado | notas
```

#### Tab `logs`

```
timestamp | nivel | ruc | mensaje | contexto_json
```

#### Tab `rucs` (NO exponer)

```
ruc | empresa | auth_method | dni_representante | password_casilla | sol_usuario | sol_clave | activo
```

> ⚠️ Restringí los permisos del Sheet: solo Yubert + el email del service account. No darle acceso de visualización a nadie más mientras `rucs` esté en el mismo Sheet.

### 2. Crear el proyecto Apps Script

1. Abrir https://script.google.com → **Nuevo proyecto**.
2. Renombrar a `MTC Casilla Bot API`.
3. Borrar el `Code.gs` por defecto y pegar el contenido de este archivo.
4. **File → Project settings → Show "appsscript.json" manifest file in editor** (toggle ON).
5. Reemplazar el `appsscript.json` con el de este repo.
6. En `Code.gs`, reemplazar `REEMPLAZAR_CON_TU_SHEET_ID` con el ID real del Sheet.
   - El ID está en la URL del Sheet: `https://docs.google.com/spreadsheets/d/<ESTE_ID>/edit`.

### 3. Probar localmente

En el editor de Apps Script:
1. Seleccionar la función `_testSummary` del dropdown.
2. Click en **Run**.
3. Autorizar permisos cuando pida (acceso al Sheet).
4. Revisar **Execution log** (Ctrl+Enter) — debería ver el JSON con métricas.

### 4. Deployar como Web App

1. Click **Deploy → New deployment**.
2. **Type:** Web app (icono engranaje).
3. **Description:** `MTC Bot API v1.0`
4. **Execute as:** Me (tu cuenta).
5. **Who has access:** Anyone (la URL es secreta).
6. Click **Deploy**.
7. **Copiar la URL** del Web App: `https://script.google.com/macros/s/AKfy.../exec`
8. Probar con `curl`:

```bash
curl "https://script.google.com/macros/s/AKfy.../exec?action=health"
# → {"ok":true,"ts":"2026-04-28T..."}

curl "https://script.google.com/macros/s/AKfy.../exec?action=summary"
# → {"total":0,"pendientes":0,...}
```

### 5. Pegar la URL en el frontend

En `frontend/app.js` reemplazar:

```js
const API_URL = 'https://script.google.com/macros/s/REEMPLAZAR_AQUI/exec';
```

### 6. (Opcional) Pegar la URL también en el bot Python

El bot Python NO necesita la API para escribir (escribe directo al Sheet con SA), pero podés pegarla en `.env` por si querés hacer health checks:

```bash
APPSCRIPT_API_URL=https://script.google.com/macros/s/.../exec
```

## Actualizar el Apps Script

Cada vez que modifiques `Code.gs`:

1. **Deploy → Manage deployments**
2. Click en el lápiz ✏️ del deployment activo.
3. **Version → New version**
4. Click **Deploy**.

> NO crear deployments NUEVOS cada vez — eso cambia la URL y rompe el frontend.

## Endpoints disponibles

| URL | Descripción |
|---|---|
| `?action=health` | Healthcheck |
| `?action=summary` | Métricas globales |
| `?action=list` | Todas las notificaciones |
| `?action=list&since=2026-04-01` | Desde fecha |
| `?action=list&ruc=20602194958` | Por RUC |
| `?action=list&estado=pendiente` | Por estado |
| `?action=list&requiere_respuesta=true&estado=pendiente` | Solo pendientes que requieren respuesta |
| `?action=detail&id=<notif_id>` | Detalle de una |
| `?action=pdf&id=<notif_id>` | Redirect al PDF en Drive |

## Troubleshooting

| Error | Causa | Fix |
|---|---|---|
| `"error":"unknown_action"` | Action mal escrito | Usar exactamente: `list`, `detail`, `summary`, `pdf`, `health` |
| `Authorization required` en logs | Permisos faltantes | Re-correr `_testSummary` y autorizar |
| `Service Spreadsheets failed` | SHEET_ID incorrecto | Verificar el ID en CONFIG |
| Header `id` no encontrado | Tab mal armado | Asegurar que la fila 1 tenga los headers exactos |
| Quota exceeded | Demasiados requests | Cache ya está activado (60s). Si persiste, subir TTL. |

## Logs

Los errores se escriben automáticamente en el tab `logs` del Sheet. Revisar ese tab si algo falla en producción.
