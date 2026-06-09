# 📬 MTC Casilla Bot

> Automatización end-to-end de notificaciones electrónicas de la **Casilla del MTC** (Perú).
> Login → descarga → análisis IA → almacenamiento Drive → propuestas de respuesta editables → dashboard web.

---

## 🎯 Qué hace

1. **Login automático** a [casilla.mtc.gob.pe](https://casilla.mtc.gob.pe) (directo o vía Clave SOL).
2. **Detecta y descarga** notificaciones nuevas con sus 3-4 adjuntos PDF.
3. **Une los PDFs** en orden estricto: documento → constancia notificación → constancia lectura.
4. **Renombra** con el nombre oficial del documento (ej: `CARTA-N-000476-CR-2026-SUTRAN.pdf`).
5. **Analiza con IA** (DeepSeek + Gemini fallback): emisor, asunto, plazo, acciones requeridas.
6. **Sube todo a Google Drive** organizado por año/mes/RUC.
7. **Registra en Google Sheet** con metadata estructurada.
8. **Gestiona 11 empresas CITV** con documentación requerida, upload de PDFs y sincronización cross-device.
9. **Tareas manuales** agregables desde el dashboard, sincronizadas con el Sheet.
10. **Genera propuesta de respuesta** matcheando con plantillas Obsidian (Fase 2).
11. **Sirve dashboard web** (localhost o GitHub Pages) con vista de plazos, búsqueda y editor.

---

## 🏗️ Arquitectura

```
                    ┌─────────────────┐
                    │  PYTHON BOT     │  (local, schedulable)
                    │  Playwright     │
                    │  PDFs + IA      │
                    │  → Drive/Sheet  │
                    └────────┬────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  GOOGLE WORKSPACE            │  (source of truth)
              │  📁 Drive                    │
              │    MTC-Casilla-Bot/          │
              │      YYYY/MM/RUC/ (notif)   │
              │      Empresas/{key}/ (docs) │
              │  📊 Sheet "RESOLVE APP"      │
              │    notificaciones            │
              │    empresa_docs              │
              │    plantillas                │
              │    logs / rucs               │
              │  ⚙️  Apps Script Web App     │
              │    GET: list/detail/summary  │
              │    GET: get_empresa_docs     │
              │    POST: upload_empresa_doc  │
              │    POST: save_tarea_manual   │
              └──────────────┬───────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  FRONTEND       │  (HTML/JS estático)
                    │  localhost:8080 │
                    │  GitHub Pages   │
                    │  canazachyub    │
                    │  .github.io/   │
                    │  mtc-casilla-  │
                    │  bot           │
                    └─────────────────┘
```

---

## 📦 Stack

| Componente | Tecnología | Por qué |
|---|---|---|
| Scraper | **Playwright (Chromium)** | OAuth Clave SOL, async, downloads |
| PDFs | **pypdf + pdfplumber** | Merge + extracción texto |
| IA primaria | **DeepSeek** (`deepseek-chat`) | ~10x más barato, OpenAI-compatible |
| IA fallback | **Gemini** (`gemini-2.5-flash`) | Tier free generoso, otro provider |
| Storage | **Google Drive** + service account | Source of truth, compartible |
| DB | **Google Sheets** | Editable, sin servidor, ya conocido |
| API REST | **Apps Script Web App** (GET + POST) | Pasarela para frontend, upload a Drive |
| Frontend | **HTML/JS vanilla + CSS** | Sin build, dark mode, mobile-ready |
| Plantillas | **Obsidian** + sync Drive | Source editable + IA en nube acceso |
| CLI | **typer + rich** | UX en terminal |
| Gestor Python | **uv** | 10-100x más rápido que pip |

---

## 🗺️ Roadmap por fases

| Fase | Foco | Estado |
|---|---|---|
| **0** | Setup, credenciales, Apps Script deploy | ✅ completada (2026-04-28) |
| **1** | MVP pipeline: notificación → Drive + Sheet + dashboard | ✅ funcional (2026-05-13) |
| **1.5** | Dashboard v2: empresas, docs, tareas manuales, sync | ✅ completada (2026-05-25) |
| **2** | Sistema de plantillas + propuestas editables | 🚀 siguiente |
| **3** | IA en la nube (regenerar desde el frontend) | ⏳ |
| **4** | Editor avanzado + exportación Word/PDF + alertas | ⏳ |
| **5** | Multi-cliente / multi-tenant | 🔮 futuro |

Detalle completo en [`ROADMAP.md`](ROADMAP.md).

---

## 🖥️ Dashboard (GitHub Pages)

**URL:** [canazachyub.github.io/mtc-casilla-bot](https://canazachyub.github.io/mtc-casilla-bot)

### Pestañas

| Pestaña | Descripción |
|---|---|
| ☰ **Tareas pendientes** | Tabla con todas las notificaciones, filtros y búsqueda |
| 📋 **Casillas en proceso** | Vista agrupada por empresa, ordenada por urgencia |
| 🏢 **Empresas** | Gestión de las 11 empresas CITV con documentación requerida |

### Funciones principales

- **Semáforo de plazos** — Vencido / Urgente (≤1d) / Alerta (≤3d) / Normal
- **Cambio de progreso** — NO INICIADO / AGENDAR / EN REVISIÓN / PRESENTADO (se guarda en Sheet)
- **Ver detalle** — PDF embebido, resumen IA, editor de tareas y notas
- **Generar respuesta** — selección de empresa (personería jurídica) + plantilla + IA
- **Exportar Word** — descarga `.docx` formateado listo para imprimir
- **Gestión de empresas** — acordeón por empresa, 11 docs requeridos, upload PDF → Drive → Sheet
- **Nueva tarea manual** — formulario para agregar tareas no scrapeadas, sincroniza con Sheet

---

## 🚀 Setup

### Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) instalado
- Cuenta Google con Drive + acceso a Apps Script
- Credenciales de Casilla MTC por RUC (DNI + password, o Clave SOL)
- API keys: [DeepSeek](https://platform.deepseek.com) + [Gemini](https://aistudio.google.com/apikey)

### Instalación

```bash
# Dependencias
uv sync
uv run playwright install chromium

# Credenciales
cp .env.example .env
# Editar .env con tus API keys y paths

# Crear el CSV de RUCs
cp data-credentials-rucs.csv.example data/credentials/rucs.csv
# Editar con los RUCs reales
```

### Configurar Google Cloud (una vez)

1. Crear proyecto en [console.cloud.google.com](https://console.cloud.google.com)
2. Habilitar **Google Drive API** y **Google Sheets API**
3. Crear **Service Account** → descargar JSON → guardar como `data/credentials/service-account.json`
4. Crear **carpeta Drive** "MTC-Casilla-Bot" → compartir con el email del SA (Editor)
5. Crear **Sheet "RESOLVE APP"** con tabs según `docs/SHEET_SCHEMA.md` → compartir con SA
6. Apuntar `DRIVE_ROOT_FOLDER_ID` y `SHEET_ID` en `.env`

### Configurar Apps Script

1. Copiar `appscript/Code.gs` al editor de Apps Script
2. Copiar `appscript/appsscript.json` al manifiesto
3. En **Propiedades de script** agregar:
   - `DEEPSEEK_API_KEY` = tu key
   - `DRIVE_ROOT_FOLDER_ID` = ID de la carpeta "MTC-Casilla-Bot" en Drive
4. Ejecutar `_setupPlantillas()` desde el editor (crea el tab `plantillas`)
5. Deployar como Web App: ejecutar como **Yo**, acceso **Cualquier usuario**

Ver [`appscript/README.md`](appscript/README.md) para el detalle completo.

---

## 💻 Uso

```bash
# Verificar configuración
uv run mtc-bot doctor

# Dry-run (solo lista, no escribe nada)
uv run mtc-bot run --dry-run --since today

# Procesar notificaciones de hoy
uv run mtc-bot run --since today

# Procesar desde una fecha específica
uv run mtc-bot run --since 2026-05-13

# Procesar un RUC específico
uv run mtc-bot run --since yesterday --ruc 20602194958

# Sobreescribir notificaciones ya procesadas (reprocesa PDFs + IA + Sheet)
uv run mtc-bot run --since 2026-05-13 --overwrite

# Dashboard local
cd frontend && python -m http.server 8080
# Abrir http://localhost:8080

# Herramienta de debug (ver sección abajo)
uv run python scripts/debug_scraper_ui.py
```

---

## 🔍 Herramienta de Debug (`debug_scraper_ui.py`)

GUI Tkinter para verificar el pipeline casilla por casilla antes de correr producción.

```bash
uv sync               # instala tkcalendar (grupo dev, solo la primera vez)
uv run python scripts/debug_scraper_ui.py
```

### Funciones

| Feature | Descripción |
|---|---|
| **Selector de casillas** | Listbox multi-selección con todas las casillas activas del CSV |
| **Calendarios 📅** | Date picker visual para Desde/Hasta |
| **Botones rápidos** | Hoy / Ayer / 7d / 14d / 30d para setear el `Desde` |
| **Modo visible** | Abre el browser en pantalla para ver el scraping en vivo |
| **Solo listar** | Dry-run: muestra fechas y paginación sin descargar PDFs |
| **🤖 Test IA** | Prueba la conexión a DeepSeek y Gemini con ping mínimo |

### Tabs de resultado

| Tab | Muestra |
|---|---|
| **Logs** | Logs en tiempo real con colores por nivel (azul=pasos, amarillo=warnings, rojo=errores) |
| **Notificaciones** | Tabla con `raw_fecha` vs `fecha parseada`, estado del filtro, columnas ✓/✗ por tipo de PDF |
| **PDFs** | Orden de descarga, clasificación, orden de merge, preview del contexto enviado a la IA |
| **Capturas** | Lista de screenshots — doble clic para abrir, botón para ir a la carpeta del run |

### Estructura de logs

Cada ejecución genera una carpeta con timestamp único:

```
data/debug_logs/
└── YYYYMMDD_HHMMSS/               ← timestamp del run
    └── EMPRESA__RUC/              ← una carpeta por casilla
        ├── 00_sesion.txt          ← empresa, RUC, desde, hasta, modo, hora
        ├── debug.log              ← log completo correlacionable con capturas
        ├── 01_login_ok.png
        ├── 02_inbox_pag01.png     ← una captura por página del inbox
        ├── 02_inbox_pag02.png
        ├── 03_01_detalle.png      ← detalle de cada notificación
        ├── 03_01_adjuntos.png
        └── contexto_ia.txt        ← texto exacto que recibirá DeepSeek/Gemini
```

### Verificaciones automáticas

- **Fechas por página** — tabla `raw_fecha → parsed → estado filtro` por cada item del inbox
- **Paginación** — espera que el label del paginator cambie antes de leer (evita duplicados)
- **Orden de merge** — muestra `← PRIMERO / ← penúltimo / ← ÚLTIMO` para verificar el orden del PDF final
- **Discrepancia de fecha** — alerta si la fecha del inbox difiere de la fecha del detalle
- **Constancias faltantes** — avisa si no hay `constancia_lectura` o `constancia_notificacion`

---

## 📊 Google Sheets — tabs

| Tab | Descripción |
|---|---|
| `notificaciones` | DB principal — una fila por notificación (scrapeada o manual) |
| `empresa_docs` | Documentos de empresa subidos a Drive (URL + fecha por empresa+doc) |
| `plantillas` | Plantillas de respuesta para el generador IA |
| `logs` | Auditoría de errores y operaciones |
| `rucs` | Credenciales por RUC — acceso restringido, nunca expuesto via API |

---

## 🧠 Extracción IA — fuentes combinadas

El modelo recibe **tres fuentes de información** por notificación para maximizar la calidad de extracción:

```
=== METADATA DEL PORTAL MTC ===
Emisor: SUPERINTENDENCIA DE TRANSPORTE TERRESTRE... - SUTRAN
Categoría: Cartas
Asunto: NOTIFICACIÓN DE LA CARTA N° 001056-CR-2026-SUTRAN/06.3.4-SGFSV
Fecha de notificación: jueves, 14 mayo 2026, 10:00:00 a. m.

=== MENSAJE DEL PORTAL (siempre texto limpio) ===
Sírvase dar cuenta que se ha notificado a [EMPRESA]...
De conformidad con el artículo 21 de la Ley N° 27444...

=== TEXTO DEL PDF ADJUNTO ===
[contenido del documento oficial]
```

| Fuente | Ventaja |
|---|---|
| Metadata portal | Emisor y asunto ya etiquetados, siempre disponibles |
| Cuerpo HTML | Siempre texto limpio (sin OCR), contiene nombre exacto del doc y base legal |
| PDF texto | Contenido completo del documento para análisis profundo |

Campos que mejoran con este enfoque: `documento`, `emisor`, `fundamento_legal`, `tipo_acto`, `casilla_origen`, `plazo_dias_habiles`.

---

## 🤖 5 sub-agentes especializados

El proyecto está diseñado para que Claude Code use 5 sub-agentes en paralelo:

1. **backend-python-agent** — scraper, PDFs, IA, CLI
2. **cloud-google-agent** — Drive, Sheets, Apps Script
3. **frontend-agent** — dashboard HTML/JS
4. **templates-agent** — plantillas Obsidian, propuestas
5. **qa-agent** — tests, code review, security

Definidos en [`.claude/agents/`](.claude/agents/). El agente principal de Claude Code orquesta y delega.

---

## 📚 Documentación

- [`PROMPT_INICIAL.md`](PROMPT_INICIAL.md) — qué pegarle a Claude Code la primera vez
- [`CLAUDE.md`](CLAUDE.md) — memoria de Claude Code (decisiones + estado)
- [`ROADMAP.md`](ROADMAP.md) — fases y planificación
- [`appscript/README.md`](appscript/README.md) — cómo deployar Apps Script
- [`frontend/README.md`](frontend/README.md) — cómo correr el dashboard
- [`docs/SHEET_SCHEMA.md`](docs/SHEET_SCHEMA.md) — schema del Sheet
- [`.claude/skills/`](.claude/skills/) — workflows reutilizables
- [`.claude/rules/`](.claude/rules/) — reglas no negociables (credenciales, Playwright)

---

## 🔐 Seguridad

- Credenciales SIEMPRE en `.env` o `data/credentials/` (gitignored)
- Service account JSON nunca commiteado
- Tab `rucs` del Sheet jamás expuesto via API pública
- Apps Script Web App: `executeAs: USER_DEPLOYING`, scope `drive` + `spreadsheets`
- Credenciales de scraper del frontend guardadas solo en localStorage (nunca en API pública)
- Logs filtran credenciales con `CredentialFilter`
- API keys de IA en Apps Script viven en `PropertiesService`

---

## 💸 Costos

Para 50 notificaciones/mes:

| Servicio | Costo |
|---|---|
| DeepSeek API | <$0.10 USD |
| Gemini Flash API | gratis (tier free) |
| Google Drive (storage PDFs) | gratis (incluido en Workspace) |
| Apps Script + Sheets | gratis |
| GitHub Pages (frontend) | gratis |
| **Total** | **<$0.10 USD/mes** |

> Para 500 notificaciones/mes: ~$1 USD/mes.

---

## 📄 Licencia

Proyecto interno TELCOM ENERGY / MALCOM S.A. — uso restringido.
