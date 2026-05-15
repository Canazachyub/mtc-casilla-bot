/**
 * ════════════════════════════════════════════════════════════════
 *  MTC Casilla Bot — Apps Script API REST  v2.0 (Fase 2)
 * ────────────────────────────────────────────────────────────────
 *  Nuevos endpoints: templates, update_status, generate_response
 *
 *  SETUP requerido (una sola vez):
 *  1. Apps Script → Configuración del proyecto → Propiedades de script
 *     Agregar: DEEPSEEK_API_KEY = sk-xxxxxxxxxxxx
 *  2. Ejecutar _setupPlantillas() desde el editor para crear el tab
 *  3. Redesplegar el Web App (Nueva versión)
 * ════════════════════════════════════════════════════════════════
 */

/* ────────── Config ────────── */
const CONFIG = Object.freeze({
  SHEET_ID: '1qX-_7atHYQV2iF7By-I6uJHOMohNMDwMvWBW58d6Vco',
  TAB_NOTIFICACIONES: 'notificaciones',
  TAB_LOGS: 'logs',
  TAB_PLANTILLAS: 'plantillas',
  CACHE_TTL_SECONDS: 60,
  ALLOWED_ESTADOS:  ['pendiente', 'en-proceso', 'completado', 'informativo', 'archivada'],
  ALLOWED_PROGRESO: ['NO INICIADO', 'AGENDAR', 'EN REVISIÓN', 'PRESENTADO'],
});

/* ────────── Entry point ────────── */
function doGet(e) {
  try {
    const action = (e.parameter.action || 'list').toLowerCase();
    switch (action) {
      case 'list':              return jsonResponse_(handleListCached_(e.parameter));
      case 'detail':            return jsonResponse_(handleDetail_(e.parameter));
      case 'summary':           return jsonResponse_(handleSummaryCached_());
      case 'templates':         return jsonResponse_(handleTemplates_());
      case 'get_template':      return jsonResponse_(handleGetTemplate_(e.parameter));
      case 'update_status':     return jsonResponse_(handleUpdateStatus_(e.parameter));
      case 'generate_response': return jsonResponse_(handleGenerateResponse_(e.parameter));
      case 'pdf':               return handlePdfRedirect_(e.parameter);
      case 'health':            return jsonResponse_({ ok: true, ts: new Date().toISOString() });
      default:                  return jsonResponse_({ error: 'unknown_action', action });
    }
  } catch (err) {
    logError_('doGet', err, e.parameter);
    return jsonResponse_({ error: 'internal', message: err.message });
  }
}

/* ────────── Handlers existentes ────────── */

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
  if (params.ruc)           data = data.filter(r => String(r.ruc) === String(params.ruc));
  if (params.estado)        data = data.filter(r => r.estado === params.estado);
  if (params.sede)          data = data.filter(r => r.sede === params.sede);
  if (params.progreso)      data = data.filter(r => r.progreso === params.progreso);
  if (params.casilla_origen) data = data.filter(r => r.casilla_origen === params.casilla_origen);
  if (params.requiere_respuesta === 'true') {
    data = data.filter(r =>
      r.requiere_respuesta === true ||
      String(r.requiere_respuesta).toUpperCase() === 'TRUE'
    );
  }

  const today = stripTime_(new Date());
  data.forEach(r => {
    if (r.plazo_vencimiento) {
      const venc = stripTime_(new Date(r.plazo_vencimiento));
      r.dias_restantes = Math.round((venc - today) / 86400000);
    }
    // plazo_vencido: venció y no está PRESENTADO
    r.plazo_vencido = !!(
      r.plazo_vencimiento &&
      stripTime_(new Date(r.plazo_vencimiento)) < today &&
      r.progreso !== 'PRESENTADO'
    );
  });

  data.sort((a, b) =>
    new Date(b.fecha_notificacion || 0) - new Date(a.fecha_notificacion || 0)
  );

  const limit  = Math.min(parseInt(params.limit  || '200', 10), 500);
  const offset = parseInt(params.offset || '0', 10);

  return { items: data.slice(offset, offset + limit), total: data.length, limit, offset };
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
      const obj = rowToObject_(headers, rows[i]);
      if (obj.plazo_vencimiento) {
        const venc = stripTime_(new Date(obj.plazo_vencimiento));
        obj.dias_restantes = Math.round((venc - stripTime_(new Date())) / 86400000);
      }
      return obj;
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
      r.progreso === 'NO INICIADO' || r.progreso === 'AGENDAR'
    ).length,
    vencidos: data.filter(r => {
      if (!r.plazo_vencimiento || r.progreso === 'PRESENTADO') return false;
      return new Date(r.plazo_vencimiento) < today;
    }).length,
    hoy: data.filter(r => String(r.fecha_notificacion).startsWith(todayStr)).length,
    por_ruc: groupBy_(data, 'ruc'),
    por_estado: groupBy_(data, 'estado'),
    por_progreso: groupBy_(data, 'progreso'),
    por_sede: groupBy_(data, 'sede'),
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

/* ────────── Nuevos handlers v2 ────────── */

function handleTemplates_() {
  const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
  const sheet = ss.getSheetByName(CONFIG.TAB_PLANTILLAS);
  if (!sheet) return { templates: [], setup_required: true,
    mensaje: 'Ejecutar _setupPlantillas() en el editor de Apps Script' };

  const rows = sheet.getDataRange().getValues();
  if (rows.length < 2) return { templates: [] };

  const headers = rows[0];
  const templates = rows.slice(1)
    .map(r => rowToObject_(headers, r))
    .filter(t => String(t.activo).toUpperCase() === 'TRUE')
    .map(t => ({ id: t.id, nombre: t.nombre, descripcion: t.descripcion || '',
                 tipo_notificacion: t.tipo_notificacion || 'general' }));

  return { templates };
}

function handleGetTemplate_(params) {
  if (!params.id) return { error: 'falta_id' };

  const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
  const sheet = ss.getSheetByName(CONFIG.TAB_PLANTILLAS);
  if (!sheet) return { error: 'tab_plantillas_no_encontrado' };

  const rows = sheet.getDataRange().getValues();
  const headers = rows[0];
  const idCol = headers.indexOf('id');
  if (idCol < 0) return { error: 'columna_id_no_encontrada' };

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][idCol]) === String(params.id)) {
      return rowToObject_(headers, rows[i]);
    }
  }
  return { error: 'not_found', id: params.id };
}

function handleUpdateStatus_(params) {
  const { id } = params;
  if (!id) return { error: 'falta_id' };

  // Soporte genérico: campo=X&valor=Y
  // Compatibilidad hacia atrás: ?estado=X o ?progreso=X
  let campo = params.campo;
  let valor = params.valor !== undefined ? params.valor : null;

  if (!campo) {
    if (params.progreso !== undefined) { campo = 'progreso'; valor = params.progreso; }
    else if (params.estado !== undefined) { campo = 'estado'; valor = params.estado; }
  }
  if (campo === 'progreso' && valor === null && params.progreso) valor = params.progreso;
  if (campo === 'estado'   && valor === null && params.estado)   valor = params.estado;

  if (!campo) return { error: 'falta_campo', hint: 'Enviar campo=progreso|estado|notas y valor=X' };
  if (valor === null || valor === undefined) return { error: 'falta_valor' };

  const CAMPOS_EDITABLES = ['estado', 'progreso', 'notas', 'tarea'];
  if (!CAMPOS_EDITABLES.includes(campo))
    return { error: 'campo_no_editable', allowed: CAMPOS_EDITABLES };

  if (campo === 'progreso' && !CONFIG.ALLOWED_PROGRESO.includes(valor))
    return { error: 'progreso_invalido', allowed: CONFIG.ALLOWED_PROGRESO };
  if (campo === 'estado' && !CONFIG.ALLOWED_ESTADOS.includes(valor))
    return { error: 'estado_invalido', allowed: CONFIG.ALLOWED_ESTADOS };

  const sheet = getNotifSheet_();
  const rows = sheet.getDataRange().getValues();
  const headers = rows[0];
  const idCol    = headers.indexOf('id');
  const campoCol = headers.indexOf(campo);
  if (idCol    < 0) return { error: 'columna_id_no_encontrada' };
  if (campoCol < 0) return { error: 'columna_no_encontrada', campo };

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][idCol]) === String(id)) {
      sheet.getRange(i + 1, campoCol + 1).setValue(valor);

      const fechaCol = headers.indexOf('fecha_respuesta');
      if (fechaCol >= 0) {
        const hoy = Utilities.formatDate(new Date(), 'America/Lima', 'yyyy-MM-dd');
        if ((campo === 'estado' && (valor === 'completado' || valor === 'archivada')) ||
            (campo === 'progreso' && valor === 'PRESENTADO')) {
          sheet.getRange(i + 1, fechaCol + 1).setValue(hoy);
        }
      }

      CacheService.getScriptCache().remove('summary');
      return { ok: true, id, [campo]: valor };
    }
  }
  return { error: 'not_found', id };
}

function handleGenerateResponse_(params) {
  const { notification_id, template_id, justificacion } = params;
  if (!notification_id) return { error: 'falta_notification_id' };
  if (!template_id)     return { error: 'falta_template_id' };
  if (!justificacion || !justificacion.trim()) return { error: 'falta_justificacion' };

  const apiKey = PropertiesService.getScriptProperties().getProperty('DEEPSEEK_API_KEY');
  if (!apiKey) return {
    error: 'deepseek_key_no_configurada',
    mensaje: 'Ir a Apps Script → Configuración del proyecto → Propiedades de script → agregar DEEPSEEK_API_KEY'
  };

  const detail = handleDetail_({ id: notification_id });
  if (detail.error) return { error: 'notificacion_no_encontrada' };

  const template = handleGetTemplate_({ id: template_id });
  if (template.error) return { error: 'template_no_encontrado' };

  const prompt   = buildResponsePrompt_(detail, template.texto_plantilla || '', justificacion);
  const respuesta = callDeepSeek_(apiKey, prompt);

  return { ok: true, respuesta };
}

function buildResponsePrompt_(detail, templateText, justificacion) {
  const hoy  = Utilities.formatDate(new Date(), 'America/Lima', 'dd/MM/yyyy');
  const anio = new Date().getFullYear();

  return `Eres un asistente legal especializado en empresas CITV (Centros de Inspección Técnica Vehicular) peruanas supervisadas por SUTRAN y el MTC.

Tu tarea es completar una plantilla de carta oficial rellenando ÚNICAMENTE los valores entre [CORCHETES] con la información proporcionada.

DATOS DE LA NOTIFICACIÓN:
- Empresa: ${detail.empresa || ''}
- RUC: ${detail.ruc || ''}
- Sede: ${detail.sede || ''}
- Tipo documento: ${detail.tipo_documento || detail.documento || ''}
- Número documento: ${detail.numero_documento || ''}
- Referencia: ${detail.referencia || ''}
- Fecha notificación: ${detail.fecha_notificacion || ''}
- Emisor: ${detail.emisor || 'SUTRAN'}
- Casilla origen: ${detail.casilla_origen || 'MTC'}
- Asunto: ${detail.asunto || ''}
- Resumen: ${detail.resumen || ''}
- Tareas requeridas: ${detail.tarea || ''}
- Plazo vencimiento: ${detail.plazo_vencimiento || 'no especificado'}
- Fecha de hoy: ${hoy}
- Año actual: ${anio}

JUSTIFICACIÓN DEL REPRESENTANTE LEGAL (integrar con lenguaje jurídico formal):
${justificacion}

INSTRUCCIONES ESTRICTAS:
1. Rellena TODOS los [CORCHETES] usando los datos provistos
2. [EMPRESA] → "${detail.empresa || ''}"
3. [RUC] → "${detail.ruc || ''}"
4. [FECHA_HOY] → "${hoy}"
5. [ANIO] → "${anio}"
6. [JUSTIFICACION_REPRESENTANTE] → transforma la justificación en lenguaje jurídico formal peruano
7. [CIUDAD] → deduce de la empresa o usa "Lima"
8. [REPRESENTANTE_LEGAL] → si no conoces el nombre exacto, usar "[Nombre del Representante Legal]"
9. [NUMERO_RESPUESTA] → genera número apropiado (ej: 001)
10. NO modifiques texto fuera de los corchetes
11. Usa lenguaje jurídico formal peruano

PLANTILLA:
${templateText}

Devuelve únicamente el documento completo rellenado. Sin comentarios adicionales.`;
}

function callDeepSeek_(apiKey, prompt) {
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'Authorization': 'Bearer ' + apiKey },
    payload: JSON.stringify({
      model: 'deepseek-chat',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.3,
      max_tokens: 3000,
    }),
    muteHttpExceptions: true,
  };

  const resp = UrlFetchApp.fetch('https://api.deepseek.com/chat/completions', options);
  const code = resp.getResponseCode();
  const text = resp.getContentText();

  if (code !== 200) throw new Error('DeepSeek HTTP ' + code + ': ' + text.slice(0, 300));

  const data = JSON.parse(text);
  if (data.error) throw new Error('DeepSeek: ' + (data.error.message || JSON.stringify(data.error)));

  return data.choices[0].message.content;
}

/* ────────── Cache wrappers ────────── */

function handleListCached_(params) {
  const cache = CacheService.getScriptCache();
  const key = 'list_' + JSON.stringify(params);
  const cached = cache.get(key);
  if (cached) return JSON.parse(cached);

  const result = handleList_(params);
  try { cache.put(key, JSON.stringify(result), CONFIG.CACHE_TTL_SECONDS); } catch (e) {}
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
  if (!sheet) throw new Error('Tab "' + CONFIG.TAB_NOTIFICACIONES + '" no encontrado');
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
    if (log) log.appendRow([new Date().toISOString(), 'ERROR', fn,
      err.message || String(err), JSON.stringify(params || {})]);
  } catch (_) {}
}

/* ────────── Setup (ejecutar UNA VEZ desde el editor) ────────── */

function _setupPlantillas() {
  const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
  if (ss.getSheetByName(CONFIG.TAB_PLANTILLAS)) {
    Logger.log('Tab plantillas ya existe. Nada que hacer.');
    return;
  }

  const sheet = ss.insertSheet(CONFIG.TAB_PLANTILLAS);
  sheet.appendRow(['id', 'nombre', 'descripcion', 'tipo_notificacion', 'texto_plantilla', 'activo']);

  const PLANTILLAS = [
    ['carta-descargo', 'Carta de Descargo SUTRAN',
     'Descargo estándar ante cartas e informes de SUTRAN', 'carta',
`CARTA DE DESCARGO N° [NUMERO_RESPUESTA]-[ANIO]

[CIUDAD], [FECHA_HOY]

Señores
[EMISOR]
[CIUDAD]

ASUNTO: Descargo a [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO]

De nuestra especial consideración:

Por medio de la presente, [EMPRESA], con RUC N° [RUC], debidamente representada por [REPRESENTANTE_LEGAL], en calidad de Representante Legal; ante ustedes respetuosamente exponemos lo siguiente:

I. ANTECEDENTES

Con fecha [FECHA_NOTIFICACION] recibimos [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO], mediante la cual [ASUNTO].

II. FUNDAMENTOS DEL DESCARGO

[JUSTIFICACION_REPRESENTANTE]

III. CONCLUSIÓN

Por los fundamentos expuestos, solicitamos respetuosamente se tome en consideración nuestros descargos y se deje sin efecto las observaciones formuladas, dado que hemos acreditado el cumplimiento de las obligaciones exigidas.

Atentamente,

___________________________
[REPRESENTANTE_LEGAL]
Representante Legal
[EMPRESA]
RUC: [RUC]`, 'TRUE'],

    ['solicitud-expediente', 'Solicitud de Expediente',
     'Solicitar acceso al expediente o documentos relacionados', 'general',
`CARTA N° [NUMERO_RESPUESTA]-[ANIO]

[CIUDAD], [FECHA_HOY]

Señores
[EMISOR]

ASUNTO: Solicitud de acceso al expediente — [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO]

De nuestra especial consideración:

[EMPRESA], con RUC N° [RUC], representada por [REPRESENTANTE_LEGAL], se dirige ante ustedes para solicitar el acceso al expediente relacionado con [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO] de fecha [FECHA_NOTIFICACION].

FUNDAMENTOS:

[JUSTIFICACION_REPRESENTANTE]

Por lo expuesto, solicitamos respetuosamente se nos otorgue acceso al expediente indicado, a efectos de ejercer nuestro legítimo derecho de defensa dentro del plazo establecido.

Atentamente,

___________________________
[REPRESENTANTE_LEGAL]
Representante Legal
[EMPRESA]
RUC: [RUC]`, 'TRUE'],

    ['carta-cumplimiento', 'Carta de Cumplimiento',
     'Comunicar el cumplimiento de una resolución o disposición', 'resolucion',
`CARTA DE CUMPLIMIENTO N° [NUMERO_RESPUESTA]-[ANIO]

[CIUDAD], [FECHA_HOY]

Señores
[EMISOR]

ASUNTO: Cumplimiento de lo dispuesto en [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO]

De nuestra especial consideración:

En atención a [TIPO_DOCUMENTO] N° [NUMERO_DOCUMENTO] notificada con fecha [FECHA_NOTIFICACION], [EMPRESA], con RUC N° [RUC], comunicamos el cumplimiento de las disposiciones emitidas:

[JUSTIFICACION_REPRESENTANTE]

Adjuntamos la documentación sustentatoria correspondiente para su verificación y archivo.

Sin otro particular, quedamos a su entera disposición.

Atentamente,

___________________________
[REPRESENTANTE_LEGAL]
Representante Legal
[EMPRESA]
RUC: [RUC]`, 'TRUE'],
  ];

  PLANTILLAS.forEach(row => sheet.appendRow(row));

  sheet.getRange(1, 1, 1, 6).setBackground('#1e293b').setFontColor('#f1f5f9').setFontWeight('bold');
  sheet.setColumnWidth(5, 600);
  sheet.autoResizeColumns(1, 4);

  Logger.log('✅ Tab "plantillas" creado con ' + PLANTILLAS.length + ' plantillas de ejemplo.');
  Logger.log('Ahora redesplegá el Web App (Nueva versión) y configurá DEEPSEEK_API_KEY en Propiedades de script.');
}

/* ────────── Tests (ejecutar desde el editor) ────────── */

function _testList() {
  const result = handleList_({ since: '2026-01-01' });
  Logger.log('Total: ' + result.total);
  if (result.items.length) Logger.log('Primer item: ' + JSON.stringify(result.items[0]));
}

function _testSummary() {
  Logger.log(JSON.stringify(handleSummary_(), null, 2));
}

function _testTemplates() {
  Logger.log(JSON.stringify(handleTemplates_(), null, 2));
}

function _testUpdateStatus() {
  // Reemplazá con un ID real antes de ejecutar
  Logger.log(JSON.stringify(handleUpdateStatus_({ id: 'TEST_ID', estado: 'en-proceso' })));
}

/**
 * Ejecutar desde el editor para forzar autorización de UrlFetchApp.
 * Google pedirá el permiso "script.external_request" la primera vez.
 */
function _testUrlFetch() {
  const resp = UrlFetchApp.fetch('https://httpbin.org/get');
  Logger.log('OK: ' + resp.getResponseCode());
}

/**
 * Verificar que la API key de DeepSeek está configurada y funciona.
 */
function _testDeepSeekKey() {
  const apiKey = PropertiesService.getScriptProperties().getProperty('DEEPSEEK_API_KEY');
  if (!apiKey) { Logger.log('ERROR: DEEPSEEK_API_KEY no configurada'); return; }

  const resp = UrlFetchApp.fetch('https://api.deepseek.com/models', {
    headers: { 'Authorization': 'Bearer ' + apiKey },
    muteHttpExceptions: true,
  });
  Logger.log('DeepSeek status: ' + resp.getResponseCode());
  Logger.log(resp.getContentText().slice(0, 200));
}
