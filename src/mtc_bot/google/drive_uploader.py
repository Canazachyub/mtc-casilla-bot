"""Cliente Google Drive vía google-api-python-client con service account."""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


class DriveFolderStatus(TypedDict):
    folder_id: str
    folder_name: str
    is_folder: bool


SCOPES = ["https://www.googleapis.com/auth/drive"]

_FOLDER_MIME = "application/vnd.google-apps.folder"


def get_drive_service(sa_json_path: Path):
    """Crea servicio de Drive v3 autenticado con service account.

    Args:
        sa_json_path: Ruta al JSON del service account.

    Returns:
        Servicio Drive v3 listo para usar (`googleapiclient.discovery.Resource`).

    Raises:
        FileNotFoundError: si el archivo de credenciales no existe.
    """
    creds = Credentials.from_service_account_file(str(sa_json_path), scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def verify_folder_access(sa_json_path: Path, folder_id: str) -> DriveFolderStatus:
    """Verifica que el SA pueda leer la carpeta indicada.

    Args:
        sa_json_path: Ruta al JSON del service account.
        folder_id: ID de la carpeta de Drive.

    Returns:
        DriveFolderStatus con id, nombre y flag is_folder.

    Raises:
        googleapiclient.errors.HttpError: 403 si no compartido, 404 si no existe.
    """
    service = get_drive_service(sa_json_path)
    metadata = (
        service.files()
        .get(fileId=folder_id, fields="id,name,mimeType")
        .execute()
    )
    return DriveFolderStatus(
        folder_id=metadata["id"],
        folder_name=metadata["name"],
        is_folder=metadata.get("mimeType") == _FOLDER_MIME,
    )
