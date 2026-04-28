/**
 * ════════════════════════════════════════════════════════════════
 *  MTC Casilla Bot — Apps Script API REST
 * ────────────────────────────────────────────────────────────────
 *  Web App de SOLO LECTURA que sirve los datos del Sheet
 *  "MTC Casilla DB" al frontend HTML/JS.
 *
 *  El bot Python NO usa esta API; escribe directo al Sheet con
 *  service account.
 * ════════════════════════════════════════════════════════════════
 */

/* ────────── Config ────────── */
const CONFIG = Object.freeze({
  SHEET_ID: '1qX-_7atHYQV2iF7By-I6uJHOMohNMDwMvWBW58d6Vco',
  TAB_NOTIFICACIONES: 'notificaciones',
  TAB_LOGS: 'logs',
  CACHE_TTL_SECONDS: 60,
});

/* ────────── Entry point ────────── */
function doGet(e) {
  try {
    const action = (e.parameter.action || 'list').toLowerCase();

    switch (action) {
      case 'list':    return jsonResponse_(handleListCached_(e.parameter));
      case 'detail':  return jsonResponse_(handleDetail_(e.parameter));
      case 'summary': return jsonResponse_(handleSummaryCached_(e.parameter));
      case 'pdf':     return handlePdfRedirect_(e.parameter);
      case 'health':  return jsonResponse_({ ok: true, ts: new Date().toISOString() });
      default:
        return jsonResponse_({ error: 'unknown_action', action });
    }
  } catch (err) {
    logError_('doGet', err, e.parameter);
    return jsonResponse_({ error: 'internal', message: err.message });
  }
}

/* ────────── Handlers ────────── */

function handleList_(params) {
  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  if (rows.length < 2) return { items: [], total: 0 };

  const headers = rows[0];
  let data = rows.slice(1).map(r => rowToObject_(headers, r));

  if (params.since) {
    const since = new Date(params.since);
    data = data.filter(r => r.fecha_notificacion && new Date(r.fecha_notificacion) >= since);
  }
  if (params.until) {
    const until = new Date(params.until);
    data = data.filter(r => r.fecha_notificacion && new Date(r.fecha_notificacion) <= until);
  }
  if (params.ruc) {
    data = data.filter(r => String(r.ruc) === String(params.ruc));
  }
  if (params.estado) {
    data = data.filter(r => r.estado === params.estado);
  }
  if (params.requiere_respuesta === 'true') {
    data = data.filter(r =>
      r.requiere_respuesta === true ||
      String(r.requiere_respuesta).toUpperCase() === 'TRUE'
    );
  }

  // Días restantes
  const today = stripTime_(new Date());
  data.forEach(r => {
    if (r.plazo_vencimiento) {
      const venc = stripTime_(new Date(r.plazo_vencimiento));
      r.dias_restantes = Math.round((venc - today) / 86400000);
    }
  });

  // Orden: más reciente primero
  data.sort((a, b) =>
    new Date(b.fecha_notificacion || 0) - new Date(a.fecha_notificacion || 0)
  );

  const limit = Math.min(parseInt(params.limit || '100', 10), 500);
  const offset = parseInt(params.offset || '0', 10);

  return {
    items: data.slice(offset, offset + limit),
    total: data.length,
    limit, offset,
  };
}

function handleDetail_(params) {
  if (!params.id) return { error: 'falta_id' };
  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  const headers = rows[0];
  const idCol = headers.indexOf('id');
  if (idCol < 0) return { error: 'header_id_no_encontrado' };

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][idCol]) === String(params.id)) {
      return rowToObject_(headers, rows[i]);
    }
  }
  return { error: 'not_found', id: params.id };
}

function handleSummary_() {
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
      String(r.requiere_respuesta).toUpperCase() === 'TRUE' &&
      r.estado === 'pendiente'
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

function handlePdfRedirect_(params) {
  if (!params.id) return jsonResponse_({ error: 'falta_id' });
  const detail = handleDetail_(params);
  if (detail.error) return jsonResponse_(detail);
  if (!detail.drive_view_url) return jsonResponse_({ error: 'sin_pdf' });

  const html = '<!DOCTYPE html><html><head>' +
    '<meta http-equiv="refresh" content="0; url=' + detail.drive_view_url + '">' +
    '</head><body>Redirigiendo a Drive...</body></html>';
  return HtmlService.createHtmlOutput(html);
}

/* ────────── Cache wrappers ────────── */

function handleListCached_(params) {
  const cache = CacheService.getScriptCache();
  const key = 'list_' + JSON.stringify(params);
  const cached = cache.get(key);
  if (cached) return JSON.parse(cached);

  const result = handleList_(params);
  try {
    cache.put(key, JSON.stringify(result), CONFIG.CACHE_TTL_SECONDS);
  } catch (e) { /* payload > 100KB no cacheable, ignorar */ }
  return result;
}

function handleSummaryCached_() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('summary');
  if (cached) return JSON.parse(cached);

  const result = handleSummary_();
  cache.put('summary', JSON.stringify(result), CONFIG.CACHE_TTL_SECONDS);
  return result;
}

/* ────────── Helpers ────────── */

function jsonResponse_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function getNotifSheet_() {
  const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
  const sheet = ss.getSheetByName(CONFIG.TAB_NOTIFICACIONES);
  if (!sheet) {
    throw new Error('Tab "' + CONFIG.TAB_NOTIFICACIONES + '" no encontrado en el Sheet');
  }
  return sheet;
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
  try {
    const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
    const log = ss.getSheetByName(CONFIG.TAB_LOGS);
    if (log) {
      log.appendRow([
        new Date().toISOString(), 'ERROR', fn,
        err.message || String(err),
        JSON.stringify(params || {}),
      ]);
    }
  } catch (_) { /* no podemos hacer nada si falla el log */ }
}

/* ────────── Test functions (corren manualmente desde el editor) ────────── */

function _testList() {
  const result = handleList_({ since: '2026-01-01' });
  Logger.log('Total: ' + result.total);
  Logger.log('Primer item: ' + JSON.stringify(result.items[0]));
}

function _testSummary() {
  Logger.log(JSON.stringify(handleSummary_(), null, 2));
}
