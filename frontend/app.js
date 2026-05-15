/* ════════════════════════════════════════════════════════════════
   MTC Casilla Bot — Frontend v3
   Consume la API REST de Apps Script (acción GET, params por URL).
   API_URL se guarda en localStorage (clave: mtc_bot_api_url).
   ════════════════════════════════════════════════════════════════ */

const STORAGE_KEY    = 'mtc_bot_api_url';
const API_URL_PREFIX = 'https://script.google.com/macros/';

const ALLOWED_ESTADOS = ['pendiente', 'en-proceso', 'completado', 'informativo', 'archivada'];
const ESTADO_LABELS   = {
  pendiente:    'Pendiente',
  'en-proceso': 'En proceso',
  completado:   'Completado',
  informativo:  'Informativo',
  archivada:    'Archivada',
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
  apiUrl: '',
  items:     [],
  filtered:  [],
  templates: [],
  currentDetailId: null,
  currentDetail:   null,
  filters: {
    search: '', sede: '', progreso: '',
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
    populateSedeFilter(state.items);
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
  document.getElementById('m-total').textContent      = s.total      ?? 0;
  document.getElementById('m-pendientes').textContent  = s.pendientes ?? 0;
  document.getElementById('m-vencidos').textContent    = s.vencidos   ?? 0;
  document.getElementById('m-hoy').textContent         = s.hoy        ?? 0;
}

function populateSedeFilter(items) {
  const sel   = document.getElementById('filter-sede');
  const sedes = [...new Set(items.map(i => i.sede).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Todas las sedes</option>' +
    sedes.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
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
  if (f.sede)    data = data.filter(i => i.sede === f.sede);
  if (f.progreso) data = data.filter(i => i.progreso === f.progreso);
  if (f.soloPendientes) {
    data = data.filter(i =>
      i.progreso === 'NO INICIADO' || i.progreso === 'AGENDAR'
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
  if (item.progreso === 'PRESENTADO') return '';
  if (item.plazo_vencido) return 'row-vencido';
  const d = parseInt(item.dias_restantes, 10);
  if (isNaN(d)) return '';
  if (d < 0)   return 'row-vencido';
  if (d <= 1)  return 'row-urgente';
  if (d <= 3)  return 'row-alerta';
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
  if (!tareaStr) return '<span class="muted">—</span>';
  const tareas = tareaStr.split(',').map(t => t.trim()).filter(Boolean);
  if (tareas.length === 0) return '<span class="muted">—</span>';
  const max   = 2;
  const shown = tareas.slice(0, max).map(t => `<span class="tag-tarea">${escapeHtml(t)}</span>`).join('');
  const extra = tareas.length > max
    ? ` <span class="tag-more">+${tareas.length - max}</span>`
    : '';
  return shown + extra;
}

function renderTable(items) {
  const tbody         = document.getElementById('notif-tbody');
  const table         = document.getElementById('notif-table');
  const emptyFiltered = document.getElementById('empty-filtered');
  const emptyApi      = document.getElementById('empty-api');

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
      <td>${progresoSelect(i)}</td>
      <td>
        <div>${formatDate(i.fecha_notificacion)}</div>
        ${i.plazo_vencido ? '<span class="badge vencido small">Venció</span>' : ''}
      </td>
      <td>
        <strong>${escapeHtml(i.documento || '—')}</strong>
        <div class="muted small">${escapeHtml((i.asunto || '').slice(0, 90))}</div>
      </td>
      <td>
        <div>${escapeHtml((i.empresa || '').slice(0, 35))}</div>
        ${i.sede ? `<div class="muted small">📍 ${escapeHtml(i.sede)}</div>` : ''}
      </td>
      <td class="col-tarea">${tareasBadges(i.tarea)}</td>
      <td>
        <div>${i.plazo_vencimiento ? formatDate(i.plazo_vencimiento) : '—'}</div>
        <div>${badgeDias(i.dias_restantes)}</div>
      </td>
      <td><button class="btn-detail" data-id="${escapeHtml(i.id)}">Ver →</button></td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.btn-detail').forEach(btn =>
    btn.addEventListener('click', () => openDetail(btn.dataset.id))
  );
}

/* ──────────────────────────── Progreso change ─────────────────── */

async function handleProgresoChange(id, progreso) {
  const select = document.querySelector(`select.select-progreso[data-id="${id}"]`);
  const prev   = select ? select.dataset.prev : progreso;

  try {
    await api('update_status', { id, campo: 'progreso', valor: progreso });
    const item = state.items.find(i => i.id === id);
    if (item) item.progreso = progreso;
    if (select) {
      const cls = PROGRESO_CSS[progreso] || 'no-iniciado';
      select.className    = `select-progreso progreso-${cls}`;
      select.dataset.prev = progreso;
      const tr = select.closest('tr');
      if (tr) tr.className = rowUrgencyClass(item || { progreso, plazo_vencido: false });
    }
    showToast(`Progreso: ${PROGRESO_LABELS[progreso] || progreso}`, 'ok');
  } catch (err) {
    if (select) select.value = prev;
    showToast('Error al actualizar: ' + err.message, 'error');
  }
}

/* ──────────────────────────── Notas save ──────────────────────── */

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

function renderDetailTab(d) {
  const tareas = (d.tarea || '').split(',').map(t => t.trim()).filter(Boolean);
  const tareasHtml = tareas.length
    ? tareas.map(t => `<span class="tag-tarea">${escapeHtml(t)}</span>`).join(' ')
    : '<span class="muted">—</span>';

  const progreso = d.progreso || 'NO INICIADO';
  const progresoOptions = ALLOWED_PROGRESO.map(p =>
    `<option value="${p}"${progreso === p ? ' selected' : ''}>${PROGRESO_LABELS[p]}</option>`
  ).join('');
  const progresoClsDetail = PROGRESO_CSS[progreso] || 'no-iniciado';

  return `
    <h2 style="margin:0 0 0.3rem">${escapeHtml(d.documento || 'Sin nombre')}</h2>
    <p class="muted">${escapeHtml(d.asunto || '')}</p>

    <div class="detail-grid">
      <div><strong>Fecha notificación:</strong> ${formatDate(d.fecha_notificacion)}</div>
      <div><strong>Lectura:</strong> ${d.lectura_notificacion ? formatDate(d.lectura_notificacion) : '—'}</div>
      <div><strong>Empresa:</strong> ${escapeHtml(d.empresa || '—')}</div>
      <div><strong>RUC:</strong> ${escapeHtml(d.ruc || '—')}</div>
      <div><strong>Sede:</strong> ${d.sede ? `📍 ${escapeHtml(d.sede)}` : '—'}</div>
      <div><strong>Emisor:</strong> ${escapeHtml(d.emisor || '—')}</div>
      <div><strong>Casilla origen:</strong> ${escapeHtml(d.casilla_origen || '—')}</div>
      <div><strong>Referencia:</strong> ${escapeHtml(d.referencia || '—')}</div>
      <div><strong>Plazo:</strong> ${escapeHtml(String(d.plazo_dias_habiles || '—'))} días hábiles</div>
      <div><strong>Vence:</strong> ${formatDate(d.plazo_vencimiento)} ${badgeDias(d.dias_restantes)}</div>
      <div><strong>Confianza IA:</strong> ${escapeHtml(d.confianza_ia || '—')} (${escapeHtml(d.modelo_ia || '—')})</div>
      <div>
        <strong>Progreso:</strong>
        <select id="detail-progreso-select"
          class="select-progreso progreso-${progresoClsDetail}"
          data-id="${escapeHtml(d.id)}"
          data-prev="${escapeHtml(progreso)}"
          style="margin-top:0.3rem">
          ${progresoOptions}
        </select>
      </div>
    </div>

    <h3>🗂 Tareas</h3>
    <div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.5rem">${tareasHtml}</div>

    <h3>📋 Resumen</h3>
    <p style="line-height:1.7">${escapeHtml(d.resumen || 'Sin resumen.')}</p>

    ${d.drive_view_url ? `
      <h3>📎 PDF unificado</h3>
      <iframe class="pdf-frame" src="${embedDriveUrl(d.drive_view_url)}" allow="autoplay"></iframe>
      <p style="margin-top:0.5rem"><a href="${d.drive_view_url}" target="_blank" rel="noopener">Abrir en Drive ↗</a></p>
    ` : ''}

    <h3>📝 Notas internas</h3>
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
    progresoSel.addEventListener('change', e => {
      handleProgresoChange(id, e.target.value);
    });
  }

  const btnSaveNotas = document.getElementById('btn-save-notas');
  if (btnSaveNotas) {
    btnSaveNotas.addEventListener('click', () => {
      const notas = document.getElementById('notas-edit').value;
      saveNotas(id, notas);
    });
  }
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
    .map(t => `<option value="${escapeHtml(t.id)}">${escapeHtml(t.nombre)}${t.tipo_notificacion ? ' — ' + escapeHtml(t.tipo_notificacion) : ''}</option>`)
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
      document.getElementById('response-output').classList.add('hidden');
      document.getElementById('btn-generate').classList.remove('hidden');
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
      notification_id: notifId,
      template_id: templateId,
      justificacion,
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

  const { Document, Packer, Paragraph, TextRun } = window.docx;

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
  if (!url)               { showOnboardingError('Ingresá la URL del Web App.'); return; }
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
  document.getElementById('filter-sede').addEventListener('change', e => {
    state.filters.sede = e.target.value; applyFilters();
  });
  document.getElementById('filter-progreso').addEventListener('change', e => {
    state.filters.progreso = e.target.value; applyFilters();
  });
  document.getElementById('filter-pendientes').addEventListener('change', e => {
    state.filters.soloPendientes = e.target.checked; applyFilters();
  });
  document.getElementById('filter-since').addEventListener('change', e => {
    state.filters.since = e.target.value; applyFilters();
  });

  /* Progreso select — event delegation on tbody */
  document.getElementById('notif-tbody').addEventListener('change', e => {
    if (e.target.classList.contains('select-progreso')) {
      handleProgresoChange(e.target.dataset.id, e.target.value);
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

  setInterval(loadAll, 5 * 60 * 1000);
}

boot();
