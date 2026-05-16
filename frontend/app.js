/* ════════════════════════════════════════════════════════════════
   MTC Casilla Bot — Frontend v4
   Vistas: Tareas pendientes (agrupadas por empresa) + Todas
   API: Apps Script REST (localStorage: mtc_bot_api_url)
   ════════════════════════════════════════════════════════════════ */

const STORAGE_KEY    = 'mtc_bot_api_url';
const API_URL_PREFIX = 'https://script.google.com/macros/';

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
  view:    'pending',       // 'pending' | 'all'
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

  try {
    const [summary, list] = await Promise.all([
      api('summary'),
      api('list', { limit: 500 }),
    ]);
    renderMetrics(summary);
    state.items = list.items || [];
    populateEmpresaFilter(state.items);
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
  document.getElementById('view-pending').classList.toggle('hidden', viewId !== 'pending');
  document.getElementById('view-all').classList.toggle('hidden', viewId !== 'all');
  applyFilters();
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
    if (f.progreso) data = data.filter(i => i.progreso === f.progreso);
    if (f.soloPendientes) {
      data = data.filter(i => i.progreso === 'NO INICIADO' || i.progreso === 'AGENDAR');
    }
  }

  if (f.since) {
    const since = new Date(f.since);
    data = data.filter(i => i.fecha_notificacion && new Date(i.fecha_notificacion) >= since);
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
      <td><button class="btn-detail" data-id="${escapeHtml(i.id)}">Ver →</button></td>
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
      <div><strong>Emisor:</strong> ${escapeHtml(d.emisor || '—')}</div>
      <div><strong>Casilla origen:</strong> ${escapeHtml(d.casilla_origen || '—')}</div>
      <div><strong>Referencia:</strong> ${escapeHtml(d.referencia || '—')}</div>
      <div><strong>Plazo:</strong> ${escapeHtml(String(d.plazo_dias_habiles || '—'))} días hábiles</div>
      <div><strong>Vence:</strong> ${formatDate(d.plazo_vencimiento)} &nbsp;${badgeDias(d.dias_restantes)}</div>
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

function renderResponsePanel(notifId, detail) {
  if (state.templates.length === 0) {
    return `
      <div class="response-no-templates">
        <p>⚠️ No hay plantillas disponibles.</p>
        <p class="muted small">Ejecutá <code>_setupPlantillas()</code> en Apps Script, luego recargá el dashboard.</p>
      </div>
    `;
  }
  const suggestedTpl  = guessTemplateId(detail);
  const tplOptions    = state.templates
    .map(t => `<option value="${escapeHtml(t.id)}"${t.id === suggestedTpl ? ' selected' : ''}>${escapeHtml(t.nombre)}${t.tipo_notificacion ? ' — ' + escapeHtml(t.tipo_notificacion) : ''}</option>`)
    .join('');
  const ciudadDefault = escapeHtml(detail.sede || 'Lima');
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
        <label class="form-label">Ciudad (encabezado del documento)</label>
        <input id="resp-ciudad" type="text" class="response-input" value="${ciudadDefault}" placeholder="Lima">
      </div>
      <div class="form-group">
        <label class="form-label">Justificación / Insumos</label>
        <textarea id="resp-justification" class="response-textarea"
          placeholder="Fechas relevantes, argumentos legales, datos de la empresa, acciones tomadas..."
          rows="6"></textarea>
      </div>
      <button id="btn-generate" class="btn-generate">✨ Generar con IA</button>
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
  document.getElementById('btn-generate').addEventListener('click', async () => {
    const templateId    = document.getElementById('resp-template').value;
    const justificacion = document.getElementById('resp-justification').value.trim();
    const ciudad        = (document.getElementById('resp-ciudad')?.value || '').trim() || detail.sede || 'Lima';
    if (!templateId) { showToast('Seleccioná una plantilla primero', 'warn'); return; }
    await handleGenerateResponse(notifId, templateId, justificacion, ciudad);
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

async function handleGenerateResponse(notifId, templateId, justificacion, ciudad) {
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
  state.apiUrl = url;
  showDashboard();
  loadTemplates();
  loadAll();
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

  // Initial view state
  switchView('pending');
});
