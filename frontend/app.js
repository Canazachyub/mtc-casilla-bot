/* ════════════════════════════════════════════════════════════════
   MTC Casilla Bot — Frontend
   Consume la API REST de Apps Script.
   La URL del API se guarda en localStorage (clave: mtc_bot_api_url).
   ════════════════════════════════════════════════════════════════ */

const STORAGE_KEY = 'mtc_bot_api_url';
const API_URL_PREFIX = 'https://script.google.com/macros/';

const state = {
  apiUrl: '',
  items: [],
  filtered: [],
  filters: {
    search: '',
    ruc: '',
    estado: '',
    soloPendientes: false,
    since: '',
  },
};

/* ────────── Config / localStorage ────────── */

function getStoredApiUrl() {
  try {
    const raw = (localStorage.getItem(STORAGE_KEY) || '').trim();
    if (!raw) return '';
    if (raw.includes('REEMPLAZAR_AQUI')) return '';
    return raw;
  } catch (_err) {
    return '';
  }
}

function saveApiUrl(url) {
  localStorage.setItem(STORAGE_KEY, url);
}

function clearApiUrlAndReload() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (_err) { /* ignore */ }
  location.reload();
}

function isValidApiUrl(url) {
  return typeof url === 'string' && url.startsWith(API_URL_PREFIX);
}

/* ────────── API ────────── */

async function api(action, params = {}) {
  if (!state.apiUrl) throw new Error('API_URL no configurada.');
  const url = new URL(state.apiUrl);
  url.searchParams.set('action', action);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) url.searchParams.set(k, v);
  });
  const resp = await fetch(url.toString());
  if (!resp.ok) throw new Error(`HTTP ${resp.status} al llamar a ${action}`);
  const data = await resp.json();
  if (data.error) throw new Error(data.message || data.error);
  return data;
}

/* ────────── Carga inicial ────────── */

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

/* ────────── Render ────────── */

function renderMetrics(s) {
  document.getElementById('m-total').textContent = s.total ?? 0;
  document.getElementById('m-pendientes').textContent = s.pendientes ?? 0;
  document.getElementById('m-vencidos').textContent = s.vencidos ?? 0;
  document.getElementById('m-hoy').textContent = s.hoy ?? 0;
}

function populateRucFilter(items) {
  const sel = document.getElementById('filter-ruc');
  const rucs = [...new Set(items.map(i => i.ruc).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Todos los RUCs</option>' +
    rucs.map(r => {
      const empresa = (items.find(i => i.ruc === r)?.empresa || '').slice(0, 30);
      return `<option value="${r}">${r} — ${empresa}</option>`;
    }).join('');
}

function applyFilters() {
  const f = state.filters;
  let data = [...state.items];

  if (f.search) {
    const q = f.search.toLowerCase();
    data = data.filter(i =>
      (i.documento || '').toLowerCase().includes(q) ||
      (i.empresa || '').toLowerCase().includes(q) ||
      (i.asunto || '').toLowerCase().includes(q) ||
      (i.resumen || '').toLowerCase().includes(q)
    );
  }
  if (f.ruc) data = data.filter(i => String(i.ruc) === f.ruc);
  if (f.estado) data = data.filter(i => i.estado === f.estado);
  if (f.soloPendientes) {
    data = data.filter(i =>
      String(i.requiere_respuesta).toUpperCase() === 'TRUE' &&
      i.estado === 'pendiente'
    );
  }
  if (f.since) {
    const since = new Date(f.since);
    data = data.filter(i =>
      i.fecha_notificacion && new Date(i.fecha_notificacion) >= since
    );
  }

  state.filtered = data;
  renderTable(data);
}

function renderTable(items) {
  const tbody = document.getElementById('notif-tbody');
  const table = document.getElementById('notif-table');
  const emptyFiltered = document.getElementById('empty-filtered');
  const emptyApi = document.getElementById('empty-api');

  // Caso 1: la API no devolvió items en absoluto → empty state amable.
  if (state.items.length === 0) {
    table.classList.add('hidden');
    emptyFiltered.classList.add('hidden');
    emptyApi.classList.remove('hidden');
    return;
  }

  emptyApi.classList.add('hidden');

  // Caso 2: hay items pero los filtros los excluyen todos.
  if (items.length === 0) {
    table.classList.add('hidden');
    emptyFiltered.classList.remove('hidden');
    return;
  }

  emptyFiltered.classList.add('hidden');
  table.classList.remove('hidden');

  tbody.innerHTML = items.map(i => `
    <tr data-id="${escapeHtml(i.id)}">
      <td>${badgeEstado(i)}</td>
      <td>${formatDate(i.fecha_notificacion)}</td>
      <td><strong>${escapeHtml(i.documento || '—')}</strong>
          <div class="muted small">${escapeHtml((i.asunto || '').slice(0, 80))}</div></td>
      <td><div>${escapeHtml((i.empresa || '').slice(0, 35))}</div>
          <div class="muted small">${i.ruc || ''}</div></td>
      <td>${escapeHtml(i.emisor || '—')}</td>
      <td>${i.plazo_vencimiento ? formatDate(i.plazo_vencimiento) : '—'}</td>
      <td>${badgeDias(i.dias_restantes)}</td>
      <td><button class="btn-detail" data-id="${escapeHtml(i.id)}">Ver</button></td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.btn-detail').forEach(btn =>
    btn.addEventListener('click', () => openDetail(btn.dataset.id))
  );
}

function badgeEstado(i) {
  const estado = i.estado || '—';
  const cls = {
    pendiente: 'badge pendiente',
    completado: 'badge completado',
    informativo: 'badge informativo',
  }[estado] || 'badge';
  return `<span class="${cls}">${estado}</span>`;
}

function badgeDias(dias) {
  if (dias === undefined || dias === null || dias === '') {
    return '<span class="muted">—</span>';
  }
  const d = parseInt(dias, 10);
  let cls = 'badge';
  if (d < 0) cls = 'badge vencido';
  else if (d <= 1) cls = 'badge urgente';
  else if (d <= 3) cls = 'badge alerta';
  else cls = 'badge ok';
  const label = d < 0 ? `Vencido (${Math.abs(d)}d)` : `${d}d`;
  return `<span class="${cls}">${label}</span>`;
}

/* ────────── Detalle ────────── */

async function openDetail(id) {
  const modal = document.getElementById('modal');
  const body = document.getElementById('modal-body');
  body.innerHTML = '<p class="loading">Cargando detalle...</p>';
  modal.classList.remove('hidden');

  try {
    const detail = await api('detail', { id });
    body.innerHTML = renderDetail(detail);
  } catch (err) {
    body.innerHTML = `<p class="error">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function renderDetail(d) {
  return `
    <h2>📄 ${escapeHtml(d.documento || 'Sin nombre')}</h2>
    <p class="muted">${escapeHtml(d.asunto || '')}</p>

    <div class="detail-grid">
      <div><strong>Fecha notificación:</strong> ${formatDate(d.fecha_notificacion)}</div>
      <div><strong>RUC:</strong> ${d.ruc || '—'}</div>
      <div><strong>Empresa:</strong> ${escapeHtml(d.empresa || '—')}</div>
      <div><strong>Emisor:</strong> ${escapeHtml(d.emisor || '—')}</div>
      <div><strong>Plazo:</strong> ${d.plazo_dias_habiles || '—'} días hábiles</div>
      <div><strong>Vence:</strong> ${formatDate(d.plazo_vencimiento)} ${badgeDias(d.dias_restantes)}</div>
      <div><strong>Estado:</strong> ${badgeEstado(d)}</div>
      <div><strong>Confianza IA:</strong> ${d.confianza_ia || '—'} (${d.modelo_ia || '—'})</div>
    </div>

    <h3>📋 Resumen</h3>
    <p>${escapeHtml(d.resumen || 'Sin resumen.')}</p>

    ${d.notas ? `<h3>📝 Notas</h3><p>${escapeHtml(d.notas)}</p>` : ''}

    ${d.drive_view_url ? `
      <h3>📎 PDF</h3>
      <iframe class="pdf-frame" src="${embedDriveUrl(d.drive_view_url)}"></iframe>
      <p><a href="${d.drive_view_url}" target="_blank">Abrir en Drive ↗</a></p>
    ` : ''}
  `;
}

function embedDriveUrl(url) {
  // Convertir https://drive.google.com/file/d/<ID>/view → .../preview
  const match = url.match(/\/file\/d\/([^/]+)/);
  if (match) return `https://drive.google.com/file/d/${match[1]}/preview`;
  return url;
}

/* ────────── Helpers ────────── */

function formatDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString('es-PE', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showLoading(on) {
  document.getElementById('loading').classList.toggle('hidden', !on);
}

function showErrorCard(msg) {
  document.getElementById('error-api-url').textContent = state.apiUrl || '(no configurada)';
  document.getElementById('error-message').textContent = msg;
  document.getElementById('error-card').classList.remove('hidden');
  // Ocultar tabla y empty states mientras hay error
  document.getElementById('notif-table').classList.add('hidden');
  document.getElementById('empty-filtered').classList.add('hidden');
  document.getElementById('empty-api').classList.add('hidden');
}

function hideErrorCard() {
  document.getElementById('error-card').classList.add('hidden');
}

function hideEmptyApi() {
  document.getElementById('empty-api').classList.add('hidden');
}

/* ────────── Onboarding ────────── */

function showOnboarding() {
  document.getElementById('onboarding').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  document.getElementById('btn-refresh').classList.add('hidden');
  document.getElementById('btn-change-url').classList.add('hidden');
  document.getElementById('api-status').innerHTML =
    '<span class="ko">●</span> Sin configurar';
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

function hideOnboardingError() {
  document.getElementById('onboarding-error').classList.add('hidden');
}

function handleSaveUrl(e) {
  e.preventDefault();
  hideOnboardingError();
  const input = document.getElementById('api-url-input');
  const url = (input.value || '').trim();

  if (!url) {
    showOnboardingError('Ingresá la URL del Web App.');
    return;
  }
  if (!isValidApiUrl(url)) {
    showOnboardingError(
      'La URL debe empezar con https://script.google.com/macros/'
    );
    return;
  }

  saveApiUrl(url);
  location.reload();
}

/* ────────── Event listeners ────────── */

function bindCommonListeners() {
  document.getElementById('api-url-form')
    .addEventListener('submit', handleSaveUrl);

  document.getElementById('btn-change-url')
    .addEventListener('click', clearApiUrlAndReload);

  document.getElementById('btn-error-change-url')
    .addEventListener('click', clearApiUrlAndReload);

  document.getElementById('btn-error-retry')
    .addEventListener('click', loadAll);
}

function bindDashboardListeners() {
  document.getElementById('btn-refresh').addEventListener('click', loadAll);

  document.getElementById('filter-search').addEventListener('input', e => {
    state.filters.search = e.target.value;
    applyFilters();
  });
  document.getElementById('filter-ruc').addEventListener('change', e => {
    state.filters.ruc = e.target.value;
    applyFilters();
  });
  document.getElementById('filter-estado').addEventListener('change', e => {
    state.filters.estado = e.target.value;
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

  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
  });
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target.id === 'modal') {
      document.getElementById('modal').classList.add('hidden');
    }
  });
}

/* ────────── Boot ────────── */

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
  // Auto-refresh cada 5 min
  setInterval(loadAll, 5 * 60 * 1000);
}

boot();
