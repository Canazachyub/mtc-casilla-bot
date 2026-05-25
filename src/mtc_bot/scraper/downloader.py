"""Descarga de PDFs adjuntos del detalle de una notificación.

Estrategia: el portal MTC abre los PDFs de dos formas distintas:

* **PDFs chicos**: dialog/modal con visor embebido (URL ``blob:``).
* **PDFs grandes**: nueva pestaña con URL tipo
  ``https://services.sutran.gob.pe/ServRefirmaGeneral/showfile.aspx?ruta=<base64>``.

Para cubrir ambos casos, instalamos un listener ``page.on("response", ...)``
que captura toda response cuyo ``Content-Type`` sea ``application/pdf`` o cuya
URL contenga ``.pdf`` / ``showfile.aspx``. Esto evita tener que parsear el DOM
del modal o seguir popups.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
from playwright.async_api import BrowserContext, Page, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Parser de fecha en español (formato del detalle MTC)
# ─────────────────────────────────────────────────────────────────

_MESES_ES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Matchea: "jueves, 14 mayo 2026, 2:18:47 p. m."
_FECHA_ES_LONG_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_MESES_ES) + r")\s+(\d{4})",
    re.IGNORECASE,
)


def parse_fecha_detail(text: str) -> date | None:
    """Parsea la fecha larga en español del detalle MTC.

    Ejemplos soportados:
        ``"jueves, 14 mayo 2026, 2:18:47 p. m."`` → ``date(2026, 5, 14)``
        ``"Fecha: miércoles, 8 mayo 2026, 10:05:00 a. m."`` → ``date(2026, 5, 8)``

    Returns:
        ``date`` si pudo parsear, ``None`` si no matcheó.
    """
    m = _FECHA_ES_LONG_RE.search(text or "")
    if not m:
        return None
    try:
        day = int(m.group(1))
        mes = _MESES_ES[m.group(2).lower()]
        year = int(m.group(3))
        return date(year, mes, day)
    except (ValueError, KeyError):
        return None


# ─────────────────────────────────────────────────────────────────
# Selectores del detalle
# ─────────────────────────────────────────────────────────────────

SEL_DETAIL_TITLE = "app-partial-detalle-notificacion mat-card-title"
SEL_DETAIL_CATEGORIA = "app-partial-detalle-notificacion .etiqueta-categoria"
SEL_DETAIL_SUBTITLES = "app-partial-detalle-notificacion mat-card-subtitle"
SEL_DETAIL_BODY = "app-partial-detalle-notificacion mat-card-content > div"
SEL_DETAIL_ATT_NAME = "ul.mailbox-attachments li a.mailbox-attachment-name"
SEL_DETAIL_ATT_FILENAME = "ul.mailbox-attachments li a.mailbox-attachment-name > div"

# Regex para identificar URLs de PDF
PDF_URL_RE = re.compile(r"\.pdf|showfile\.aspx", re.IGNORECASE)

# HTTP status: solo capturamos responses con 200 OK
_HTTP_OK = 200

# Timeouts
_DEFAULT_FIELD_TIMEOUT_MS = 5_000
_DEFAULT_BODY_TIMEOUT_MS = 5_000
_DEFAULT_POPUP_WAIT_MS = 3_000
_DEFAULT_POPUP_LOAD_MS = 15_000
_DEFAULT_PDF_TIMEOUT_MS = 30_000
_DEFAULT_NO_POPUP_GRACE_S = 2.0
_POLL_MS = 500


# ─────────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DetailMetadata:
    """Metadata extraída del panel de detalle.

    Attributes:
        emisor: emisor (versión completa, del ``mat-card-title``).
        categoria: etiqueta de la categoría.
        de: línea ``De:`` del subtítulo (sin el prefijo).
        fecha_full: línea ``Fecha:`` cruda (ej. "jueves, 14 mayo 2026, 2:18:47 p. m.").
        fecha: fecha parseada de ``fecha_full`` (``None`` si no pudo parsear).
        asunto: línea ``Asunto:`` cruda.
        cuerpo: texto del cuerpo del mensaje.
    """

    emisor: str = ""
    categoria: str = ""
    de: str = ""
    fecha_full: str = ""
    fecha: date | None = field(default=None)
    asunto: str = ""
    cuerpo: str = ""


@dataclass(slots=True)
class AttachmentDownload:
    """Resultado de descarga de un adjunto.

    Attributes:
        filename: nombre final guardado.
        path: ruta absoluta del PDF guardado.
        size_bytes: tamaño del archivo en disco.
        source_url: URL desde la que se capturó la response.
    """

    filename: str
    path: Path
    size_bytes: int
    source_url: str


# ─────────────────────────────────────────────────────────────────
# Lectura de metadata
# ─────────────────────────────────────────────────────────────────


async def _safe_inner_text(  # noqa: ASYNC109 — timeout es de Playwright, no asyncio
    locator,
    timeout_ms: int = _DEFAULT_FIELD_TIMEOUT_MS,
) -> str:
    """``inner_text`` defensivo: devuelve string vacío en timeout."""
    try:
        return (await locator.inner_text(timeout=timeout_ms)).strip()
    except PlaywrightTimeoutError:
        return ""


def _strip_label(text: str) -> str:
    """Quita el prefijo ``Algo:`` y devuelve solo el valor."""
    return text.split(":", 1)[1].strip() if ":" in text else text


async def extract_detail_metadata(page: Page) -> DetailMetadata:
    """Lee la metadata del panel de detalle ya cargado.

    Args:
        page: Page con el componente ``app-partial-detalle-notificacion`` visible.

    Returns:
        ``DetailMetadata`` con los campos disponibles. Los que no se encuentran
        quedan como string vacío (no lanza excepción).
    """
    md = DetailMetadata()
    md.emisor = await _safe_inner_text(page.locator(SEL_DETAIL_TITLE).first)
    md.categoria = await _safe_inner_text(
        page.locator(SEL_DETAIL_CATEGORIA).first,
        timeout_ms=2_000,
    )

    # Subtítulos: 3 líneas (De, Fecha, Asunto)
    try:
        subs_loc = page.locator(SEL_DETAIL_SUBTITLES)
        n = await subs_loc.count()
        for i in range(n):
            text = (await subs_loc.nth(i).inner_text()).strip()
            low = text.lower()
            if low.startswith("de:"):
                md.de = _strip_label(text)
            elif low.startswith("fecha:"):
                md.fecha_full = _strip_label(text)
                md.fecha = parse_fecha_detail(md.fecha_full)
                if md.fecha is None:
                    logger.warning(
                        "Fecha del detalle no parseada: %r — revisar parse_fecha_detail",
                        md.fecha_full,
                    )
                else:
                    logger.debug("Fecha detalle parseada: %s (raw=%r)", md.fecha, md.fecha_full)
            elif low.startswith("asunto:"):
                md.asunto = _strip_label(text)
    except PlaywrightTimeoutError as exc:
        logger.debug("Timeout leyendo subtitles: %s", exc)
    except Exception as exc:  # noqa: BLE001 — defensivo
        logger.debug("Error leyendo subtitles: %s", exc)

    md.cuerpo = await _safe_inner_text(
        page.locator(SEL_DETAIL_BODY).first,
        timeout_ms=_DEFAULT_BODY_TIMEOUT_MS,
    )
    return md


async def list_detail_attachments(page: Page) -> list[str]:
    """Devuelve los nombres de archivo (filenames) de los adjuntos visibles.

    Args:
        page: Page con el detalle abierto.

    Returns:
        Lista de strings con los filenames tal como aparecen en el portal.
    """
    names: list[str] = []
    locs = page.locator(SEL_DETAIL_ATT_FILENAME)
    n = await locs.count()
    for i in range(n):
        names.append((await locs.nth(i).inner_text()).strip())
    return names


# ─────────────────────────────────────────────────────────────────
# Captura de PDFs vía page.on("response", ...)
# ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _capture_pdf_responses(
    context: BrowserContext,
) -> AsyncIterator[list[tuple[str, bytes]]]:
    """Captura responses PDF de TODAS las páginas del context.

    Engancha el listener al ``BrowserContext`` (no a una ``Page`` específica)
    para que también se capturen los PDFs que se abren en pestañas/popups
    nuevas — caso típico cuando el portal MTC abre PDFs grandes en una
    nueva pestaña con URL ``services.sutran.gob.pe/.../showfile.aspx``.

    Yields:
        Lista (mutable) de tuplas ``(url, body)``. Se va llenando mientras
        dura el contexto.
    """
    captured: list[tuple[str, bytes]] = []

    # Cola asíncrona para serializar la lectura de bodies (context.on emite sync)
    queue: asyncio.Queue[Response] = asyncio.Queue()

    def _on_response(response: Response) -> None:
        url = response.url
        ct = (response.headers.get("content-type") or "").lower()
        if "application/pdf" in ct or PDF_URL_RE.search(url):
            queue.put_nowait(response)

    async def _drain() -> None:
        while True:
            response = await queue.get()
            if response is _SENTINEL:  # type: ignore[comparison-overlap]
                return
            try:
                if response.status != _HTTP_OK:
                    continue
                body = await response.body()
                captured.append((response.url, body))
                logger.debug("PDF capturado: %s (%d bytes)", response.url, len(body))
            except Exception as exc:  # noqa: BLE001 — no debe romper el pipeline
                logger.debug("No se pudo leer body de %s: %s", response.url, exc)

    context.on("response", _on_response)
    drain_task = asyncio.create_task(_drain())
    try:
        yield captured
    finally:
        context.remove_listener("response", _on_response)
        await queue.put(_SENTINEL)  # type: ignore[arg-type]
        try:
            await asyncio.wait_for(drain_task, timeout=5)
        except TimeoutError:
            drain_task.cancel()


# Sentinela única para parar el drain
_SENTINEL: object = object()


# ─────────────────────────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────────────────────────


_WINDOW_OPEN_PATCH_JS = """
() => {
  if (window.__mtcBotPatched) return;
  window.__mtcBotPatched = true;
  window.__mtcBotCapturedUrls = [];
  const origOpen = window.open;
  window.open = function (url, name, features) {
    try {
      if (url) window.__mtcBotCapturedUrls.push(String(url));
    } catch (e) { /* no-op */ }
    // Bloqueamos el popup real para evitar overhead: el caller descarga via httpx.
    return { closed: true, close: () => {}, focus: () => {}, location: { href: url } };
  };
  // Compat: si Angular usa anchor.click() con target=_blank, también lo capturamos
  document.addEventListener('click', (ev) => {
    const a = ev.target && ev.target.closest && ev.target.closest('a[target="_blank"][href]');
    if (a) {
      try { window.__mtcBotCapturedUrls.push(String(a.href)); } catch (e) { /* no-op */ }
    }
  }, true);
};
"""


async def _install_window_open_interceptor(page: Page) -> None:
    """Inyecta un monkey-patch de ``window.open`` para capturar URLs de popups.

    El portal MTC abre PDFs grandes con ``window.open(url)`` desde Angular.
    Interceptamos la llamada para capturar la URL sin abrir el popup real
    (más rápido y robusto que ``expect_page`` con timing variable).
    """
    await page.evaluate(_WINDOW_OPEN_PATCH_JS)


async def _click_attachment_with_popup_fallback(
    context: BrowserContext,
    page: Page,
    locator,
) -> str | None:
    """Hace click en el adjunto y captura la URL del popup vía interceptor JS.

    Args:
        context: BrowserContext (no usado actualmente, kept for API compat).
        page: Page del detalle.
        locator: locator del enlace clickeable del adjunto.

    Returns:
        URL del popup si ``window.open`` fue invocado, ``None`` si abrió en
        modal embebido. Cuando devuelve URL, el caller descarga vía httpx.
    """
    _ = context  # kept for API compat
    # Asegurar que el patch está instalado (idempotente)
    await _install_window_open_interceptor(page)

    # Snapshot del array de URLs capturadas antes del click
    initial_count: int = await page.evaluate(
        "() => (window.__mtcBotCapturedUrls && window.__mtcBotCapturedUrls.length) || 0"
    )

    await locator.click()

    # Polling corto: window.open se llama de forma síncrona en el handler del click,
    # pero Angular puede usar setTimeout/Promise.then antes del open. 3s es suficiente.
    elapsed_ms = 0
    while elapsed_ms < _DEFAULT_POPUP_WAIT_MS:
        try:
            current_count: int = await page.evaluate(
                "() => (window.__mtcBotCapturedUrls && window.__mtcBotCapturedUrls.length) || 0"
            )
        except Exception as exc:  # noqa: BLE001 — defensivo (page puede estar navegando)
            logger.debug("Error leyendo __mtcBotCapturedUrls: %s", exc)
            current_count = initial_count
        if current_count > initial_count:
            url = await page.evaluate(
                "() => window.__mtcBotCapturedUrls[window.__mtcBotCapturedUrls.length - 1]"
            )
            if url and isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
            logger.debug("URL capturada pero no http/https: %r", url)
            return None
        await asyncio.sleep(0.2)
        elapsed_ms += 200

    # No hubo window.open → modal embebido. Damos un grace para que cargue.
    await asyncio.sleep(_DEFAULT_NO_POPUP_GRACE_S)
    return None


async def _download_url_with_context_cookies(
    context: BrowserContext,
    url: str,
    timeout: float = 60.0,  # noqa: ASYNC109 — timeout es de httpx, no asyncio
) -> bytes:
    """Descarga ``url`` con un cliente httpx usando las cookies del browser context.

    Útil para PDFs que abren en popup: en vez de depender de interceptar la
    response, capturamos la URL del popup y bajamos directo. Más rápido y
    confiable.

    Args:
        context: BrowserContext con cookies de sesión válidas.
        url: URL absoluta del recurso a descargar.
        timeout: timeout total en segundos.

    Returns:
        Body del response como ``bytes``.

    Raises:
        httpx.HTTPError: si la descarga falla.
    """
    cookies = await context.cookies()
    cookie_jar = httpx.Cookies()
    for c in cookies:
        cookie_jar.set(
            name=c.get("name", ""),
            value=c.get("value", ""),
            domain=c.get("domain", "") or "",
            path=c.get("path", "/") or "/",
        )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }
    async with httpx.AsyncClient(
        cookies=cookie_jar,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _try_close_pdf_modal(page: Page) -> None:
    """Intenta cerrar el modal del visor PDF si quedó abierto."""
    try:
        close_btn = page.get_by_role("button", name="Cerrar").first
        if await close_btn.is_visible(timeout=1_000):
            await close_btn.click()
    except PlaywrightTimeoutError:
        return
    except Exception as exc:  # noqa: BLE001 — modal no presente o no clickeable
        logger.debug("No se pudo cerrar modal PDF: %s", exc)


async def download_attachments(
    context: BrowserContext,
    page: Page,
    dest_dir: Path,
    timeout_per_pdf_ms: int = _DEFAULT_PDF_TIMEOUT_MS,
) -> list[AttachmentDownload]:
    """Hace clic en cada adjunto y captura los PDFs vía intercept de responses.

    Args:
        context: BrowserContext (para abrir/cerrar popups).
        page: Page con el detalle abierto.
        dest_dir: directorio destino para los PDFs.
        timeout_per_pdf_ms: tiempo máximo a esperar después de cada clic.

    Returns:
        Lista de ``AttachmentDownload`` con paths locales. Si un adjunto falla
        en capturarse, se loggea WARNING y se continúa con los siguientes.
    """
    # mkdir es sync local (rápido, no bloquea de forma significativa).
    dest_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

    filenames = await list_detail_attachments(page)
    if not filenames:
        logger.info("No se detectaron adjuntos en el detalle")
        return []

    logger.info("Descargando %d adjunto(s) a %s", len(filenames), dest_dir)
    results: list[AttachmentDownload] = []

    async with _capture_pdf_responses(context) as captured:
        att_locs = page.locator(SEL_DETAIL_ATT_NAME)
        n = await att_locs.count()
        for i in range(n):
            filename = filenames[i] if i < len(filenames) else f"adjunto_{i}.pdf"
            initial_count = len(captured)

            popup_url = await _click_attachment_with_popup_fallback(
                context,
                page,
                att_locs.nth(i),
            )

            url: str | None = None
            body: bytes | None = None

            # Caso 1: si hubo popup con URL útil, descargar directo via httpx
            # (más confiable que esperar el intercept de responses).
            if popup_url:
                logger.debug("Descarga vía httpx desde popup URL: %s", popup_url)
                try:
                    body = await _download_url_with_context_cookies(context, popup_url)
                    url = popup_url
                except httpx.HTTPError as exc:
                    logger.warning("Descarga httpx falló para %s: %s", filename, exc)

            # Caso 2: fallback al intercept de responses (PDFs en modal embed)
            if body is None:
                elapsed = 0
                while elapsed < timeout_per_pdf_ms and len(captured) <= initial_count:
                    await asyncio.sleep(_POLL_MS / 1000)
                    elapsed += _POLL_MS
                new_responses = captured[initial_count:]
                if new_responses:
                    url, body = new_responses[-1]

            if body is None:
                logger.warning("No se capturó PDF para %s", filename)
                await _try_close_pdf_modal(page)
                continue

            target = dest_dir / filename
            if not target.suffix:
                target = target.with_suffix(".pdf")
            target.write_bytes(body)
            size = target.stat().st_size
            if size == 0:
                target.unlink(missing_ok=True)
                logger.warning("PDF vacío descartado: %s", filename)
                await _try_close_pdf_modal(page)
                continue
            results.append(
                AttachmentDownload(
                    filename=target.name,
                    path=target,
                    size_bytes=size,
                    source_url=url or "",
                )
            )
            logger.info("PDF guardado: %s (%d bytes)", target.name, size)

            await _try_close_pdf_modal(page)

    return results


__all__ = [
    "AttachmentDownload",
    "DetailMetadata",
    "PDF_URL_RE",
    "download_attachments",
    "extract_detail_metadata",
    "list_detail_attachments",
]
