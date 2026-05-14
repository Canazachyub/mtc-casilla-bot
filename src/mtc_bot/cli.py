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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

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

    oauth_path = settings.oauth_credentials_json
    if oauth_path.exists():
        lines.append(f"  {OK} OAuth credentials (upload): {oauth_path.name}")
    else:
        lines.append(
            f"  {WARN} oauth-credentials.json no encontrado — uploads usarán SA (riesgo 403)"
        )
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


def _parse_since(since: str) -> date | None:
    """Convierte la opción ``--since`` a fecha. Lanza ``typer.Exit`` si es inválido."""
    from datetime import timedelta

    today = date.today()
    if since == "today":
        return today
    if since == "yesterday":
        return today - timedelta(days=1)
    if since == "all":
        return None
    if since.endswith("d") and since[:-1].isdigit():
        return today - timedelta(days=int(since[:-1]))
    console.print(f"[red]✗ --since inválido: {since!r}[/red]")
    raise typer.Exit(code=1)


def _load_targets(settings: Settings, ruc: str | None) -> list:
    """Carga RUCs desde el CSV y filtra por activos / por ``--ruc``."""
    try:
        rucs_all = load_rucs(settings.mtc_credentials_csv)
    except FileNotFoundError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[red]✗ CSV inválido: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if ruc:
        targets = [r for r in rucs_all if r.ruc == ruc and r.activo]
    else:
        targets = [r for r in rucs_all if r.activo]
    if not targets:
        console.print("[red]✗ Ningún RUC activo encontrado para procesar[/red]")
        raise typer.Exit(code=1)
    return targets


def _build_sheet_id(ruc: str, notification_id: str) -> str:
    """Construye el ``id`` único de Sheet combinando RUC y notification_id.

    Formato: ``<ruc>__<notification_id>``. Evita colisiones entre RUCs y es
    legible al inspeccionar el Sheet.
    """
    return f"{ruc}__{notification_id}"


def _estimate_vencimiento(fecha_base: date, plazo_dias_habiles: int) -> str:
    """Estima la fecha de vencimiento dados días hábiles.

    Aproximación simple: 5 días hábiles ≈ 7 días corridos. NO considera
    feriados peruanos (TODO: integrar ``holidays.Peru()`` cuando se valide
    la dependencia). Si ``plazo_dias_habiles <= 0``, devuelve string vacío.

    Args:
        fecha_base: fecha de notificación.
        plazo_dias_habiles: días hábiles otorgados.

    Returns:
        Fecha estimada en formato ISO ``YYYY-MM-DD``, o "" si no aplica.
    """
    if plazo_dias_habiles <= 0:
        return ""
    # Aproximación: avanzar día por día, saltando sábados/domingos.
    current = fecha_base
    days_added = 0
    while days_added < plazo_dias_habiles:
        current = current + timedelta(days=1)
        # weekday(): Mon=0 ... Sun=6. Saltamos Sat=5 y Sun=6.
        if current.weekday() < 5:  # noqa: PLR2004 — 5 = sábado en weekday()
            days_added += 1
    return current.isoformat()


async def _process_notification(  # noqa: PLR0911,PLR0912,PLR0913,PLR0915 — pipeline lineal con muchos pasos
    ctx,
    page,
    item,
    creds,
    settings,
    downloads_root,
    shots_dir=None,
) -> bool:
    """Procesa UNA notificación end-to-end.

    Pasos: idempotencia-check → click → metadata → descarga → merge → texto
    → IA → rename → Drive upload → Sheet append.

    Args:
        ctx: ``BrowserContext`` activo.
        page: ``Page`` del inbox (con item visible).
        item: ``InboxItem`` a procesar.
        creds: ``RucCredentials`` del RUC.
        settings: ``Settings`` global.
        downloads_root: ``Path`` raíz de descargas para este RUC.

    Returns:
        ``True`` si llegó hasta el append en Sheet, ``False`` si se saltó o
        falló en algún paso intermedio (no levanta excepciones — todas se
        capturan y loguean para no abortar el batch).
    """
    from mtc_bot.ai_extractor import AIExtractionFailed
    from mtc_bot.ai_extractor import extract as ai_extract
    from mtc_bot.google.drive_uploader import upload_pdf
    from mtc_bot.google.sheets_writer import append_notificacion, notification_exists
    from mtc_bot.pdf_pipeline import extract_text, merge_pdfs, rename_merged
    from mtc_bot.scraper.downloader import (
        download_attachments,
        extract_detail_metadata,
    )
    from mtc_bot.scraper.inbox import click_item

    sheet_id_value = _build_sheet_id(item.ruc, item.notification_id)
    asunto_short = item.asunto[:50]

    # 1) Idempotencia
    try:
        if notification_exists(
            settings.google_service_account_json,
            settings.sheet_id,
            settings.sheet_tab_notificaciones,
            sheet_id_value,
        ):
            console.print(f"    [yellow]⊝[/yellow] {asunto_short} — ya procesada (skip)")
            return False
    except Exception as exc:  # noqa: BLE001 — no abortar batch por error de Sheet
        console.print(f"    [red]✗[/red] {asunto_short}: idempotencia check falló: {exc}")
        return False

    # 2) Click + 3) metadata
    try:
        await click_item(page, item)
        if shots_dir is not None:
            await _take_screenshot(page, shots_dir / f"{item.notification_id}_detail.png", "detail")
        detail_md = await extract_detail_metadata(page)
    except Exception as exc:  # noqa: BLE001
        console.print(f"    [red]✗[/red] {asunto_short}: click/metadata falló: {exc}")
        return False

    # 4) Descarga
    dest = downloads_root / item.notification_id
    try:
        console.print(f"    [download] {asunto_short}...")
        pdfs = await download_attachments(ctx, page, dest)
        if shots_dir is not None:
            await _take_screenshot(
                page, shots_dir / f"{item.notification_id}_attachments.png", "attachments"
            )
    except Exception as exc:  # noqa: BLE001
        console.print(f"    [red]✗[/red] {asunto_short}: descarga falló: {exc}")
        return False

    if not pdfs:
        console.print(f"    [yellow]⚠[/yellow] {asunto_short}: 0 PDFs (skip)")
        return False

    # 5) Merge (puede fallar si no hay documento principal)
    try:
        console.print(f"    [merge] {asunto_short}...")
        merged_path = merge_pdfs([p.path for p in pdfs], dest / "merged.pdf")
    except (ValueError, OSError) as exc:
        console.print(f"    [red]✗[/red] {asunto_short}: merge falló: {exc}")
        return False

    # 6) Extract text
    try:
        texto = extract_text(merged_path)
    except FileNotFoundError as exc:
        console.print(f"    [red]✗[/red] {asunto_short}: extract_text falló: {exc}")
        return False

    # 7) IA
    try:
        console.print(f"    [ai] {asunto_short}...")
        extraction = await ai_extract(texto, settings)
    except AIExtractionFailed as exc:
        console.print(f"    [yellow]⚠[/yellow] {asunto_short}: IA falló: {exc} (skip Sheet)")
        return False

    # 8) Rename
    rename_seed = extraction.documento or detail_md.asunto or item.asunto
    try:
        final_pdf = rename_merged(merged_path, rename_seed)
    except (FileNotFoundError, OSError) as exc:
        console.print(f"    [red]✗[/red] {asunto_short}: rename falló: {exc}")
        return False

    # 9) Upload a Drive
    try:
        console.print(f"    [drive] {asunto_short}...")
        uploaded = upload_pdf(
            settings.google_service_account_json,
            settings.drive_root_folder_id,
            final_pdf,
            item.ruc,
            item.fecha,
            oauth_json_path=settings.oauth_credentials_json,
            oauth_token_path=settings.oauth_token_json,
        )
    except Exception as exc:  # noqa: BLE001 — HttpError u otros
        console.print(f"    [red]✗[/red] {asunto_short}: Drive upload falló: {exc}")
        return False

    # 10) Append a Sheet
    timestamp_proceso = datetime.now(tz=ZoneInfo("America/Lima")).isoformat(
        timespec="seconds",
    )
    plazo_venc = _estimate_vencimiento(item.fecha, extraction.plazo_dias_habiles)
    row: dict[str, str | int | float | bool | None] = {
        "id": sheet_id_value,
        "timestamp_proceso": timestamp_proceso,
        "fecha_notificacion": item.fecha.isoformat(),
        "ruc": item.ruc,
        "empresa": creds.empresa,
        "documento": extraction.documento or item.asunto,
        "emisor": extraction.emisor or item.emisor,
        "asunto": extraction.asunto or item.asunto,
        "resumen": extraction.resumen,
        "requiere_respuesta": extraction.requiere_respuesta,
        "plazo_dias_habiles": extraction.plazo_dias_habiles,
        "plazo_vencimiento": plazo_venc,
        "confianza_ia": extraction.confianza,
        "modelo_ia": extraction.modelo_ia,
        "drive_file_id": uploaded.file_id,
        "drive_view_url": uploaded.view_url,
        "estado": "pendiente",
    }
    try:
        append_notificacion(
            settings.google_service_account_json,
            settings.sheet_id,
            settings.sheet_tab_notificaciones,
            row,
        )
    except Exception as exc:  # noqa: BLE001 — APIError de gspread u otros
        console.print(f"    [red]✗[/red] {asunto_short}: Sheet append falló: {exc}")
        return False

    console.print(
        f"    [green]✓[/green] {asunto_short} → {len(pdfs)} PDF(s), "
        f"drive={uploaded.file_id[:8]}..."
    )
    return True


async def _take_screenshot(page, path: Path, label: str) -> None:
    """Guarda captura de pantalla ignorando errores (no aborta el pipeline)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
        logger.debug("Screenshot guardado: %s", path.name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Screenshot falló (%s): %s", label, exc)


async def _process_one_ruc(  # noqa: PLR0913 — función privada del CLI
    creds,
    since_date,
    limit: int,
    dry_run: bool,
    headless: bool,
    downloads_root_base,
    settings,
) -> tuple[int, int]:
    """Procesa un RUC. Devuelve ``(items_listados, items_completados)``.

    En ``dry_run`` solo lista items sin descargar ni procesar.
    """
    from mtc_bot.config import PROJECT_ROOT
    from mtc_bot.scraper.inbox import list_inbox

    downloads_root = downloads_root_base / creds.ruc
    shots_dir = PROJECT_ROOT / "playwright-screenshots" / creds.ruc
    async with browser_session(
        headless=headless,
        downloads_path=downloads_root,
    ) as ctx:
        page = await ctx.new_page()
        try:
            await perform_login(page, creds)
        except (LoginFailed, NotImplementedError) as exc:
            console.print(f"  [red]✗[/red] {creds.ruc[:5]}*** login falló: {exc}")
            if not headless:
                await _take_screenshot(page, shots_dir / "login_failed.png", "login_failed")
            return 0, 0

        if not headless:
            await _take_screenshot(page, shots_dir / "inbox.png", "inbox")

        items = await list_inbox(page, creds.ruc, since=since_date, limit=limit)
        console.print(f"  {creds.empresa[:40]}: {len(items)} notif para procesar")

        if dry_run:
            for it in items:
                console.print(f"    - [{it.fecha}] {it.asunto[:60]}")
            return len(items), 0

        completados = 0
        for it in items:
            try:
                ok = await _process_notification(
                    ctx, page, it, creds, settings, downloads_root,
                    shots_dir=shots_dir if not headless else None,
                )
                if ok:
                    completados += 1
            except Exception as exc:  # noqa: BLE001 — seguir con la siguiente
                console.print(f"    [red]✗[/red] {it.asunto[:50]}: error inesperado: {exc}")
        return len(items), completados


@app.command("run")
def run_cmd(
    ruc: Annotated[
        str | None,
        typer.Option("--ruc", "-r", help="RUC específico a procesar (opcional)."),
    ] = None,
    since: Annotated[
        str,
        typer.Option(
            "--since",
            help="Filtro temporal: 'today', 'yesterday', 'NNd' (ej '7d') o 'all'.",
        ),
    ] = "today",
    limit: Annotated[
        int,
        typer.Option("--limit", help="Máximo de notificaciones por RUC."),
    ] = 5,
    headed: Annotated[
        bool,
        typer.Option("--headed", help="Forzar modo visible del browser."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Solo lista; no descarga PDFs."),
    ] = False,
) -> None:
    """Ciclo end-to-end completo de Fase 1.

    Pipeline por notificación: login → listar inbox → idempotencia-check →
    descarga PDFs → merge → extracción texto → IA (DeepSeek + Gemini fallback)
    → rename → upload a Drive → append al Sheet ``notificaciones``.

    En ``--dry-run`` solo lista items, no descarga ni procesa nada.
    """
    from mtc_bot.config import PROJECT_ROOT

    _setup_logging("INFO")
    settings = get_settings()

    since_date = _parse_since(since)
    targets = _load_targets(settings, ruc)
    headless = not (headed or settings.mtc_bot_headed)
    downloads_root_base = PROJECT_ROOT / "data" / "downloads"

    async def _run_all() -> None:
        console.print(
            f"\n[bold]Procesando {len(targets)} RUC(s) — "
            f"since={since}, limit={limit}, dry_run={dry_run}[/bold]\n"
        )
        # Secuencial por RUC: regla del proyecto (no paralelizar el mismo RUC).
        for creds in targets:
            console.print(f"[cyan]→ {creds.empresa}[/cyan]")
            try:
                listed, completados = await _process_one_ruc(
                    creds,
                    since_date,
                    limit,
                    dry_run,
                    headless,
                    downloads_root_base,
                    settings,
                )
                if dry_run:
                    console.print(f"  [green]✓[/green] {listed} listadas (dry-run)\n")
                else:
                    console.print(
                        f"  [green]✓[/green] {listed} listadas, "
                        f"{completados} completadas (Sheet)\n"
                    )
            except Exception as exc:  # noqa: BLE001 — no abortar batch
                console.print(f"  [red]✗ Error fatal: {exc}[/red]\n")

    asyncio.run(_run_all())


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
