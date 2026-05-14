"""Cliente Google Drive vía google-api-python-client.

- ``verify_folder_access``: usa service account (sin cuota, solo lectura de metadata).
- ``upload_pdf``: usa OAuth user delegation para evitar el error 403 de cuota del SA.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials as SACredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


class DriveFolderStatus(TypedDict):
    folder_id: str
    folder_name: str
    is_folder: bool


_SA_SCOPES = ["https://www.googleapis.com/auth/drive"]
_OAUTH_SCOPES = ["https://www.googleapis.com/auth/drive"]

_FOLDER_MIME = "application/vnd.google-apps.folder"

_MONTH_NAMES_ES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


@dataclass(slots=True, frozen=True)
class UploadedFile:
    """Resultado de subir un PDF a Drive.

    Attributes:
        file_id: ID del archivo en Drive.
        name: nombre final del archivo en Drive.
        view_url: ``webViewLink`` (URL de visualización en Drive).
        folder_id: ID de la subcarpeta donde quedó (``YYYY/MM-Mes/RUC``).
    """

    file_id: str
    name: str
    view_url: str
    folder_id: str


def get_drive_service(sa_json_path: Path):
    """Crea servicio Drive v3 autenticado con service account.

    Args:
        sa_json_path: Ruta al JSON del service account.

    Returns:
        Servicio Drive v3 listo para usar.
    """
    creds = SACredentials.from_service_account_file(str(sa_json_path), scopes=_SA_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_drive_service_oauth(oauth_json_path: Path, token_path: Path):
    """Crea servicio Drive v3 con OAuth user delegation.

    Primera vez abre el navegador para consentimiento y guarda el token.
    Siguientes veces carga el token guardado y lo refresca si expiró.

    Args:
        oauth_json_path: ruta al JSON del OAuth 2.0 Client (Desktop app).
        token_path: ruta donde se guarda/carga el token OAuth entre runs.

    Returns:
        Servicio Drive v3 autenticado con la cuenta del usuario.
    """
    creds: OAuthCredentials | None = None

    if token_path.exists():
        creds = OAuthCredentials.from_authorized_user_file(str(token_path), _OAUTH_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("[drive] Refrescando OAuth token...")
            creds.refresh(Request())
        else:
            logger.info("[drive] Primera autenticación OAuth — se abrirá el navegador...")
            flow = InstalledAppFlow.from_client_secrets_file(str(oauth_json_path), _OAUTH_SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("[drive] OAuth token guardado en %s", token_path)

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def verify_folder_access(sa_json_path: Path, folder_id: str) -> DriveFolderStatus:
    """Verifica que el SA pueda leer la carpeta indicada.

    Args:
        sa_json_path: Ruta al JSON del service account.
        folder_id: ID de la carpeta de Drive.

    Returns:
        DriveFolderStatus con id, nombre y flag is_folder.
    """
    service = get_drive_service(sa_json_path)
    metadata = service.files().get(fileId=folder_id, fields="id,name,mimeType").execute()
    return DriveFolderStatus(
        folder_id=metadata["id"],
        folder_name=metadata["name"],
        is_folder=metadata.get("mimeType") == _FOLDER_MIME,
    )


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    """Devuelve el ID de la subcarpeta ``name`` dentro de ``parent_id``, creándola si no existe."""
    safe_name = name.replace("'", r"\'")
    query = (
        f"name = '{safe_name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = '{_FOLDER_MIME}' and "
        f"trashed = false"
    )
    resp = (
        service.files()
        .list(q=query, fields="files(id, name)", spaces="drive")
        .execute()
    )
    items = resp.get("files", [])
    if items:
        return items[0]["id"]

    body = {"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]}
    folder = service.files().create(body=body, fields="id").execute()
    return folder["id"]


def upload_pdf(
    sa_json_path: Path,
    root_folder_id: str,
    pdf_path: Path,
    ruc: str,
    fecha: date,
    oauth_json_path: Path | None = None,
    oauth_token_path: Path | None = None,
) -> UploadedFile:
    """Sube un PDF a Drive en la estructura ``<root>/YYYY/MM-Mes/RUC/<filename>``.

    Usa OAuth user delegation si ``oauth_json_path`` está disponible (evita el
    error 403 de cuota del SA). Si no, cae a service account.

    Args:
        sa_json_path: path al ``service-account.json``.
        root_folder_id: ID de la carpeta raíz (``DRIVE_ROOT_FOLDER_ID`` del .env).
        pdf_path: PDF local a subir.
        ruc: RUC (nombre de la carpeta de tercer nivel).
        fecha: fecha de la notificación (define YYYY/MM-Mes).
        oauth_json_path: path al ``oauth-credentials.json`` (Desktop app).
        oauth_token_path: path al token OAuth guardado entre runs.

    Returns:
        ``UploadedFile`` con file_id, name, view_url, folder_id.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no existe: {pdf_path}")

    if oauth_json_path and oauth_json_path.exists() and oauth_token_path is not None:
        service = get_drive_service_oauth(oauth_json_path, oauth_token_path)
    else:
        logger.warning("[drive] OAuth no configurado — usando SA (puede fallar con 403 quota)")
        service = get_drive_service(sa_json_path)

    year_name = f"{fecha.year:04d}"
    month_name = f"{fecha.month:02d}-{_MONTH_NAMES_ES[fecha.month - 1]}"

    year_folder = _find_or_create_folder(service, year_name, root_folder_id)
    month_folder = _find_or_create_folder(service, month_name, year_folder)
    ruc_folder = _find_or_create_folder(service, ruc, month_folder)

    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=False)
    body = {"name": pdf_path.name, "parents": [ruc_folder]}
    file_obj = (
        service.files()
        .create(body=body, media_body=media, fields="id, name, webViewLink")
        .execute()
    )
    return UploadedFile(
        file_id=file_obj["id"],
        name=file_obj["name"],
        view_url=file_obj.get("webViewLink", ""),
        folder_id=ruc_folder,
    )


__all__ = [
    "DriveFolderStatus",
    "UploadedFile",
    "get_drive_service",
    "get_drive_service_oauth",
    "upload_pdf",
    "verify_folder_access",
]
