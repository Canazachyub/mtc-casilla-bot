# 🚀 Deployment Guide — MTC Casilla Bot

> Pasos manuales que Yubert hace **una vez** para tener el sistema funcionando. Después de esto, todo es automático.

---

## ✅ Checklist global

- [ ] **Paso 1:** Service account de Google Cloud
- [ ] **Paso 2:** Google Sheet "MTC Casilla DB" creado
- [ ] **Paso 3:** Carpeta Drive "MTC-Casilla-Bot" creada
- [ ] **Paso 4:** Apps Script Web App deployado
- [ ] **Paso 5:** API keys de DeepSeek y Gemini obtenidas
- [ ] **Paso 6:** CSV de RUCs preparado
- [ ] **Paso 7:** `.env` completado
- [ ] **Paso 8:** Verificación con `mtc-bot doctor`

Tiempo total estimado: **45-60 minutos** la primera vez.

---

## Paso 1 — Service Account (10 min)

1. Ir a [console.cloud.google.com](https://console.cloud.google.com).
2. **New Project:** `mtc-casilla-bot`.
3. Ir a **APIs & Services → Library**:
   - Habilitar **Google Drive API**
   - Habilitar **Google Sheets API**
4. **APIs & Services → Credentials → Create Credentials → Service account**:
   - Nombre: `mtc-bot-sa`
   - Role: ninguno (gestionamos permisos via Drive sharing)
5. En el SA creado: **Keys → Add Key → Create new key → JSON**.
6. Guardar el JSON descargado en `data/credentials/service-account.json`.
7. **Linux/Mac:** `chmod 600 data/credentials/service-account.json`.
8. Anotar el **email del SA** (algo como `mtc-bot-sa@mtc-casilla-bot.iam.gserviceaccount.com`).

---

## Paso 2 — Google Sheet (10 min)

1. Drive → **New → Google Sheets** → renombrar a `MTC Casilla DB`.
2. Crear los 3 tabs según [`SHEET_SCHEMA.md`](SHEET_SCHEMA.md):
   - `notificaciones`
   - `logs`
   - `rucs` (ocultar)
3. Pegar los headers exactos de cada tab.
4. **Compartir** con el email del SA → permiso **Editor**.
5. Compartir con tu cuenta personal → **Editor**.
6. NO compartir con nadie más (al menos hasta que `rucs` esté vacío o migrado).
7. Copiar el **Sheet ID** de la URL.

---

## Paso 3 — Carpeta Drive (5 min)

1. Drive → **New → Folder** → `MTC-Casilla-Bot`.
2. Click derecho → **Share**:
   - Email del SA → **Editor**
   - Tu cuenta → **Editor**
   - (Opcional) equipo → **Viewer**
3. Copiar el **Folder ID** de la URL: `https://drive.google.com/drive/folders/<ESTE_ID>`.

---

## Paso 4 — Apps Script Web App (15 min)

Seguir [`appscript/README.md`](../appscript/README.md). Resumen:

1. [script.google.com](https://script.google.com) → New project → `MTC Casilla Bot API`.
2. Copiar `appscript/Code.gs` y `appscript/appsscript.json`.
3. Reemplazar `SHEET_ID` en `Code.gs` con el ID real.
4. Correr función `_testSummary` → autorizar permisos.
5. **Deploy → New deployment → Web app:**
   - Execute as: Me
   - Access: Anyone
6. Copiar la URL `https://script.google.com/macros/s/.../exec`.
7. Probar: `curl "URL?action=health"` → debería devolver `{"ok": true}`.

---

## Paso 5 — API keys de IA (5 min)

### DeepSeek

1. [platform.deepseek.com](https://platform.deepseek.com) → Sign in.
2. **API Keys → Create new key**.
3. Cargar saldo (~$5 USD alcanzan para meses).
4. Copiar la key (`sk-...`) al `.env` como `DEEPSEEK_API_KEY`.

### Gemini

1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → Create API key.
2. Copiar al `.env` como `GEMINI_API_KEY`.

> Tier gratuito de Gemini: 15 req/min, 1M tokens/día. Suficiente para fallback.

---

## Paso 6 — CSV de RUCs (10 min)

1. Copiar `data-credentials-rucs.csv.example` a `data/credentials/rucs.csv`.
2. Editar con los RUCs reales según el schema (ver `.claude/rules/credentials.md`).
3. Si tenés un Google Sheet con todos los RUCs:
   - Exportar como CSV (File → Download → Comma-separated values).
   - Renombrar a `rucs.csv` y mover a `data/credentials/`.
4. **Linux/Mac:** `chmod 600 data/credentials/rucs.csv`.
5. Verificar: cada fila tiene `auth_method` correcto y los campos requeridos para ese método.

---

## Paso 7 — Archivo `.env` (5 min)

```bash
cp .env.example .env
```

Completar con valores reales:

```bash
DEEPSEEK_API_KEY=sk-...
GEMINI_API_KEY=...
GOOGLE_SERVICE_ACCOUNT_JSON=data/credentials/service-account.json
DRIVE_ROOT_FOLDER_ID=1aBcD...
SHEET_ID=1xYz...
APPSCRIPT_API_URL=https://script.google.com/macros/s/.../exec
OBSIDIAN_VAULT_PATH=C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE
MTC_CREDENTIALS_CSV=data/credentials/rucs.csv
```

> Recordá: `.env` está en `.gitignore`, NUNCA se sube al repo.

---

## Paso 8 — Verificación (5 min)

```bash
# Instalar deps
uv sync
uv run playwright install chromium

# Ejecutar diagnóstico
uv run mtc-bot doctor
```

Salida esperada:

```
[doctor] Verificando configuración...

  ✓ Python 3.11.x detectado
  ✓ uv instalado
  ✓ Playwright + Chromium OK
  ✓ DEEPSEEK_API_KEY presente (sk-***...a3f7)
  ✓ GEMINI_API_KEY presente (***...x9k2)
  ✓ Service account JSON existe y permisos OK
  ✓ Conexión a Drive OK (carpeta raíz visible)
  ✓ Conexión a Sheet OK (3 tabs encontrados)
  ✓ Apps Script API OK (?action=health → 200)
  ✓ Bóveda Obsidian existe y es escribible
  ✓ rucs.csv: 12 filas (10 activas, 2 inactivas)
  ✓ Métodos auth: 8 direct, 4 clave_sol

[doctor] ✅ Sistema listo para uso.
```

Si algo falla, leer el mensaje específico — `doctor` indica exactamente qué corregir.

---

## Test de fuego (smoke test)

```bash
# Login con un solo RUC (modo headed para ver el browser)
MTC_BOT_HEADED=1 uv run mtc-bot test-login --ruc 20602194958
```

Si esto funciona, el sistema está listo.

---

## Próximos pasos

- **Fase 1:** correr `mtc-bot run --since today` y ver datos en el Sheet + dashboard
- **Fase 2:** agregar plantillas reales en `RESOLVE/_templates/`
- **Fase 3:** extender Apps Script con regeneración IA en la nube

---

## Troubleshooting de deployment

| Error | Causa | Solución |
|---|---|---|
| `403 Permission denied` al subir a Drive | SA no tiene acceso | Compartir carpeta con email del SA |
| `Sheet "notificaciones" not found` | Tab mal nombrado | Verificar capitalización exacta |
| `Apps Script: Authorization required` | No autorizaste permisos | Correr `_testSummary` y aceptar |
| `Playwright: browserType.launch: Executable not found` | Chromium no instalado | `uv run playwright install chromium` |
| `httpx.ConnectError` a DeepSeek | Firewall corporativo bloquea | Probar con VPN o desde otra red |
| `gspread.exceptions.SpreadsheetNotFound` | SHEET_ID incorrecto | Verificar la URL del Sheet |
