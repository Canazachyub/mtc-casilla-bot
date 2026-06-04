"""Listado de notificaciones del inbox de la Casilla MTC.

Asume que la página ya está logueada (URL en ``/#/casilla``). Lista items con
su metadata, soporta paginación, devuelve dataclasses livianas para que el
orquestador decida cuáles descargar.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Selectores (verificados contra HTML real del portal)
# ─────────────────────────────────────────────────────────────────

SEL_ITEM = ".item-notificacion"
SEL_EMISOR = ".notificacion-emisor"
SEL_FECHA = ".notificacion-fecha"
SEL_ASUNTO = ".notificacion-asunto"
SEL_CATEGORIA = ".etiqueta-categoria"
SEL_ICONO_ADJUNTO = ".icono-adjunto"
SEL_PAG_RANGE = ".mat-mdc-paginator-range-label"
SEL_PAG_NEXT = ".mat-mdc-paginator-navigation-next"
SEL_PAG_PREV = ".mat-mdc-paginator-navigation-previous"
SEL_PAG_FIRST = ".mat-mdc-paginator-navigation-first"

# Detalle (post-click)
SEL_DETAIL_TITLE = "app-partial-detalle-notificacion mat-card-title"

# Regex para parsear "1 – 25 of 95" (en-dash o hyphen)
_PAG_RANGE_RE = re.compile(r"(\d+)\s*[–-]\s*(\d+)\s+of\s+(\d+)", re.IGNORECASE)

# Timeouts (ms)
_DEFAULT_INBOX_LOAD_TIMEOUT = 30_000
_DEFAULT_FIELD_TIMEOUT = 3_000
_DEFAULT_DETAIL_TIMEOUT = 15_000
_DEFAULT_PAGINATOR_TIMEOUT = 10_000

# Defensa contra loops infinitos
DEFAULT_MAX_PAGES = 20


# ─────────────────────────────────────────────────────────────────
# Modelo
# ─────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class InboxItem:
    """Metadata mínima de un item del inbox (sin cuerpo ni adjuntos descargados).

    Attributes:
        notification_id: hash determinístico de ``(ruc, asunto, fecha)``.
        ruc: RUC del usuario logueado.
        emisor: texto del emisor (versión corta de la lista).
        fecha: fecha de la notificación parseada desde ``DD/MM/YYYY``.
        asunto: asunto/título de la notificación.
        categoria: etiqueta (``Informe``, ``Cartas``, ``Notificación``, etc).
        has_adjuntos: ``True`` si el item muestra el icono de adjunto.
        page_index: página del paginator donde apareció (1-indexed).
        item_index_in_page: índice 0-based del item dentro de la página.
        raw_fecha: texto crudo de la fecha (debug).
    """

    notification_id: str
    ruc: str
    emisor: str
    fecha: date
    asunto: str
    categoria: str
    has_adjuntos: bool
    page_index: int
    item_index_in_page: int
    raw_fecha: str = ""


# ─────────────────────────────────────────────────────────────────
# Utilidades públicas
# ─────────────────────────────────────────────────────────────────


def notification_id(ruc: str, asunto: str, fecha: date) -> str:
    """Genera un ID determinístico para idempotencia.

    Args:
        ruc: RUC del usuario.
        asunto: asunto exacto de la notificación.
        fecha: fecha de la notificación.

    Returns:
        SHA1 truncado a 16 caracteres hex.
    """
    payload = f"{ruc}|{asunto.strip()}|{fecha.isoformat()}".encode()
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:16]


def _parse_fecha_dmy(text: str) -> date | None:
    """Parsea la fecha del inbox a ``date``.

    Soporta: ``DD/MM/YYYY``, ``"Hoy"`` (hoy), ``"Ayer"`` (ayer) y strings
    que contienen ``DD/MM/YYYY`` como subcadena (ej. ``"13/05/2026 19:35"``).
    Devuelve ``None`` si no matchea ningún formato.
    """
    text = (text or "").strip()
    if not text:
        return None
    lower = text.lower()
    if lower == "hoy":
        return date.today()
    if lower == "ayer":
        return date.today() - timedelta(days=1)
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        pass
    # Fallback: extraer DD/MM/YYYY de strings más largos (ej. con hora)
    m = re.search(r"\d{2}/\d{2}/\d{4}", text)
    if m:
        try:
            return datetime.strptime(m.group(), "%d/%m/%Y").date()
        except ValueError:
            pass
    return None


# ─────────────────────────────────────────────────────────────────
# Paginator helpers
# ─────────────────────────────────────────────────────────────────


async def _get_paginator_state(page: Page) -> tuple[int, int, int] | None:
    """Devuelve ``(start, end, total)`` parseando el paginator. ``None`` si no se ve."""
    try:
        loc = page.locator(SEL_PAG_RANGE).first
        await loc.wait_for(state="visible", timeout=_DEFAULT_PAGINATOR_TIMEOUT)
        text = (await loc.inner_text()).strip()
    except PlaywrightTimeoutError:
        return None
    m = _PAG_RANGE_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


async def _is_next_page_enabled(page: Page) -> bool:
    """``True`` si el botón Next del paginator NO está deshabilitado."""
    btn = page.locator(SEL_PAG_NEXT).first
    try:
        disabled = await btn.get_attribute("disabled")
    except PlaywrightTimeoutError:
        return False
    except Exception as exc:  # noqa: BLE001 — defensivo
        logger.debug("Error leyendo disabled del paginator-next: %s", exc)
        return False
    return disabled is None


# ─────────────────────────────────────────────────────────────────
# Lectura de items
# ─────────────────────────────────────────────────────────────────


async def _safe_inner_text(  # noqa: ASYNC109 — timeout es de Playwright, no asyncio
    locator,
    timeout_ms: int = _DEFAULT_FIELD_TIMEOUT,
) -> str:
    """Lee ``inner_text`` con timeout corto, devolviendo string vacío en error."""
    try:
        return (await locator.inner_text(timeout=timeout_ms)).strip()
    except PlaywrightTimeoutError:
        return ""


async def _read_items_in_current_page(
    page: Page,
    ruc: str,
    page_index: int,
) -> list[InboxItem]:
    """Lee todos los ``.item-notificacion`` visibles en la página actual."""
    items: list[InboxItem] = []
    locators = page.locator(SEL_ITEM)
    count = await locators.count()
    for i in range(count):
        item_loc = locators.nth(i)
        emisor = await _safe_inner_text(item_loc.locator(SEL_EMISOR).first)
        raw_fecha = await _safe_inner_text(item_loc.locator(SEL_FECHA).first)
        asunto = await _safe_inner_text(item_loc.locator(SEL_ASUNTO).first)
        categoria = await _safe_inner_text(
            item_loc.locator(SEL_CATEGORIA).first,
        )
        has_adjunto = await item_loc.locator(SEL_ICONO_ADJUNTO).count() > 0
        fecha_parsed = _parse_fecha_dmy(raw_fecha)
        if fecha_parsed is None:
            logger.warning(
                "FECHA NO PARSEADA: %r (item %d pág %d asunto=%r) "
                "— el item será descartado con cualquier --since. "
                "Revisar _parse_fecha_dmy si este formato es nuevo.",
                raw_fecha, i, page_index, asunto[:50],
            )
        fecha = fecha_parsed or date.min  # date.min = año 1 → nunca pasa filtro since=today
        logger.debug(
            "Item %d pág %d: raw_fecha=%r → %s | %s", i, page_index, raw_fecha, fecha, asunto[:40]
        )
        nid = notification_id(ruc, asunto, fecha)
        items.append(
            InboxItem(
                notification_id=nid,
                ruc=ruc,
                emisor=emisor,
                fecha=fecha,
                asunto=asunto,
                categoria=categoria,
                has_adjuntos=has_adjunto,
                page_index=page_index,
                item_index_in_page=i,
                raw_fecha=raw_fecha,
            )
        )
    return items


# ─────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────


async def _wait_paginator_changed(
    page: Page,
    pag_before: tuple[int, int, int] | None,
    current_page_index: int,
    *,
    max_wait_s: float = 8.0,
    poll_s: float = 0.1,
) -> None:
    """Espera que el label del paginator cambie su rango de inicio.

    Angular actualiza el DOM de forma asíncrona después del click en Next.
    ``networkidle`` dispara antes de que los nuevos items rendericen, lo que
    causa que se lean los items viejos de la página anterior.

    Esperamos que el campo "start" del paginator (ej. ``1`` → ``26``) cambie,
    lo cual es la señal definitiva de que los nuevos items ya están en el DOM.
    Si no hay paginator visible o ya cambió, retorna de inmediato.

    Args:
        page: Page del inbox.
        pag_before: resultado de ``_get_paginator_state`` justo antes del click.
        current_page_index: número de página (para logging).
        max_wait_s: tiempo máximo de espera en segundos.
        poll_s: intervalo entre lecturas del paginator.
    """
    import asyncio as _asyncio

    if pag_before is None:
        # Sin paginator visible: fallback al networkidle original
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=int(_DEFAULT_PAGINATOR_TIMEOUT)
            )
        except PlaywrightTimeoutError:
            pass
        return

    start_before = pag_before[0]
    iterations = int(max_wait_s / poll_s)
    for _ in range(iterations):
        await _asyncio.sleep(poll_s)
        pag_now = await _get_paginator_state(page)
        if pag_now and pag_now[0] != start_before:
            logger.debug(
                "Paginator cambió: %d–%d → %d–%d (pág %d→%d)",
                pag_before[0], pag_before[1],
                pag_now[0], pag_now[1],
                current_page_index, current_page_index + 1,
            )
            return
    logger.warning(
        "Paginator no cambió tras %.1fs (pág %d, start=%d) — "
        "posible página duplicada o portal lento",
        max_wait_s, current_page_index, start_before,
    )


async def list_inbox(
    page: Page,
    ruc: str,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[InboxItem]:
    """Lista las notificaciones del inbox actual.

    Args:
        page: Page logueada en ``/#/casilla``.
        ruc: del usuario actual (para generar IDs).
        since: filtra items con ``fecha < since`` (opcional).
        until: filtra items con ``fecha > until`` (opcional).
        limit: máximo de items a recolectar (``None`` = todos).
        max_pages: tope defensivo de páginas a recorrer.

    Returns:
        Lista de ``InboxItem`` ordenada como aparece en el portal (más reciente primero).
    """
    await page.wait_for_selector(
        SEL_ITEM,
        state="visible",
        timeout=_DEFAULT_INBOX_LOAD_TIMEOUT,
    )

    pag = await _get_paginator_state(page)
    if pag is not None:
        logger.info("Inbox paginator: %d–%d of %d", *pag)

    all_items: list[InboxItem] = []
    seen_ids: set[str] = set()
    page_index = 1
    while page_index <= max_pages:
        page_items = await _read_items_in_current_page(page, ruc, page_index)
        for it in page_items:
            if since and it.fecha < since:
                if it.fecha == date.min:
                    logger.warning(
                        "Item DESCARTADO por fecha no parseada (raw=%r, asunto=%r, pág %d) "
                        "— puede ser una notificación real que se está perdiendo.",
                        it.raw_fecha, it.asunto[:50], it.page_index,
                    )
                else:
                    logger.debug(
                        "Filtro since: %s < %s — %s", it.fecha, since, it.asunto[:40]
                    )
                continue
            if until and it.fecha > until:
                continue
            if it.notification_id in seen_ids:
                logger.debug("Dedup inbox: %s ya visto (pág %d)", it.notification_id, page_index)
                continue
            seen_ids.add(it.notification_id)
            all_items.append(it)
            if limit and len(all_items) >= limit:
                logger.info("Límite de %d items alcanzado", limit)
                return all_items

        if not await _is_next_page_enabled(page):
            break

        # Early termination: si TODOS los items de esta página son anteriores a
        # `since`, el inbox (orden desc) no tendrá más items relevantes.
        if since and page_items and all(it.fecha < since for it in page_items):
            logger.debug("Early stop: pág %d toda anterior a %s", page_index, since)
            break

        pag_before = await _get_paginator_state(page)
        await page.locator(SEL_PAG_NEXT).first.click()
        await _wait_paginator_changed(page, pag_before, page_index)
        page_index += 1

    logger.info("list_inbox recolectó %d items en %d página(s)", len(all_items), page_index)
    return all_items


async def _navigate_to_page(page: Page, target_page: int) -> None:
    """Navega al paginator hasta la página ``target_page`` (1-indexed).

    Primero va a la página 1 usando el botón "first" (si existe) o con Previous
    repetido, luego avanza con Next hasta llegar a ``target_page``.
    """
    if target_page == 1:
        # Intentar botón "first page" (|<)
        navigated = False
        first_btn = page.locator(SEL_PAG_FIRST).first
        try:
            disabled = await first_btn.get_attribute("disabled", timeout=1000)
            if disabled is None:
                pag_before = await _get_paginator_state(page)
                await first_btn.click()
                await _wait_paginator_changed(page, pag_before, 1)
                navigated = True
        except PlaywrightTimeoutError:
            pass

        if not navigated:
            # Fallback: clic en Previous (<) hasta que esté deshabilitado (= página 1)
            for _ in range(50):
                prev_btn = page.locator(SEL_PAG_PREV).first
                try:
                    disabled = await prev_btn.get_attribute("disabled", timeout=1000)
                except PlaywrightTimeoutError:
                    break
                if disabled is not None:
                    break  # prev deshabilitado → ya estamos en página 1
                pag_before = await _get_paginator_state(page)
                await prev_btn.click()
                await _wait_paginator_changed(page, pag_before, 1)
        return

    # Ir a página 1 vía "first" o Previous repetido
    first_btn = page.locator(SEL_PAG_FIRST).first
    try:
        disabled = await first_btn.get_attribute("disabled", timeout=2000)
        if disabled is None:
            await first_btn.click()
            await page.wait_for_load_state("networkidle", timeout=_DEFAULT_PAGINATOR_TIMEOUT)
    except PlaywrightTimeoutError:
        # Sin botón "first": retroceder hasta que Previous esté deshabilitado
        for _ in range(50):
            prev_btn = page.locator(SEL_PAG_PREV).first
            try:
                disabled = await prev_btn.get_attribute("disabled", timeout=1000)
            except PlaywrightTimeoutError:
                break
            if disabled is not None:
                break
            await prev_btn.click()
            await page.wait_for_load_state("networkidle", timeout=_DEFAULT_PAGINATOR_TIMEOUT)

    # Avanzar hasta target_page
    for _ in range(target_page - 1):
        await page.locator(SEL_PAG_NEXT).first.click()
        with contextlib.suppress(PlaywrightTimeoutError):
            await page.wait_for_load_state("networkidle", timeout=_DEFAULT_PAGINATOR_TIMEOUT)


async def click_item(page: Page, item: InboxItem) -> None:
    """Hace clic en el ``item-notificacion`` y espera que cargue el detalle.

    Navega a la página correcta del paginator antes de hacer click. Usa un
    fragmento único del asunto para encontrar el item exacto en el DOM, en vez
    de depender del índice de posición que puede cambiar tras la navegación.

    Args:
        page: Page con la lista del inbox visible.
        item: ``InboxItem`` previamente devuelto por ``list_inbox``.
    """
    import re as _re
    import asyncio as _asyncio

    await _navigate_to_page(page, item.page_index)

    # Esperar que los items estén visibles Y que la fecha del item aparezca en el DOM.
    # En modo headless, el paginator cambia antes de que Angular re-renderice los items,
    # por eso esperamos explícitamente que raw_fecha esté presente en los items.
    await page.wait_for_selector(SEL_ITEM, state="visible", timeout=_DEFAULT_INBOX_LOAD_TIMEOUT)
    for _ in range(60):  # hasta 6 s para que Angular renderice los items correctos
        if await page.locator(SEL_ITEM).filter(has_text=item.raw_fecha).count() > 0:
            break
        await _asyncio.sleep(0.1)
    else:
        logger.warning(
            "click_item: la fecha '%s' no apareció en los items tras 6 s — "
            "posible página incorrecta. Paginator: %s",
            item.raw_fecha, await _get_paginator_state(page),
        )

    # Extraer el número único de la notificación (ej: "001265-CR-2026") del asunto.
    # Para items sin número (ej: "Notificacion Electronica MTC."), usar la fecha como
    # discriminador único para evitar clicks en el item incorrecto.
    _m = _re.search(r'\d{5,6}-[A-Z]{2}-\d{4}', item.asunto)
    unique_text = _m.group(0) if _m else item.asunto[:30].strip()

    # Polling hasta 4 s buscando el item por asunto + fecha exacta del portal.
    target = None
    for _ in range(40):
        narrowed = page.locator(SEL_ITEM).filter(has_text=unique_text).filter(
            has_text=item.raw_fecha
        )
        if await narrowed.count() > 0:
            target = narrowed.first
            break
        await _asyncio.sleep(0.1)

    if target is None:
        logger.error(
            "click_item: no encontró '%s' tras 4 s de espera en página %d. "
            "Paginator actual: %s",
            unique_text, item.page_index, await _get_paginator_state(page),
        )
        raise RuntimeError(f"Notificación no encontrada en el DOM: {unique_text}")

    await target.scroll_into_view_if_needed()
    await target.click()

    # Esperar que el título del detalle contenga el texto único de ESTE item.
    # No alcanza con `wait_for_selector(SEL_DETAIL_TITLE, "visible")` porque cuando
    # ya hay un detalle abierto (item anterior), el título viejo sigue visible y la
    # espera retorna inmediatamente — el downloader leería los adjuntos equivocados.
    detail_with_text = page.locator(SEL_DETAIL_TITLE).filter(has_text=unique_text)
    try:
        await detail_with_text.wait_for(state="visible", timeout=_DEFAULT_DETAIL_TIMEOUT)
    except Exception:
        # Fallback: al menos verificar que hay algún título visible
        await page.wait_for_selector(SEL_DETAIL_TITLE, state="visible", timeout=5000)


__all__ = [
    "DEFAULT_MAX_PAGES",
    "InboxItem",
    "click_item",
    "list_inbox",
    "notification_id",
]
