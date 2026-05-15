/* ════════════════════════════════════════════════════════════════
   MTC Casilla Bot — Frontend v2
   Consume la API REST de Apps Script (acción GET, params por URL).
   API_URL se guarda en localStorage (clave: mtc_bot_api_url).
   ════════════════════════════════════════════════════════════════ */

const STORAGE_KEY    = 'mtc_bot_api_url';
const API_URL_PREFIX = 'https://script.google.com/macros/';

const ALLOWED_ESTADOS = ['pendiente', 'en-proceso', 'completado', 'informativo', 'archivada'];
const ESTADO_LABELS   = {
  pendiente:   'Pendiente',
  'en-proceso': 'En proceso',
  completado:  'Completado',
  informativo: 'Informativo',
  archivada:   'Archivada',
};

const state = {
  apiUrl: '',
  items:     [],
  filtered:  [],
  templates: [],
  currentDetailId: null,
  currentDetail:   null,
  filters: {
    search: '', ruc: '', estado: '',
    soloPendientes: false, since: '',
  },
};

/* ──────────────────────────── Config ──────────────────────────── */

function getStoredApiUrl() {
  try {
    const raw = (localStorage.getItem(STORAGE_KEY) || '').trim();
    return (!raw || raw.includes('REEMPLAZAR_AQUI')) ? '' : raw;
  } catch { return ''; }
}
function saveApiUrl(url)       { localStorage.setItem(STORAGE_KEY, url); }
function clearApiUrlAndReload(){ try { localStorage.removeItem(STORAGE_KEY); } catch {} location.reload(); }
function isValidApiUrl(url)    { return typeof url === 'string' && url.startsWith(API_URL_PREFIX); }

/* ──────────────────────────── API ─────────────────────────────── */

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
  hideEmptyApi();

  try {
    const [summary, list] = await Promise.all([
      api('summary'),
      api('list', { limit: 500 }),
    ]);
    renderMetrics(summary);
    state.items = list.items || [];
    populateRucFilter(state.items);
    applyFilters();

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

/* ──────────────────────────── Render metrics ──────────────────── */

function renderMetrics(s) {
  document.getElementById('m-total').textContent     = s.total      ?? 0;
  document.getElementById('m-pendientes').textContent = s.pendientes ?? 0;
  document.getElementById('m-vencidos').textContent   = s.vencidos   ?? 0;
  document.getElementById('m-hoy').textContent        = s.hoy        ?? 0;
}

function populateRucFilter(items) {
  const sel  = document.getElementById('filter-ruc');
  const rucs = [...new Set(items.map(i => i.ruc).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Todos los RUCs</option>' +
    rucs.map(r => {
      const empresa = (items.find(i => i.ruc === r)?.empresa || '').slice(0, 30);
      return `<option value="${r}">${r} — ${empresa}</option>`;
    }).join('');
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
      (i.resumen   || '').toLowerCase().includes(q)
    );
  }
  if (f.ruc)   data = data.filter(i => String(i.ruc) === f.ruc);
  if (f.estado) data = data.filter(i => i.estado === f.estado);
  if (f.soloPendientes) {
    data = data.filter(i =>
      String(i.requiere_respuesta).toUpperCase() === 'TRUE' && i.estado === 'pendiente'
    );
  }
  if (f.since) {
    const since = new Date(f.since);
    data = data.filter(i => i.fecha_notificacion && new Date(i.fecha_notificacion) >= since);
  }

  state.filtered = data;
  renderTable(data);
}

/* ──────────────────────────── Tabla ───────────────────────────── */

function rowUrgencyClass(item) {
  if (['completado', 'archivada', 'informativo'].includes(item.estado)) return '';
  const d = parseInt(item.dias_restantes, 10);
  if (isNaN(d)) return '';
  if (d < 0)  return 'row-vencido';
  if (d <= 1) return 'row-urgente';
  if (d <= 3) return 'row-alerta';
  return '';
}

function statusSelect(item) {
  const estado  = item.estado || 'pendiente';
  const options = ALLOWED_ESTADOS.map(s =>
    `<option value="${s}"${estado === s ? ' selected' : ''}>${ESTADO_LABELS[s]}</option>`
  ).join('');
  return `<select class="select-estado estado-${estado}" data-id="${escapeHtml(item.id)}" data-prev="${escapeHtml(estado)}">${options}</select>`;
}

function renderTable(items) {
  const tbody        = document.getElementById('notif-tbody');
  const table        = document.getElementById('notif-table');
  const emptyFiltered = document.getElementById('empty-filtered');
  const emptyApi     = document.getElementById('empty-api');

  if (state.items.length === 0) {
    table.classList.add('hidden');
    emptyFiltered.classList.add('hidden');
    emptyApi.classList.remove('hidden');
    return;
  }

  emptyApi.classList.add('hidden');

  if (items.length === 0) {
    table.classList.add('hidden');
    emptyFiltered.classList.remove('hidden');
    return;
  }

  emptyFiltered.classList.add('hidden');
  table.classList.remove('hidden');

  tbody.innerHTML = items.map(i => `
    <tr class="${rowUrgencyClass(i)}" data-id="${escapeHtml(i.id)}">
      <td>${statusSelect(i)}</td>
      <td>${formatDate(i.fecha_notificacion)}</td>
      <td>
        <strong>${escapeHtml(i.documento || '—')}</strong>
        <div class="muted small">${escapeHtml((i.asunto || '').slice(0, 80))}</div>
      </td>
      <td>
        <div>${escapeHtml((i.empresa || '').slice(0, 35))}</div>
        <div class="muted small">${i.ruc || ''}</div>
      </td>
      <td>${escapeHtml(i.emisor || '—')}</td>
      <td>${i.plazo_vencimiento ? formatDate(i.plazo_vencimiento) : '—'}</td>
      <td>${badgeDias(i.dias_restantes)}</td>
      <td><button class="btn-detail" data-id="${escapeHtml(i.id)}">Ver →</button></td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.btn-detail').forEach(btn =>
    btn.addEventListener('click', () => openDetail(btn.dataset.id))
  );
}

/* ──────────────────────────── Estado change ───────────────────── */

async function handleStatusChange(id, estado) {
  const select = document.querySelector(`select.select-estado[data-id="${id}"]`);
  const prev   = select ? select.dataset.prev : estado;

  try {
    await api('update_status', { id, estado });
    const item = state.items.find(i => i.id === id);
    if (item) item.estado = estado;
    if (select) {
      select.className    = `select-estado estado-${estado}`;
      select.dataset.prev = estado;
      const tr = select.closest('tr');
      if (tr) {
        tr.className = rowUrgencyClass(item || { estado, dias_restantes: null });
      }
    }
    showToast(`Estado actualizado: ${ESTADO_LABELS[estado] || estado}`, 'ok');
  } catch (err) {
    if (select) select.value = prev;
    showToast('Error al actualizar: ' + err.message, 'error');
  }
}

/* ──────────────────────────── Badges ──────────────────────────── */

function badgeEstado(item) {
  const estado = item.estado || '—';
  const cls    = ALLOWED_ESTADOS.includes(estado) ? `badge ${estado}` : 'badge';
  return `<span class="${cls}">${ESTADO_LABELS[estado] || estado}</span>`;
}

function badgeDias(dias) {
  if (dias === undefined || dias === null || dias === '') return '<span class="muted">—</span>';
  const d   = parseInt(dias, 10);
  let cls   = 'badge';
  if (d < 0)      cls = 'badge vencido';
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

  body.innerHTML  = '<p class="loading">⏳ Cargando detalle...</p>';
  rPanel.innerHTML = '';
  modal.classList.remove('hidden');
  switchTab('detalle');

  try {
    const detail = await api('detail', { id });
    state.currentDetail = detail;
    body.innerHTML  = renderDetailTab(detail);
    rPanel.innerHTML = renderResponsePanel(id, detail);
    bindResponsePanelEvents(id, detail);
  } catch (err) {
    body.innerHTML = `<p class="error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

/* ──────────────────────────── Detalle tab ─────────────────────── */

function renderDetailTab(d) {
  return `
    <h2 style="margin:0 0 0.3rem">${escapeHtml(d.documento || 'Sin nombre')}</h2>
    <p class="muted">${escapeHtml(d.asunto || '')}</p>

    <div class="detail-grid">
      <div><strong>Fecha notificación:</strong> ${formatDate(d.fecha_notificacion)}</div>
      <div><strong>RUC:</strong> ${escapeHtml(d.ruc || '—')}</div>
      <div><strong>Empresa:</strong> ${escapeHtml(d.empresa || '—')}</div>
      <div><strong>Emisor:</strong> ${escapeHtml(d.emisor || '—')}</div>
      <div><strong>Plazo:</strong> ${escapeHtml(String(d.plazo_dias_habiles || '—'))} días hábiles</div>
      <div><strong>Vence:</strong> ${formatDate(d.plazo_vencimiento)} ${badgeDias(d.dias_restantes)}</div>
      <div><strong>Estado:</strong> ${badgeEstado(d)}</div>
      <div><strong>Confianza IA:</strong> ${escapeHtml(d.confianza_ia || '—')} (${escapeHtml(d.modelo_ia || '—')})</div>
    </div>

    <h3>📋 Resumen</h3>
    <p style="line-height:1.7">${escapeHtml(d.resumen || 'Sin resumen.')}</p>

    ${d.notas ? `<h3>📝 Notas</h3><p>${escapeHtml(d.notas)}</p>` : ''}

    ${d.drive_view_url ? `
      <h3>📎 PDF unificado</h3>
      <iframe class="pdf-frame" src="${embedDriveUrl(d.drive_view_url)}" allow="autoplay"></iframe>
      <p style="margin-top:0.5rem"><a href="${d.drive_view_url}" target="_blank" rel="noopener">Abrir en Drive ↗</a></p>
    ` : ''}
  `;
}

function embedDriveUrl(url) {
  const match = url.match(/\/file\/d\/([^/]+)/);
  return match ? `https://drive.google.com/file/d/${match[1]}/preview` : url;
}

/* ──────────────────────────── Respuesta tab ───────────────────── */

function renderResponsePanel(notifId, detail) {
  if (state.templates.length === 0) {
    return `
      <div class="response-no-templates">
        <p>⚠️ No hay plantillas disponibles.</p>
        <p class="muted small">Ejecutá <code>_setupPlantillas()</code> en Apps Script para crear las plantillas de ejemplo, luego recargá el dashboard.</p>
      </div>
    `;
  }

  const tplOptions = state.templates
    .map(t => `<option value="${escapeHtml(t.id)}">${escapeHtml(t.nombre)} — ${escapeHtml(t.tipo_documento || '')}</option>`)
    .join('');

  return `
    <div class="response-panel">
      <div class="response-context">
        <strong>${escapeHtml(detail.documento || '—')}</strong>
        <p class="muted small" style="margin:0.2rem 0 0">${escapeHtml(detail.asunto || '')}</p>
      </div>

      <div class="form-group">
        <label class="form-label">Plantilla de respuesta</label>
        <select id="resp-template" class="response-select">
          <option value="">— Seleccioná una plantilla —</option>
          ${tplOptions}
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Justificación / Insumos</label>
        <textarea id="resp-justification" class="response-textarea"
          placeholder="Pegá aquí: fechas relevantes, argumentos legales, datos de la empresa, acciones tomadas, o cualquier contexto que deba incluir la respuesta..."
          rows="7"></textarea>
      </div>

      <button id="btn-generate" class="btn-generate">✨ Generar con IA</button>

      <div id="response-generating" class="response-loading hidden">
        <div class="spinner"></div>
        Generando respuesta con DeepSeek... esto puede tomar unos segundos.
      </div>

      <div id="response-output" class="hidden response-output-panel">
        <div class="form-label-row">
          <label class="form-label">Borrador generado</label>
          <span class="muted small">Editá directamente el texto antes de descargar</span>
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
  document.getElementById('btn-generate').addEventListener('click', async () => {
    const templateId    = document.getElementById('resp-template').value;
    const justificacion = document.getElementById('resp-justification').value.trim();
    if (!templateId) { showToast('Seleccioná una plantilla primero', 'warn'); return; }
    await handleGenerateResponse(notifId, templateId, justificacion);
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
      const output  = document.getElementById('response-output');
      const genBtn  = document.getElementById('btn-generate');
      output.classList.add('hidden');
      genBtn.classList.remove('hidden');
    });
  }
}

async function handleGenerateResponse(notifId, templateId, justificacion) {
  const genBtn  = document.getElementById('btn-generate');
  const spinner = document.getElementById('response-generating');
  const output  = document.getElementById('response-output');

  genBtn.disabled = true;
  genBtn.classList.add('hidden');
  spinner.classList.remove('hidden');
  output.classList.add('hidden');

  try {
    const result  = await api('generate_response', {
      id: notifId,
      template_id: templateId,
      justificacion,
    });
    const preview = document.getElementById('resp-preview');
    preview.innerText = result.respuesta || '(Sin respuesta generada)';
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

  const { Document, Packer, Paragraph, TextRun, HeadingLevel } = window.docx;

  const blocks = text.split(/\n\n+/);
  const paragraphs = blocks.map(block => {
    const lines = block.split('\n');
    const runs  = [];
    lines.forEach((line, i) => {
      if (line.trim()) runs.push(new TextRun(line));
      if (i < lines.length - 1 && lines[i + 1]) runs.push(new TextRun({ break: 1 }));
    });
    return new Paragraph({
      children: runs.length ? runs : [new TextRun('')],
      spacing:  { after: 200 },
    });
  });

  const doc = new Document({
    creator: 'MTC Casilla Bot',
    title:   `Respuesta — ${detail?.documento || filename}`,
    sections: [{ properties: {}, children: paragraphs }],
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

function formatDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString('es-PE', { year: 'numeric', month: '2-digit', day: '2-digit' });
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
function hideEmptyApi()  { document.getElementById('empty-api').classList.add('hidden'); }

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
  if (!url)              { showOnboardingError('Ingresá la URL del Web App.'); return; }
  if (!isValidApiUrl(url)) {
    showOnboardingError('La URL debe empezar con https://script.google.com/macros/');
    return;
  }
  saveApiUrl(url);
  location.reload();
}

/* ──────────────────────────── Event listeners ──────────────────── */

function bindCommonListeners() {
  document.getElementById('api-url-form').addEventListener('submit', handleSaveUrl);
  document.getElementById('btn-change-url').addEventListener('click', clearApiUrlAndReload);
  document.getElementById('btn-error-change-url').addEventListener('click', clearApiUrlAndReload);
  document.getElementById('btn-error-retry').addEventListener('click', loadAll);
}

function bindDashboardListeners() {
  document.getElementById('btn-refresh').addEventListener('click', loadAll);

  document.getElementById('filter-search').addEventListener('input', e => {
    state.filters.search = e.target.value; applyFilters();
  });
  document.getElementById('filter-ruc').addEventListener('change', e => {
    state.filters.ruc = e.target.value; applyFilters();
  });
  document.getElementById('filter-estado').addEventListener('change', e => {
    state.filters.estado = e.target.value; applyFilters();
  });
  document.getElementById('filter-pendientes').addEventListener('change', e => {
    state.filters.soloPendientes = e.target.checked; applyFilters();
  });
  document.getElementById('filter-since').addEventListener('change', e => {
    state.filters.since = e.target.value; applyFilters();
  });

  /* Status select — event delegation on tbody */
  document.getElementById('notif-tbody').addEventListener('change', e => {
    if (e.target.classList.contains('select-estado')) {
      handleStatusChange(e.target.dataset.id, e.target.value);
    }
  });

  /* Modal close */
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
  });
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target.id === 'modal') document.getElementById('modal').classList.add('hidden');
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.getElementById('modal').classList.add('hidden');
  });

  /* Modal tabs */
  document.querySelectorAll('.modal-tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
}

/* ──────────────────────────── Boot ────────────────────────────── */

function boot() {
  bindCommonListeners();
  state.apiUrl = getStoredApiUrl();

  if (!state.apiUrl) {
    showOnboarding();
    return;
  }

  showDashboard();
  bindDashboardListeners();
  loadAll();
  loadTemplates();

  /* Auto-refresh cada 5 min */
  setInterval(loadAll, 5 * 60 * 1000);
}

boot();
