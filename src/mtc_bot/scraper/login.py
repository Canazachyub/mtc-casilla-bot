"""Login en la Casilla Electrónica MTC (PERSONA JURIDICA).

Soporta dos modos:

* ``direct``: form de login con RUC + DNI rep. legal + contraseña casilla.
* ``clave_sol``: redirect OAuth2 a ``api-seguridad.sunat.gob.pe`` y vuelta a MTC.

Las cuentas de la Casilla MTC son SIEMPRE PERSONA JURIDICA en este proyecto;
nunca PERSONA NATURAL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from mtc_bot.config import get_settings
from mtc_bot.models import RucCredentials

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Constantes públicas
# ─────────────────────────────────────────────────────────────────

LOGIN_URL: str = "https://casilla.mtc.gob.pe/#/auth/login"
INBOX_URL_GLOB: str = "**/casilla**"
SUNAT_HOST_FRAGMENT: str = "sunat.gob.pe"

DEFAULT_TIMEOUT_MS: int = 60_000
LOGIN_NAV_TIMEOUT_MS: int = 30_000

# Cantidad mínima de dígitos del RUC que se exponen al enmascarar (los primeros N).
_RUC_MASK_PREFIX = 5

# Selectores Angular (estables — basados en formcontrolname)
SEL_TIPO_PERSONA = "mat-select[formcontrolname='tipoPersona']"
SEL_RUC = "input[formcontrolname='ruc']"
SEL_USERNAME = "input[formcontrolname='username']"
SEL_PASSWORD = "input[formcontrolname='password']"  # noqa: S105 — selector CSS, no credencial
SEL_BTN_LOGIN = "button.btn-login"
SEL_BTN_CLAVE_SOL = "button.btn-clave-sol"
SEL_MAT_OPTION_PJ = "mat-option:has-text('PERSONA JURIDICA')"
SEL_MAT_ERROR = "mat-error"

# Selectores SUNAT (Bootstrap clásico, IDs únicos en api-seguridad.sunat.gob.pe)
SUNAT_SEL_TAB_RUC = "#btnPorRuc"
SUNAT_SEL_TAB_DNI = "#btnPorDni"
SUNAT_SEL_INPUT_RUC = "#txtRuc"
SUNAT_SEL_INPUT_USUARIO = "#txtUsuario"
SUNAT_SEL_INPUT_PASSWORD = "#txtContrasena"  # noqa: S105 — selector CSS, no credencial
SUNAT_SEL_BTN_SUBMIT = "#btnAceptar"
SUNAT_SEL_ERROR = "#divMensajeError #spanMensajeError"
SUNAT_SEL_CHECKBOX_REMEMBER = "#chkRecuerdame"

# Selectores post-login
SEL_HEADER_REP_LEGAL = ".custom-header span[style*='font-weight: 500']"
SEL_HEADER_TIPO_PERSONA = ".custom-header small"
SEL_PAGINATOR_RANGE = ".mat-mdc-paginator-range-label"

# Regex para parsear "1 – 25 of 95" (con guion en U+2013) o "1 - 25 of 95"
_PAGINATOR_TOTAL_RE = re.compile(r"of\s+(\d+)", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────
# Excepciones
# ─────────────────────────────────────────────────────────────────


class LoginFailed(Exception):
    """Login fracasado: credenciales inválidas, portal caído o redirección inesperada."""


# ─────────────────────────────────────────────────────────────────
# Browser session
# ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def browser_session(
    headless: bool | None = None,
    downloads_path: Path | None = None,
    trace_path: Path | None = None,
) -> AsyncIterator[BrowserContext]:
    """Abre un ``BrowserContext`` Chromium con la config canónica del bot.

    Sigue las convenciones de ``.claude/rules/playwright.md``: locale es-PE,
    timezone Lima, viewport 1366x768, UA real y flags anti-automation. El
    cleanup del browser está garantizado en ``finally``.

    Args:
        headless: si ``None``, se respeta ``settings.mtc_bot_headed`` (headed
            cuando es ``True``); si se pasa explícitamente, se usa ese valor.
        downloads_path: directorio donde guardar descargas (opcional).
        trace_path: si se provee, se activa tracing y se vuelca al cerrar.

    Yields:
        ``BrowserContext`` listo para crear páginas.
    """
    settings = get_settings()
    if headless is None:
        headless = not settings.mtc_bot_headed

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
    if os.name == "posix":
        launch_args.append("--no-sandbox")

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Crear directorio de descargas antes de entrar al contexto async.
    # mkdir es sync local: aceptable acá, no bloquea de forma significativa.
    if downloads_path is not None:
        downloads_path.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=launch_args,
            slow_mo=50 if not headless else 0,
        )
        context_kwargs: dict[str, object] = {
            "accept_downloads": True,
            "locale": "es-PE",
            "timezone_id": "America/Lima",
            "viewport": {"width": 1366, "height": 768},
            "user_agent": user_agent,
        }
        context = await browser.new_context(**context_kwargs)  # type: ignore[arg-type]
        context.set_default_timeout(settings.playwright_timeout_ms or DEFAULT_TIMEOUT_MS)

        tracing_started = False
        if trace_path is not None:
            await context.tracing.start(snapshots=True, screenshots=True, sources=True)
            tracing_started = True

        try:
            yield context
        finally:
            if tracing_started and trace_path is not None:
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    await context.tracing.stop(path=str(trace_path))
                except Exception as exc:  # noqa: BLE001 — no romper cleanup
                    logger.warning("No se pudo guardar trace en %s: %s", trace_path, exc)
            try:
                await context.close()
            finally:
                await browser.close()


# ─────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────


async def _ensure_persona_juridica(page: Page) -> None:
    """Asegura que el dropdown ``tipoPersona`` esté en ``PERSONA JURIDICA``.

    Flujo:
        1. Esperar el trigger (``.mat-mdc-select-trigger``) en el DOM.
        2. Esperar que Angular haya seteado el valor (``innerText != ''``).
           Sin este paso, el click abre un panel vacío o no abre nada.
        3. Si ya es JURIDICA, retornar.
        4. Click en el trigger → esperar ``mat-option`` visible.
        5. Fallback teclado si el click no abrió el panel.

    Args:
        page: página del browser ya posicionada en el form de login.
    """
    select_locator = page.locator(SEL_TIPO_PERSONA).first
    await select_locator.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)

    trigger_sel = (
        "mat-select[formcontrolname='tipoPersona'] .mat-mdc-select-trigger, "
        "mat-select[formcontrolname='tipoPersona'] .mat-select-trigger"
    )
    try:
        await page.wait_for_selector(trigger_sel, state="visible", timeout=45_000)
    except PlaywrightTimeoutError as exc:
        raise LoginFailed(
            "mat-select trigger no apareció en 45 s — Angular no finalizó bootstrap"
        ) from exc

    # Esperar que Angular complete el data binding y ponga el valor en innerText.
    # El trigger puede estar en el DOM ANTES de que el binding se aplique.
    # Si interactuamos antes, el panel se abre vacío o no abre.
    _JS_VALUE_READY = (
        "() => { const s = document.querySelector(\"mat-select[formcontrolname='tipoPersona']\");"
        " return !!(s && s.innerText && s.innerText.trim().length > 0); }"
    )
    try:
        await page.wait_for_function(_JS_VALUE_READY, timeout=25_000)
    except PlaywrightTimeoutError:
        logger.warning(
            "mat-select innerText no se pobló en 25s — Angular puede no haber terminado el binding"
        )

    try:
        current = (await select_locator.inner_text(timeout=2_000)).strip().upper()
    except PlaywrightTimeoutError:
        current = ""

    if "JURIDICA" in current or "JURÍDICA" in current:
        logger.debug("tipoPersona ya en PERSONA JURIDICA")
        return

    logger.info("Cambiando tipoPersona a PERSONA JURIDICA (estado actual=%r)", current)

    trigger_loc = page.locator(trigger_sel).first
    await trigger_loc.scroll_into_view_if_needed()
    await page.bring_to_front()  # asegurar foco para que los eventos Angular lleguen
    await trigger_loc.click(timeout=5_000)

    option_loc = page.locator(SEL_MAT_OPTION_PJ).first
    try:
        await option_loc.wait_for(state="visible", timeout=12_000)
    except PlaywrightTimeoutError:
        # Fallback: teclado. Algunos contextos Playwright no disparan el MouseEvent
        # que Angular escucha. Space abre el panel en Angular Material.
        logger.warning("Panel no abrió con click — intentando con teclado (Space)")
        await select_locator.focus()
        await page.keyboard.press("Space")
        await option_loc.wait_for(state="visible", timeout=12_000)

    await option_loc.click()
    await page.wait_for_selector("mat-option", state="hidden", timeout=DEFAULT_TIMEOUT_MS)


async def _read_mat_error(page: Page) -> str | None:
    """Lee el primer ``mat-error`` visible en el form, si existe.

    Returns:
        Texto del error o ``None`` si no hay ninguno visible en 1 segundo.
    """
    try:
        err = page.locator(SEL_MAT_ERROR).first
        if await err.is_visible(timeout=1_000):
            return (await err.inner_text()).strip()
    except (PlaywrightTimeoutError, Exception):  # noqa: BLE001
        return None
    return None


async def _read_sunat_error(page: Page) -> str | None:
    """Lee el mensaje de error visible en el portal SUNAT, si existe.

    El form de SUNAT usa ``#divMensajeError #spanMensajeError`` con clase
    ``hidden`` cuando no hay error.

    Returns:
        Texto del error o ``None`` si no hay ninguno visible en 2 segundos.
    """
    try:
        err = page.locator(SUNAT_SEL_ERROR).first
        if await err.is_visible(timeout=2_000):
            text = (await err.inner_text()).strip()
            return text or None
    except (PlaywrightTimeoutError, Exception):  # noqa: BLE001
        return None
    return None


def _mask_ruc(ruc: str) -> str:
    """Devuelve el RUC enmascarado tipo ``20602***``."""
    if len(ruc) >= _RUC_MASK_PREFIX:
        return f"{ruc[:_RUC_MASK_PREFIX]}***"
    return "***"


async def _open_mtc_login_with_pj(page: Page) -> None:
    """Navega al login MTC y asegura el dropdown ``tipoPersona`` en JURIDICA.

    Usar solo para ``login_direct``. Para ``login_clave_sol`` no es necesario
    cambiar el dropdown — SUNAT autentica por RUC independientemente.

    Args:
        page: página del browser sobre la que operar.
    """
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(SEL_TIPO_PERSONA, state="visible", timeout=DEFAULT_TIMEOUT_MS)
    await _ensure_persona_juridica(page)


async def _open_mtc_login_clave_sol(page: Page) -> None:
    """Navega al login MTC y espera el botón Clave SOL sin tocar el dropdown.

    Para Clave SOL no hace falta seleccionar PERSONA JURIDICA — SUNAT identifica
    al usuario por RUC + clave SOL y MTC acepta el redirect como JURIDICA.

    Args:
        page: página del browser sobre la que operar.
    """
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.bring_to_front()
    await page.wait_for_selector(SEL_BTN_CLAVE_SOL, state="visible", timeout=DEFAULT_TIMEOUT_MS)


# ─────────────────────────────────────────────────────────────────
# Logins
# ─────────────────────────────────────────────────────────────────


async def login_direct(page: Page, creds: RucCredentials) -> None:
    """Realiza el login directo PERSONA JURIDICA en la Casilla MTC.

    Flujo:
        1. Navega a ``LOGIN_URL``.
        2. Asegura que ``tipoPersona = PERSONA JURIDICA``.
        3. Llena RUC, DNI del rep. legal, password.
        4. Click en ``button.btn-login`` (NO presiona Enter).
        5. Espera que la URL cambie a ``**/casilla**``.

    Args:
        page: página del browser donde realizar el login.
        creds: credenciales del RUC (debe tener ``auth_method='direct'``).

    Raises:
        LoginFailed: si las credenciales son inválidas, el portal redirige a
            SUNAT inesperadamente o la navegación al inbox no completa.
    """
    if creds.auth_method != "direct":
        raise ValueError(
            f"login_direct requiere auth_method='direct', recibido: {creds.auth_method!r}"
        )
    if not creds.dni_representante or not creds.password_casilla:
        raise ValueError(f"RUC {_mask_ruc(creds.ruc)}: faltan dni_representante/password")

    masked = _mask_ruc(creds.ruc)
    logger.info("Login DIRECT iniciado para RUC %s (empresa=%s)", masked, creds.empresa)

    # 1-2. Navegar al login MTC y asegurar PERSONA JURIDICA (helper compartido)
    await _open_mtc_login_with_pj(page)

    # 3. Esperar el campo RUC (existe solo cuando tipoPersona == PERSONA JURIDICA) y llenar
    await page.wait_for_selector(SEL_RUC, state="visible", timeout=DEFAULT_TIMEOUT_MS)
    await page.locator(SEL_RUC).fill(creds.ruc)
    await page.locator(SEL_USERNAME).fill(creds.dni_representante)
    # NO loggear el password ni su longitud — solo confirmar que se llenó
    await page.locator(SEL_PASSWORD).fill(creds.password_casilla)
    logger.debug("Form completado para RUC %s — listo para submit", masked)

    # 4. Click en btn-login (es type="button", NO submit)
    btn = page.locator(SEL_BTN_LOGIN).first
    await btn.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    await btn.click()

    # 5. Esperar la UI del inbox (header con rep legal o paginator) — el hash
    # routing de Angular no se puede matchear con wait_for_url glob estándar.
    try:
        await page.wait_for_selector(
            SEL_HEADER_REP_LEGAL,
            state="visible",
            timeout=LOGIN_NAV_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        current_url = page.url
        # Detectar si nos mandaron a SUNAT inesperadamente
        if SUNAT_HOST_FRAGMENT in current_url:
            raise LoginFailed(
                f"RUC {masked}: el portal MTC redirigió a SUNAT inesperadamente "
                f"(url={current_url}). El método 'direct' parece no estar habilitado "
                f"para esta cuenta — probar con 'clave_sol'."
            ) from exc
        # Buscar mat-error
        err_msg = await _read_mat_error(page)
        if err_msg:
            raise LoginFailed(f"RUC {masked}: login rechazado por el portal: {err_msg}") from exc
        raise LoginFailed(
            f"RUC {masked}: timeout esperando UI del inbox post-login "
            f"(url actual={current_url}). Puede ser portal lento o credenciales inválidas."
        ) from exc

    # Sanity check: la URL final debe contener "/#/casilla" (path Angular post-login)
    if "/#/casilla" not in page.url:
        raise LoginFailed(f"RUC {masked}: post-login URL inesperada: {page.url}")
    logger.info("Login DIRECT OK para RUC %s — URL=%s", masked, page.url)


async def login_clave_sol(page: Page, creds: RucCredentials) -> None:
    """Realiza login vía Clave SOL de SUNAT (single-sign-on OAuth2).

    Flujo:
        1. Navega al login MTC y selecciona PERSONA JURIDICA.
        2. Clic en "Iniciar sesión con Clave SOL" (``button.btn-clave-sol``).
        3. Espera redirect a ``api-seguridad.sunat.gob.pe``.
        4. Asegura tab RUC activo (``#btnPorRuc``).
        5. Llena ``#txtRuc``, ``#txtUsuario``, ``#txtContrasena`` con creds.
        6. NO toca ``#chkRecuerdame`` — queda OFF (no persistir sesiones).
        7. Click en ``#btnAceptar``.
        8. Espera redirect de vuelta a ``casilla.mtc.gob.pe/#/casilla``.
        9. Valida que el header del inbox MTC esté visible.

    Args:
        page: página del browser.
        creds: credenciales (``auth_method='clave_sol'``, debe tener
            ``sol_usuario`` y ``sol_clave``).

    Raises:
        ValueError: si ``auth_method != 'clave_sol'`` o faltan
            ``sol_usuario``/``sol_clave``.
        LoginFailed: si SUNAT rechaza credenciales o no hay redirect a MTC.
    """
    if creds.auth_method != "clave_sol":
        raise ValueError(
            f"login_clave_sol requiere auth_method='clave_sol', recibido: {creds.auth_method!r}"
        )
    if not creds.sol_usuario or not creds.sol_clave:
        raise ValueError(
            f"RUC {_mask_ruc(creds.ruc)}: faltan sol_usuario/sol_clave en credenciales"
        )

    masked = _mask_ruc(creds.ruc)
    logger.info("Login CLAVE SOL iniciado para RUC %s (empresa=%s)", masked, creds.empresa)

    # 1. Navegar al login MTC — NO cambiar tipo persona (Clave SOL no lo requiere)
    await _open_mtc_login_clave_sol(page)

    # 2. Click en Clave SOL
    btn_sol = page.locator(SEL_BTN_CLAVE_SOL).first
    await btn_sol.click()

    # 3. Esperar landing en SUNAT (URL contiene sunat.gob.pe)
    try:
        await page.wait_for_url(f"**{SUNAT_HOST_FRAGMENT}**", timeout=LOGIN_NAV_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise LoginFailed(
            f"RUC {masked}: timeout esperando redirect a SUNAT (url actual={page.url})"
        ) from exc

    # 4. Asegurar tab RUC activo y campo visible
    await page.wait_for_selector(SUNAT_SEL_INPUT_RUC, state="visible", timeout=DEFAULT_TIMEOUT_MS)
    tab_ruc = page.locator(SUNAT_SEL_TAB_RUC).first
    classes = (await tab_ruc.get_attribute("class")) or ""
    if "active" not in classes:
        logger.debug("Tab RUC no activo en SUNAT — clickeando para activarlo")
        await tab_ruc.click()
        await page.wait_for_selector(SUNAT_SEL_INPUT_RUC, state="visible", timeout=5_000)

    # 5. Llenar campos. NO loggear sol_clave (ni siquiera su longitud)
    sol_clave_value = (
        creds.sol_clave.get_secret_value()
        if hasattr(creds.sol_clave, "get_secret_value")
        else creds.sol_clave
    )
    await page.locator(SUNAT_SEL_INPUT_RUC).fill(creds.ruc)
    await page.locator(SUNAT_SEL_INPUT_USUARIO).fill(creds.sol_usuario)
    await page.locator(SUNAT_SEL_INPUT_PASSWORD).fill(sol_clave_value)
    logger.debug("Form SUNAT completado para RUC %s — listo para submit", masked)

    # 6. (chkRecuerdame queda OFF intencionalmente — regla del proyecto)

    # 7. Click Entrar
    await page.locator(SUNAT_SEL_BTN_SUBMIT).first.click()

    # 8. Esperar redirect de vuelta a MTC + UI del inbox
    # Usa DEFAULT_TIMEOUT_MS (60s): el render Angular post-OAuth puede ser lento.
    try:
        await page.wait_for_selector(
            SEL_HEADER_REP_LEGAL,
            state="visible",
            timeout=DEFAULT_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        current_url = page.url
        # Si seguimos en SUNAT, intentar leer el mensaje de error visible
        if SUNAT_HOST_FRAGMENT in current_url:
            err_text = await _read_sunat_error(page)
            if err_text:
                raise LoginFailed(f"RUC {masked}: SUNAT rechazó credenciales: {err_text}") from exc
            raise LoginFailed(
                f"RUC {masked}: SUNAT no completó autenticación (url={current_url})"
            ) from exc
        raise LoginFailed(
            f"RUC {masked}: timeout esperando UI MTC post-SUNAT (url={current_url})"
        ) from exc

    # 9. Sanity check final
    if "/#/casilla" not in page.url:
        raise LoginFailed(f"RUC {masked}: post-clave-sol URL inesperada: {page.url}")
    logger.info("Login CLAVE SOL OK para RUC %s — URL=%s", masked, page.url)


async def perform_login(page: Page, creds: RucCredentials) -> None:
    """Despacha al método de login según ``creds.auth_method``.

    Args:
        page: página del browser.
        creds: credenciales del RUC.

    Raises:
        ValueError: si ``auth_method`` no es ``direct`` ni ``clave_sol``.
        LoginFailed: si el login falla.
        NotImplementedError: si ``auth_method='clave_sol'`` (stub).
    """
    if creds.auth_method == "direct":
        await login_direct(page, creds)
    elif creds.auth_method == "clave_sol":
        await login_clave_sol(page, creds)
    else:
        raise ValueError(f"auth_method desconocido: {creds.auth_method!r}")


# ─────────────────────────────────────────────────────────────────
# Detección post-login
# ─────────────────────────────────────────────────────────────────


async def detect_login_summary(page: Page) -> dict[str, str | int | None]:
    """Extrae info del header y paginador post-login.

    Lee:
        * ``representante_legal`` — span del header con el nombre.
        * ``tipo_persona`` — small del header (debería decir ``PERSONA JURIDICA``).
        * ``total_notificaciones`` — total parseado del paginador.

    Si algún elemento no se encuentra, devuelve ``None`` en ese campo (no lanza).

    Args:
        page: página post-login.

    Returns:
        Diccionario con las tres claves anteriores.
    """
    summary: dict[str, str | int | None] = {
        "representante_legal": None,
        "tipo_persona": None,
        "total_notificaciones": None,
    }

    # representante legal
    try:
        rep_loc = page.locator(SEL_HEADER_REP_LEGAL).first
        if await rep_loc.is_visible(timeout=5_000):
            summary["representante_legal"] = (await rep_loc.inner_text()).strip()
    except (PlaywrightTimeoutError, Exception) as exc:  # noqa: BLE001
        logger.debug("No se detectó representante legal en header: %s", exc)

    # tipo persona
    try:
        tipo_loc = page.locator(SEL_HEADER_TIPO_PERSONA).first
        if await tipo_loc.is_visible(timeout=2_000):
            summary["tipo_persona"] = (await tipo_loc.inner_text()).strip()
    except (PlaywrightTimeoutError, Exception) as exc:  # noqa: BLE001
        logger.debug("No se detectó tipo_persona en header: %s", exc)

    # total notificaciones — el paginator carga después del header,
    # esperar explícitamente con timeout más amplio.
    try:
        pag_loc = page.locator(SEL_PAGINATOR_RANGE).first
        await pag_loc.wait_for(state="visible", timeout=15_000)
        text = (await pag_loc.inner_text()).strip()
        match = _PAGINATOR_TOTAL_RE.search(text)
        if match:
            summary["total_notificaciones"] = int(match.group(1))
        else:
            logger.debug("No se pudo parsear total del paginador: %r", text)
    except (PlaywrightTimeoutError, Exception) as exc:  # noqa: BLE001
        logger.debug("No se detectó paginador: %s", exc)

    return summary


__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "INBOX_URL_GLOB",
    "LOGIN_URL",
    "LoginFailed",
    "browser_session",
    "detect_login_summary",
    "login_clave_sol",
    "login_direct",
    "perform_login",
]


# Marca de timestamp para trazas (usado opcionalmente por callers que quieran
# nombrar archivos de tracing). No usado internamente.
def _trace_filename(ruc: str) -> str:
    """Devuelve un nombre canónico para un trace (RUC enmascarado + ts)."""
    return f"{_mask_ruc(ruc)}_{datetime.now():%Y%m%d_%H%M%S}.zip"
