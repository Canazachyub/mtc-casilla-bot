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
    sa_json_path: Path,
    sheet_id: str,
    tab: str,
    notification_id: str,
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
    headers = [h.strip() for h in ws.row_values(1)]
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
    headers = [h.strip() for h in ws.row_values(1)]
    flat_row: list[str] = []
    for h in headers:
        v = row.get(h, "")
        if isinstance(v, bool):
            flat_row.append("TRUE" if v else "FALSE")
        elif v is None:
            flat_row.append("")
        else:
            flat_row.append(str(v))
    # Usar update con rango explícito en vez de append_row: evita que gspread
    # trunque al ancho de los datos existentes (que puede ser < len(headers)).
    next_row = len(ws.col_values(1)) + 1
    last_col = gspread.utils.rowcol_to_a1(1, len(headers))[:-1]
    ws.update(f"A{next_row}:{last_col}{next_row}", [flat_row], value_input_option="RAW")
    logger.info(
        "Sheet append OK: tab=%s id=%s",
        tab,
        row.get("id", "<sin id>"),
    )


def delete_notificacion(
    sa_json_path: Path,
    sheet_id: str,
    tab: str,
    notification_id: str,
) -> bool:
    """Elimina la fila cuyo campo ``id`` coincide con ``notification_id``.

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        tab: nombre del tab.
        notification_id: ID a buscar y eliminar.

    Returns:
        ``True`` si encontró y eliminó la fila, ``False`` si no existía.
    """
    client = get_client(sa_json_path)
    ws = _get_worksheet(client, sheet_id, tab)
    headers = [h.strip() for h in ws.row_values(1)]
    if "id" not in headers:
        raise RuntimeError(f"Tab '{tab}' no tiene columna 'id'")
    id_col_index = headers.index("id") + 1
    column_values = ws.col_values(id_col_index)  # fila 1 = header
    for row_num, val in enumerate(column_values, start=1):
        if val == notification_id:
            ws.delete_rows(row_num)
            logger.info("Fila eliminada: tab=%s id=%s (row %d)", tab, notification_id, row_num)
            return True
    return False


def get_all_notificaciones(
    sa_json_path: Path,
    sheet_id: str,
    tab: str,
    only_missing_field: str | None = None,
) -> list[dict]:
    """Lee todas las filas del tab y las devuelve como lista de dicts.

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        tab: nombre del tab.
        only_missing_field: si se especifica, filtra solo filas donde ese campo
            esté vacío o ausente. Útil para ``reprocess --missing-only``.

    Returns:
        Lista de dicts ``{columna: valor}`` por fila.
    """
    client = get_client(sa_json_path)
    ws = _get_worksheet(client, sheet_id, tab)
    rows = ws.get_all_records(default_blank="")
    if only_missing_field:
        rows = [r for r in rows if not str(r.get(only_missing_field, "")).strip()]
    logger.info(
        "Leídas %d filas del tab '%s'%s",
        len(rows),
        tab,
        f" (filtro: {only_missing_field} vacío)" if only_missing_field else "",
    )
    return rows


def update_notificacion_fields(
    sa_json_path: Path,
    sheet_id: str,
    tab: str,
    notification_id: str,
    fields: dict[str, str | int | float | bool | None],
) -> bool:
    """Actualiza campos específicos de una fila existente identificada por su ``id``.

    Usa ``batch_update`` para minimizar llamadas a la API (una sola request por fila).

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        tab: nombre del tab.
        notification_id: valor del campo ``id`` de la fila a actualizar.
        fields: dict ``{nombre_columna: nuevo_valor}`` con los campos a actualizar.
            Columnas que no existen en el Sheet se ignoran con un warning.

    Returns:
        ``True`` si encontró y actualizó la fila; ``False`` si el ID no existe.
    """
    client = get_client(sa_json_path)
    ws = _get_worksheet(client, sheet_id, tab)
    headers = [h.strip() for h in ws.row_values(1)]

    if "id" not in headers:
        raise RuntimeError(f"Tab '{tab}' no tiene columna 'id'")

    id_col_index = headers.index("id") + 1  # 1-based
    id_values = ws.col_values(id_col_index)[1:]  # skip header

    try:
        row_idx = id_values.index(notification_id) + 2  # +2: header + 1-based
    except ValueError:
        logger.warning("ID '%s' no encontrado en tab '%s'", notification_id, tab)
        return False

    updates: list[dict] = []
    for field, value in fields.items():
        if field not in headers:
            logger.warning("Campo '%s' no existe en el Sheet (tab=%s), ignorando", field, tab)
            continue
        col_idx = headers.index(field) + 1  # 1-based
        if isinstance(value, bool):
            cell_value = "TRUE" if value else "FALSE"
        elif value is None:
            cell_value = ""
        else:
            cell_value = str(value)
        # Notación A1 manual: col letra + row número
        col_letter = gspread.utils.rowcol_to_a1(1, col_idx)[:-1]  # strip the "1"
        updates.append({"range": f"{col_letter}{row_idx}", "values": [[cell_value]]})

    if not updates:
        logger.warning(
            "Ningún campo válido para actualizar (id=%s). "
            "Verificá que las columnas existen en el Sheet.",
            notification_id,
        )
        return False

    ws.batch_update(updates, value_input_option="USER_ENTERED")
    logger.info(
        "Sheet update OK: id=%s fields=[%s]",
        notification_id,
        ", ".join(f for f in fields if f in headers),
    )
    return True


def write_resumen_diario(
    sa_json_path: Path,
    sheet_id: str,
    results: list[tuple[str, str, int, int, str | None]],
    run_date: "date",
    texto_resumen: str,
) -> None:
    """Escribe el resumen del run en el tab ``resumen_diario``, creándolo si no existe.

    Cada run agrega una fila por empresa. Si el tab no existe se crea con headers.

    Args:
        sa_json_path: path al SA JSON.
        sheet_id: ID del Sheet.
        results: lista de tuplas ``(empresa, ruc, listed, completados, error)``.
        run_date: fecha del run (``date.today()``).
        texto_resumen: texto completo formateado para WhatsApp.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    HEADERS = [
        "fecha", "timestamp_run", "empresa", "ruc",
        "notif_encontradas", "notif_nuevas", "estado", "error_msg", "texto_linea",
    ]
    TAB = "resumen_diario"

    client = get_client(sa_json_path)
    sh = client.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=TAB, rows=500, cols=len(HEADERS))
        ws.append_row(HEADERS)
        ws.freeze(rows=1)
        logger.info("Tab '%s' creado", TAB)

    now = _dt.now(tz=ZoneInfo("America/Lima")).isoformat(timespec="seconds")
    fecha_str = run_date.isoformat()

    rows_to_add = []
    for empresa, ruc, listed, completados, error in results:
        if error:
            estado = "error"
            linea = f"• {empresa}: ❌ error de conexión"
        elif completados > 0:
            estado = "ok"
            suf = "es" if completados > 1 else ""
            linea = f"• {empresa}: {completados} notificación{suf} nueva{'s' if completados > 1 else ''}"
        elif listed > 0:
            estado = "ok"
            linea = f"• {empresa}: {listed} encontradas (ya registradas)"
        else:
            estado = "ok"
            linea = f"• {empresa}: no hay notificaciones nuevas"

        rows_to_add.append([
            fecha_str, now, empresa, ruc,
            listed, completados, estado, error or "", linea,
        ])

    if rows_to_add:
        ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")

    logger.info(
        "resumen_diario: %d filas escritas para fecha=%s",
        len(rows_to_add),
        fecha_str,
    )


__all__ = [
    "REQUIRED_TABS",
    "SheetStatus",
    "append_notificacion",
    "get_all_notificaciones",
    "get_client",
    "notification_exists",
    "update_notificacion_fields",
    "verify_sheet_access",
    "write_resumen_diario",
]

