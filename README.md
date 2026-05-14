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
8. **Genera propuesta de respuesta** matcheando con plantillas Obsidian (Fase 2).
9. **Sirve dashboard web** (localhost o GitHub Pages) con vista de plazos, búsqueda y editor.

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
              │  📊 Sheet "MTC Casilla DB"   │
              │  ⚙️  Apps Script Web App     │
              └──────────────┬───────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  FRONTEND       │  (HTML/JS estático)
                    │  localhost o    │
                    │  GitHub Pages   │
                    └─────────────────┘
```

**Detalle del flujo:** ver [`ROADMAP.md`](ROADMAP.md) y [`docs/`](docs/).

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
| API REST | **Apps Script Web App** | Pasarela de lectura para frontend |
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
| **2** | Sistema de plantillas + propuestas editables | 🚀 siguiente |
| **3** | IA en la nube (regenerar desde el frontend) | ⏳ |
| **4** | Editor avanzado + exportación Word/PDF + alertas | ⏳ |
| **5** | Multi-cliente / multi-tenant | 🔮 futuro |

Detalle completo en [`ROADMAP.md`](ROADMAP.md).

---

## 🚀 Setup

### Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) instalado
- Cuenta Google con Drive + acceso a Apps Script
- Cuentas en Casilla MTC con credenciales (RUC + DNI + password, o Clave SOL)
- API keys: [DeepSeek](https://platform.deepseek.com) + [Gemini](https://aistudio.google.com/apikey)

### Instalación

```bash
# Dependencias
uv sync
uv run playwright install chromium

# Credenciales
cp .env.example .env
# Editar .env con tus API keys

# Crear el CSV de RUCs
cp data-credentials-rucs.csv.example data/credentials/rucs.csv
# Editar con los RUCs reales
```

### Configurar Google Cloud (una vez)

1. Crear proyecto en [console.cloud.google.com](https://console.cloud.google.com)
2. Habilitar **Google Drive API** y **Google Sheets API**
3. Crear **Service Account** → descargar JSON → guardar como `data/credentials/service-account.json`
4. Crear **carpeta Drive** "MTC-Casilla-Bot" → compartir con el email del SA (Editor)
5. Crear **Sheet "MTC Casilla DB"** con tabs según `docs/SHEET_SCHEMA.md` → compartir con SA
6. Apuntar `DRIVE_ROOT_FOLDER_ID` y `SHEET_ID` en `.env`

### Deployar Apps Script

Ver [`appscript/README.md`](appscript/README.md). Toma 5 minutos.

---

## 💻 Uso

### Modo dry-run (recomendado primera vez)

```bash
uv run mtc-bot run --dry-run
```

### Procesamiento real

```bash
uv run mtc-bot run --since today
uv run mtc-bot run --since yesterday --ruc 20602194958
```

### Dashboard local

```bash
# Terminal 1: si querés correr el bot ahora
uv run mtc-bot run

# Terminal 2: levantar el frontend
cd frontend && python -m http.server 8080
# Abrir http://localhost:8080
```

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
- [`.claude/rules/`](.claude/rules/) — reglas no negociables

---

## 🔐 Seguridad

- Credenciales SIEMPRE en `.env` o `data/credentials/` (gitignored)
- Service account JSON nunca commiteado
- Tab `rucs` del Sheet jamás expuesto via API pública
- Apps Script Web App con `executeAs: USER_DEPLOYING`
- Logs filtran credenciales con `CredentialFilter`
- API keys de IA en Apps Script viven en `PropertiesService`

---

## 💸 Costos

Para 50 notificaciones/mes:

- DeepSeek: <$0.10 USD
- Gemini: gratis
- Drive + Apps Script + Sheets: gratis (incluido en Workspace)
- GitHub Pages: gratis
- **Total: <$0.10 USD/mes**

---

## 📄 Licencia

Proyecto interno TELCOM ENERGY / MALCOM S.A. — uso restringido.
