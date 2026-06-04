# CLAUDE.md — MTC Casilla Bot

> Memoria persistente del proyecto. Claude Code lee este archivo en cada sesión.
> **Mantener bajo 250 líneas.** Si crece, mover detalles a `.claude/rules/<tema>.md` o `docs/`.

---

## 1. Identidad

- **Nombre:** mtc-casilla-bot
- **Propósito:** Automatizar el ciclo end-to-end de notificaciones de la **Casilla Electrónica del MTC** (Perú): login → detección → descarga → unión PDF → análisis IA → almacenamiento Drive/Sheets → propuestas de respuesta editables → dashboard web.
- **Owner:** Yubert Canaza (Puno, Perú)
- **Cliente / contexto:** TELCOM ENERGY / MALCOM S.A. — supervisión de CITV que reciben notificaciones de SUTRAN vía MTC.
- **Estado:** Fase 0/1 (setup + MVP).
- **Plataforma objetivo:** Windows 11 (Linux Mint también soportado).

## 2. Stack técnico

### Backend Python (local)
- **Python 3.11+** (gestor: `uv`)
- **Playwright** (Chromium) — scraper con Clave SOL OAuth
- **pypdf** + **pdfplumber** — merge y extracción
- **openai SDK** (apuntando a DeepSeek) + **httpx** (Gemini)
- **google-api-python-client** + **gspread** — Drive + Sheets con service account
- **Pydantic v2** + **typer** + **rich** — modelos y CLI

### Cloud Google
- **Google Drive** — almacenamiento de PDFs unidos (`MTC-Casilla-Bot/YYYY/MM/RUC/`)
- **Google Sheets** — DB principal (`MTC Casilla DB`: tabs `notificaciones`, `logs`, `rucs`)
- **Apps Script Web App** — API REST de lectura para el frontend, IA en la nube
- **Service account** — auth para Python → Drive/Sheets

### Frontend
- **HTML + JS vanilla + CSS** — sin frameworks, sin build step
- Sirve en `localhost` (Python `http.server`) o GitHub Pages
- Consume **solo** la API del Apps Script (nunca toca credenciales)

### IA (dual provider)
- **DeepSeek** (`deepseek-chat`) — primario, extracción JSON estructurada
- **Gemini** (`gemini-2.5-flash`) — fallback automático
- Ambos usables desde **Python local** y **Apps Script (UrlFetchApp)** según el caso

### Almacenamiento de plantillas
- **Bóveda Obsidian RESOLVE** (`C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE`)
  - source of truth de plantillas en `_templates/`
  - notas de notificaciones procesadas en `YYYY/MM-MES/`
- **Drive sincronizado** — para que Apps Script también pueda leer plantillas

## 3. Arquitectura

```
┌──────── PYTHON BOT (local, schedulable) ────────┐
│ Playwright → MTC → descarga                     │
│ Merge PDFs → extracción texto                   │
│ DeepSeek/Gemini → metadata + propuesta          │
│ Sube PDF a Drive (service account)              │
│ Append fila al Sheet (service account)          │
│ (Opcional) escribe nota a Obsidian local        │
└──────────────────────────────────────────────────┘
                    │
                    ▼
┌──────── GOOGLE WORKSPACE (source of truth) ─────┐
│ Drive: PDFs organizados por año/mes/RUC         │
│ Sheet "MTC Casilla DB":                         │
│   ├─ notificaciones (DB)                        │
│   ├─ logs (auditoría)                           │
│   └─ rucs (credenciales — restricted)           │
│ Apps Script Web App:                            │
│   GET ?action=list/detail/summary/pdf           │
│   POST ?action=regenerate (Fase 3, IA en nube)  │
└──────────────────────────────────────────────────┘
                    │
                    ▼
┌──────── FRONTEND (localhost o GH Pages) ────────┐
│ HTML/JS estático                                │
│ Tabla con notificaciones + filtros + semáforo   │
│ Detalle con PDF embebido                        │
│ (Fase 2) Editor de propuesta de respuesta       │
│ (Fase 3) Botón "regenerar" → Apps Script → IA   │
└──────────────────────────────────────────────────┘
```

## 4. Estructura del repositorio

```
mtc-casilla-bot/
├── CLAUDE.md, README.md, ROADMAP.md, PROMPT_INICIAL.md
├── pyproject.toml, .env.example, .gitignore, .mcp.json
├── .claude/
│   ├── settings.json, hooks/, commands/
│   ├── agents/                  ← 5 sub-agentes (paralelizables)
│   │   ├── backend-python-agent.md
│   │   ├── cloud-google-agent.md
│   │   ├── frontend-agent.md
│   │   ├── templates-agent.md
│   │   └── qa-agent.md
│   ├── rules/                   ← convenciones (credentials, playwright)
│   └── skills/                  ← workflows reutilizables
│       ├── mtc-scraper/
│       ├── pdf-pipeline/
│       ├── ai-extractor/
│       ├── drive-uploader/
│       ├── appscript-api/
│       ├── response-generator/
│       └── obsidian-writer/
├── src/mtc_bot/
│   ├── config.py, models.py, cli.py, orchestrator.py
│   ├── scraper/                 ← login, inbox, downloader
│   ├── pdf_pipeline.py
│   ├── ai_extractor.py
│   ├── response_generator.py    ← matching plantillas + fill IA
│   ├── google/                  ← drive_uploader, sheets_writer
│   └── obsidian_writer.py
├── tests/
├── data/                        ← gitignored
│   ├── credentials/             (rucs.csv, service-account.json)
│   ├── downloads/, merged/, processed/
│   └── templates/               (sync local de Obsidian _templates/)
├── appscript/
│   ├── Code.gs, appsscript.json, README.md
├── frontend/
│   ├── index.html, app.js, styles.css, README.md
└── docs/
    ├── SHEET_SCHEMA.md, DEPLOYMENT.md, TEMPLATE_CATALOG.md
```

## 5. Comandos comunes

```bash
# Setup (una vez)
uv sync && uv run playwright install chromium

# Ciclo diario
uv run mtc-bot doctor                       # verificar config
uv run mtc-bot run --dry-run                # vista previa
uv run mtc-bot run --since today            # ejecución real
uv run mtc-bot serve                        # frontend local en :8080

# Plantillas (Fase 2)
uv run mtc-bot templates list
uv run mtc-bot templates sync               # Obsidian → Drive
uv run mtc-bot debug-match --notification-id <X>

# Tests / lint
uv run pytest                               # todos
uv run ruff check src/ && uv run ruff format src/
```

## 6. Convenciones de código

- **Naming:** snake_case (Python), camelCase (JS), PascalCase (clases).
- **Docstrings:** Google style, en español.
- **Type hints:** OBLIGATORIOS en funciones públicas.
- **Async:** scraper, IA, Drive, Sheets — todo async con `httpx.AsyncClient` y `playwright.async_api`.
- **Errores:** capturar específico, loguear con contexto, re-raise si no recuperable.
- **Logs:** `logger.info("X = %s", x)` — formato lazy, NUNCA f-strings con datos sensibles.
- **Líneas:** máximo 100 chars.
- **Tests:** mínimo happy path por módulo público. Mock APIs externas con `respx`.
- **Commits:** Conventional Commits.

## 7. Reglas estrictas (NO HACER)

- ❌ Hardcodear credenciales (ni para "probar rápido")
- ❌ Commitear `data/credentials/`, `.env`, `service-account.json`, `playwright-traces/`
- ❌ Exponer el tab `rucs` del Sheet vía endpoints públicos
- ❌ Procesar 2 veces la misma notificación (chequear `id` antes)
- ❌ Paralelizar el scraping del MISMO RUC
- ❌ Saltar a fases siguientes sin completar la actual + QA pass
- ❌ Implementar features fuera del ROADMAP sin aprobación
- ✅ Si tenés dudas con operación destructiva, **preguntá antes**

## 8. Sub-agentes especializados

5 sub-agentes en `.claude/agents/`, cada uno con su contexto y dominio:

| Agente | Lead en fases | Dominio principal |
|---|---|---|
| `backend-python-agent` | 1 | Scraper, PDFs, IA local, CLI, tests Python |
| `cloud-google-agent` | 0, 3 | Apps Script, Drive, Sheets, service account |
| `frontend-agent` | 4 | HTML/JS/CSS estático, dashboard |
| `templates-agent` | 2 | Plantillas Obsidian, matching, propuestas |
| `qa-agent` | (todas) | Tests, security review, code quality |

**El agente principal (Claude Code) es ORQUESTADOR.** Delega vía Task tool, paraleliza cuando las tareas son independientes, coordina handoffs entre agentes.

## 9. Workflow de Git

- **Branch principal:** `main`
- **Features:** `feat/<descripcion>` (ej: `feat/clave-sol-login`)
- **Commits incrementales:** uno por hito o cambio lógico
- **Pre-push:** `uv run pytest && uv run ruff check`

## 10. Decision Log

| Fecha | Decisión | Razón |
|---|---|---|
| 2026-04-28 | Drive como source of truth (no filesystem local) | Persistencia, compartible, backup |
| 2026-04-28 | Service account para Python, Apps Script solo lectura | Separation of concerns + simplicidad |
| 2026-04-28 | DeepSeek primario, Gemini fallback | DeepSeek 10x más barato; redundancia |
| 2026-04-28 | Plantillas en Obsidian, sync a Drive | Yubert ya edita en Obsidian + permite IA en nube |
| 2026-04-28 | Frontend vanilla JS, sin frameworks | Sin build step, deployable en cualquier estático |
| 2026-04-28 | 5 sub-agentes especializados con context window propio | Paralelismo + reduce contaminación de contexto |
| 2026-04-28 | Roadmap por fases incrementales | No improvisar features; cada fase deployable independientemente |
| 2026-05-13 | OAuth User Delegation para Drive uploads | Service Account no tiene storage quota; usuario OAuth sí |
| 2026-05-13 | `tzdata` como dep explícita en pyproject.toml | Windows no incluye IANA tz data; `ZoneInfo("America/Lima")` falla sin él |
| 2026-05-13 | `date.min` fallback para fechas no parseables en inbox | Evita que items con fecha vacía pasen el filtro `--since today` |
| 2026-06-04 | `click_item` espera título de detalle con texto único del item nuevo | En headless, `wait_for_selector(title)` retorna con título del item anterior; el fix usa `locator.filter(has_text=unique_text)` para evitar descargar PDFs equivocados |

## 11. Estado actual

> **Actualizar al final de cada sesión.**

**Fase actual:** Fase 1 ✅ + feature informe (2026-06-04)
**Próximo paso:** QA pass formal → Fase 2 (plantillas + propuestas de respuesta).

**Hitos Fase 0 — completados (2026-04-28):**
- [x] Estructura, `pyproject.toml`, `config.py`, `models.py`, `cli.py`
- [x] Service account + Sheet "RESOLVE APP" (3 tabs) + Drive + Apps Script
- [x] Frontend localhost:8080 + `mtc-bot doctor` verde

**Hitos Fase 1 — completados (2026-05-13):**
- [x] `scraper/login.py`: login directo (PERSONA JURÍDICA) + Clave SOL — 10 RUCs reales OK
- [x] `scraper/inbox.py`: listado, paginación, date parser, early termination, `_navigate_to_page`
- [x] `scraper/downloader.py`: descarga de 3 adjuntos por notificación vía Playwright
- [x] `pdf_pipeline.py`: merge ordenado + rename con nombre oficial
- [x] `ai_extractor.py`: DeepSeek primario + Gemini fallback + contexto combinado (portal+PDF)
- [x] `google/drive_uploader.py`: estructura `YYYY/MM/RUC/` + OAuth User Delegation
- [x] `google/sheets_writer.py`: append idempotente + `delete_notificacion` para `--overwrite`
- [x] `cli.py`: `mtc-bot run --since --overwrite` end-to-end en 9 RUCs reales
- [x] Paginación robusta: espera cambio del label del paginator (no solo networkidle)
- [x] Frontend: edición inline de `emisor`, `plazo_dias_habiles`, `plazo_vencimiento`
- [x] `scripts/debug_scraper_ui.py`: GUI Tkinter para verificación día a día
- [x] 9 casillas verificadas con debug tool (13/05→03/06/2026) — sin errores de fecha/PDFs
- [x] Run completo con `--overwrite` exitoso: 10 notifs procesadas, Sheet actualizado
- [x] Fix crítico: 2ª notificación ya no descarga PDFs de la 1ª (bug Angular headless)
- [ ] `obsidian_writer.py` — diferido a Fase 2
- [ ] Tests ≥70% coverage — pendiente QA pass formal

**Mejoras aplicadas en sesión 2026-06-03:**
- `inbox.py`: fix paginación Angular — esperar cambio de paginator antes de leer items
- `cli.py`: flag `--overwrite` — borra fila existente y reprocesa completo
- `ai_extractor.py` (input): combina metadata portal + cuerpo HTML + PDF texto
- `debug_scraper_ui.py`: GUI completa con calendarios, capturas por página, test IA,
  tabla de fechas por pág, orden de merge, preview contexto IA, carpetas timestampeadas

**Mejoras aplicadas en sesión 2026-06-04:**
- `inbox.py` `click_item`: bug crítico — 2ª notificación descargaba PDFs de la 1ª.
  Causa: `wait_for_selector(SEL_DETAIL_TITLE)` retornaba con el título anterior visible.
  Fix: `page.locator(SEL_DETAIL_TITLE).filter(has_text=unique_text).wait_for(visible)` —
  espera que el título del detalle contenga el número/texto único del item nuevo.
  Verificado con `--overwrite` completo: 10 notifs con PDFs y constancias distintos.
- Feature `informe`: nuevo campo `informe` en Sheet + frontend. Gemini (contexto 1M)
  primario → DeepSeek fallback. `pdf_pipeline.extract_text(max_pages=None)` para texto
  completo. `_gemini_auth()` detecta formato `AQ.` vs `AIzaSy` automáticamente.
  Gemini bloqueado por account type (cuenta institucional edu); DeepSeek fallback OK.
- `frontend/app.js`: `renderMarkdown()` propio + sección "🧾 Informe IA" colapsable.
- Sheet: columna `informe` añadida manualmente.

**Pendientes para Fase 2:**
1. QA pass formal de Fase 1 (ruff + pytest + security scan).
2. 5 plantillas reales en `_templates/` (Obsidian).
3. `response_generator.py`: scoring TF-IDF + matcher + fill IA.
4. `mtc-bot templates sync` (Obsidian → Drive).
5. Sheet: columnas `template_id`, `propuesta_respuesta`, `propuesta_calidad`, `estado_propuesta`.
6. Frontend: modal con propuesta editable + botones Guardar/Aprobar/Copiar.
7. `obsidian_writer.py`: nota .md con frontmatter por notificación procesada.

## 12. Glosario

| Término | Significado |
|---|---|
| **Casilla MTC** | Buzón electrónico oficial: https://casilla.mtc.gob.pe |
| **Clave SOL** | Auth federada de SUNAT, usada para login en MTC |
| **CITV** | Centro de Inspección Técnica Vehicular |
| **SUTRAN** | Superintendencia de Transporte Terrestre |
| **RUC** | Registro Único de Contribuyentes (11 dígitos) |
| **Documento principal** | Oficio/Carta/Informe — siempre PRIMERO en el merge |
| **Constancia Notificación Electrónica** | Penúltima en el merge |
| **Constancia de Lectura** | Última en el merge |
| **Plantilla** | `.md` en Obsidian `_templates/` con frontmatter de matching + cuerpo con placeholders |
| **Propuesta** | Borrador editable de respuesta, generado a partir de plantilla + IA |
| **Bóveda RESOLVE** | `C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE` |

## 13. Notas para Claude

- Sos ORQUESTADOR. NO escribas código directo; delegá a los 5 sub-agentes vía Task tool.
- Antes de delegar, leé las skills relevantes para dar instrucciones precisas.
- Paralelizá tareas independientes; serializá cuando hay dependencia.
- Después de cada hito → invocar `qa-agent`.
- Después de cada FASE → commit, mostrar diff, esperar visto bueno.
- Si Yubert pide algo fuera del roadmap, **discutilo antes de implementar**.
- Si un agente devuelve "necesito X", coordínalo VOS, no lo dejes pendiente.
