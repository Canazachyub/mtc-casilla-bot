"""Cliente Google Sheets vía gspread con service account."""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import gspread
from google.oauth2.service_account import Credentials


class SheetStatus(TypedDict):
    sheet_id: str
    sheet_title: str
    tabs_present: list[str]
    tabs_missing: list[str]


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REQUIRED_TABS = ("notificaciones", "logs", "rucs")


def get_client(sa_json_path: Path) -> gspread.Client:
    """Crea cliente gspread autenticado con service account.

    Args:
        sa_json_path: Ruta al JSON del service account.

    Returns:
        Cliente gspread autorizado.

    Raises:
        FileNotFoundError: si el archivo de credenciales no existe.
        ValueError: si el JSON es inválido.
    """
    creds = Credentials.from_service_account_file(str(sa_json_path), scopes=SCOPES)
    return gspread.authorize(creds)


def verify_sheet_access(sa_json_path: Path, sheet_id: str) -> SheetStatus:
    """Abre el Sheet, lista tabs presentes y calcula faltantes según REQUIRED_TABS.

    Args:
        sa_json_path: Ruta al JSON del service account.
        sheet_id: ID del Google Sheet.

    Returns:
        SheetStatus con título, tabs presentes y tabs faltantes.

    Raises:
        gspread.exceptions.APIError: si el SA no tiene acceso (403) o el
            Sheet no existe (404).
    """
    client = get_client(sa_json_path)
    sheet = client.open_by_key(sheet_id)
    worksheets = sheet.worksheets()
    tabs_present = [ws.title for ws in worksheets]
    tabs_missing = [tab for tab in REQUIRED_TABS if tab not in tabs_present]
    return SheetStatus(
        sheet_id=sheet_id,
        sheet_title=sheet.title,
        tabs_present=tabs_present,
        tabs_missing=tabs_missing,
    )
