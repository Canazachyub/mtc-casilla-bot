"""Cliente Google Sheets vía gspread con service account."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


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


def _get_worksheet(client: gspread.Client, sheet_id: str, tab_name: str):
    """Devuelve el ``Worksheet`` ``tab_name`` del Sheet ``sheet_id``.

    Args:
        client: cliente gspread autorizado.
        sheet_id: ID del Google Sheet.
        tab_name: nombre del tab.

    Returns:
        ``gspread.Worksheet``.

    Raises:
        gspread.exceptions.WorksheetNotFound: si el tab no existe.
    """
    sh = client.open_by_key(sheet_id)
    return sh.worksheet(tab_name)


def notification_exists(
    sa_json_path: Path, sheet_id: str, tab: str, notification_id: str,
) -> bool:
    """Devuelve ``True`` si ya existe una fila en ``tab`` cuyo ``id`` matchea.

    Lee la columna ``id`` del tab y busca match exacto. Útil para idempotencia
    antes de procesar una notificación.

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        tab: nombre del tab (típicamente ``notificaciones``).
        notification_id: ID a buscar (formato ``<ruc>__<hash>``).

    Returns:
        ``True`` si encontró match, ``False`` si no.

    Raises:
        RuntimeError: si el tab no tiene columna ``id`` en la primera fila.
    """
    client = get_client(sa_json_path)
    ws = _get_worksheet(client, sheet_id, tab)
    headers = ws.row_values(1)
    if "id" not in headers:
        raise RuntimeError(f"Tab '{tab}' no tiene columna 'id' en la primera fila")
    id_col_index = headers.index("id") + 1  # gspread es 1-based
    column_values = ws.col_values(id_col_index)[1:]  # skip header
    return notification_id in column_values


def append_notificacion(
    sa_json_path: Path,
    sheet_id: str,
    tab: str,
    row: dict[str, str | int | float | bool | None],
) -> None:
    """Agrega una fila al tab ``notificaciones`` respetando el orden de columnas.

    ``row`` puede traer cualquier subset de columnas; las que no figuren se
    rellenan con string vacío. Booleans se serializan como ``TRUE``/``FALSE``
    (compatibles con checkboxes del Sheet).

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        tab: nombre del tab destino.
        row: diccionario columna → valor.
    """
    client = get_client(sa_json_path)
    ws = _get_worksheet(client, sheet_id, tab)
    headers = ws.row_values(1)
    flat_row: list[str] = []
    for h in headers:
        v = row.get(h, "")
        if isinstance(v, bool):
            flat_row.append("TRUE" if v else "FALSE")
        elif v is None:
            flat_row.append("")
        else:
            flat_row.append(str(v))
    ws.append_row(flat_row, value_input_option="USER_ENTERED")
    logger.info(
        "Sheet append OK: tab=%s id=%s",
        tab,
        row.get("id", "<sin id>"),
    )


__all__ = [
    "REQUIRED_TABS",
    "SheetStatus",
    "append_notificacion",
    "get_client",
    "notification_exists",
    "verify_sheet_access",
]
