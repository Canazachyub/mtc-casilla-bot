# 🗺️ ROADMAP — MTC Casilla Bot

> Plan de evolución por fases. Las fases son **incrementales**: cada una agrega valor sobre la anterior.
> NO empezar Fase 2 antes de tener Fase 1 funcionando end-to-end.

---

## 🎯 Visión global

| Fase | Foco | Entregable principal | Estado |
|---|---|---|---|
| **0** | Setup + foundations | Estructura, config, credenciales, primer login | ✅ 2026-04-28 |
| **1** | MVP del pipeline | Notificación → Drive + Sheet + frontend básico | ✅ 2026-05-13 |
| **1.5** | Dashboard v2 | Empresas, docs, tareas manuales, sync cross-device | ✅ 2026-05-25 |
| **2** | Sistema de plantillas | Propuestas de respuesta editables desde el frontend | 🚀 siguiente |
| **3** | IA en la nube | Regeneración desde Apps Script sin Python local | ⏳ |
| **4** | Productividad | Editor avanzado, exportación Word/PDF, alertas | ⏳ |
| **5** | Multi-cliente | Onboarding nuevas empresas, white-label, multi-tenant | 🔮 |

---

## ✅ FASE 0 — Setup (días 1-2) — COMPLETADA 2026-04-28

**Owner:** backend-python-agent · cloud-google-agent

- [x] Estructura del proyecto (`src/`, `tests/`, `.claude/`)
- [x] `pyproject.toml` con uv
- [x] `config.py` que carga `.env` y CSV de RUCs
- [x] Service account de Google creado y JSON guardado
- [x] Sheet "RESOLVE APP" con los 3 tabs (notificaciones, logs, rucs)
- [x] Carpeta Drive "RESOLVE APP" creada y compartida con SA
- [x] Apps Script Web App deployado (endpoints health + summary funcionan)
- [x] Frontend abre, conecta con la API, muestra "0 notificaciones"
- [x] `mtc-bot doctor` devuelve todo verde

---

## ✅ FASE 1 — MVP del pipeline — FUNCIONAL 2026-05-13

**Owner:** backend-python-agent + cloud-google-agent + qa-agent

- [x] Scraper completo: login directo + Clave SOL — 10 RUCs reales probados
- [x] PDF pipeline: merge ordenado (doc → constancia notif → lectura) + rename oficial
- [x] AI Extractor: DeepSeek primario, Gemini fallback, schema Pydantic
- [x] Drive uploader: estructura `YYYY/MM/RUC/` + OAuth User Delegation
- [x] Sheet writer: append idempotente por `{ruc}__{notification_id}`
- [x] CLI `mtc-bot run --since today` ejecuta pipeline end-to-end
- [x] Idempotencia verificada: re-ejecutar muestra `⊝ ya procesada (skip)`
- [x] Frontend muestra datos reales 2026 (notificaciones, emisor, plazo, PDF embebido)
- [ ] `obsidian_writer.py` — diferido a Fase 2
- [ ] Tests ≥70% coverage — pendiente QA pass formal
- [ ] QA pass formal (qa-agent) — pendiente

**Criterio de Done Fase 1:** ✅ notificación de hoy aparece en el frontend tras `mtc-bot run --since today`.

---

## ✅ FASE 1.5 — Dashboard v2 + Gestión de Empresas — COMPLETADA 2026-05-25

**Owner:** frontend-agent + cloud-google-agent

> Mejoras de UX y gestión documental implementadas entre las fases 1 y 2.

### Frontend

- [x] Pestaña **☰ Tareas pendientes** — tabla con filtros (empresa, progreso, fecha, búsqueda)
- [x] Pestaña **📋 Casillas en proceso** — vista agrupada por empresa con semáforo de urgencia
- [x] Pestaña **🏢 Empresas** — acordeón de 11 empresas CITV con documentación requerida
- [x] **Upload PDF por empresa** — 11 slots de documentos por empresa (póliza, calibración, acreditaciones, etc.)
- [x] **Previsualización PDF** en iframe (Google Drive `/preview`)
- [x] **Selector de empresa** en "Generar Respuesta" con texto legal completo de personería jurídica
- [x] **➕ Nueva tarea manual** — modal con formulario, se guarda en localStorage + Sheet
- [x] **Sync cross-device** — al cargar, trae URLs de Drive desde Sheet para cualquier navegador
- [x] Filtro "Solo pendientes" excluye PRESENTADO (antes era solo NO INICIADO/AGENDAR)
- [x] Formulario de alta/edición de empresa desde el dashboard (incluye credenciales scraper)

### Apps Script (doPost + nuevos GET)

- [x] `POST upload_empresa_doc` → sube PDF a `Drive/Empresas/{key}/{doc}.pdf`, registra en Sheet
- [x] `POST save_tarea_manual` → append idempotente en tab `notificaciones` (origen=manual)
- [x] `GET get_empresa_docs` → devuelve todos los docs de empresa para sync al cargar
- [x] Tab `empresa_docs` creado automáticamente en el primer upload
- [x] Scope `drive` (no `drive.readonly`) para permitir escritura desde Apps Script

### Infraestructura

- [x] Deploy en GitHub Pages vía workflow automático (push a `main` → deploy `frontend/`)
- [x] URL pública: `canazachyub.github.io/mtc-casilla-bot`
- [x] Tests de todos los endpoints desde PowerShell (health ✅ / get_empresa_docs ✅ / save_tarea_manual ✅ / upload_empresa_doc ✅)

---

## 🚀 FASE 2 — Sistema de plantillas (próxima)

**Owner:** templates-agent + backend-python-agent + frontend-agent

### Pendiente de Fase 1 (completar antes)

- [ ] QA pass formal: `uv run ruff check` + `uv run pytest` + security scan
- [ ] `obsidian_writer.py` — nota `.md` por notificación procesada con frontmatter
- [ ] Tests ≥70% coverage en módulos del pipeline

### Plantillas

- [ ] Crear 5 plantillas reales en `RESOLVE/_templates/`:
  - `sutran-solicitud-expedientes.md`
  - `sutran-solicitud-filmaciones.md`
  - `sutran-descargo-observacion.md`
  - `sutran-cumplimiento-resolucion.md`
  - `generica-acuse-recibo.md`
- [ ] `response_generator.py` con scoring TF-IDF + matcher
- [ ] `mtc-bot templates sync` → Obsidian → Drive

### Pipeline

- [ ] Integrar `response_generator.py` tras extracción IA
- [ ] Sheet: agregar columnas `template_id`, `propuesta_respuesta`, `propuesta_calidad`, `estado_propuesta`
- [ ] Llenar propuesta automáticamente al procesar notificación

### Frontend

- [ ] Modal detalle muestra propuesta editable (contenteditable)
- [ ] Botones: 💾 Guardar · ✅ Aprobar · 📋 Copiar
- [ ] Apps Script: endpoint `POST save_propuesta` para persistir cambios

**Criterio de Done Fase 2:** notificación SUTRAN llega → 30s después hay propuesta lista para revisar en el frontend.

---

## ☁️ FASE 3 — IA en la nube

**Owner:** cloud-google-agent + frontend-agent

> El equipo puede regenerar respuestas sin Python corriendo — desde el celular, otra máquina, o un domingo.

- [ ] `UrlFetchApp` a DeepSeek desde Apps Script (ya hay `DEEPSEEK_API_KEY` en PropertiesService)
- [ ] `UrlFetchApp` a Gemini como fallback
- [ ] Endpoint `GET ?action=generate_response` — ya existe, expandir para que use empresa_texto
- [ ] Frontend: botón 🔄 Regenerar funcional sin necesitar Python
- [ ] Loading state + timeout + error con mensaje claro
- [ ] Log de regeneraciones en tab `logs` (quién, cuándo, modelo)

**Criterio de Done Fase 3:** desde el celular, abrir el frontend, abrir una notif, click "Regenerar", ver propuesta en ≤15 segundos.

---

## 🛠️ FASE 4 — Productividad

**Owner:** frontend-agent + templates-agent

- [ ] Diff visual entre versiones de propuesta
- [ ] Exportar a Word (`.docx`) con membrete — botón ya existe, mejorar formato
- [ ] Exportar a PDF (vía LibreOffice headless)
- [ ] Crear Google Doc desde propuesta (botón "Abrir como Doc")
- [ ] Sistema de comentarios por notificación
- [ ] Notificaciones por correo (Gmail API) ante plazo urgente (<2 días)
- [ ] Telegram bot opcional (`mtc-bot notify --telegram`)
- [ ] Vista calendario con plazos
- [ ] Métricas: tiempo promedio de respuesta, % completado a tiempo
- [ ] Tracking "enviada" — fecha de respuesta real registrada

**Criterio de Done Fase 4:** ciclo completo (recepción → análisis → propuesta → revisión → exportación → tracking) sin abrir Word ni Drive manualmente.

---

## 🏢 FASE 5 — Multi-cliente

**Owner:** todos

> Si TELCOM ENERGY quiere ofrecer esto como servicio a otros CITV o empresas reguladas.

- [ ] Onboarding wizard para agregar nuevo cliente (RUC + credenciales + logo)
- [ ] Multi-tenancy: cada empresa ve solo sus notificaciones
- [ ] Auth en frontend (Google Sign-In + whitelist por dominio)
- [ ] Personalización de plantillas por empresa
- [ ] Dashboards individuales por empresa
- [ ] Reportes mensuales (PDF) generados automáticamente
- [ ] SLA monitoring: alertas si notificación no procesada en N horas

---

## 🔮 Ideas futuras (sin fecha)

- **OCR para escaneados** (Tesseract o Gemini Vision)
- **Búsqueda semántica** de notificaciones similares (embeddings)
- **Auto-aprende plantillas**: si Yubert edita la propuesta, aprender para futuras similares
- **Integración con casillas de OTRAS entidades** (OEFA, INDECOPI, OSITRAN)
- **App móvil nativa** (después de Fase 4 si hay demanda)
- **Vencimientos de docs de empresa**: alerta automática cuando póliza o calibración vence pronto
- **Historial de cambios** por notificación (quién cambió progreso, cuándo)

---

## 📋 Reglas de evolución

1. **No saltar fases.** Si Fase 1 está al 80%, terminar primero.
2. **Cada fase debe tener QA pass** (qa-agent) antes de declararse done.
3. **Cada fase debe ser deployable.** Si Fase 2 se demora, Fase 1 sigue siendo útil.
4. **Decision Log obligatorio** en `CLAUDE.md` para cambios arquitectónicos.
5. **No agregar features fuera del roadmap** sin discutirlo primero.

---

## 🤖 Asignación de agentes por fase

| Fase | backend-python | cloud-google | frontend | templates | qa |
|---|:-:|:-:|:-:|:-:|:-:|
| 0 | ✓✓✓ | ✓✓✓ | ✓ | — | ✓ |
| 1 | ✓✓✓ | ✓✓ | ✓✓ | — | ✓✓ |
| 1.5 | — | ✓✓ | ✓✓✓ | — | ✓ |
| 2 | ✓✓ | ✓ | ✓✓ | ✓✓✓ | ✓✓ |
| 3 | ✓ | ✓✓✓ | ✓✓ | ✓ | ✓ |
| 4 | ✓✓ | ✓ | ✓✓✓ | ✓✓ | ✓✓ |
| 5 | ✓✓ | ✓✓ | ✓✓ | ✓✓ | ✓✓✓ |

> ✓ = involucrado · ✓✓ = activo · ✓✓✓ = lead

---

## 💸 Estimación de costos (mensual)

| Volumen | DeepSeek | Gemini | Drive + Sheets + Apps Script | GitHub Pages | Total |
|---|---|---|---|---|---|
| 50 notif/mes | <$0.10 | gratis | gratis | gratis | **<$0.10 USD** |
| 200 notif/mes | ~$0.40 | gratis | gratis | gratis | **~$0.40 USD** |
| 500 notif/mes | ~$1.00 | gratis | gratis | gratis | **~$1.00 USD** |
