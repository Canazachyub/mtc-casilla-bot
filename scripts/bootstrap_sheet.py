"""Bootstrap interactivo del Google Sheet "MTC Casilla DB".

Verifica acceso del service account al Sheet, reporta tabs presentes/faltantes
y, opcionalmente, crea los tabs faltantes con los headers definidos en
``docs/SHEET_SCHEMA.md`` y ``.claude/rules/credentials.md``.

Uso:
    uv run python scripts/bootstrap_sheet.py

NO sobrescribe tabs existentes. NO loguea credenciales.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Permitir ejecutar el script tanto con `python scripts/bootstrap_sheet.py` como
# con `uv run`. Insertamos `src/` al path para importar `mtc_bot`.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mtc_bot.google.sheets_writer import (  # noqa: E402
    REQUIRED_TABS,
    get_client,
    verify_sheet_access,
)

# ─── Headers por tab (según docs/SHEET_SCHEMA.md + credentials.md) ─────────
HEADERS_NOTIFICACIONES: list[str] = [
    "id",
    "timestamp_proceso",
    "fecha_notificacion",
    "ruc",
    "empresa",
    "representante_legal",
    "documento",
    "emisor",
    "asunto",
    "resumen",
    "requiere_respuesta",
    "plazo_dias_habiles",
    "plazo_vencimiento",
    "confianza_ia",
    "modelo_ia",
    "drive_file_id",
    "drive_view_url",
    "template_id",
    "propuesta_respuesta",
    "propuesta_calidad",
    "estado_propuesta",
    "estado",
    "notas",
    "fecha_respuesta",
    "link_respuesta",
]

HEADERS_LOGS: list[str] = [
    "timestamp",
    "nivel",
    "ruc",
    "mensaje",
    "contexto_json",
]

HEADERS_RUCS: list[str] = [
    "ruc",
    "empresa",
    "auth_method",
    "dni_representante",
    "password_casilla",
    "sol_usuario",
    "sol_clave",
    "representante_legal",
    "activo",
]

HEADERS_BY_TAB: dict[str, list[str]] = {
    "notificaciones": HEADERS_NOTIFICACIONES,
    "logs": HEADERS_LOGS,
    "rucs": HEADERS_RUCS,
}


def _fail(msg: str) -> None:
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def _load_env() -> tuple[Path, str]:
    """Carga `.env` y devuelve (sa_json_path, sheet_id).

    Sale con código 1 si falta `.env` o variables requeridas.
    """
    env_path = ROOT / ".env"
    if not env_path.exists():
        _fail(
            f"No existe {env_path}. Copiá `.env.example` a `.env` y completá "
            "GOOGLE_SERVICE_ACCOUNT_JSON y SHEET_ID."
        )
    load_dotenv(env_path)

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.environ.get("SHEET_ID")
    if not sa_json:
        _fail("Falta GOOGLE_SERVICE_ACCOUNT_JSON en .env")
    if not sheet_id:
        _fail("Falta SHEET_ID en .env")

    sa_json_path = (ROOT / sa_json).resolve() if not Path(sa_json).is_absolute() \
        else Path(sa_json)
    if not sa_json_path.exists():
        _fail(f"No existe el archivo de service account: {sa_json_path}")

    return sa_json_path, sheet_id  # type: ignore[return-value]


def _print_report(status: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  Sheet: {status['sheet_title']}")
    print("=" * 60)
    if status["tabs_present"]:
        print("Tabs presentes:")
        for tab in status["tabs_present"]:
            mark = "[OK]" if tab in REQUIRED_TABS else "    "
            print(f"  {mark} {tab}")
    else:
        print("Tabs presentes: (ninguno)")

    if status["tabs_missing"]:
        print("\nTabs faltantes (requeridos):")
        for tab in status["tabs_missing"]:
            print(f"  [X] {tab}")
    else:
        print("\nTodos los tabs requeridos estan presentes.")
    print("=" * 60 + "\n")


def _ask_yes_no(prompt: str) -> bool:
    """Pregunta s/N (default N). Devuelve True solo si el usuario responde 's'."""
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in ("s", "si", "sí", "y", "yes")


def _create_missing_tabs(
    sa_json_path: Path,
    sheet_id: str,
    missing: list[str],
) -> None:
    """Crea los tabs faltantes con sus headers en la fila 1."""
    client = get_client(sa_json_path)
    sheet = client.open_by_key(sheet_id)

    for tab in missing:
        headers = HEADERS_BY_TAB.get(tab)
        if not headers:
            print(f"  [SKIP] No hay headers definidos para '{tab}'")
            continue

        cols = max(len(headers), 10)
        ws = sheet.add_worksheet(title=tab, rows=1000, cols=cols)
        # Escribimos headers en la fila 1 (rango A1).
        ws.update(values=[headers], range_name="A1")
        print(f"  [+] Tab '{tab}' creado con {len(headers)} columnas.")


def main() -> int:
    sa_json_path, sheet_id = _load_env()

    print("Verificando acceso al Sheet...")
    try:
        status = verify_sheet_access(sa_json_path, sheet_id)
    except Exception as exc:  # noqa: BLE001
        # No exponemos el sheet_id ni el path del JSON en el mensaje.
        print(f"\n[ERROR] No se pudo abrir el Sheet: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    _print_report(status)

    missing = list(status["tabs_missing"])
    if not missing:
        print("Nada que hacer. Salida OK.")
        return 0

    create = _ask_yes_no(
        f"Crear los {len(missing)} tab(s) faltante(s) con headers segun "
        "docs/SHEET_SCHEMA.md? [s/N]: "
    )
    if not create:
        print("\nNo se realizaron cambios. Salida OK.")
        return 0

    print("\nCreando tabs faltantes...")
    try:
        _create_missing_tabs(sa_json_path, sheet_id, missing)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] Fallo creando tabs: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    print("\nVerificando estado final...")
    final = verify_sheet_access(sa_json_path, sheet_id)
    _print_report(final)

    if final["tabs_missing"]:
        print("[WARN] Aun faltan tabs:", ", ".join(final["tabs_missing"]))
        return 1

    print("Bootstrap completado exitosamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
