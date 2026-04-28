---
name: drive-uploader
description: |
  Workflow para subir PDFs procesados a Google Drive y escribir metadata en
  Google Sheets desde el bot Python. Activá esta skill cuando el usuario
  mencione: subir a Drive, service account, gspread, google-api-python-client,
  upload de PDFs, escribir en Sheet desde Python, append row al Sheet de
  notificaciones MTC. NO usar para autenticación OAuth de usuario final
  (esto es para automatización con service account).
---

# Skill: Drive Uploader (Python)

## Objetivo

Desde el bot Python, después de procesar una notificación:
1. Subir el PDF unido a una carpeta específica de Drive (organizada por año/mes/RUC).
2. Hacer `append` de una fila en el Sheet "MTC Casilla DB" con la metadata.
3. Devolver el `file_id` y `file_url` del PDF para que el orquestador los use.

## Setup: service account

**El usuario debe hacer una vez (paso manual, fuera del bot):**

1. Crear un proyecto en [Google Cloud Console](https://console.cloud.google.com).
2. Habilitar **Google Drive API** y **Google Sheets API**.
3. Crear un **Service Account**.
4. Generar una **clave JSON** y descargarla como `data/credentials/service-account.json`.
5. Compartir la carpeta de Drive raíz (`MTC-Casilla-Bot/`) con el email del service account (con permiso "Editor").
6. Compartir el Sheet "MTC Casilla DB" con el email del service account (con permiso "Editor").

> ⚠️ El JSON del service account es ULTRA sensible. Nunca commitear. Permisos `600`. Si se filtra, revocar inmediatamente desde GCP Console.

## Variables de entorno

```bash
GOOGLE_SERVICE_ACCOUNT_JSON=data/credentials/service-account.json
DRIVE_ROOT_FOLDER_ID=1aBcD...  # ID de la carpeta MTC-Casilla-Bot en Drive
SHEET_ID=1xYz...                # ID del Sheet "MTC Casilla DB"
SHEET_TAB_NOTIFICACIONES=notificaciones
SHEET_TAB_LOGS=logs
```

> Para obtener un folder ID: abrir la carpeta en Drive, copiar de la URL `https://drive.google.com/drive/folders/<ESTE_ID>`.
> Para el Sheet ID: `https://docs.google.com/spreadsheets/d/<ESTE_ID>/edit`.

## Dependencias

```toml
dependencies = [
    "google-api-python-client>=2.140.0",
    "google-auth>=2.32.0",
    "gspread>=6.1.0",  # wrapper más cómodo para Sheets
]
```

## Estructura de carpetas en Drive

```
MTC-Casilla-Bot/                 (carpeta raíz, compartida con SA)
├── 2026/
│   ├── 04-Abril/
│   │   ├── 20602194958/
│   │   │   ├── CARTA-N-000476-CR-2026-SUTRAN.pdf
│   │   │   └── OFICIO-N-1234-MTC-DGAT.pdf
│   │   └── 20512345678/
│   └── 05-Mayo/
└── 2025/
```

Si el árbol no existe, el bot lo crea on-demand.

## Implementación: cliente Drive

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pathlib import Path
from functools import lru_cache

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

@lru_cache(maxsize=1)
def get_credentials():
    return service_account.Credentials.from_service_account_file(
        settings.google_service_account_json,
        scopes=SCOPES,
    )

@lru_cache(maxsize=1)
def get_drive_service():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def find_or_create_folder(name: str, parent_id: str) -> str:
    """Busca una subcarpeta por nombre dentro de parent_id; si no existe, la crea."""
    drive = get_drive_service()
    query = (
        f"name = '{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    result = drive.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]

    # No existe, crear
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def ensure_folder_path(year: int, month: int, ruc: str) -> str:
    """Devuelve el folder_id de YYYY/MM-MES/<ruc>, creando el árbol si falta."""
    year_id = find_or_create_folder(str(year), settings.drive_root_folder_id)
    month_name = f"{month:02d}-{MESES_ES[month]}"
    month_id = find_or_create_folder(month_name, year_id)
    ruc_id = find_or_create_folder(ruc, month_id)
    return ruc_id


def upload_pdf(local_path: Path, year: int, month: int, ruc: str) -> dict:
    """Sube el PDF a Drive y devuelve {id, name, webViewLink, webContentLink}."""
    drive = get_drive_service()
    folder_id = ensure_folder_path(year, month, ruc)

    metadata = {"name": local_path.name, "parents": [folder_id]}
    media = MediaFileUpload(str(local_path), mimetype="application/pdf", resumable=True)

    file = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, webViewLink, webContentLink, mimeType, size",
    ).execute()

    logger.info(
        "PDF subido a Drive: %s (id=%s, %s bytes)",
        file["name"], file["id"], file.get("size", "?"),
    )
    return file
```

## Implementación: cliente Sheets

```python
import gspread

@lru_cache(maxsize=1)
def get_gspread_client():
    return gspread.authorize(get_credentials())

@lru_cache(maxsize=1)
def get_sheet():
    gc = get_gspread_client()
    return gc.open_by_key(settings.sheet_id)


def append_notificacion(record: dict) -> None:
    """Agrega una fila al tab 'notificaciones'."""
    sh = get_sheet()
    ws = sh.worksheet(settings.sheet_tab_notificaciones)

    # Header esperado (debe existir como fila 1):
    # id | timestamp_proceso | fecha_notificacion | ruc | empresa | documento |
    # emisor | asunto | resumen | requiere_respuesta | plazo_dias_habiles |
    # plazo_vencimiento | confianza_ia | modelo_ia | drive_file_id |
    # drive_view_url | estado | notas

    headers = ws.row_values(1)
    row = [record.get(col, "") for col in headers]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info("Sheet append OK: id=%s doc=%s", record["id"], record["documento"])


def upsert_notificacion(record: dict) -> None:
    """Actualiza si existe (por 'id'), sino inserta."""
    sh = get_sheet()
    ws = sh.worksheet(settings.sheet_tab_notificaciones)
    headers = ws.row_values(1)
    id_col = headers.index("id") + 1

    cells = ws.findall(record["id"], in_column=id_col)
    if cells:
        # Update
        row_num = cells[0].row
        row_values = [record.get(col, "") for col in headers]
        ws.update(f"A{row_num}", [row_values], value_input_option="USER_ENTERED")
        logger.info("Sheet UPDATE: id=%s row=%d", record["id"], row_num)
    else:
        append_notificacion(record)


def append_log(level: str, ruc: str, mensaje: str, contexto: dict | None = None) -> None:
    """Loguea al tab 'logs' del Sheet."""
    sh = get_sheet()
    ws = sh.worksheet(settings.sheet_tab_logs)
    ws.append_row(
        [
            datetime.now().isoformat(),
            level,
            ruc,
            mensaje,
            json.dumps(contexto or {}, ensure_ascii=False),
        ],
        value_input_option="USER_ENTERED",
    )
```

## Idempotencia

El `id` único de cada notificación se construye así:

```python
def build_notification_id(ruc: str, casilla_notif_id: str) -> str:
    """
    Si la notificación tiene un ID propio en la casilla MTC, usar ese.
    Sino, hash determinístico de (ruc, fecha, asunto).
    """
    return f"{ruc}__{casilla_notif_id}"
```

Antes de subir un PDF, **chequear primero**:

```python
def is_already_in_sheet(notif_id: str) -> bool:
    sh = get_sheet()
    ws = sh.worksheet(settings.sheet_tab_notificaciones)
    headers = ws.row_values(1)
    id_col = headers.index("id") + 1
    cells = ws.findall(notif_id, in_column=id_col)
    return bool(cells)
```

Si ya existe → saltar (a menos que el flag `--force` esté activo, en cuyo caso `upsert`).

## Resiliencia: caché de operaciones

Si el upload a Drive falla pero el merge PDF ya está hecho, NO reintentar todo el pipeline. Persistir el estado en `data/processed/index.json`:

```json
{
  "20602194958__notif-12345": {
    "stage": "pdf_merged",
    "merged_pdf_path": "data/merged/20602194958/CARTA-N-...-pdf",
    "extraction": { ... },
    "drive_uploaded_at": null,
    "sheet_appended_at": null
  }
}
```

Próximo run: si `stage = pdf_merged` pero `drive_uploaded_at = null`, retomar desde upload.

## Manejo de errores específicos

| Error | Causa | Estrategia |
|---|---|---|
| `HttpError 403 'storageQuotaExceeded'` | Drive lleno | Logguear y avisar. NO retry. |
| `HttpError 401` | Token expirado o SA mal configurado | Refrescar credentials, retry 1x. Si persiste, abortar. |
| `HttpError 429 'rateLimitExceeded'` | Mucho upload concurrente | Backoff exponencial (3s, 9s, 27s). |
| `gspread.exceptions.APIError 400` | Headers del Sheet no coinciden | Loguear el header esperado vs actual y abortar. |
| `FileNotFoundError` (PDF local) | Pipeline incompleto | NO subir nada, marcar como error. |

## Tests sugeridos

- `test_ensure_folder_path_creates_when_missing` (mock con responses)
- `test_upload_pdf_returns_drive_metadata`
- `test_append_notificacion_uses_correct_columns`
- `test_idempotency_skips_existing` (mock findall que devuelve cell)
- `test_credentials_filter_doesnt_log_sa_email`

## Permisos del PDF subido

Por defecto, el SA es el "owner" del archivo. Para que el equipo pueda VER los PDFs sin compartirlos uno por uno:

**Opción A (recomendada):** la **carpeta raíz** ya está compartida con el equipo (View-only). Los archivos heredan el permiso. ✓

**Opción B:** después del upload, hacer `permissions().create()` con `role: reader` y `type: domain` (si trabajas con Workspace) o `type: anyone` (NO recomendado para info sensible).

## Logging mínimo

```
[12:34:56] DRIVE: ensure_folder_path 2026/04-Abril/20602194958 → folder_id=1ZyX...
[12:34:57] DRIVE: upload CARTA-N-000476-CR-2026-SUTRAN.pdf (3.2 MB)
[12:34:59] DRIVE: ✓ subido id=1aBc... viewLink=https://drive.google.com/...
[12:35:00] SHEET: append id=20602194958__12345 doc=CARTA N° 000476-CR-2026-SUTRAN
[12:35:01] SHEET: ✓ row 47 escrita
```
