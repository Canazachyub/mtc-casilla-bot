/* ════════════════════════════════════════════════════════════════
   MTC Casilla Bot — Frontend v4
   Vistas: Tareas pendientes (agrupadas por empresa) + Todas
   API: Apps Script REST (localStorage: mtc_bot_api_url)
   ════════════════════════════════════════════════════════════════ */

const STORAGE_KEY    = 'mtc_bot_api_url';
const API_URL_PREFIX = 'https://script.google.com/macros/';
const DEFAULT_API_URL = 'https://script.google.com/macros/s/AKfycbznqF-CmlzlNs3IsnS7x0DUjQFeB1ObpxfwaCjUPz3L2r5JCBpSAlFV063xxo3EKZZ0/exec';
// URL del Redactor (app Streamlit que genera los Word). Cambiar acá si corre en otro host/puerto.
const REDACTOR_URL   = 'http://localhost:8501';

/* ──────────────────────────── Datos legales de empresas ───────── */
const EMPRESAS_LEGALES = {
  'CEDIJICA': {
    nombre: 'CEDIJICA',
    texto: 'CENTRO DE INSPECCIÓN TÉCNICA VEHICULAR CEDIJICA S.A.C., con RUC N° 20608210939, debidamente representado por JORGE LENIN QUISPE VILCHEZ Identificado con DNI N° 48986264 con domicilio legal en ubicado en la Avenida Sinchi Roca, Manzana I, Lote 08, Lgr. Asociación de Posesionarios Del Sector Pedregal, distrito de San Antonio, provincia de Huarochirí, departamento de Lima; con poder inscrito en la Partida Electrónica N° 14717580, del Registro de Personas Jurídicas de la Oficina Registral de Lima, de la Superintendencia Nacional de los Registros Públicos – SUNARP.',
  },
  'ESPINAR': {
    nombre: 'ESPINAR',
    texto: 'CENTRO DE INSPECCIONES TÉCNICAS VEHICULARES ESPINAR S.A.C., con RUC N° 20602194958, con domicilio legal en la calle Wiracocha N°100, distrito, provincia de Espinar y departamento del Cusco; debidamente representado por su Gerente General, Sr. Justo Pastor Sasari Quispe, identificado con el DNI 29697807; según poder inscrito en la Partida Electrónica N° 11109864 de la Zona Registral N°X – Sede Cusco, de la Oficina Registral de Espinar de la Superintendencia Nacional de Registros Públicos – SUNARP.',
  },
  'CHECK&GO': {
    nombre: 'CHECK&GO',
    texto: 'CHECK & GO S.A.C., con RUC N° 20520690094, con domicilio en Avenida El Parque, Asoc. de Vivienda La Planicie, distrito de San Juan de Lurigancho, provincia y departamento de Lima; debidamente representado por su Gerente MARIA TERESA CHOCARRO MARTINEZ Identificada con C.E. N° 001376147; cuyo poder obra inscrito en la Partida Electrónica N°12251656 de la Oficina Registral Lima Zona Registral N° IX – Sede Lima, de la Superintendencia Nacional de los Registros Públicos – SUNARP.',
  },
  'EMG': {
    nombre: 'EMG',
    texto: 'EMG DEL PERÚ S.A.C., con RUC N° 20608373293, con domicilio en Calle Ramón Castilla s/n, distrito de Sapallanga, provincia de Huancayo, departamento de Junín; debidamente representada por su Gerente General EDWIN DE LA CRUZ SALHUA, identificado con DNI N° 09597947, según nombramiento y facultades inscrita en la Partida Electrónica N° 11302016 del registro de Personas Jurídicas de la Zona Registral N° VIII – Sede Huancayo de la Superintendencia Nacional de los Registros Públicos – SUNARP.',
  },
  'GFG': {
    nombre: 'GFG',
    texto: 'FG LOGÍSTICA INTEGRAL VIA PERU S.A.C., con RUC N° 20613984900, con domicilio legal en Av. Santa Rosa Sub Lote 1-D Remanente– Fundo Tinajeras, Distrito De San Juan Bautista, Provincia De Huamanga Y Departamento De Ayacucho; debidamente representado por MARLENY EVANAN ORTIZ, identificado con D.N.I. N° 48618681; según poder inscrito en la Partida Electrónica N° 11189852 del registro de poderes de la Oficina Registral de Ayacucho de la Zona Registral N° XIV–Sede Ayacucho.',
  },
  'LIDERSUR ILAVE': {
    nombre: 'LIDERSUR ILAVE',
    texto: 'LIDER-SUR SERVICIOS MULTIPLES EIRL, con RUC N°20448179690, representado legalmente por Brenda Mariel Ojeda Manrique, identificada con D.N.I. N° 47776232, con poder inscrito en Partida Electrónica N°11091017 de la Oficina Registral Puno de la Zona Registral N° XIII, de la Superintendencia Nacional de los Registros Públicos – SUNARP, y autorizado mediante Resolución Directoral N° 010-2022-MTC/17.03, para operar como Centro de Inspección Técnica Vehicular Fijo con una (01) Línea de Inspección Técnica Vehicular Tipo Combinada, en el local ubicado en Avenida Panamericana Norte N° 487, distrito de Ilave, provincia de El Collao, departamento de Puno.',
  },
  'LIDERSUR LIMA': {
    nombre: 'LIDERSUR LIMA',
    texto: 'GRUPO LIDER SUR SERVICIOS MÚLTIPLES E.I.R.L. con RUC N° 20448179690, con domicilio en Av. Gerardo Unger N°3617, distrito de Independencia, provincia y departamento de Lima, debidamente representado por Brenda Mariel Ojeda Manrique, identificada con DNI N°47776232; cuyo poder obra inscrito en la Partida Electrónica N°11091017 de la Superintendencia Nacional de Registros Públicos-SUNARP, y autorizado mediante Resolución Directoral N° 010-2022-MTC/17.03, para operar como Centro de Inspección Técnica Vehicular Fijo con una (01) Línea de Inspección Técnica Vehicular Tipo Combinada.',
  },
  'LIDERSUR PUNO': {
    nombre: 'LIDERSUR PUNO',
    texto: 'GRUPO LIDER SUR REVISIONES TÉCNICAS E.I.R.L. con RUC N° 20609575230, con domicilio en Jr. Prolongación Arboleda Mz. Ñ, Lote 6 y 7 del Centro Poblado Salcedo, Parque Industrial de Puno, provincia y departamento de Puno, debidamente representado por Aimar Silva Vela, identificado con DNI N°78015846; cuyo poder obra inscrito en la Partida Electrónica N°11183337 de la Superintendencia Nacional de Registros Públicos-SUNARP.',
  },
  'LIDERSUR PUERTO': {
    nombre: 'LIDERSUR PUERTO',
    texto: 'GRUPO LIDER SUR REVISIONES TECNICAS E.I.R.L., con RUC N° 20609575230, debidamente representado por AIMAR SILVA VELA, identificado con DNI N°78015846; autorizado para operar mediante Resolución Directoral N° 379-2023-MTC/17.03, en Av. Andres Avelino Caceres Km. 6.5 La Pastora, Distrito Tambopata, Provincia Tambopata, Departamento de Madre de Dios.',
  },
  'FEDY': {
    nombre: 'FEDY',
    texto: 'REVISION TECNICA VEHICULAR GRUPO FEDY S.A.C., con RUC N° 20612501051, con domicilio legal en Av. Milton Cordova La Torre, distrito de Huanta, provincia de Huanta y departamento de Ayacucho; debidamente representado por su Gerente General, Sr. ELMER LOPEZ ROMAN, identificado con el DNI N° 42362480; según nombramiento y facultades inscritas en la Partida Electrónica N° 11182721 del registro de Personas Jurídicas de la Superintendencia Nacional de los Registros Públicos - SUNARP.',
  },
  'AUTOREAL': {
    nombre: 'AUTOREAL',
    texto: 'CENTRO DE INSPECCIÓN TÉCNICA VEHICULAR SERVICIOS GENERALES AUTO REAL E.I.R.L., con RUC N° 20565549392, debidamente representado por NORMA MARGARITA BAUTISTA POMA Identificada con DNI N° 09587028 y que, mediante Resolución Directoral N° 072-2022-MTC/17.03 de fecha 11 de febrero de 2022, se obtuvo autorización para operar como Centro de Inspección Técnica Vehicular Tipo Mixta en Mz. A Sub Lt 1 D Sector Equipamiento, distrito de Ventanilla, provincia Constitucional del Callao.',
  },
};

const ALLOWED_PROGRESO = ['NO INICIADO', 'AGENDAR', 'EN REVISIÓN', 'PRESENTADO'];
const PROGRESO_LABELS  = {
  'NO INICIADO': 'No iniciado',
  'AGENDAR':     'Agendar',
  'EN REVISIÓN': 'En revisión',
  'PRESENTADO':  'Presentado',
};
const PROGRESO_CSS = {
  'NO INICIADO': 'no-iniciado',
  'AGENDAR':     'agendar',
  'EN REVISIÓN': 'en-revision',
  'PRESENTADO':  'presentado',
};

const state = {
  apiUrl:  '',
  view:    'all',           // 'pending' | 'all'
  items:   [],
  filtered: [],
  templates: [],
  currentDetailId: null,
  currentDetail:   null,
  filters: {
    search: '', empresa: '', progreso: '',
    soloPendientes: false, since: '',
  },
};

/* ──────────────────────────── Config ──────────────────────────── */

function getStoredApiUrl() {
  try {
    const raw = (localStorage.getItem(STORAGE_KEY) || '').trim();
    return (!raw || raw.includes('REEMPLAZAR_AQUI')) ? DEFAULT_API_URL : raw;
  } catch { return DEFAULT_API_URL; }
}
function saveApiUrl(url)       { localStorage.setItem(STORAGE_KEY, url); }
function clearApiUrlAndReload(){ try { localStorage.removeItem(STORAGE_KEY); } catch {} location.reload(); }
function isValidApiUrl(url)    { return typeof url === 'string' && url.startsWith(API_URL_PREFIX); }

/* ──────────────────────────── API ─────────────────────────────── */

async function apiPost(action, body = {}) {
  if (!state.apiUrl) throw new Error('API_URL no configurada.');
  const resp = await fetch(state.apiUrl, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ action, ...body }),
    redirect: 'follow',
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (data.error) throw new Error(data.message || data.error);
  return data;
}

async function api(action, params = {}) {
  if (!state.apiUrl) throw new Error('API_URL no configurada.');
  const url = new URL(state.apiUrl);
  url.searchParams.set('action', action);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) url.searchParams.set(k, String(v));
  });
  const resp = await fetch(url.toString());
  if (!resp.ok) throw new Error(`HTTP ${resp.status} al llamar a ${action}`);
  const data = await resp.json();
  if (data.error) throw new Error(data.message || data.error);
  return data;
}

/* ──────────────────────────── Templates ───────────────────────── */

async function loadTemplates() {
  try {
    const data = await api('templates');
    state.templates = data.templates || [];
  } catch (err) {
    console.warn('Plantillas no disponibles:', err.message);
    state.templates = [];
  }
}

/* ──────────────────────────── Carga inicial ───────────────────── */

async function loadAll() {
  showLoading(true);
  hideErrorCard();

  try {
    const [summary, list] = await Promise.all([
      api('summary'),
      api('list', { limit: 500 }),
    ]);
    renderMetrics(summary);
    const apiItems    = list.items || [];
    const manualItems = loadManualTasks();
    const apiIds      = new Set(apiItems.map(i => i.id));
    state.items = [...manualItems.filter(m => !apiIds.has(m.id)), ...apiItems];
    populateEmpresaFilter(state.items);
    applyFilters();

    // Sincronizar docs de empresa desde el Sheet (para que funcione en cualquier navegador)
    syncEmpresaDocsFromApi();

    document.getElementById('last-update').textContent =
      'Actualizado ' + new Date().toLocaleTimeString('es-PE');
    document.getElementById('api-status').innerHTML =
      '<span class="ok">●</span> API conectada';
  } catch (err) {
    showErrorCard(err.message || String(err));
    document.getElementById('api-status').innerHTML =
      '<span class="ko">●</span> API desconectada';
  } finally {
    showLoading(false);
  }
}

/* ──────────────────────────── Métricas ────────────────────────── */

function renderMetrics(s) {
  document.getElementById('m-total').textContent     = s.total      ?? 0;
  document.getElementById('m-pendientes').textContent = s.pendientes ?? 0;
  document.getElementById('m-vencidos').textContent   = s.vencidos   ?? 0;

  // Empresas con items pendientes (calculado del lado cliente)
  const empresasActivas = new Set(
    state.items
      .filter(i => i.progreso !== 'PRESENTADO')
      .map(i => i.empresa)
      .filter(Boolean)
  );
  document.getElementById('m-empresas').textContent = empresasActivas.size || '—';
}

function populateEmpresaFilter(items) {
  const sel      = document.getElementById('filter-empresa');
  const empresas = [...new Set(items.map(i => i.empresa).filter(Boolean))].sort();
  sel.innerHTML  = '<option value="">Todas las empresas</option>' +
    empresas.map(e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`).join('');
}

/* ──────────────────────────── View tabs ───────────────────────── */

function switchView(viewId) {
  state.view = viewId;
  document.querySelectorAll('.view-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.view === viewId)
  );
  const allOnlyEls = document.querySelectorAll('.filter-all-only');
  allOnlyEls.forEach(el => {
    el.style.opacity = viewId === 'all' ? '1' : '0.4';
    el.style.pointerEvents = viewId === 'all' ? '' : 'none';
  });
  const filtersBar = document.getElementById('filters-bar');
  if (filtersBar) filtersBar.classList.toggle('hidden', viewId === 'empresas');
  document.getElementById('view-pending').classList.toggle('hidden', viewId !== 'pending');
  document.getElementById('view-all').classList.toggle('hidden', viewId !== 'all');
  document.getElementById('view-empresas').classList.toggle('hidden', viewId !== 'empresas');
  if (viewId === 'empresas') renderEmpresasView();
  else applyFilters();
}

/* ══════════════════════════════════════════════════════════════
   GESTIÓN DE EMPRESAS
   ══════════════════════════════════════════════════════════════ */

const DOCS_TEMPLATE = () => ({
  certificado_vigencia:    { nombre: 'Certificado de vigencia',           url: '', fecha: '' },
  acreditacion_supervisor: { nombre: 'Acreditación de supervisor',        url: '', fecha: '' },
  acreditacion_suplente:   { nombre: 'Acreditación de suplente',          url: '', fecha: '' },
  acreditacion_tecnico_1:  { nombre: 'Acreditación técnico 1',            url: '', fecha: '' },
  acreditacion_tecnico_2:  { nombre: 'Acreditación técnico 2',            url: '', fecha: '' },
  acreditacion_tecnico_3:  { nombre: 'Acreditación técnico 3',            url: '', fecha: '' },
  calibracion_semestral:   { nombre: 'Calibración semestral (6 meses)',   url: '', fecha: '' },
  calibracion_anual:       { nombre: 'Calibración anual',                 url: '', fecha: '' },
  poliza_seguros:          { nombre: 'Póliza de seguros',                 url: '', fecha: '' },
  dni_representante:       { nombre: 'DNI del representante legal',       url: '', fecha: '' },
  firma_representante:     { nombre: 'Firma del representante legal',     url: '', fecha: '' },
});

function loadEmpresasFromStorage() {
  try {
    const raw = localStorage.getItem('mtc_empresas');
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  // Seed inicial desde EMPRESAS_LEGALES
  const seed = {};
  Object.entries(EMPRESAS_LEGALES).forEach(([key, e]) => {
    seed[key] = {
      key,
      nombre:      e.nombre,
      descripcion: e.texto,
      ruc:         extractRuc(e.texto),
      sede:        '',
      activo:      true,
      auth_method: 'clave_sol',
      sol_usuario: '', sol_clave: '',
      dni_representante: '', password_casilla: '',
      documentos: DOCS_TEMPLATE(),
    };
  });
  saveEmpresasToStorage(seed);
  return seed;
}

function extractRuc(texto) {
  const m = texto.match(/RUC\s*N[°º]?\s*([\d]{11})/);
  return m ? m[1] : '';
}

function saveEmpresasToStorage(data) {
  localStorage.setItem('mtc_empresas', JSON.stringify(data));
}

function renderEmpresasView() {
  const empresas = loadEmpresasFromStorage();
  const list     = document.getElementById('empresas-list');
  if (!list) return;
  const keys = Object.keys(empresas);
  if (keys.length === 0) {
    list.innerHTML = '<p class="muted" style="padding:2rem">No hay empresas. Agregá la primera con el botón ➕.</p>';
    return;
  }
  list.innerHTML = keys.map(k => renderEmpresaCard(empresas[k])).join('');
  // Bind accordion toggles
  list.querySelectorAll('.empresa-card-header').forEach(h => {
    h.addEventListener('click', () => {
      const card = h.closest('.empresa-card');
      card.classList.toggle('open');
    });
  });
  // Bind description save
  list.querySelectorAll('.btn-save-desc').forEach(btn => {
    btn.addEventListener('click', () => {
      const key  = btn.dataset.key;
      const val  = document.getElementById(`desc-${key}`).value;
      const data = loadEmpresasFromStorage();
      data[key].descripcion = val;
      saveEmpresasToStorage(data);
      showToast('Descripción guardada', 'ok');
    });
  });
  // Bind: toggle link row
  list.querySelectorAll('.btn-link-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = document.getElementById(`dlink-${btn.dataset.key}-${btn.dataset.doc}`);
      if (row) row.classList.toggle('hidden');
    });
  });

  // Bind: save URL from link row
  list.querySelectorAll('.btn-save-doc-url').forEach(btn => {
    btn.addEventListener('click', () => {
      const { key, doc } = btn.dataset;
      const row       = document.getElementById(`dlink-${key}-${doc}`);
      const urlInput  = row?.querySelector('.doc-url-inline');
      const dateInput = row?.querySelector('.doc-date-inline');
      const data = loadEmpresasFromStorage();
      data[key].documentos[doc].url   = urlInput?.value.trim() || '';
      data[key].documentos[doc].fecha = dateInput?.value || '';
      saveEmpresasToStorage(data);
      showToast('Link guardado', 'ok');
      renderEmpresasView();
    });
  });

  // Bind: file upload
  list.querySelectorAll('.doc-file-input').forEach(input => {
    input.addEventListener('change', async function () {
      const file = this.files[0];
      if (!file) return;
      const { key, doc, nombre } = this.dataset;
      await handleDocUpload(key, doc, nombre, file);
    });
  });

  // Bind: preview PDF
  list.querySelectorAll('.btn-preview-doc').forEach(btn => {
    btn.addEventListener('click', () => openPdfPreview(btn.dataset.preview, btn.dataset.nombre));
  });
  // Bind edit empresa
  list.querySelectorAll('.btn-edit-empresa').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openEmpresaModal(btn.dataset.key);
    });
  });
  // Bind delete empresa
  list.querySelectorAll('.btn-delete-empresa').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      if (!confirm(`¿Eliminar la empresa "${btn.dataset.key}"?`)) return;
      const data = loadEmpresasFromStorage();
      delete data[btn.dataset.key];
      saveEmpresasToStorage(data);
      renderEmpresasView();
    });
  });
}

function extractDriveFileId(url) {
  if (!url) return null;
  const m = url.match(/\/d\/([a-zA-Z0-9_-]{25,})/);
  return m ? m[1] : null;
}

function renderDocCard(key, docKey, doc) {
  const hasUrl     = !!doc.url;
  const fileId     = extractDriveFileId(doc.url);
  const previewUrl = fileId ? `https://drive.google.com/file/d/${fileId}/preview` : '';
  const eKey = escapeHtml(key);
  const eDk  = escapeHtml(docKey);
  return `
    <div class="doc-card" id="dcard-${eKey}-${eDk}">
      <div class="doc-card-main">
        <div class="doc-card-info">
          <span class="doc-card-icon">${hasUrl ? '📄' : '📋'}</span>
          <div>
            <span class="doc-card-name">${escapeHtml(doc.nombre)}</span>
            ${doc.fecha ? `<span class="doc-card-date">⏰ Vence: ${escapeHtml(doc.fecha)}</span>` : '<span class="doc-card-date doc-sin-vence">Sin fecha de vencimiento</span>'}
          </div>
        </div>
        <div class="doc-card-right">
          <span class="doc-badge ${hasUrl ? 'badge-doc-ok' : 'badge-doc-pending'}">${hasUrl ? '✅ Subido' : '⏳ Pendiente'}</span>
          <div class="doc-card-btns">
            ${previewUrl ? `<button class="btn-doc-action btn-preview-doc" data-preview="${escapeHtml(previewUrl)}" data-nombre="${escapeHtml(doc.nombre)}">👁 Ver</button>` : ''}
            <label class="btn-doc-action btn-upload-label">
              ${hasUrl ? '🔄 Actualizar' : '📎 Subir PDF'}
              <input type="file" class="file-input-hidden doc-file-input" accept="application/pdf"
                data-key="${eKey}" data-doc="${eDk}" data-nombre="${escapeHtml(doc.nombre)}">
            </label>
            <button class="btn-doc-action btn-link-toggle" data-key="${eKey}" data-doc="${eDk}" title="Pegar link">🔗</button>
          </div>
        </div>
      </div>
      <div class="doc-link-row hidden" id="dlink-${eKey}-${eDk}">
        <input type="url" class="doc-url-inline" placeholder="https://drive.google.com/file/d/..." value="${escapeHtml(doc.url || '')}">
        <input type="date" class="doc-date-inline" value="${escapeHtml(doc.fecha || '')}" title="Fecha de vencimiento del documento" placeholder="Vencimiento">
        <button class="btn-doc-action btn-save-doc-url" data-key="${eKey}" data-doc="${eDk}">💾 Guardar</button>
      </div>
      <div class="doc-upload-progress hidden" id="dprog-${eKey}-${eDk}">
        <span class="spinner-inline"></span> Subiendo a Drive...
      </div>
    </div>`;
}

function renderEmpresaCard(e) {
  const docsHtml = Object.entries(e.documentos).map(([docKey, doc]) =>
    renderDocCard(e.key, docKey, doc)
  ).join('');

  const authBadge = e.auth_method === 'direct'
    ? '<span class="badge-auth badge-direct">Directo</span>'
    : '<span class="badge-auth badge-sol">Clave SOL</span>';

  const docsOk      = Object.values(e.documentos).filter(d => d.url).length;
  const docsTotal   = Object.keys(e.documentos).length;
  const docProgress = `${docsOk}/${docsTotal} docs`;

  return `
    <div class="empresa-card" data-key="${escapeHtml(e.key)}">
      <div class="empresa-card-header">
        <div class="empresa-card-left">
          <span class="empresa-activo-dot ${e.activo ? 'dot-on' : 'dot-off'}"></span>
          <div>
            <strong class="empresa-card-name">${escapeHtml(e.nombre)}</strong>
            <span class="empresa-card-meta">RUC ${escapeHtml(e.ruc || '—')} · ${authBadge} · ${docProgress}</span>
          </div>
        </div>
        <div class="empresa-card-actions">
          <button class="btn-edit-empresa btn-icon" data-key="${escapeHtml(e.key)}" title="Editar empresa">✏️</button>
          <button class="btn-delete-empresa btn-icon" data-key="${escapeHtml(e.key)}" title="Eliminar">🗑</button>
          <span class="empresa-chevron">▸</span>
        </div>
      </div>
      <div class="empresa-card-body">
        <div class="empresa-body-grid">
          <div class="empresa-body-left">
            <label class="form-label">Descripción / personería jurídica</label>
            <textarea id="desc-${escapeHtml(e.key)}" class="response-textarea empresa-desc-textarea" rows="6">${escapeHtml(e.descripcion || '')}</textarea>
            <button class="btn-secondary btn-save-desc" data-key="${escapeHtml(e.key)}" style="margin-top:0.5rem">💾 Guardar descripción</button>
          </div>
          <div class="empresa-body-right">
            <label class="form-label">Documentación requerida</label>
            <div class="docs-list">${docsHtml}</div>
          </div>
        </div>
      </div>
    </div>`;
}

function openEmpresaModal(key) {
  const data    = key ? loadEmpresasFromStorage()[key] : null;
  const modal   = document.getElementById('modal-empresa');
  const title   = document.getElementById('modal-empresa-title');
  title.textContent = key ? `Editar — ${key}` : 'Nueva Empresa';

  document.getElementById('fe-key').value         = key || '';
  document.getElementById('fe-key').disabled      = !!key;
  document.getElementById('fe-ruc').value         = data?.ruc || '';
  document.getElementById('fe-nombre').value      = data?.nombre || '';
  document.getElementById('fe-descripcion').value = data?.descripcion || '';
  document.getElementById('fe-sede').value        = data?.sede || '';
  document.getElementById('fe-activo').checked    = data ? data.activo : true;
  document.getElementById('fe-auth').value        = data?.auth_method || 'clave_sol';
  document.getElementById('fe-sol-user').value    = data?.sol_usuario || '';
  document.getElementById('fe-sol-clave').value   = data?.sol_clave || '';
  document.getElementById('fe-dni').value         = data?.dni_representante || '';
  document.getElementById('fe-pass').value        = data?.password_casilla || '';

  toggleCredsSection(document.getElementById('fe-auth').value);
  modal.classList.remove('hidden');
}

function toggleCredsSection(method) {
  document.getElementById('fe-creds-direct').classList.toggle('hidden', method !== 'direct');
  document.getElementById('fe-creds-sol').classList.toggle('hidden', method !== 'clave_sol');
}

async function handleDocUpload(empresaKey, docKey, docNombre, file) {
  const MAX_MB = 25;
  if (file.size > MAX_MB * 1024 * 1024) {
    showToast(`El PDF supera ${MAX_MB}MB`, 'warn');
    return;
  }
  const progressEl = document.getElementById(`dprog-${empresaKey}-${docKey}`);
  if (progressEl) progressEl.classList.remove('hidden');

  try {
    const base64 = await new Promise((res, rej) => {
      const reader = new FileReader();
      reader.onload  = ev => res(ev.target.result.split(',')[1]);
      reader.onerror = () => rej(new Error('Error al leer el archivo'));
      reader.readAsDataURL(file);
    });

    const fileName = `${empresaKey}_${docKey}.pdf`;
    const result   = await apiPost('upload_empresa_doc', {
      empresa_key: empresaKey,
      doc_key:     docKey,
      file_base64: base64,
      file_name:   fileName,
    });

    const data = loadEmpresasFromStorage();
    data[empresaKey].documentos[docKey].url   = result.view_url;
    data[empresaKey].documentos[docKey].fecha = todayLocalStr();
    saveEmpresasToStorage(data);
    showToast(`${docNombre} subido correctamente ✅`, 'ok');
    renderEmpresasView();
    // Reabrir el acordeón
    setTimeout(() => {
      const card = document.querySelector(`.empresa-card[data-key="${empresaKey}"]`);
      if (card && !card.classList.contains('open')) card.classList.add('open');
    }, 100);
  } catch (err) {
    showToast('Error al subir: ' + err.message, 'error');
    if (progressEl) progressEl.classList.add('hidden');
  }
}

function openPdfPreview(previewUrl, nombre) {
  const modal  = document.getElementById('modal-pdf-preview');
  const frame  = document.getElementById('pdf-preview-frame');
  const title  = document.getElementById('modal-pdf-title');
  if (!modal || !frame) return;
  title.textContent = nombre || 'Documento';
  frame.src = previewUrl;
  modal.classList.remove('hidden');
}

function bindEmpresasEvents() {
  // PDF preview close
  document.getElementById('btn-cerrar-pdf-preview').addEventListener('click', () => {
    document.getElementById('modal-pdf-preview').classList.add('hidden');
    document.getElementById('pdf-preview-frame').src = '';
  });
  document.getElementById('modal-pdf-preview').addEventListener('click', function (e) {
    if (e.target === this) {
      this.classList.add('hidden');
      document.getElementById('pdf-preview-frame').src = '';
    }
  });

  document.getElementById('btn-nueva-empresa').addEventListener('click', () => openEmpresaModal(null));
  document.getElementById('btn-cerrar-empresa').addEventListener('click', () =>
    document.getElementById('modal-empresa').classList.add('hidden'));
  document.getElementById('btn-cancelar-empresa').addEventListener('click', () =>
    document.getElementById('modal-empresa').classList.add('hidden'));

  document.getElementById('fe-auth').addEventListener('change', function () {
    toggleCredsSection(this.value);
  });

  document.getElementById('form-empresa').addEventListener('submit', e => {
    e.preventDefault();
    const key = document.getElementById('fe-key').value.trim().toUpperCase();
    if (!key) return showToast('El nombre clave es obligatorio', 'warn');
    const data = loadEmpresasFromStorage();
    const existing = data[key] || {};
    data[key] = {
      key,
      nombre:           document.getElementById('fe-nombre').value.trim(),
      ruc:              document.getElementById('fe-ruc').value.trim(),
      descripcion:      document.getElementById('fe-descripcion').value.trim(),
      sede:             document.getElementById('fe-sede').value.trim(),
      activo:           document.getElementById('fe-activo').checked,
      auth_method:      document.getElementById('fe-auth').value,
      sol_usuario:      document.getElementById('fe-sol-user').value.trim(),
      sol_clave:        document.getElementById('fe-sol-clave').value,
      dni_representante: document.getElementById('fe-dni').value.trim(),
      password_casilla:  document.getElementById('fe-pass').value,
      documentos:       existing.documentos || DOCS_TEMPLATE(),
    };
    saveEmpresasToStorage(data);
    document.getElementById('modal-empresa').classList.add('hidden');
    showToast(`Empresa "${key}" guardada`, 'ok');
    renderEmpresasView();
    // Actualizar selector de empresa en el panel de respuesta
    refreshEmpresasLegales(data);
  });
}

function refreshEmpresasLegales(data) {
  // Mantener EMPRESAS_LEGALES sincronizado con el storage
  Object.entries(data).forEach(([key, e]) => {
    EMPRESAS_LEGALES[key] = { nombre: e.nombre, texto: e.descripcion };
  });
}

/* ──────────────────────────── Filtros ─────────────────────────── */

function applyFilters() {
  const f = state.filters;
  let data = [...state.items];

  if (f.search) {
    const q = f.search.toLowerCase();
    data = data.filter(i =>
      (i.documento || '').toLowerCase().includes(q) ||
      (i.empresa   || '').toLowerCase().includes(q) ||
      (i.asunto    || '').toLowerCase().includes(q) ||
      (i.resumen   || '').toLowerCase().includes(q) ||
      (i.tarea     || '').toLowerCase().includes(q)
    );
  }
  if (f.empresa) data = data.filter(i => i.empresa === f.empresa);

  if (state.view === 'all') {
    if (f.progreso === 'ACTIVAS') {
      data = data.filter(i => i.progreso !== 'PRESENTADO' && i.progreso !== 'archivada');
    } else if (f.progreso) {
      data = data.filter(i => i.progreso === f.progreso);
    }
    if (f.soloPendientes) {
      data = data.filter(i => i.progreso !== 'PRESENTADO');
    }
  }

  if (f.since) {
    const since = parseLocalDate(f.since);
    data = data.filter(i => {
      const d = parseLocalDate(i.fecha_notificacion);
      return d && d >= since;
    });
  }

  state.filtered = data;
  updateViewBadges(data);

  if (state.view === 'pending') {
    renderPendingView(data);
  } else {
    renderTable(data);
  }
}

function updateViewBadges(allFiltered) {
  const totalCount   = allFiltered.length;
  const pendingCount = allFiltered.filter(
    i => i.progreso !== 'PRESENTADO' && i.progreso !== 'archivada'
  ).length;

  const badgePending = document.getElementById('vtab-pending-badge');
  const badgeAll     = document.getElementById('vtab-all-badge');
  if (badgePending) badgePending.textContent = pendingCount || '';
  if (badgeAll)     badgeAll.textContent     = totalCount   || '';
}

/* ──────────────────────────── Pending view ────────────────────── */

function itemUrgencyScore(item) {
  if (item.plazo_vencido === true || parseInt(item.dias_restantes) < 0) return 100;
  const d = parseInt(item.dias_restantes);
  if (isNaN(d)) return 0;
  if (d <= 1)  return 60;
  if (d <= 3)  return 30;
  if (d <= 7)  return 10;
  return 1;
}

function groupUrgencyScore(items) {
  return items.reduce((max, i) => Math.max(max, itemUrgencyScore(i)), 0);
}

function cardUrgencyClass(item) {
  const score = itemUrgencyScore(item);
  if (score >= 100) return 'card-vencido';
  if (score >= 60)  return 'card-urgente';
  if (score >= 30)  return 'card-alerta';
  if (score >= 1)   return 'card-normal';
  return '';
}

function companyCountClass(items) {
  const score = groupUrgencyScore(items);
  if (score >= 100) return 'company-count-vencido';
  if (score >= 60)  return 'company-count-urgente';
  if (score >= 30)  return 'company-count-alerta';
  return 'company-count-normal';
}

function renderPendingView(allItems) {
  const groups  = document.getElementById('pending-groups');
  const emptyEl = document.getElementById('empty-pending');

  const pending = allItems.filter(
    i => i.progreso !== 'PRESENTADO' && i.progreso !== 'archivada'
  );

  if (pending.length === 0) {
    groups.innerHTML = '';
    emptyEl.classList.remove('hidden');
    return;
  }
  emptyEl.classList.add('hidden');

  // Agrupar por empresa
  const groupMap = new Map();
  pending.forEach(item => {
    const key = (item.empresa || 'Sin empresa').trim();
    if (!groupMap.has(key)) {
      groupMap.set(key, {
        empresa: key,
        ruc:  item.ruc  || '',
        sede: item.sede || '',
        items: [],
      });
    }
    groupMap.get(key).items.push(item);
  });

  // Ordenar grupos: mayor urgencia primero
  const sorted = [...groupMap.values()].sort(
    (a, b) => groupUrgencyScore(b.items) - groupUrgencyScore(a.items)
  );

  // Ordenar items dentro de cada grupo
  sorted.forEach(g => {
    g.items.sort((a, b) => itemUrgencyScore(b) - itemUrgencyScore(a));
  });

  groups.innerHTML = sorted.map(g => renderCompanyGroup(g)).join('');

  // Bind: colapsar / expandir grupos
  groups.querySelectorAll('.company-group-header').forEach(header => {
    header.addEventListener('click', () =>
      header.closest('.company-group').classList.toggle('collapsed')
    );
  });

  // Bind: botones detalle
  groups.querySelectorAll('.btn-detail').forEach(btn =>
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openDetail(btn.dataset.id);
    })
  );

  // Bind: progreso selects
  groups.querySelectorAll('select.select-progreso').forEach(sel =>
    sel.addEventListener('change', e => {
      e.stopPropagation();
      handleProgresoChange(sel.dataset.id, sel.value);
    })
  );
}

function renderCompanyGroup(group) {
  const { empresa, ruc, sede, items } = group;
  const n          = items.length;
  const cntClass   = companyCountClass(items);
  const metaParts  = [
    ruc  ? `RUC ${ruc}`      : '',
    sede ? `📍 ${sede}` : '',
  ].filter(Boolean);

  return `
    <div class="company-group" data-empresa="${escapeHtml(empresa)}">
      <div class="company-group-header">
        <div class="company-group-left">
          <span class="company-group-name">${escapeHtml(empresa)}</span>
          ${metaParts.length ? `<span class="company-group-meta">${escapeHtml(metaParts.join(' · '))}</span>` : ''}
        </div>
        <div class="company-group-right">
          <span class="company-count ${cntClass}">${n} pendiente${n !== 1 ? 's' : ''}</span>
          <span class="group-toggle-icon">▼</span>
        </div>
      </div>
      <div class="company-group-body">
        ${items.map(i => renderNotifCard(i)).join('')}
      </div>
    </div>
  `;
}

function renderNotifCard(item) {
  const urgClass = cardUrgencyClass(item);
  const progreso = item.progreso || 'NO INICIADO';
  const progCls  = PROGRESO_CSS[progreso] || 'no-iniciado';
  const progOpts = ALLOWED_PROGRESO.map(p =>
    `<option value="${p}"${progreso === p ? ' selected' : ''}>${PROGRESO_LABELS[p]}</option>`
  ).join('');

  const reqResp = item.requiere_respuesta === true ||
    String(item.requiere_respuesta).toUpperCase() === 'TRUE';

  return `
    <div class="notif-card ${urgClass}">
      <div class="notif-card-main">
        <div class="notif-card-top">
          <span class="notif-card-doc">${escapeHtml(item.documento || '—')}</span>
          <span class="notif-card-date">${formatDate(item.fecha_notificacion)}</span>
        </div>
        ${item.asunto
          ? `<div class="notif-card-asunto">${escapeHtml(item.asunto)}</div>`
          : ''}
        <div class="notif-card-tareas">${tareasBadges(item.tarea)}</div>
        <div class="notif-card-flags">
          ${reqResp ? '<span class="badge urgente" style="font-size:0.68rem">Requiere respuesta</span>' : ''}
          ${item.tipo_acto ? `<span class="badge" style="font-size:0.68rem;background:rgba(100,116,139,0.15);color:#94a3b8">${escapeHtml(item.tipo_acto)}</span>` : ''}
        </div>
      </div>
      <div class="notif-card-actions">
        <div>${badgeDias(item.dias_restantes)}</div>
        <select class="select-progreso progreso-${progCls}"
          data-id="${escapeHtml(item.id)}"
          data-prev="${escapeHtml(progreso)}">
          ${progOpts}
        </select>
        <button class="btn-detail" data-id="${escapeHtml(item.id)}">Ver →</button>
      </div>
    </div>
  `;
}

/* ──────────────────────────── Tabla (all view) ────────────────── */

function rowUrgencyClass(item) {
  if (item.progreso === 'PRESENTADO') return '';
  if (item.plazo_vencido) return 'row-vencido';
  const d = parseInt(item.dias_restantes, 10);
  if (isNaN(d)) return '';
  if (d < 0)  return 'row-vencido';
  if (d <= 1) return 'row-urgente';
  if (d <= 3) return 'row-alerta';
  return '';
}

function progresoSelect(item) {
  const p   = item.progreso || 'NO INICIADO';
  const cls = PROGRESO_CSS[p] || 'no-iniciado';
  const options = ALLOWED_PROGRESO.map(v =>
    `<option value="${v}"${p === v ? ' selected' : ''}>${PROGRESO_LABELS[v]}</option>`
  ).join('');
  return `<select class="select-progreso progreso-${cls}" data-id="${escapeHtml(item.id)}" data-prev="${escapeHtml(p)}">${options}</select>`;
}

function tareasBadges(tareaStr) {
  if (!tareaStr) return '<span class="muted" style="font-size:0.78rem">—</span>';
  const tareas = tareaStr.split(',').map(t => t.trim()).filter(Boolean);
  if (tareas.length === 0) return '<span class="muted" style="font-size:0.78rem">—</span>';
  const max    = 2;
  const shown  = tareas.slice(0, max).map(t => `<span class="tag-tarea">${escapeHtml(t)}</span>`).join('');
  const extra  = tareas.length > max ? ` <span class="tag-more">+${tareas.length - max}</span>` : '';
  return shown + extra;
}

function renderTable(items) {
  const tbody      = document.getElementById('notif-tbody');
  const table      = document.getElementById('notif-table');
  const emptyFilt  = document.getElementById('empty-filtered');
  const emptyApi   = document.getElementById('empty-api');

  if (state.items.length === 0) {
    table.classList.add('hidden');
    emptyFilt.classList.add('hidden');
    emptyApi.classList.remove('hidden');
    return;
  }
  emptyApi.classList.add('hidden');

  if (items.length === 0) {
    table.classList.add('hidden');
    emptyFilt.classList.remove('hidden');
    return;
  }
  emptyFilt.classList.add('hidden');
  table.classList.remove('hidden');

  tbody.innerHTML = items.map(i => `
    <tr class="${rowUrgencyClass(i)}" data-id="${escapeHtml(i.id)}">
      <td>${progresoSelect(i)}</td>
      <td>
        <div style="white-space:nowrap">${formatDate(i.fecha_notificacion)}</div>
        ${i.plazo_vencido ? '<span class="badge vencido" style="font-size:0.68rem;margin-top:2px">Venció</span>' : ''}
      </td>
      <td>
        <strong style="font-size:0.875rem">${escapeHtml(i.documento || '—')}</strong>
        <div class="muted" style="font-size:0.78rem;margin-top:2px">${escapeHtml((i.asunto || '').slice(0, 90))}</div>
      </td>
      <td>
        <div style="font-size:0.875rem">${escapeHtml((i.empresa || '').slice(0, 35))}</div>
        ${i.sede ? `<div class="muted" style="font-size:0.75rem;margin-top:2px">📍 ${escapeHtml(i.sede)}</div>` : ''}
      </td>
      <td class="col-tarea">${tareasBadges(i.tarea)}</td>
      <td style="white-space:nowrap">
        <div style="font-size:0.82rem">${i.plazo_vencimiento ? formatDate(i.plazo_vencimiento) : '—'}</div>
        <div style="margin-top:2px">${badgeDias(i.dias_restantes)}</div>
      </td>
      <td style="white-space:nowrap">
        <button class="btn-detail" data-id="${escapeHtml(i.id)}">Ver →</button>
        <a class="btn-detail btn-redactar-mini" href="${redactorLink(i.id)}" target="_blank"
          rel="noopener" title="Redactar respuesta">📝</a>
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.btn-detail').forEach(btn =>
    btn.addEventListener('click', () => openDetail(btn.dataset.id))
  );
  tbody.querySelectorAll('select.select-progreso').forEach(sel =>
    sel.addEventListener('change', e => handleProgresoChange(sel.dataset.id, e.target.value))
  );
}

/* ──────────────────────────── Progreso change ─────────────────── */

async function handleProgresoChange(id, progreso) {
  const selectors = `select.select-progreso[data-id="${id}"]`;
  const allSelects = document.querySelectorAll(selectors);
  const prev = allSelects.length ? allSelects[0].dataset.prev : progreso;

  try {
    await api('update_status', { id, campo: 'progreso', valor: progreso });
    const item = state.items.find(i => i.id === id);
    if (item) item.progreso = progreso;

    allSelects.forEach(sel => {
      const cls = PROGRESO_CSS[progreso] || 'no-iniciado';
      sel.className    = `select-progreso progreso-${cls}`;
      sel.dataset.prev = progreso;
      const tr = sel.closest('tr');
      if (tr) tr.className = rowUrgencyClass(item || { progreso, plazo_vencido: false });
    });

    showToast(`Progreso: ${PROGRESO_LABELS[progreso] || progreso}`, 'ok');

    // Si en pending view un item pasa a PRESENTADO, refresca el grupo
    if (state.view === 'pending' && progreso === 'PRESENTADO') {
      setTimeout(() => applyFilters(), 800);
    }
  } catch (err) {
    allSelects.forEach(sel => { sel.value = prev; });
    showToast('Error al actualizar: ' + err.message, 'error');
  }
}

/* ──────────────────────────── Tarea ───────────────────────────── */

const TAREAS_CATALOGO = [
  'comunicar en WhatsApp', 'descargos', 'remitir expedientes', 'subsanar observaciones',
  'inspección', 'cumplir con pago', 'carta de ampliación', 'cumplo requerimiento',
  'hacer algo?', 'nueva solicitud', 'remitir información', 'dar seguimiento',
  'archivar', 'baja de ing', 'pago de infracción', 'no iniciar PAS', 'carta', 'apelación',
];

async function saveTarea(id, tareaStr) {
  const btn    = document.getElementById('btn-save-tarea');
  const status = document.getElementById('tarea-status');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Guardando...';
  try {
    await api('update_status', { id, campo: 'tarea', valor: tareaStr });
    const item = state.items.find(i => i.id === id);
    if (item) item.tarea = tareaStr;
    document.querySelectorAll(`tr[data-id="${id}"] .col-tarea`).forEach(td => {
      td.innerHTML = tareasBadges(tareaStr);
    });
    if (status) status.textContent = '✓ Guardado';
    showToast('Tareas guardadas', 'ok');
    setTimeout(() => { if (status) status.textContent = ''; }, 2500);
  } catch (err) {
    if (status) status.textContent = '⚠ Error';
    showToast('Error al guardar tareas: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ──────────────────────────── Notas ───────────────────────────── */

async function saveNotas(id, notas) {
  const btn    = document.getElementById('btn-save-notas');
  const status = document.getElementById('notas-status');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Guardando...';
  try {
    await api('update_status', { id, campo: 'notas', valor: notas });
    const item = state.items.find(i => i.id === id);
    if (item) item.notas = notas;
    if (status) status.textContent = '✓ Guardado';
    showToast('Notas guardadas', 'ok');
    setTimeout(() => { if (status) status.textContent = ''; }, 2500);
  } catch (err) {
    if (status) status.textContent = '⚠ Error al guardar';
    showToast('Error al guardar notas: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ──────────────────────────── Badges ──────────────────────────── */

function badgeDias(dias) {
  if (dias === undefined || dias === null || dias === '') return '<span class="muted">—</span>';
  const d   = parseInt(dias, 10);
  let cls   = 'badge';
  if (d < 0)       cls = 'badge vencido';
  else if (d <= 1) cls = 'badge urgente';
  else if (d <= 3) cls = 'badge alerta';
  else             cls = 'badge ok';
  const label = d < 0 ? `Vencido (${Math.abs(d)}d)` : `${d}d`;
  return `<span class="${cls}">${label}</span>`;
}

/* ──────────────────────────── Modal / Tabs ────────────────────── */

function switchTab(tab) {
  document.querySelectorAll('.modal-tab').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('hidden', panel.id !== `tab-${tab}`);
  });
}

async function openDetail(id) {
  state.currentDetailId = id;
  state.currentDetail   = null;

  const modal  = document.getElementById('modal');
  const body   = document.getElementById('modal-body');
  const rPanel = document.getElementById('response-panel');

  body.innerHTML   = '<p class="loading">⏳ Cargando detalle...</p>';
  rPanel.innerHTML = '';
  modal.classList.remove('hidden');
  switchTab('detalle');

  try {
    const detail = await api('detail', { id });
    state.currentDetail = detail;
    body.innerHTML   = renderDetailTab(detail);
    rPanel.innerHTML = renderResponsePanel(id, detail);
    bindDetailTabEvents(id, detail);
    bindResponsePanelEvents(id, detail);
  } catch (err) {
    body.innerHTML = `<p class="error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

/* ──────────────────────────── Detalle tab ─────────────────────── */

function renderTareaEditor(currentTareaStr) {
  const selected = new Set(
    (currentTareaStr || '').split(',').map(t => t.trim()).filter(Boolean)
  );
  const checks = TAREAS_CATALOGO.map(t => `
    <label class="tarea-check">
      <input type="checkbox" value="${escapeHtml(t)}"${selected.has(t) ? ' checked' : ''}>
      <span>${escapeHtml(t)}</span>
    </label>
  `).join('');
  return `
    <div class="tarea-editor">
      <div class="tarea-grid">${checks}</div>
      <div class="notas-actions" style="margin-top:0.7rem">
        <button id="btn-save-tarea">💾 Guardar tareas</button>
        <span id="tarea-status" class="muted small"></span>
      </div>
    </div>
  `;
}

function renderResumenEstructurado(d) {
  const tiene = d.tipo_acto || d.accion_requerida || d.consecuencias || d.fundamento_legal;
  if (!tiene) return '';

  const row = (label, val, icon) => val
    ? `<div class="re-row">
         <span class="re-label">${icon} ${label}</span>
         <span class="re-val">${escapeHtml(val)}</span>
       </div>`
    : '';

  return `
    <p class="section-heading">🧩 Resumen estructurado</p>
    <div class="resumen-estructurado">
      ${row('Tipo de acto', d.tipo_acto, '📄')}
      ${row('Acción requerida', d.accion_requerida, '⚡')}
      ${row('Consecuencias', d.consecuencias, '⚠️')}
      ${row('Fundamento legal', d.fundamento_legal, '⚖️')}
    </div>
  `;
}

/* ──────────────────────── Inline field editor ─────────────────── */

function eField(campo, id, rawVal, displayVal, type = 'text') {
  const raw  = escapeHtml(String(rawVal ?? ''));
  const disp = displayVal !== undefined ? String(displayVal) : (raw || '—');
  return `<span class="editable-val" data-campo="${campo}" data-id="${escapeHtml(id)}" data-raw="${raw}" data-type="${type}" title="Haz clic para editar">${disp}</span>`;
}

function startEditField(el) {
  if (el.classList.contains('editing')) return;
  el.classList.add('editing');
  const raw      = el.dataset.raw;
  const type     = el.dataset.type || 'text';
  const origHTML = el.innerHTML;
  const extra    = type === 'number' ? ' min="0" step="1"' : '';
  el.innerHTML = `<input class="ef-input" type="${type}" value="${escapeHtml(raw)}"${extra}><button class="ef-save-btn" title="Guardar">✓</button><button class="ef-cancel-btn" title="Cancelar">✕</button>`;
  const input = el.querySelector('.ef-input');
  input.focus();
  if (input.select) input.select();
  el.querySelector('.ef-cancel-btn').onclick = e => { e.stopPropagation(); el.innerHTML = origHTML; el.classList.remove('editing'); };
  el.querySelector('.ef-save-btn').onclick   = async e => { e.stopPropagation(); await saveField(el, input.value, origHTML); };
  input.addEventListener('keydown', async e => {
    if (e.key === 'Enter')  { e.preventDefault(); await saveField(el, input.value, origHTML); }
    else if (e.key === 'Escape') { el.innerHTML = origHTML; el.classList.remove('editing'); }
  });
}

async function saveField(el, newVal, origHTML) {
  const { campo, id } = el.dataset;
  el.querySelectorAll('button').forEach(b => { b.disabled = true; });
  const input = el.querySelector('.ef-input');
  if (input) input.disabled = true;
  try {
    await api('update_status', { id, campo, valor: newVal });
    const item = state.items.find(i => i.id === id);
    if (item) item[campo] = newVal;
    el.dataset.raw = newVal;
    el.innerHTML = campo === 'plazo_vencimiento' ? formatDate(newVal) : escapeHtml(newVal || '—');
    el.classList.remove('editing');
    showToast(`${campo.replace(/_/g, ' ')} actualizado`, 'ok');
  } catch (err) {
    el.innerHTML = origHTML;
    el.classList.remove('editing');
    showToast('Error al guardar: ' + err.message, 'error');
  }
}

function renderDetailTab(d) {
  const progreso = d.progreso || 'NO INICIADO';
  const progresoOptions = ALLOWED_PROGRESO.map(p =>
    `<option value="${p}"${progreso === p ? ' selected' : ''}>${PROGRESO_LABELS[p]}</option>`
  ).join('');
  const progCls = PROGRESO_CSS[progreso] || 'no-iniciado';

  const reqResp = d.requiere_respuesta === true ||
    String(d.requiere_respuesta).toUpperCase() === 'TRUE';

  return `
    <h2 style="margin:0 0 0.2rem;font-size:1.15rem;font-weight:800">${escapeHtml(d.documento || 'Sin nombre')}</h2>
    <p class="muted" style="margin:0 0 1rem;font-size:0.85rem">${escapeHtml(d.asunto || '')}</p>

    ${reqResp ? '<span class="badge urgente" style="margin-bottom:0.75rem;display:inline-block">⚡ Requiere respuesta</span>' : ''}

    <p class="section-heading">📋 Datos de la notificación</p>
    <div class="detail-grid">
      <div><strong>Fecha:</strong> ${formatDate(d.fecha_notificacion)}</div>
      <div><strong>Lectura:</strong> ${d.lectura_notificacion ? formatDate(d.lectura_notificacion) : '—'}</div>
      <div><strong>Empresa:</strong> ${escapeHtml(d.empresa || '—')}</div>
      <div><strong>RUC:</strong> ${escapeHtml(d.ruc || '—')}</div>
      <div><strong>Sede:</strong> ${d.sede ? `📍 ${escapeHtml(d.sede)}` : '—'}</div>
      <div><strong>Emisor:</strong> ${eField('emisor', d.id, d.emisor || '', escapeHtml(d.emisor || '—'))}</div>
      <div><strong>Casilla origen:</strong> ${escapeHtml(d.casilla_origen || '—')}</div>
      <div><strong>Referencia:</strong> ${escapeHtml(d.referencia || '—')}</div>
      <div><strong>Plazo:</strong> ${eField('plazo_dias_habiles', d.id, d.plazo_dias_habiles ?? '', escapeHtml(String(d.plazo_dias_habiles || '—')), 'number')} días hábiles</div>
      <div><strong>Vence:</strong> ${eField('plazo_vencimiento', d.id, d.plazo_vencimiento || '', formatDate(d.plazo_vencimiento), 'date')} &nbsp;${badgeDias(d.dias_restantes)}</div>
      <div><strong>Confianza IA:</strong> ${escapeHtml(d.confianza_ia || '—')} &nbsp;<span class="muted small">${escapeHtml(d.modelo_ia || '')}</span></div>
      <div>
        <strong>Progreso:</strong><br>
        <select id="detail-progreso-select"
          class="select-progreso progreso-${progCls}"
          data-id="${escapeHtml(d.id)}"
          data-prev="${escapeHtml(progreso)}"
          style="margin-top:0.4rem">
          ${progresoOptions}
        </select>
      </div>
    </div>

    <p class="section-heading">📝 Resumen IA</p>
    <p style="line-height:1.7;font-size:0.9rem;margin:0 0 0.75rem">${escapeHtml(d.resumen || 'Sin resumen.')}</p>

    ${renderResumenEstructurado(d)}

    ${d.informe ? `
    <details class="informe-details" open>
      <summary class="section-heading" style="cursor:pointer;list-style:none;display:flex;align-items:center;gap:0.4rem">
        🧾 Informe IA <span class="muted small" style="font-weight:400;text-transform:none;letter-spacing:0">(análisis completo del documento)</span>
        <span class="informe-toggle-icon">▾</span>
      </summary>
      <div class="informe-body">${renderMarkdown(d.informe)}</div>
    </details>` : ''}

    <p class="section-heading">🗂 Tareas <span style="font-weight:400;font-size:0.8rem;text-transform:none;letter-spacing:0">(seleccioná las que aplican)</span></p>
    ${renderTareaEditor(d.tarea)}

    ${d.drive_view_url ? `
      <p class="section-heading">📎 PDF unificado</p>
      <iframe class="pdf-frame" src="${embedDriveUrl(d.drive_view_url)}" allow="autoplay"></iframe>
      <p style="margin-top:0.5rem;font-size:0.85rem"><a href="${d.drive_view_url}" target="_blank" rel="noopener" style="color:var(--primary)">Abrir en Drive ↗</a></p>
    ` : ''}

    <p class="section-heading">💬 Notas internas</p>
    <div class="notas-editor">
      <textarea id="notas-edit" rows="4"
        placeholder="Agregar notas sobre esta notificación...">${escapeHtml(d.notas || '')}</textarea>
      <div class="notas-actions">
        <button id="btn-save-notas">💾 Guardar notas</button>
        <span id="notas-status" class="muted small"></span>
      </div>
    </div>
  `;
}

function bindDetailTabEvents(id, detail) {
  const progresoSel = document.getElementById('detail-progreso-select');
  if (progresoSel) {
    progresoSel.addEventListener('change', e => handleProgresoChange(id, e.target.value));
  }
  const btnSaveTarea = document.getElementById('btn-save-tarea');
  if (btnSaveTarea) {
    btnSaveTarea.addEventListener('click', () => {
      const checks   = document.querySelectorAll('.tarea-grid input[type="checkbox"]:checked');
      const tareaStr = [...checks].map(c => c.value).join(', ');
      saveTarea(id, tareaStr);
    });
  }
  const btnSaveNotas = document.getElementById('btn-save-notas');
  if (btnSaveNotas) {
    btnSaveNotas.addEventListener('click', () => {
      const notas = document.getElementById('notas-edit').value;
      saveNotas(id, notas);
    });
  }
  document.querySelectorAll('#modal-body .editable-val').forEach(el => {
    el.addEventListener('click', () => startEditField(el));
  });
}

function embedDriveUrl(url) {
  const match = url.match(/\/file\/d\/([^/]+)/);
  return match ? `https://drive.google.com/file/d/${match[1]}/preview` : url;
}

/* ──────────────────────────── Respuesta tab ───────────────────── */

function guessTemplateId(detail) {
  const haystack = [
    detail.tipo_acto     || '',
    detail.tipo_documento || '',
    detail.documento      || '',
    detail.asunto         || '',
  ].join(' ').toLowerCase();

  if (/ejecuci[oó]n coactiv|medida cautelar|embargo|remate/.test(haystack))
    return 'carta-cumplimiento';
  if (/solicitud|acceso.*expediente|expediente/.test(haystack))
    return 'solicitud-expediente';
  if (/cumplimiento|subsanar|disposici[oó]n/.test(haystack))
    return 'carta-cumplimiento';
  return 'carta-descargo';
}

// Link al Redactor Streamlit para un caso (requiere el Redactor corriendo en REDACTOR_URL)
function redactorLink(id) {
  return `${REDACTOR_URL}/?case_id=${encodeURIComponent(id)}`;
}

function btnRedactarHtml(id, extraClass = '') {
  return `<a class="btn-redactar ${extraClass}" href="${redactorLink(id)}" target="_blank"
    rel="noopener" title="Redactar respuesta en el Redactor (Streamlit)">📝 Redactar</a>`;
}

function renderResponsePanel(notifId, detail) {
  if (state.templates.length === 0) {
    return `
      <div class="response-no-templates">
        <p>⚠️ No hay plantillas disponibles.</p>
        <p class="muted small">Ejecutá <code>_setupPlantillas()</code> en Apps Script, luego recargá el dashboard.</p>
        <div class="response-actions" style="margin-top:0.7rem">${btnRedactarHtml(notifId)}</div>
      </div>
    `;
  }
  const suggestedTpl  = guessTemplateId(detail);
  const tplOptions    = state.templates
    .map(t => `<option value="${escapeHtml(t.id)}"${t.id === suggestedTpl ? ' selected' : ''}>${escapeHtml(t.nombre)}${t.tipo_notificacion ? ' — ' + escapeHtml(t.tipo_notificacion) : ''}</option>`)
    .join('');
  const ciudadDefault = escapeHtml(detail.sede || 'Lima');
  const empresaOptions = Object.keys(EMPRESAS_LEGALES)
    .map(k => `<option value="${escapeHtml(k)}">${escapeHtml(EMPRESAS_LEGALES[k].nombre)}</option>`)
    .join('');
  return `
    <div class="response-panel">
      <div class="response-context">
        <strong>${escapeHtml(detail.documento || '—')}</strong>
        <p class="muted small" style="margin:0.2rem 0 0">${escapeHtml(detail.asunto || '')}</p>
      </div>
      <div class="form-group">
        <label class="form-label">Empresa que representa (personería jurídica)</label>
        <select id="resp-empresa" class="response-select">
          <option value="">— Seleccioná la empresa —</option>
          ${empresaOptions}
        </select>
        <div id="resp-empresa-preview" class="empresa-preview hidden"></div>
      </div>
      <div class="form-group">
        <label class="form-label">Plantilla de respuesta</label>
        <select id="resp-template" class="response-select">
          <option value="">— Seleccioná una plantilla —</option>
          ${tplOptions}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Ciudad (encabezado del documento)</label>
        <input id="resp-ciudad" type="text" class="response-input" value="${ciudadDefault}" placeholder="Lima">
      </div>
      <div class="form-group">
        <label class="form-label">Justificación / Insumos</label>
        <textarea id="resp-justification" class="response-textarea"
          placeholder="Fechas relevantes, argumentos legales, datos de la empresa, acciones tomadas..."
          rows="6"></textarea>
      </div>
      <div class="response-actions">
        <button id="btn-generate" class="btn-generate">✨ Generar con IA</button>
        ${btnRedactarHtml(notifId)}
      </div>
      <div id="response-generating" class="response-loading hidden">
        <div class="spinner"></div>
        Generando respuesta... esto puede tomar unos segundos.
      </div>
      <div id="response-output" class="hidden response-output-panel">
        <div class="form-label-row">
          <label class="form-label">Borrador generado</label>
          <span class="muted small">Editá el texto antes de descargar</span>
        </div>
        <div id="resp-preview" class="response-preview" contenteditable="true" spellcheck="true"></div>
        <div class="response-actions">
          <button id="btn-download-word" class="btn-word">⬇ Descargar Word (.docx)</button>
          <button id="btn-regenerate" class="btn-secondary">↺ Regenerar</button>
        </div>
      </div>
    </div>
  `;
}

function bindResponsePanelEvents(notifId, detail) {
  // Mostrar preview del texto legal al seleccionar empresa
  document.getElementById('resp-empresa').addEventListener('change', function () {
    const preview = document.getElementById('resp-empresa-preview');
    const empresa = EMPRESAS_LEGALES[this.value];
    if (empresa) {
      preview.textContent = empresa.texto;
      preview.classList.remove('hidden');
    } else {
      preview.classList.add('hidden');
    }
  });

  document.getElementById('btn-generate').addEventListener('click', async () => {
    const templateId    = document.getElementById('resp-template').value;
    const empresaKey    = document.getElementById('resp-empresa').value;
    const justificacion = document.getElementById('resp-justification').value.trim();
    const ciudad        = (document.getElementById('resp-ciudad')?.value || '').trim() || detail.sede || 'Lima';
    if (!empresaKey)   { showToast('Seleccioná la empresa primero', 'warn'); return; }
    if (!templateId)   { showToast('Seleccioná una plantilla primero', 'warn'); return; }
    const empresaTexto = EMPRESAS_LEGALES[empresaKey]?.texto || '';
    await handleGenerateResponse(notifId, templateId, justificacion, ciudad, empresaTexto);
  });
  const btnDownload = document.getElementById('btn-download-word');
  if (btnDownload) {
    btnDownload.addEventListener('click', () => {
      const text     = document.getElementById('resp-preview').innerText || '';
      const filename = `Respuesta_${(detail.documento || notifId).replace(/[^a-zA-Z0-9_\-]/g, '_')}`;
      downloadWord(text, filename, detail);
    });
  }
  const btnRegen = document.getElementById('btn-regenerate');
  if (btnRegen) {
    btnRegen.addEventListener('click', () => {
      document.getElementById('response-output').classList.add('hidden');
      document.getElementById('btn-generate').classList.remove('hidden');
    });
  }
}

async function handleGenerateResponse(notifId, templateId, justificacion, ciudad, empresaTexto) {
  const genBtn  = document.getElementById('btn-generate');
  const spinner = document.getElementById('response-generating');
  const output  = document.getElementById('response-output');

  genBtn.disabled = true;
  genBtn.classList.add('hidden');
  spinner.classList.remove('hidden');
  output.classList.add('hidden');

  try {
    const result = await api('generate_response', {
      notification_id: notifId,
      template_id:     templateId,
      justificacion,
      ciudad:          ciudad || 'Lima',
      empresa_texto:   empresaTexto || '',
    });
    document.getElementById('resp-preview').innerText = result.respuesta || '(Sin respuesta generada)';
    output.classList.remove('hidden');
    showToast('Respuesta generada correctamente', 'ok');
  } catch (err) {
    showToast('Error al generar: ' + err.message, 'error');
    genBtn.classList.remove('hidden');
  } finally {
    genBtn.disabled = false;
    spinner.classList.add('hidden');
  }
}

/* ──────────────────────────── Word download ───────────────────── */

async function downloadWord(text, filename, detail) {
  if (!window.docx) {
    showToast('Librería Word no cargada. Revisá la conexión a internet.', 'error');
    return;
  }

  const { Document, Packer, Paragraph, TextRun, AlignmentType } = window.docx;

  const FONT    = 'Arial';
  const SZ      = 24;  // 12pt (half-points)
  const SZ_TTL  = 28;  // 14pt for document title

  function run(t, bold, size) {
    return new TextRun({ text: t, font: FONT, size: size || SZ, bold: !!bold });
  }

  function para(text, { bold, align, size, spacing } = {}) {
    return new Paragraph({
      children:  [run(text, bold, size)],
      alignment: align || AlignmentType.LEFT,
      spacing:   spacing || { line: 360, lineRule: 'auto', after: 160 },
    });
  }

  const lines    = text.split('\n');
  const children = [];
  let isFirstLine = true;
  let inSig       = false;

  for (const rawLine of lines) {
    const t = rawLine.trim();

    if (!t) {
      children.push(new Paragraph({ text: '', spacing: { after: 100 } }));
      continue;
    }

    // Signature divider line: ________________________
    if (/^_{3,}/.test(t)) {
      children.push(para('________________________________', {
        align:   AlignmentType.CENTER,
        spacing: { before: 480, after: 80 },
      }));
      continue;
    }

    // "Atentamente," triggers signature block
    if (/^atentamente[,.]?\s*$/i.test(t)) {
      inSig = true;
      children.push(para(t, {
        align:   AlignmentType.CENTER,
        spacing: { before: 480, after: 80 },
      }));
      continue;
    }

    // Lines after "Atentamente," — centered, bold if all-caps (name)
    if (inSig) {
      const isName = /^[A-ZÁÉÍÓÚÑ\s]+$/.test(t) && t.length > 4;
      children.push(para(t, {
        bold:    isName,
        align:   AlignmentType.CENTER,
        spacing: { after: 80 },
      }));
      continue;
    }

    // Document title: first non-empty line, all-caps (or CARTA/OFICIO/SOLICITUD)
    if (isFirstLine && /^[A-ZÁÉÍÓÚÑ°\s\-\/\d\.]+$/.test(t) && t.length > 6) {
      isFirstLine = false;
      children.push(para(t, {
        bold:    true,
        size:    SZ_TTL,
        align:   AlignmentType.CENTER,
        spacing: { before: 0, after: 400 },
      }));
      continue;
    }
    isFirstLine = false;

    // Date / city line: "Lima, 15/05/2026" or "Puno, 15 de mayo de 2026"
    if (/^[A-ZÁÉÍÓÚÑa-záéíóúñ\s]+,\s*\d{1,2}/.test(t)) {
      children.push(para(t, {
        align:   AlignmentType.RIGHT,
        spacing: { before: 240, after: 240 },
      }));
      continue;
    }

    // ASUNTO: line
    if (/^ASUNTO:/i.test(t)) {
      children.push(para(t, {
        bold:    true,
        spacing: { before: 160, after: 160 },
      }));
      continue;
    }

    // Roman numeral section headings: I. ANTECEDENTES, II. FUNDAMENTOS, etc.
    if (/^[IVX]+\.\s/.test(t)) {
      children.push(para(t, {
        bold:    true,
        spacing: { before: 320, after: 160 },
      }));
      continue;
    }

    // Regular body paragraph
    children.push(para(t));
  }

  const doc = new Document({
    creator: 'MTC Casilla Bot',
    title:   `Respuesta — ${detail?.documento || filename}`,
    sections: [{
      properties: {
        page: {
          margin: { top: 1800, right: 1440, bottom: 1800, left: 1800 },
        },
      },
      children,
    }],
  });

  try {
    const blob = await Packer.toBlob(doc);
    saveAs(blob, filename + '.docx');
    showToast('Archivo Word descargado', 'ok');
  } catch (err) {
    showToast('Error al crear el archivo: ' + err.message, 'error');
  }
}

/* ──────────────────────────── Toast ───────────────────────────── */

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast     = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('toast-show')));
  setTimeout(() => {
    toast.classList.remove('toast-show');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }, 3500);
}

/* ──────────────────────────── Helpers ─────────────────────────── */

// Parsea fechas YYYY-MM-DD como fecha LOCAL (no UTC) para evitar el corrimiento
// de -5h en Perú. Los datetimes ISO con hora ("T") se delegan a new Date().
function parseLocalDate(s) {
  if (!s) return null;
  if (typeof s === 'string') {
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

// Medianoche de HOY en hora local (para comparar contra fechas date-only)
function todayLocal() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

// Fecha de HOY como string YYYY-MM-DD en hora local (no UTC)
function todayLocalStr() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function formatDate(s) {
  if (!s) return '—';
  const d = parseLocalDate(s);
  if (!d) return s;
  return d.toLocaleDateString('es-PE', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function renderMarkdown(md) {
  if (!md) return '';
  const lines = md.split('\n');
  let html = '';
  let inList = false;
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith('## ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<h4 class="informe-h4">${escapeHtml(line.slice(3))}</h4>`;
    } else if (/^[-*] /.test(line)) {
      if (!inList) { html += '<ul class="informe-list">'; inList = true; }
      const item = line.slice(2).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      html += `<li>${escapeHtml(item).replace(/&lt;strong&gt;/g,'<strong>').replace(/&lt;\/strong&gt;/g,'</strong>')}</li>`;
    } else if (/^\d+\. /.test(line)) {
      if (!inList) { html += '<ol class="informe-list">'; inList = true; }
      const item = line.replace(/^\d+\. /, '');
      html += `<li>${escapeHtml(item)}</li>`;
    } else {
      if (inList) { html += inList ? '</ul>' : '</ol>'; inList = false; }
      if (line.trim() === '') {
        html += '<br>';
      } else {
        const inline = escapeHtml(line).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html += `<p class="informe-p">${inline}</p>`;
      }
    }
  }
  if (inList) html += '</ul>';
  return html;
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showLoading(on) { document.getElementById('loading').classList.toggle('hidden', !on); }

function showErrorCard(msg) {
  document.getElementById('error-api-url').textContent = state.apiUrl || '(no configurada)';
  document.getElementById('error-message').textContent  = msg;
  document.getElementById('error-card').classList.remove('hidden');
  document.getElementById('notif-table').classList.add('hidden');
  document.getElementById('empty-filtered').classList.add('hidden');
  document.getElementById('empty-api').classList.add('hidden');
}
function hideErrorCard() { document.getElementById('error-card').classList.add('hidden'); }

/* ──────────────────────────── Onboarding ──────────────────────── */

function showOnboarding() {
  document.getElementById('onboarding').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  document.getElementById('btn-refresh').classList.add('hidden');
  document.getElementById('btn-change-url').classList.add('hidden');
  document.getElementById('api-status').innerHTML = '<span class="ko">●</span> Sin configurar';
}

function showDashboard() {
  document.getElementById('onboarding').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
  document.getElementById('btn-refresh').classList.remove('hidden');
  document.getElementById('btn-resumen-dia').classList.remove('hidden');
  document.getElementById('btn-change-url').classList.remove('hidden');
}

function showOnboardingError(msg) {
  const el = document.getElementById('onboarding-error');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideOnboardingError() { document.getElementById('onboarding-error').classList.add('hidden'); }

function handleSaveUrl(e) {
  e.preventDefault();
  hideOnboardingError();
  const url = (document.getElementById('api-url-input').value || '').trim();
  if (!url)               { showOnboardingError('Ingresá la URL del Web App.'); return; }
  if (!isValidApiUrl(url)) {
    showOnboardingError('La URL debe empezar con https://script.google.com/macros/');
    return;
  }
  saveApiUrl(url);
  state.apiUrl = url;
  showDashboard();
  loadTemplates();
  loadAll();
}

/* ──────────────────────────── Sync empresa docs desde API ─────── */

async function syncEmpresaDocsFromApi() {
  try {
    const data = await api('get_empresa_docs');
    if (!data.docs || data.docs.length === 0) return;
    const empresas = loadEmpresasFromStorage();
    let changed = false;
    data.docs.forEach(doc => {
      const emp = empresas[doc.empresa_key];
      if (!emp || !emp.documentos[doc.doc_key]) return;
      const current = emp.documentos[doc.doc_key];
      // Solo actualizar si el Sheet tiene una URL más reciente
      if (doc.view_url && doc.view_url !== current.url) {
        current.url   = doc.view_url;
        current.fecha = (doc.fecha_subida || '').slice(0, 10);
        changed = true;
      }
    });
    if (changed) {
      saveEmpresasToStorage(empresas);
      // Si la vista empresas está abierta, refrescarla
      if (state.view === 'empresas') renderEmpresasView();
    }
  } catch (_) {}
}

/* ──────────────────────────── Resumen del día ─────────────────── */

function generateResumenDiario() {
  const todayStr = todayLocalStr();
  const fecha    = new Date().toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const empresas = loadEmpresasFromStorage();

  const lineas = Object.values(empresas)
    .filter(e => e.activo !== false)
    .map(e => {
      const count = state.items.filter(i => {
        const f = (i.fecha_notificacion || '').slice(0, 10);
        if (f !== todayStr) return false;
        // Coincidir por RUC si existe, sino por nombre
        if (e.ruc && i.ruc) return String(i.ruc).trim() === String(e.ruc).trim();
        return (i.empresa || '').toUpperCase().includes(e.key.toUpperCase().split(' ')[0]);
      }).length;

      const msg = count > 0
        ? `${count} notificación${count !== 1 ? 'es' : ''} nueva${count !== 1 ? 's' : ''}.`
        : 'no hay notificaciones nuevas.';
      return `• ${e.key}: ${msg}`;
    });

  return `De la revisión de casillas de MTC al día de hoy ${fecha}:\n${lineas.join('\n')}`;
}

function renderResumenPanel() {
  const panel = document.getElementById('panel-resumen');
  const texto = document.getElementById('resumen-texto');
  if (!panel || !texto) return;
  texto.textContent = generateResumenDiario();
}

function bindResumenEvents() {
  const btnAbrir  = document.getElementById('btn-resumen-dia');
  const btnCerrar = document.getElementById('btn-cerrar-resumen');
  const btnCopiar = document.getElementById('btn-copiar-resumen');
  const panel     = document.getElementById('panel-resumen');

  btnAbrir?.addEventListener('click', () => {
    renderResumenPanel();
    panel.classList.toggle('hidden');
  });

  btnCerrar?.addEventListener('click', () => panel.classList.add('hidden'));

  btnCopiar?.addEventListener('click', () => {
    const txt = document.getElementById('resumen-texto').textContent;
    navigator.clipboard.writeText(txt).then(() => {
      btnCopiar.textContent = '¡Copiado!';
      setTimeout(() => { btnCopiar.textContent = 'Copiar'; }, 2000);
    }).catch(() => {
      // Fallback para navegadores sin clipboard API
      const ta = document.createElement('textarea');
      ta.value = txt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      btnCopiar.textContent = '¡Copiado!';
      setTimeout(() => { btnCopiar.textContent = 'Copiar'; }, 2000);
    });
  });
}

/* ──────────────────────────── Tareas manuales ─────────────────── */

const MANUAL_TASKS_KEY = 'mtc_tareas_manuales';

function loadManualTasks() {
  try { return JSON.parse(localStorage.getItem(MANUAL_TASKS_KEY) || '[]'); } catch { return []; }
}

function saveManualTask(item) {
  const tasks = loadManualTasks();
  tasks.push(item);
  localStorage.setItem(MANUAL_TASKS_KEY, JSON.stringify(tasks));
}

function calcDiasRestantes(plazoStr) {
  if (!plazoStr) return '';
  const today = todayLocal();
  const plazo = parseLocalDate(plazoStr);
  if (!plazo) return '';
  plazo.setHours(0, 0, 0, 0);
  return String(Math.round((plazo - today) / 86400000));
}

function bindNuevaTareaEvents() {
  const modal     = document.getElementById('modal-nueva-tarea');
  const btnAbrir  = document.getElementById('btn-nueva-tarea');
  const btnCerrar = document.getElementById('btn-cerrar-nueva-tarea');
  const btnCancel = document.getElementById('btn-cancelar-nueva-tarea');
  const form      = document.getElementById('form-nueva-tarea');
  let   currentMode = 'simple';

  function populateEmpresaSelects() {
    const empresas = loadEmpresasFromStorage();
    const opts = '<option value="">— Seleccioná la empresa —</option>' +
      Object.values(empresas)
        .map(e => `<option value="${escapeHtml(e.nombre)}">${escapeHtml(e.nombre)}</option>`)
        .join('');
    ['nt-empresa', 'pdf-empresa'].forEach(id => {
      const sel = document.getElementById(id);
      if (sel) sel.innerHTML = opts;
    });
  }

  function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.nt-mode-tab').forEach(t =>
      t.classList.toggle('active', t.dataset.mode === mode));
    document.getElementById('form-nueva-tarea').classList.toggle('hidden', mode !== 'simple');
    document.getElementById('form-pdf-manual').classList.toggle('hidden', mode !== 'pdf');
  }

  function openModal() {
    populateEmpresaSelects();
    const today = todayLocalStr();
    const fechaInput = document.getElementById('nt-fecha');
    if (fechaInput && !fechaInput.value) fechaInput.value = today;
    const pdfFecha = document.getElementById('pdf-fecha');
    if (pdfFecha && !pdfFecha.value) pdfFecha.value = today;
    setMode('simple');
    modal.classList.remove('hidden');
  }

  function closeModal() {
    modal.classList.add('hidden');
    form.reset();
    resetPdfForm();
  }

  function resetPdfForm() {
    document.getElementById('pdf-contexto').value = '';
    document.getElementById('pdf-ruc').value = '';
    document.getElementById('pdf-file-input').value = '';
    document.getElementById('pdf-upload-placeholder').classList.remove('hidden');
    document.getElementById('pdf-upload-selected').classList.add('hidden');
    document.getElementById('pdf-progress').classList.add('hidden');
    document.getElementById('pdf-result').classList.add('hidden');
    document.getElementById('pdf-result').innerHTML = '';
    document.querySelectorAll('.pdf-progress-step').forEach(s => {
      s.textContent = s.textContent.replace(/^[✅❌]/, '⏳');
      s.className = 'pdf-progress-step';
    });
  }

  // Tabs de modo
  document.querySelectorAll('.nt-mode-tab').forEach(tab =>
    tab.addEventListener('click', () => setMode(tab.dataset.mode)));

  btnAbrir?.addEventListener('click', openModal);
  btnCerrar?.addEventListener('click', closeModal);
  btnCancel?.addEventListener('click', closeModal);
  document.getElementById('btn-cancelar-pdf')?.addEventListener('click', closeModal);
  modal?.addEventListener('click', e => { if (e.target === modal) closeModal(); });

  // ── File upload drag & drop ──────────────────────────────────────────────
  const uploadZone = document.getElementById('pdf-upload-zone');
  const fileInput  = document.getElementById('pdf-file-input');

  uploadZone?.addEventListener('click', () => fileInput.click());
  uploadZone?.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
  uploadZone?.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone?.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const file = e.dataTransfer?.files[0];
    if (file) setSelectedFile(file);
  });
  fileInput?.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) setSelectedFile(file);
  });

  function setSelectedFile(file) {
    if (!file.type.includes('pdf')) { showToast('Solo se aceptan archivos PDF', 'warn'); return; }
    document.getElementById('pdf-file-name').textContent = file.name;
    document.getElementById('pdf-file-size').textContent = (file.size / 1024).toFixed(0) + ' KB';
    document.getElementById('pdf-upload-placeholder').classList.add('hidden');
    document.getElementById('pdf-upload-selected').classList.remove('hidden');
    // Sync file input
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
  }

  // ── Procesar PDF ─────────────────────────────────────────────────────────
  document.getElementById('btn-procesar-pdf')?.addEventListener('click', async () => {
    const empresa = document.getElementById('pdf-empresa').value;
    const file    = fileInput?.files[0];
    if (!empresa) { showToast('Seleccioná la empresa', 'warn'); return; }
    if (!file)    { showToast('Seleccioná un PDF', 'warn'); return; }

    const btn = document.getElementById('btn-procesar-pdf');
    btn.disabled = true;
    btn.textContent = '⏳ Procesando...';

    document.getElementById('pdf-progress').classList.remove('hidden');
    document.getElementById('pdf-result').classList.add('hidden');

    const steps = ['step-extract', 'step-ai', 'step-informe', 'step-drive', 'step-sheet'];
    function markStep(id, ok) {
      const el = document.getElementById(id);
      if (!el) return;
      const text = el.textContent.replace(/^[⏳✅❌]\s*/, '');
      el.textContent = (ok ? '✅' : '❌') + ' ' + text;
      el.classList.add(ok ? 'step-ok' : 'step-err');
    }
    function activeStep(id) {
      const el = document.getElementById(id);
      if (!el) return;
      const text = el.textContent.replace(/^[⏳✅❌]\s*/, '');
      el.textContent = '⏳ ' + text;
    }

    try {
      // Los pasos de UI son aproximados — el servidor los ejecuta en secuencia
      activeStep('step-extract');
      await new Promise(r => setTimeout(r, 200));

      const fd = new FormData();
      fd.append('empresa', empresa);
      fd.append('ruc',     document.getElementById('pdf-ruc').value.trim());
      fd.append('contexto', document.getElementById('pdf-contexto').value.trim());
      fd.append('fecha',   document.getElementById('pdf-fecha').value);
      fd.append('pdf',     file);

      // Simular progreso visual mientras se espera la respuesta
      const stepDelays = [500, 2000, 1000, 1500, 500];
      let stepIdx = 0;
      const stepInterval = setInterval(() => {
        if (stepIdx > 0) markStep(steps[stepIdx - 1], true);
        if (stepIdx < steps.length) activeStep(steps[stepIdx]);
        stepIdx++;
        if (stepIdx >= steps.length) clearInterval(stepInterval);
      }, stepDelays[stepIdx] || 1000);

      const resp = await fetch('/api/manual', { method: 'POST', body: fd });
      clearInterval(stepInterval);
      steps.forEach((s, i) => markStep(s, i < stepIdx));

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Error desconocido' }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();
      steps.forEach(s => markStep(s, true));

      const n = data.notification || {};
      document.getElementById('pdf-result').innerHTML = `
        <div class="pdf-result-ok">
          <strong>✅ Notificación creada correctamente</strong>
          <div class="pdf-result-detail">
            <div><strong>Documento:</strong> ${escapeHtml(n.documento || '—')}</div>
            <div><strong>Emisor:</strong> ${escapeHtml(n.emisor || '—')}</div>
            <div><strong>Tipo:</strong> ${escapeHtml(n.tipo_acto || '—')}</div>
            <div><strong>Plazo:</strong> ${n.plazo_dias_habiles ? n.plazo_dias_habiles + ' días hábiles' : '—'}</div>
            ${n.drive_view_url ? `<div><a href="${escapeHtml(n.drive_view_url)}" target="_blank" rel="noopener">📄 Ver PDF en Drive ↗</a></div>` : ''}
          </div>
        </div>`;
      document.getElementById('pdf-result').classList.remove('hidden');

      // Añadir a la lista sin recargar
      await loadAll();
      showToast(`✅ "${n.documento || 'Documento'}" procesado y guardado`, 'ok');

    } catch (err) {
      steps.forEach(s => {
        const el = document.getElementById(s);
        if (el && !el.classList.contains('step-ok')) markStep(s, false);
      });
      document.getElementById('pdf-result').innerHTML =
        `<div class="pdf-result-error">❌ Error: ${escapeHtml(err.message)}</div>`;
      document.getElementById('pdf-result').classList.remove('hidden');
      showToast('Error procesando PDF: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '⚡ Procesar con IA';
    }
  });

  form?.addEventListener('submit', e => {
    e.preventDefault();
    const empresaNombre = document.getElementById('nt-empresa').value;
    if (!empresaNombre) { showToast('Seleccioná la empresa', 'warn'); return; }
    const documento = document.getElementById('nt-documento').value.trim();
    if (!documento)  { showToast('El título es obligatorio', 'warn'); return; }

    const plazo = document.getElementById('nt-plazo').value;
    const item  = {
      id:                 'manual-' + Date.now(),
      empresa:            empresaNombre,
      documento,
      asunto:             document.getElementById('nt-asunto').value.trim(),
      fecha_notificacion: document.getElementById('nt-fecha').value,
      plazo_vencimiento:  plazo,
      dias_restantes:     calcDiasRestantes(plazo),
      plazo_vencido:      plazo ? parseLocalDate(plazo) < todayLocal() : false,
      progreso:           document.getElementById('nt-progreso').value,
      tarea:              document.getElementById('nt-tarea').value.trim(),
      sede:               '',
      origen:             'manual',
      ruc:                '',
    };

    saveManualTask(item);
    state.items.unshift(item);
    applyFilters();
    closeModal();
    showToast(`Tarea "${documento}" agregada`, 'ok');

    // Sincronizar con el Sheet si hay API configurada
    if (state.apiUrl) {
      apiPost('save_tarea_manual', item)
        .then(() => showToast('Tarea guardada en el Sheet ✅', 'ok'))
        .catch(err => showToast('Guardado local OK · Sheet: ' + err.message, 'warn'));
    }
  });
}

/* ──────────────────────────── Init ────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  state.apiUrl = getStoredApiUrl();

  if (state.apiUrl) {
    showDashboard();
    loadTemplates();
    loadAll();
  } else {
    showOnboarding();
  }

  // View tabs
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });

  // Filters
  document.getElementById('filter-search').addEventListener('input', e => {
    state.filters.search = e.target.value;
    applyFilters();
  });
  document.getElementById('filter-empresa').addEventListener('change', e => {
    state.filters.empresa = e.target.value;
    applyFilters();
  });
  document.getElementById('filter-progreso').addEventListener('change', e => {
    state.filters.progreso = e.target.value;
    applyFilters();
  });
  document.getElementById('filter-pendientes').addEventListener('change', e => {
    state.filters.soloPendientes = e.target.checked;
    applyFilters();
  });
  document.getElementById('filter-since').addEventListener('change', e => {
    state.filters.since = e.target.value;
    applyFilters();
  });

  // Refresh
  document.getElementById('btn-refresh').addEventListener('click', loadAll);

  // Modal close
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
  });
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target === document.getElementById('modal'))
      document.getElementById('modal').classList.add('hidden');
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.getElementById('modal').classList.add('hidden');
  });

  // Modal tabs
  document.querySelectorAll('.modal-tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Onboarding
  document.getElementById('api-url-form').addEventListener('submit', handleSaveUrl);

  // Change URL buttons
  document.getElementById('btn-change-url').addEventListener('click', clearApiUrlAndReload);
  document.getElementById('btn-error-change-url').addEventListener('click', clearApiUrlAndReload);
  document.getElementById('btn-error-retry').addEventListener('click', loadAll);

  // Empresas
  bindEmpresasEvents();

  // Tareas manuales
  bindNuevaTareaEvents();

  // Resumen del día
  bindResumenEvents();

  // Initial view state
  switchView('all');
});
