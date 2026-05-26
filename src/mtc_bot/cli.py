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


def _short_name(empresa: str) -> str:
    """Deriva nombre corto de la razón social para el resumen."""
    import re as _re
    s = _re.sub(r'\s*\([^)]+\)', '', empresa).strip()
    s = _re.sub(r'\b(SAC|EIRL|SRL|S\.A\.C\.|S\.R\.L\.|LTDA|S\.A\.)\b\.?', '', s, flags=_re.IGNORECASE)
    s = _re.sub(r'\bCITV\s+', '', s, flags=_re.IGNORECASE)
    s = _re.sub(r'\s+', ' ', s).strip(' -')
    return s or empresa


def _print_run_summary(
    results: list[tuple[str, int, int, str | None]],
    since_date: "date | None",
) -> None:
    """Imprime el resumen final copy-paste listo para WhatsApp."""
    from datetime import date as _date
    hoy = _date.today()
    if since_date == hoy:
        fecha_label = "al día de hoy"
    elif since_date is not None:
        fecha_label = f"desde {since_date.strftime('%d/%m/%Y')}"
    else:
        fecha_label = "de todas las fechas"

    lines: list[str] = [f"De la revisión de casillas de MTC {fecha_label}:"]
    nuevas_total = 0
    for empresa, _ruc, listed, completados, error in results:
        name = _short_name(empresa)
        if error:
            lines.append(f"• {name}: ❌ error de conexión (timeout MTC)")
        elif completados > 0:
            nuevas_total += completados
            suf = "es" if completados > 1 else ""
            lines.append(f"• {name}: *{completados:02d} notificación{suf} nueva{'s' if completados > 1 else ''}* ✅")
        elif listed > 0:
            lines.append(f"• {name}: {listed} encontradas (ya registradas).")
        else:
            lines.append(f"• {name}: no hay notificaciones nuevas.")

    resumen_body = "\n".join(lines)
    border = "green" if nuevas_total > 0 else "cyan"
    console.print(
        Panel(
            resumen_body,
            title=f"[bold]RESUMEN — {hoy.strftime('%d/%m/%Y')}[/bold]",
            border_style=border,
            padding=(1, 2),
        )
    )
    # Versión plain-text (fácil de copiar)
    console.print("\n[dim]── Texto para copiar ──[/dim]")
    console.print(resumen_body)
    console.print()


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
    try:
        return date.fromisoformat(since)
    except ValueError:
        pass
    console.print(f"[red]✗ --since inválido: {since!r}. Formatos válidos: today, yesterday, all, 3d, YYYY-MM-DD[/red]")
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
    asunto_short = f"[{item.fecha}] {item.asunto[:40]}"

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

    # Fecha definitiva: preferir la del detalle (más precisa, incluye hora) si
    # la del inbox no se pudo parsear (date.min = fallback por formato desconocido).
    from datetime import date as _date
    fecha_final = item.fecha
    if fecha_final == _date.min:
        if detail_md.fecha is not None:
            logger.warning(
                "Usando fecha del DETALLE como fallback (%s) — la fecha del inbox no pudo parsearse",
                detail_md.fecha,
            )
            fecha_final = detail_md.fecha
        else:
            logger.warning(
                "Sin fecha válida ni en inbox ni en detalle para notif %s — se usará date.min",
                item.notification_id,
            )

    plazo_venc = _estimate_vencimiento(fecha_final, extraction.plazo_dias_habiles)

    # Sede: usar la del RUC, pero si es LIDERSUR Puno y el texto menciona
    # Puerto Maldonado, usar esa sede en su lugar.
    sede = creds.sede
    if "REVISIONES TECNICAS" in creds.empresa.upper():
        texto_lower = (extraction.asunto + " " + extraction.resumen).lower()
        if "maldonado" in texto_lower or "madre de dios" in texto_lower:
            sede = "Puerto Maldonado"

    row: dict[str, str | int | float | bool | None] = {
        "id": sheet_id_value,
        "timestamp_proceso": timestamp_proceso,
        "fecha_notificacion": fecha_final.isoformat(),
        "lectura_notificacion": fecha_final.isoformat(),
        "ruc": item.ruc,
        "empresa": creds.empresa,
        "sede": sede,
        "documento": extraction.documento or item.asunto,
        "emisor": extraction.emisor or item.emisor,
        "casilla_origen": extraction.casilla_origen or "MTC",
        "asunto": extraction.asunto or item.asunto,
        "referencia": extraction.referencia,
        "resumen": extraction.resumen,
        "tipo_acto": extraction.tipo_acto,
        "accion_requerida": extraction.accion_requerida,
        "consecuencias": extraction.consecuencias,
        "fundamento_legal": extraction.fundamento_legal,
        "tarea": ", ".join(extraction.tarea),
        "requiere_respuesta": extraction.requiere_respuesta,
        "plazo_dias_habiles": extraction.plazo_dias_habiles,
        "plazo_vencimiento": plazo_venc,
        "progreso": "NO INICIADO",
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
        f"    [green]✓[/green] {asunto_short} → {len(pdfs)} PDF(s), drive={uploaded.file_id[:8]}..."
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
        except LoginFailed as exc:
            if "timeout" in str(exc).lower():
                raise  # propagar para que _run_all reintente
            console.print(f"  [red]✗[/red] {creds.ruc[:5]}*** login falló: {exc}")
            if not headless:
                await _take_screenshot(page, shots_dir / "login_failed.png", "login_failed")
            return 0, 0
        except NotImplementedError as exc:
            console.print(f"  [red]✗[/red] {creds.ruc[:5]}*** auth no implementada: {exc}")
            return 0, 0

        items = await list_inbox(page, creds.ruc, since=since_date, limit=limit)
        console.print(f"  {creds.empresa[:40]}: {len(items)} notif para procesar")
        if not headless:
            from mtc_bot.scraper.inbox import _navigate_to_page
            await _navigate_to_page(page, 1)  # volver a pág 1 para capturar ítems recientes
            await _take_screenshot(page, shots_dir / "inbox.png", "inbox")

        if dry_run:
            for it in items:
                console.print(f"    - [{it.fecha}] {it.asunto[:60]}")
            return len(items), 0

        completados = 0
        for it in items:
            try:
                ok = await _process_notification(
                    ctx,
                    page,
                    it,
                    creds,
                    settings,
                    downloads_root,
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

    _MAX_ATTEMPTS = 3   # 1 intento original + 2 reintentos
    _RETRY_WAIT_S = 30  # segundos entre reintentos (aumentado para evitar rate-limit)
    _INTER_RUC_WAIT_S = 15  # pausa entre compañías — evita Cloudflare 1015

    async def _run_all() -> None:
        console.print(
            f"\n[bold]Procesando {len(targets)} RUC(s) — "
            f"since={since}, limit={limit}, dry_run={dry_run}[/bold]\n"
        )
        run_results: list[tuple[str, int, int, str | None]] = []
        # Secuencial por RUC: regla del proyecto (no paralelizar el mismo RUC).
        for idx, creds in enumerate(targets):
            # Pausa entre compañías para no disparar el rate-limit de Cloudflare.
            if idx > 0:
                console.print(f"  [dim]Esperando {_INTER_RUC_WAIT_S}s antes de la siguiente empresa...[/dim]")
                await asyncio.sleep(_INTER_RUC_WAIT_S)
            console.print(f"[cyan]→ {creds.empresa}[/cyan]")
            last_exc: Exception | None = None
            listed = completados = 0
            for attempt in range(1, _MAX_ATTEMPTS + 1):
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
                    last_exc = None
                    break  # éxito — salir del loop de reintentos
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    is_timeout = "Timeout" in str(exc) or "timeout" in str(exc).lower()
                    if is_timeout and attempt < _MAX_ATTEMPTS:
                        console.print(
                            f"  [yellow]⚠ Timeout MTC — reintentando en {_RETRY_WAIT_S}s "
                            f"(intento {attempt + 1}/{_MAX_ATTEMPTS})[/yellow]"
                        )
                        await asyncio.sleep(_RETRY_WAIT_S)
                    else:
                        break  # error no recuperable o último intento

            if last_exc is not None:
                run_results.append((creds.empresa, creds.ruc, 0, 0, str(last_exc)))
                console.print(f"  [red]✗ Error fatal: {last_exc}[/red]\n")
            else:
                run_results.append((creds.empresa, creds.ruc, listed, completados, None))
                if dry_run:
                    console.print(f"  [green]✓[/green] {listed} listadas (dry-run)\n")
                else:
                    console.print(
                        f"  [green]✓[/green] {listed} listadas, {completados} completadas (Sheet)\n"
                    )

        if not dry_run:
            _print_run_summary(run_results, since_date)
            # Guardar resumen en Sheet tab resumen_diario
            try:
                from .google.sheets_writer import write_resumen_diario
                texto = "\n".join(
                    f"• {_short_name(e)}: " + (
                        f"{c} notificación{'es' if c > 1 else ''} nueva{'s' if c > 1 else ''}"
                        if c > 0 else ("error" if err else "no hay notificaciones nuevas")
                    )
                    for e, _r, l, c, err in run_results
                )
                write_resumen_diario(
                    settings.google_service_account_json,
                    settings.sheet_id,
                    run_results,
                    date.today(),
                    texto,
                )
                console.print("[dim]✓ Resumen guardado en Sheet (tab: resumen_diario)[/dim]")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]⚠ No se pudo guardar resumen en Sheet: {exc}[/yellow]")

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


@app.command("reprocess")
def reprocess_cmd(
    limit: Annotated[
        int,
        typer.Option("--limit", help="Máximo de notificaciones a re-procesar."),
    ] = 50,
    all_fields: Annotated[
        bool,
        typer.Option("--all-fields", help="Actualizar TODOS los campos IA (no solo los nuevos vacíos)."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simular sin escribir en el Sheet."),
    ] = False,
    log_level: Annotated[str, typer.Option("--log-level")] = "INFO",
) -> None:
    """Re-analiza notificaciones existentes descargando su PDF de Drive y re-corriendo la IA.

    Por defecto procesa solo filas donde ``tipo_acto`` está vacío.
    Con ``--all-fields`` re-analiza todas y sobreescribe todos los campos IA.

    Ejemplos:
        uv run mtc-bot reprocess
        uv run mtc-bot reprocess --limit 10 --dry-run
        uv run mtc-bot reprocess --all-fields --limit 5
    """
    _setup_logging(log_level)
    asyncio.run(_reprocess_async(limit=limit, all_fields=all_fields, dry_run=dry_run))


async def _reprocess_async(limit: int, all_fields: bool, dry_run: bool) -> None:
    """Orquesta el re-procesamiento de notificaciones existentes."""
    from mtc_bot.ai_extractor import AIExtractionFailed
    from mtc_bot.ai_extractor import extract as ai_extract
    from mtc_bot.google.drive_uploader import download_pdf_from_drive
    from mtc_bot.google.sheets_writer import get_all_notificaciones, update_notificacion_fields
    from mtc_bot.pdf_pipeline import extract_text

    from mtc_bot.config import PROJECT_ROOT  # noqa: PLC0415

    settings = get_settings()
    tmp_dir = PROJECT_ROOT / "data" / "downloads" / "_reprocess_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Campos que siempre actualizamos (los nuevos del resumen estructurado)
    NEW_FIELDS = {"tipo_acto", "accion_requerida", "consecuencias", "fundamento_legal"}
    # Campos adicionales que se actualizan con --all-fields
    ALL_AI_FIELDS = NEW_FIELDS | {"resumen", "tarea", "casilla_origen", "referencia",
                                   "emisor", "asunto", "requiere_respuesta",
                                   "plazo_dias_habiles", "confianza_ia", "modelo_ia"}

    missing_field = None if all_fields else "tipo_acto"

    console.print(
        Panel(
            f"[bold]mtc-bot reprocess[/bold]\n"
            f"Modo: {'todos los campos' if all_fields else 'solo campos nuevos vacíos'}\n"
            f"Límite: {limit} · Dry-run: {dry_run}",
            border_style="cyan",
        )
    )

    # 1) Leer filas candidatas del Sheet
    try:
        rows = get_all_notificaciones(
            settings.google_service_account_json,
            settings.sheet_id,
            settings.sheet_tab_notificaciones,
            only_missing_field=missing_field,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗ Error leyendo el Sheet: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not rows:
        console.print("[green]✓ No hay notificaciones pendientes de re-procesar.[/green]")
        return

    # Verificar columnas destino ANTES de procesar (evita falsos positivos)
    if not dry_run:
        target_fields = NEW_FIELDS if not all_fields else ALL_AI_FIELDS
        sample_keys = set(rows[0].keys()) if rows else set()
        missing_cols = sorted(f for f in target_fields if f not in sample_keys)
        if missing_cols:
            console.print("[red bold]✗ Las siguientes columnas no existen en el Sheet:[/red bold]")
            for col in missing_cols:
                console.print(f"  [red]  • {col}[/red]")
            console.print(
                "\n[yellow]Agregá esas columnas al tab "
                f"'{settings.sheet_tab_notificaciones}' del Sheet "
                "y volvé a ejecutar:[/yellow]\n"
                "  [cyan]uv run mtc-bot reprocess[/cyan]"
            )
            raise typer.Exit(code=1)

    total = min(len(rows), limit)
    console.print(f"  {len(rows)} filas candidatas · procesando {total}\n")

    ok_count = err_count = skip_count = 0

    for row in rows[:limit]:
        notif_id    = str(row.get("id", "")).strip()
        empresa     = str(row.get("empresa", "")).strip()[:35]
        documento   = str(row.get("documento", "")).strip()[:50]
        file_id     = str(row.get("drive_file_id", "")).strip()
        short_label = f"[{empresa}] {documento}"

        if not file_id:
            console.print(f"  {WARN} {short_label}: sin drive_file_id, saltando")
            skip_count += 1
            continue

        if dry_run:
            console.print(f"  [cyan]DRY[/cyan] {short_label}")
            ok_count += 1
            continue

        # 2) Descargar PDF de Drive
        tmp_pdf = tmp_dir / f"{notif_id}.pdf"
        try:
            download_pdf_from_drive(
                settings.google_service_account_json,
                file_id,
                tmp_pdf,
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"  {FAIL} {short_label}: descarga Drive falló: {exc}")
            err_count += 1
            continue

        # 3) Extraer texto (con mejoras: layout, tablas, OCR si es necesario)
        try:
            texto = extract_text(tmp_pdf)
        except Exception as exc:  # noqa: BLE001
            console.print(f"  {FAIL} {short_label}: extracción texto falló: {exc}")
            err_count += 1
            tmp_pdf.unlink(missing_ok=True)
            continue

        if not texto.strip():
            console.print(f"  {WARN} {short_label}: texto vacío tras extracción, saltando")
            skip_count += 1
            tmp_pdf.unlink(missing_ok=True)
            continue

        # 4) Re-análisis IA
        try:
            extraction = await ai_extract(texto, settings)
        except AIExtractionFailed as exc:
            console.print(f"  {FAIL} {short_label}: IA falló: {exc}")
            err_count += 1
            tmp_pdf.unlink(missing_ok=True)
            continue

        # 5) Construir dict de campos a actualizar
        fields_to_update: dict[str, str | int | float | bool | None] = {
            "tipo_acto":       extraction.tipo_acto,
            "accion_requerida": extraction.accion_requerida,
            "consecuencias":   extraction.consecuencias,
            "fundamento_legal": extraction.fundamento_legal,
        }
        if all_fields:
            fields_to_update.update({
                "resumen":           extraction.resumen,
                "tarea":             ", ".join(extraction.tarea),
                "casilla_origen":    extraction.casilla_origen,
                "referencia":        extraction.referencia,
                "emisor":            extraction.emisor,
                "asunto":            extraction.asunto,
                "requiere_respuesta": extraction.requiere_respuesta,
                "plazo_dias_habiles": extraction.plazo_dias_habiles,
                "confianza_ia":      extraction.confianza,
                "modelo_ia":         extraction.modelo_ia,
            })

        # 6) Actualizar Sheet
        try:
            updated = update_notificacion_fields(
                settings.google_service_account_json,
                settings.sheet_id,
                settings.sheet_tab_notificaciones,
                notif_id,
                fields_to_update,
            )
            if updated:
                console.print(
                    f"  {OK} {short_label} "
                    f"[dim]({extraction.modelo_ia}, confianza={extraction.confianza})[/dim]"
                )
                ok_count += 1
            else:
                console.print(f"  {WARN} {short_label}: ID no encontrado en Sheet")
                skip_count += 1
        except Exception as exc:  # noqa: BLE001
            console.print(f"  {FAIL} {short_label}: Sheet update falló: {exc}")
            err_count += 1

        tmp_pdf.unlink(missing_ok=True)

    # Limpiar directorio temporal
    try:
        tmp_dir.rmdir()
    except OSError:
        pass  # aún tiene archivos si hubo errores — no importa

    console.print(
        Panel(
            f"{OK} [green]{ok_count}[/green] actualizadas · "
            f"{WARN} [yellow]{skip_count}[/yellow] saltadas · "
            f"{FAIL} [red]{err_count}[/red] errores",
            border_style="green" if err_count == 0 else "yellow",
        )
    )


if __name__ == "__main__":
    app()
