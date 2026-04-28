---
name: appscript-api
description: |
  Workflow para construir y mantener la Web App de Apps Script que sirve como
  API REST para el frontend del bot MTC. Activá esta skill cuando se mencione:
  Apps Script Web App, doGet, doPost, deployar Apps Script, endpoint REST de
  notificaciones MTC, CORS Apps Script, frontend que consume el Sheet,
  Code.gs del bot. NO usar para uploads desde Python (eso usa drive-uploader).
---

# Skill: Apps Script API

## Propósito

Servir como **API REST de SOLO LECTURA** para el frontend (HTML/JS estático en `localhost` o GitHub Pages). El bot Python NO usa esta API; escribe directo al Sheet con service account.

## Endpoints

| Método | Action | Descripción |
|---|---|---|
| GET | `?action=list&since=YYYY-MM-DD&ruc=...&estado=...` | Lista notificaciones con filtros |
| GET | `?action=detail&id=<notif_id>` | Detalle completo de una notificación |
| GET | `?action=summary` | Métricas: pendientes, vencidos, total mes |
| GET | `?action=pdf&id=<notif_id>` | Redirect 302 al Drive viewer del PDF |
| GET | `?action=health` | Healthcheck simple |

> Diseño SOLO LECTURA. Si en el futuro hace falta editar (ej: marcar como completado), agregar `doPost` con auth por token.

## Estructura del proyecto Apps Script

```
appscript/
├── Code.gs                  ← endpoints + helpers
├── Config.gs                ← constantes (Sheet ID, tabs, etc.)
├── Auth.gs                  ← (opcional) validación de token si se agrega POST
└── appsscript.json          ← manifest
```

## Code.gs (esqueleto)

```javascript
/**
 * MTC Casilla Bot — Apps Script API REST
 * Web App deployada como /exec, ejecuta como "yo", acceso "cualquiera con el enlace".
 */

function doGet(e) {
  try {
    const action = (e.parameter.action || 'list').toLowerCase();

    switch (action) {
      case 'list':    return jsonResponse(handleList(e.parameter));
      case 'detail':  return jsonResponse(handleDetail(e.parameter));
      case 'summary': return jsonResponse(handleSummary(e.parameter));
      case 'pdf':     return handlePdfRedirect(e.parameter);
      case 'health':  return jsonResponse({ ok: true, ts: new Date().toISOString() });
      default:
        return jsonResponse({ error: 'unknown_action', action }, 400);
    }
  } catch (err) {
    logError_('doGet', err, e.parameter);
    return jsonResponse({ error: 'internal', message: err.message }, 500);
  }
}

/* ────────────── List ────────────── */

function handleList(params) {
  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  if (rows.length < 2) return { items: [], total: 0 };

  const headers = rows[0];
  const data = rows.slice(1).map(r => rowToObject_(headers, r));

  // Filtros
  let filtered = data;
  if (params.since) {
    const since = new Date(params.since);
    filtered = filtered.filter(r => new Date(r.fecha_notificacion) >= since);
  }
  if (params.until) {
    const until = new Date(params.until);
    filtered = filtered.filter(r => new Date(r.fecha_notificacion) <= until);
  }
  if (params.ruc) {
    filtered = filtered.filter(r => String(r.ruc) === String(params.ruc));
  }
  if (params.estado) {
    filtered = filtered.filter(r => r.estado === params.estado);
  }
  if (params.requiere_respuesta === 'true') {
    filtered = filtered.filter(r => r.requiere_respuesta === true || r.requiere_respuesta === 'TRUE');
  }

  // Calcular días restantes
  const today = stripTime_(new Date());
  filtered.forEach(r => {
    if (r.plazo_vencimiento) {
      const venc = stripTime_(new Date(r.plazo_vencimiento));
      r.dias_restantes = Math.round((venc - today) / 86400000);
    }
  });

  // Orden por defecto: más reciente primero
  filtered.sort((a, b) => new Date(b.fecha_notificacion) - new Date(a.fecha_notificacion));

  // Paginación
  const limit = Math.min(parseInt(params.limit || '100', 10), 500);
  const offset = parseInt(params.offset || '0', 10);

  return {
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    limit, offset,
  };
}

/* ────────────── Detail ────────────── */

function handleDetail(params) {
  if (!params.id) throw new Error('Falta id');
  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  const headers = rows[0];
  const idCol = headers.indexOf('id');
  if (idCol < 0) throw new Error('Header "id" no encontrado en el Sheet');

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][idCol]) === String(params.id)) {
      return rowToObject_(headers, rows[i]);
    }
  }
  return { error: 'not_found', id: params.id };
}

/* ────────────── Summary ────────────── */

function handleSummary(params) {
  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  if (rows.length < 2) return { total: 0, pendientes: 0, vencidos: 0, hoy: 0 };

  const headers = rows[0];
  const data = rows.slice(1).map(r => rowToObject_(headers, r));
  const today = stripTime_(new Date());
  const todayStr = today.toISOString().slice(0, 10);

  return {
    total: data.length,
    pendientes: data.filter(r =>
      String(r.requiere_respuesta).toUpperCase() === 'TRUE' && r.estado === 'pendiente'
    ).length,
    vencidos: data.filter(r => {
      if (!r.plazo_vencimiento || r.estado === 'completado') return false;
      return new Date(r.plazo_vencimiento) < today;
    }).length,
    hoy: data.filter(r => String(r.fecha_notificacion).startsWith(todayStr)).length,
    por_ruc: groupBy_(data, 'ruc'),
    por_estado: groupBy_(data, 'estado'),
  };
}

/* ────────────── PDF redirect ────────────── */

function handlePdfRedirect(params) {
  if (!params.id) {
    return jsonResponse({ error: 'falta_id' }, 400);
  }
  const detail = handleDetail(params);
  if (detail.error) {
    return jsonResponse(detail, 404);
  }
  if (!detail.drive_view_url) {
    return jsonResponse({ error: 'sin_pdf' }, 404);
  }
  // Apps Script no soporta 302 directo, usamos meta refresh
  const html = `<!DOCTYPE html><html><head>
    <meta http-equiv="refresh" content="0; url=${detail.drive_view_url}">
    </head><body>Redirigiendo a Drive...</body></html>`;
  return HtmlService.createHtmlOutput(html);
}

/* ────────────── Helpers ────────────── */

function jsonResponse(payload, status) {
  // Apps Script no tiene status codes en doGet; el cliente debe leer payload.error
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function getNotifSheet_() {
  return SpreadsheetApp.openById(CONFIG.SHEET_ID).getSheetByName(CONFIG.TAB_NOTIFICACIONES);
}

function rowToObject_(headers, row) {
  const obj = {};
  headers.forEach((h, i) => {
    let v = row[i];
    if (v instanceof Date) v = v.toISOString();
    obj[h] = v;
  });
  return obj;
}

function stripTime_(d) {
  const r = new Date(d);
  r.setHours(0, 0, 0, 0);
  return r;
}

function groupBy_(arr, key) {
  return arr.reduce((acc, r) => {
    const k = String(r[key] || '(sin valor)');
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
}

function logError_(fn, err, params) {
  const logSheet = SpreadsheetApp.openById(CONFIG.SHEET_ID).getSheetByName(CONFIG.TAB_LOGS);
  if (logSheet) {
    logSheet.appendRow([
      new Date().toISOString(), 'ERROR', fn, err.message,
      JSON.stringify(params || {}),
    ]);
  }
}
```

## Config.gs

```javascript
const CONFIG = Object.freeze({
  SHEET_ID: 'REEMPLAZAR_CON_TU_SHEET_ID',
  TAB_NOTIFICACIONES: 'notificaciones',
  TAB_LOGS: 'logs',
  TAB_RUCS: 'rucs',  // NO exponer al frontend; solo lectura interna
});
```

## appsscript.json

```json
{
  "timeZone": "America/Lima",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "webapp": {
    "executeAs": "USER_DEPLOYING",
    "access": "ANYONE_ANONYMOUS"
  },
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/script.external_request"
  ]
}
```

> ⚠️ `executeAs: USER_DEPLOYING` significa que la API corre con permisos del que deployó. El frontend público NO tiene acceso al Sheet directamente, solo via esta API. Esto es correcto.

## Deployment (proceso manual del usuario)

1. Abrir https://script.google.com → Nuevo proyecto.
2. Pegar `Code.gs` y `Config.gs`.
3. Reemplazar `SHEET_ID` con el ID real.
4. **File → Project properties → Time zone:** `America/Lima`.
5. **Deploy → New deployment → Type: Web app**:
   - Description: `MTC Bot API v1`
   - Execute as: **Me**
   - Who has access: **Anyone** (la URL es secreta-ish; es como una API key)
6. Autorizar permisos al Sheet.
7. Copiar la **URL del Web App** (`https://script.google.com/macros/s/.../exec`).
8. Pegarla en `frontend/app.js` como `API_URL`.

> Cada vez que cambies `Code.gs`, hacer **Deploy → Manage deployments → Edit (lápiz) → New version → Deploy**. NO crear deployments nuevos cada vez (cambia la URL).

## Performance y quotas

- **Cuota:** 6 minutos por ejecución, ~30k requests/día (suficiente para uso interno).
- **Cache layer recomendado:** envolver `handleList` y `handleSummary` con `CacheService` (ttl 60s) si el Sheet crece a >1000 filas:

```javascript
function handleListCached(params) {
  const cache = CacheService.getScriptCache();
  const key = 'list_' + Object.entries(params).map(([k,v]) => `${k}=${v}`).join('&');
  const cached = cache.get(key);
  if (cached) return JSON.parse(cached);

  const result = handleList(params);
  cache.put(key, JSON.stringify(result), 60);  // 60 segundos
  return result;
}
```

## CORS

Apps Script Web Apps **NO permiten configurar headers CORS arbitrarios**. Pero las respuestas con `executeAs: USER_DEPLOYING + access: ANYONE_ANONYMOUS` ya tienen `Access-Control-Allow-Origin: *` por default. Funciona para frontends estáticos.

Si el frontend está en `localhost:5173` (Vite) o `localhost:8000` (Python `http.server`), funciona.

## Validación de seguridad

Antes de declarar la API lista:

- [ ] `Config.gs` NO contiene credenciales sensibles, solo IDs (que están protegidos por permisos del Sheet)
- [ ] El Sheet `rucs` (con credenciales) **nunca** se expone via algún endpoint
- [ ] Logs en el Sheet NO contienen contraseñas (filtro previo en Python)
- [ ] El Web App está accesible solo via su URL única (no es googleable)
- [ ] Si en el futuro hay `doPost`, requerir un token `X-Bot-Token` validado contra `PropertiesService.getScriptProperties()`

## Test manual de la API

```bash
# Health check
curl "https://script.google.com/macros/s/.../exec?action=health"

# Listar últimas 7 días
curl "https://script.google.com/macros/s/.../exec?action=list&since=2026-04-21" | jq

# Detalle
curl "https://script.google.com/macros/s/.../exec?action=detail&id=20602194958__12345" | jq

# Summary
curl "https://script.google.com/macros/s/.../exec?action=summary" | jq
```
