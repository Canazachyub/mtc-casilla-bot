"""CLI principal del bot MTC (entry point ``mtc-bot``).

Comandos disponibles:
    * ``doctor`` — health check de la configuración y conectividad Google.
    * ``version`` — imprime la versión del paquete.
    * ``run`` — stub Fase 1 (no implementado todavía).
    * ``test-login`` — prueba el login en la Casilla MTC para 1 RUC.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

# Forzar UTF-8 en stdout/stderr en Windows para evitar UnicodeEncodeError
# con caracteres como ✓ ✗ ⚠ en consolas con codepage cp1252.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass  # Python <3.7 o stream no soporta reconfigure

from mtc_bot import __version__
from mtc_bot.config import (
    Settings,
    apply_credential_filter,
    audit_print_settings,
    get_settings,
)
from mtc_bot.models import load_rucs
from mtc_bot.scraper.login import (
    LoginFailed,
    browser_session,
    detect_login_summary,
    perform_login,
)

app = typer.Typer(
    name="mtc-bot",
    help="Automatización de notificaciones de la Casilla Electrónica del MTC.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console(force_terminal=True, legacy_windows=False)
logger = logging.getLogger(__name__)

# Símbolos del summary
OK = "[green]✓[/green]"
FAIL = "[red]✗[/red]"
WARN = "[yellow]⚠[/yellow]"


def _setup_logging(level: str) -> None:
    """Inicializa el logger raíz con el nivel solicitado y aplica el filtro."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    apply_credential_filter()


# ─────────────────────────────────────────────────────────────────
# Comando: version
# ─────────────────────────────────────────────────────────────────


@app.command("version")
def version_cmd() -> None:
    """Imprime la versión del paquete."""
    console.print(f"mtc-casilla-bot [bold cyan]{__version__}[/bold cyan]")


# ─────────────────────────────────────────────────────────────────
# Comando: doctor
# ─────────────────────────────────────────────────────────────────


def _check_settings() -> tuple[Settings | None, list[str], list[str]]:
    """Carga ``Settings`` y reporta éxito/error.

    Returns:
        Tupla ``(settings, lines, errors)`` donde ``settings`` puede ser
        ``None`` si la carga falló.
    """
    lines: list[str] = []
    errors: list[str] = []
    try:
        settings = get_settings()
    except Exception as exc:  # configuración inválida
        errors.append(f"No se pudo cargar Settings: {exc}")
        lines.append(f"  {FAIL} Cargar configuración desde .env")
        return None, lines, errors

    lines.append(f"  {OK} Configuración cargada desde .env")
    return settings, lines, errors


def _check_api_keys(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica que las API keys estén presentes (no las usa)."""
    lines: list[str] = []
    errors: list[str] = []

    if settings.deepseek_api_key.get_secret_value().strip():
        lines.append(f"  {OK} DEEPSEEK_API_KEY presente")
    else:
        lines.append(f"  {FAIL} DEEPSEEK_API_KEY vacío")
        errors.append("DEEPSEEK_API_KEY vacío")

    if settings.gemini_api_key.get_secret_value().strip():
        lines.append(f"  {OK} GEMINI_API_KEY presente")
    else:
        lines.append(f"  {FAIL} GEMINI_API_KEY vacío")
        errors.append("GEMINI_API_KEY vacío")

    return lines, errors


def _check_service_account(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica que el JSON del service account exista."""
    lines: list[str] = []
    errors: list[str] = []
    sa_path = settings.google_service_account_json
    if sa_path.exists():
        lines.append(f"  {OK} Service account JSON: {sa_path}")
    else:
        lines.append(f"  {FAIL} Service account JSON no existe: {sa_path}")
        errors.append(f"Falta {sa_path}")
    return lines, errors


def _check_rucs_csv(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica el CSV de RUCs (warning, no fatal si falta)."""
    lines: list[str] = []
    errors: list[str] = []
    csv_path = settings.mtc_credentials_csv
    if not csv_path.exists():
        lines.append(
            f"  {WARN} CSV de RUCs no existe: {csv_path} "
            "(podés correr `doctor` igual; necesario para `run`)"
        )
        return lines, errors
    try:
        rucs = load_rucs(csv_path)
        activos = sum(1 for r in rucs if r.activo)
        lines.append(f"  {OK} CSV de RUCs: {len(rucs)} entradas ({activos} activas)")
    except Exception as exc:
        lines.append(f"  {FAIL} CSV de RUCs inválido: {exc}")
        errors.append(f"CSV inválido: {exc}")
    return lines, errors


def _check_sheet(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica acceso al Google Sheet vía ``sheets_writer``."""
    lines: list[str] = []
    errors: list[str] = []
    try:
        from mtc_bot.google.sheets_writer import (
            verify_sheet_access,  # type: ignore[import-not-found]
        )
    except ImportError as exc:
        lines.append(
            f"  {WARN} Módulo google.sheets_writer no disponible (¿faltó instalar deps?): {exc}"
        )
        return lines, errors
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  {FAIL} Error importando sheets_writer: {exc}")
        errors.append(f"Import sheets_writer: {exc}")
        return lines, errors

    if not settings.google_service_account_json.exists():
        lines.append(f"  {FAIL} Sheet check skipped: falta service-account.json")
        errors.append("Sheet check sin SA")
        return lines, errors

    try:
        status = verify_sheet_access(settings.google_service_account_json, settings.sheet_id)
        title = status.get("sheet_title", "?")
        present = status.get("tabs_present", []) or []
        missing = status.get("tabs_missing", []) or []
        lines.append(f"  {OK} Sheet accesible: '{title}' (id={settings.sheet_id})")
        if present:
            lines.append(f"      tabs presentes: {', '.join(present)}")
        if missing:
            lines.append(f"  {FAIL} tabs faltantes: {', '.join(missing)}")
            errors.append(f"Sheet sin tabs: {', '.join(missing)}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  {FAIL} No se pudo acceder al Sheet: {exc}")
        errors.append(f"Sheet inaccesible: {exc}")
    return lines, errors


def _check_drive(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica acceso a la carpeta raíz de Drive vía ``drive_uploader``."""
    lines: list[str] = []
    errors: list[str] = []
    try:
        from mtc_bot.google.drive_uploader import (
            verify_folder_access,  # type: ignore[import-not-found]
        )
    except ImportError as exc:
        lines.append(
            f"  {WARN} Módulo google.drive_uploader no disponible (¿faltó instalar deps?): {exc}"
        )
        return lines, errors
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  {FAIL} Error importando drive_uploader: {exc}")
        errors.append(f"Import drive_uploader: {exc}")
        return lines, errors

    if not settings.google_service_account_json.exists():
        lines.append(f"  {FAIL} Drive check skipped: falta service-account.json")
        errors.append("Drive check sin SA")
        return lines, errors

    try:
        status = verify_folder_access(
            settings.google_service_account_json, settings.drive_root_folder_id
        )
        name = status.get("folder_name") or status.get("name") or "?"
        lines.append(
            f"  {OK} Carpeta Drive accesible: '{name}' (id={settings.drive_root_folder_id})"
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  {FAIL} No se pudo acceder a la carpeta de Drive: {exc}")
        errors.append(f"Drive inaccesible: {exc}")
    return lines, errors


def _check_obsidian(settings: Settings) -> tuple[list[str], list[str]]:
    """Verifica que la bóveda Obsidian (si está seteada) exista."""
    lines: list[str] = []
    errors: list[str] = []
    vault = settings.obsidian_vault_path
    if vault is None:
        lines.append(f"  {WARN} OBSIDIAN_VAULT_PATH no seteado (opcional)")
        return lines, errors
    if not vault.exists():
        lines.append(f"  {FAIL} Bóveda Obsidian no existe: {vault}")
        errors.append(f"Bóveda inexistente: {vault}")
        return lines, errors
    lines.append(f"  {OK} Bóveda Obsidian: {vault}")
    templates = vault / settings.obsidian_templates_folder
    if templates.exists():
        lines.append(f"  {OK} Carpeta '_templates' presente: {templates}")
    else:
        lines.append(f"  {WARN} Carpeta '_templates' no existe: {templates}")
    return lines, errors


@app.command("doctor")
def doctor_cmd() -> None:
    """Health check completo: configuración, credenciales y conectividad."""
    _setup_logging("INFO")
    console.print(Panel.fit("[bold cyan]mtc-bot doctor[/bold cyan] — health check"))

    all_errors: list[str] = []

    # 1. Settings
    console.print("\n[bold]Configuración[/bold]")
    settings, lines, errors = _check_settings()
    for line in lines:
        console.print(line)
    all_errors.extend(errors)
    if settings is None:
        console.print(f"\n{FAIL} [red]Configuración inválida — abortando chequeos restantes.[/red]")
        raise typer.Exit(code=1)

    # Audit log de las vars (enmascarado)
    audit_print_settings(settings)

    # 2. API keys
    console.print("\n[bold]API keys IA[/bold]")
    lines, errors = _check_api_keys(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # 3. Service account
    console.print("\n[bold]Google service account[/bold]")
    lines, errors = _check_service_account(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # 4. CSV de RUCs (warning si falta)
    console.print("\n[bold]Credenciales MTC (CSV)[/bold]")
    lines, errors = _check_rucs_csv(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # 5. Google Sheet
    console.print("\n[bold]Google Sheet 'MTC Casilla DB'[/bold]")
    lines, errors = _check_sheet(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # 6. Carpeta Drive
    console.print("\n[bold]Google Drive — carpeta raíz[/bold]")
    lines, errors = _check_drive(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # 7. Obsidian
    console.print("\n[bold]Bóveda Obsidian[/bold]")
    lines, errors = _check_obsidian(settings)
    for line in lines:
        console.print(line)
    all_errors.extend(errors)

    # Summary
    console.print()
    if all_errors:
        console.print(
            Panel.fit(
                f"[bold red]✗ {len(all_errors)} problema(s) detectado(s)[/bold red]\n"
                + "\n".join(f"  • {e}" for e in all_errors),
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            "[bold green]✓ Todo OK — el bot está listo[/bold green]",
            border_style="green",
        )
    )


# ─────────────────────────────────────────────────────────────────
# Comandos stub (Fase 1)
# ─────────────────────────────────────────────────────────────────


@app.command("run")
def run_cmd(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Vista previa sin escribir cambios.")
    ] = False,
    since: Annotated[
        str, typer.Option("--since", help="Filtro temporal (ej. 'today', '7d').")
    ] = "today",
) -> None:
    """Ejecuta el ciclo end-to-end del bot. (stub Fase 1)."""
    _ = (dry_run, since)
    console.print("[yellow]Not implemented yet (Fase 1)[/yellow]")
    raise typer.Exit(code=0)


@app.command("test-login")
def test_login_cmd(
    ruc: Annotated[str, typer.Option("--ruc", "-r", help="RUC a probar (11 dígitos).")],
    headed: Annotated[
        bool,
        typer.Option(
            "--headed",
            help="Forzar modo visible (override de MTC_BOT_HEADED).",
        ),
    ] = False,
) -> None:
    """Prueba el login en la Casilla MTC para 1 RUC.

    Ejemplo:
        uv run mtc-bot test-login --ruc 20602194958
        uv run mtc-bot test-login --ruc 20602194958 --headed
    """
    _setup_logging("INFO")
    apply_credential_filter()
    settings = get_settings()

    try:
        rucs = load_rucs(settings.mtc_credentials_csv)
    except FileNotFoundError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[red]✗ CSV inválido: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    target = next((r for r in rucs if r.ruc == ruc and r.activo), None)
    if target is None:
        ruc_mask_prefix = 5
        masked = f"{ruc[:ruc_mask_prefix]}***" if len(ruc) >= ruc_mask_prefix else "***"
        console.print(f"[red]✗ RUC {masked} no encontrado o inactivo en el CSV.[/red]")
        raise typer.Exit(code=1)

    # Override headed solo si el flag --headed se pasa explícitamente
    headless = not (headed or settings.mtc_bot_headed)

    async def _run() -> None:
        async with browser_session(headless=headless) as ctx:
            page = await ctx.new_page()
            try:
                await perform_login(page, target)
            except LoginFailed as exc:
                console.print(f"[red]✗ LoginFailed:[/red] {exc}")
                raise typer.Exit(code=1) from exc
            except NotImplementedError as exc:
                console.print(f"[yellow]⚠ {exc}[/yellow]")
                raise typer.Exit(code=2) from exc

            summary = await detect_login_summary(page)
            console.print(f"[green]✓ Login OK[/green] — {target.empresa}")
            console.print(
                f"  Representante legal cuenta: "
                f"{summary.get('representante_legal') or '(no detectado)'}"
            )
            console.print(f"  Tipo: {summary.get('tipo_persona') or '(no detectado)'}")
            tot = summary.get("total_notificaciones")
            console.print(f"  Total notificaciones: {tot if tot is not None else '(no detectado)'}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
