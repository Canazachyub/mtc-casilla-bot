#!/usr/bin/env python3
"""
scripts/debug_scraper_ui.py — GUI de depuración del scraper MTC.

Permite verificar el pipeline día a día:
  · Seleccionar una o varias casillas (RUCs)
  · Elegir rango de fechas (por defecto: desde 13/05/2026 hasta hoy)
  · Ver logs en tiempo real con color por nivel
  · Inspeccionar qué notificaciones aparecen y qué PDFs se descargaron
  · Capturas de pantalla automáticas en cada paso clave

Uso:
    uv run python scripts/debug_scraper_ui.py

Log + screenshots se guardan en:
    data/debug_logs/YYYY-MM-DD/RUC/
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import tkinter as tk
from tkinter import messagebox, ttk

# ── Tema Catppuccin Mocha ─────────────────────────────────────────────────────
_BG      = "#1e1e2e"
_SURF    = "#313244"
_SURF2   = "#45475a"
_FG      = "#cdd6f4"
_SUBTEXT = "#a6adc8"
_PRIMARY = "#89b4fa"
_GREEN   = "#a6e3a1"
_YELLOW  = "#f9e2af"
_RED     = "#f38ba8"
_PURPLE  = "#cba6f7"

# ── Custom log levels ─────────────────────────────────────────────────────────
_STEP_LV  = 25   # entre INFO(20) y WARNING(30)
_PHOTO_LV = 15   # entre DEBUG(10) y INFO(20)
logging.addLevelName(_STEP_LV,  "STEP")
logging.addLevelName(_PHOTO_LV, "PHOTO")

def _step_fn(self: logging.Logger, msg: str, *a: Any, **kw: Any) -> None:
    if self.isEnabledFor(_STEP_LV):
        self._log(_STEP_LV, msg, a, **kw)

def _photo_fn(self: logging.Logger, msg: str, *a: Any, **kw: Any) -> None:
    if self.isEnabledFor(_PHOTO_LV):
        self._log(_PHOTO_LV, msg, a, **kw)

logging.Logger.step  = _step_fn   # type: ignore[attr-defined]
logging.Logger.photo = _photo_fn  # type: ignore[attr-defined]

_LOG_COLORS: dict[str, str] = {
    "DEBUG":    _SUBTEXT,
    "PHOTO":    _PURPLE,
    "INFO":     _FG,
    "STEP":     _PRIMARY,
    "WARNING":  _YELLOW,
    "ERROR":    _RED,
    "CRITICAL": _RED,
}


# ── Logging handler → queue ───────────────────────────────────────────────────
class _QueueHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[tuple[str, str]]") -> None:
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait((record.levelname, self.format(record)))
        except Exception:
            self.handleError(record)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _slug(text: str) -> str:
    """Convierte texto a nombre de carpeta seguro (sin espacios ni caracteres raros)."""
    return re.sub(r"[^A-Za-z0-9]", "_", text)[:20].strip("_")


def _pick_date(root: tk.Tk, var: tk.StringVar) -> None:
    """Abre un popup con calendario para seleccionar una fecha y actualiza `var`."""
    try:
        from tkcalendar import Calendar
    except ImportError:
        messagebox.showinfo(
            "tkcalendar no instalado",
            "Ejecutá: uv sync --extra dev",
        )
        return

    popup = tk.Toplevel(root)
    popup.title("Seleccionar fecha")
    popup.configure(bg=_BG)
    popup.resizable(False, False)

    try:
        cur = date.fromisoformat(var.get().strip())
    except ValueError:
        cur = date.today()

    cal = Calendar(
        popup,
        selectmode="day",
        year=cur.year, month=cur.month, day=cur.day,
        date_pattern="yyyy-mm-dd",
        background=_SURF,
        foreground=_FG,
        selectbackground=_PRIMARY,
        selectforeground=_BG,
        headersbackground=_BG,
        headersforeground=_PRIMARY,
        normalbackground=_SURF,
        normalforeground=_FG,
        weekendbackground=_SURF,
        weekendforeground=_YELLOW,
        othermonthbackground=_SURF2,
        othermonthforeground=_SUBTEXT,
        bordercolor=_SURF2,
        font=("Consolas", 9),
    )
    cal.pack(padx=10, pady=10)

    def _ok() -> None:
        var.set(cal.get_date())
        popup.destroy()

    btnf = tk.Frame(popup, bg=_BG)
    btnf.pack(pady=(0, 10))
    tk.Button(
        btnf, text="Aceptar", bg=_PRIMARY, fg=_BG,
        font=("Consolas", 9, "bold"), relief=tk.FLAT, bd=0, padx=14,
        command=_ok,
    ).pack(side=tk.LEFT, padx=4)
    tk.Button(
        btnf, text="Cancelar", bg=_SURF2, fg=_FG,
        font=("Consolas", 8), relief=tk.FLAT, bd=0, padx=10,
        command=popup.destroy,
    ).pack(side=tk.LEFT, padx=4)

    popup.transient(root)
    popup.grab_set()
    popup.wait_window()


async def _screenshot(page: Any, path: Path) -> None:
    """Captura de pantalla silenciosa — nunca aborta el pipeline."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
    except Exception as exc:
        logging.getLogger("debug_scraper").debug(
            "Screenshot falló (%s): %s", path.name, exc
        )


# ── Async scraping session ────────────────────────────────────────────────────
class _ScrapeSession:
    """Corre el pipeline de scraping en un hilo de fondo."""

    def __init__(
        self,
        creds_list: list[Any],
        since: date,
        until: date,
        log_q: "queue.Queue[tuple[str, str]]",
        res_q: "queue.Queue[tuple[str, Any]]",
        headed: bool,
        dry_run: bool,
    ) -> None:
        self.creds_list = creds_list
        self.since      = since
        self.until      = until
        self.log_q      = log_q
        self.res_q      = res_q
        self.headed     = headed
        self.dry_run    = dry_run
        self._stop      = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=lambda: asyncio.run(self._run_all()),
            daemon=True, name="mtc-debug",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    async def _run_all(self) -> None:
        lg = logging.getLogger("debug_scraper")
        # Timestamp único para esta ejecución — todas las casillas de un run comparten carpeta raíz
        self._run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        n = len(self.creds_list)
        for i, creds in enumerate(self.creds_list):
            if self._stop.is_set():
                lg.warning("Sesión detenida por el usuario.")
                break
            self.res_q.put(("progress", (i, n, creds.empresa)))
            await self._run_one(lg, creds)
        self.res_q.put(("progress", (n, n, "Listo")))
        self.res_q.put(("done", None))

    async def _run_one(self, lg: logging.Logger, creds: Any) -> None:
        from mtc_bot.scraper.login import LoginFailed, browser_session, perform_login
        from mtc_bot.scraper.inbox import (
            click_item,
            _get_paginator_state,
            _is_next_page_enabled,
            _read_items_in_current_page,
            DEFAULT_MAX_PAGES,
            SEL_ITEM,
            SEL_PAG_NEXT,
        )
        from mtc_bot.scraper.downloader import (
            download_attachments,
            extract_detail_metadata,
            list_detail_attachments,
        )
        from mtc_bot.pdf_pipeline import classify_pdfs

        # ── Estructura de carpetas ────────────────────────────────────────
        # data/debug_logs/
        #   └── YYYYMMDD_HHMMSS/          ← timestamp del run (único por ejecución)
        #       └── EMPRESA__RUC/         ← carpeta por casilla
        #           ├── 00_sesion.txt     ← metadata legible
        #           ├── debug.log         ← log completo
        #           ├── 01_login_ok.png
        #           ├── 02_inbox_pag01.png
        #           ├── 02_inbox_pag02.png
        #           ├── 03_01_detalle.png
        #           ├── 03_01_adjuntos.png
        #           └── ...
        shot_dir = (
            _ROOT / "data" / "debug_logs"
            / getattr(self, "_run_ts", datetime.now().strftime("%Y%m%d_%H%M%S"))
            / f"{_slug(creds.empresa)}__{creds.ruc}"
        )
        shot_dir.mkdir(parents=True, exist_ok=True)
        dl_dir = _ROOT / "data" / "debug_downloads" / creds.ruc

        # Metadata legible de la sesión
        (shot_dir / "00_sesion.txt").write_text(
            f"Empresa:   {creds.empresa}\n"
            f"RUC:       {creds.ruc}\n"
            f"Desde:     {self.since}\n"
            f"Hasta:     {self.until}\n"
            f"Modo:      headed={self.headed}, dry_run={self.dry_run}\n"
            f"Ejecutado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            encoding="utf-8",
        )

        # File log para esta casilla
        log_file = shot_dir / "debug.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s — %(message)s", "%H:%M:%S"
            )
        )
        lg.addHandler(fh)

        lg.step("══ %s  [%s] ══", creds.empresa, creds.ruc[:5] + "×××")
        lg.info(
            "Rango: %s → %s | headed=%s | dry_run=%s",
            self.since, self.until, self.headed, self.dry_run,
        )
        lg.info("📁 Capturas → %s", shot_dir)
        self.res_q.put(("run_dir", str(shot_dir)))

        try:
            async with browser_session(headless=not self.headed) as ctx:
                page = await ctx.new_page()

                # ── 1. Login ──────────────────────────────────────────
                lg.step("[ 1/4 ] Login...")
                try:
                    await perform_login(page, creds)
                    lg.step("       ✓ Login exitoso")
                    sc = shot_dir / "01_login_ok.png"
                    await _screenshot(page, sc)
                    lg.photo("📷 %s", sc.name)
                    self.res_q.put(("screenshot", (str(sc), "01 Login OK")))
                except LoginFailed as exc:
                    lg.error("Login falló: %s", exc)
                    sc = shot_dir / "01_login_failed.png"
                    await _screenshot(page, sc)
                    self.res_q.put(("screenshot", (str(sc), "01 Login FALLÓ")))
                    return

                if self._stop.is_set():
                    return

                # ── 2. Inbox — paginación manual con screenshot por página ────
                lg.step("[ 2/4 ] Listando inbox [%s → %s]...", self.since, self.until)
                from playwright.async_api import TimeoutError as _PwTimeout

                await page.wait_for_selector(
                    SEL_ITEM, state="visible", timeout=30_000
                )
                pag = await _get_paginator_state(page)
                if pag:
                    lg.info("Paginator: %d–%d de %d total", *pag)

                items: list = []
                seen_ids: set[str] = set()
                page_idx = 1

                while page_idx <= DEFAULT_MAX_PAGES:
                    if self._stop.is_set():
                        break

                    # Screenshot de esta página del inbox
                    sc = shot_dir / f"02_inbox_pag{page_idx:02d}.png"
                    await _screenshot(page, sc)
                    lg.photo("📷 Inbox pág %d → %s", page_idx, sc.name)
                    self.res_q.put((
                        "screenshot",
                        (str(sc), f"02 Inbox pág {page_idx}"),
                    ))

                    page_items = await _read_items_in_current_page(
                        page, creds.ruc, page_idx
                    )
                    lg.info(
                        "  Pág %d: %d items leídos", page_idx, len(page_items)
                    )

                    added_this_page = 0
                    for it in page_items:
                        if self.since and it.fecha < self.since:
                            lg.info(
                                "    SKIP (fecha %s < desde %s): %s",
                                it.fecha, self.since, it.asunto[:45],
                            )
                            continue
                        if self.until and it.fecha > self.until:
                            lg.info(
                                "    SKIP (fecha %s > hasta %s): %s",
                                it.fecha, self.until, it.asunto[:45],
                            )
                            continue
                        if it.notification_id in seen_ids:
                            continue
                        seen_ids.add(it.notification_id)
                        items.append(it)
                        added_this_page += 1
                        lg.info(
                            "    ✓ [%s raw=%r adj=%s] %s",
                            it.fecha, it.raw_fecha,
                            it.has_adjuntos, it.asunto[:55],
                        )

                    lg.info(
                        "  Pág %d: %d aceptadas / %d leídas",
                        page_idx, added_this_page, len(page_items),
                    )

                    if not await _is_next_page_enabled(page):
                        lg.info("  → Última página alcanzada.")
                        break

                    # Early termination: todas anteriores al filtro
                    if (
                        self.since
                        and page_items
                        and all(it.fecha < self.since for it in page_items)
                    ):
                        lg.info(
                            "  → Early stop: pág %d toda anterior a %s",
                            page_idx, self.since,
                        )
                        break

                    await page.locator(SEL_PAG_NEXT).first.click()
                    try:
                        await page.wait_for_load_state(
                            "networkidle", timeout=10_000
                        )
                    except _PwTimeout:
                        pass
                    page_idx += 1

                lg.step(
                    "       ✓ %d notificación(es) en %d página(s)",
                    len(items), page_idx,
                )

                for it in items:
                    lg.info(
                        "  [fecha=%s  raw=%r  adj=%s  pág=%d  idx=%d]  %s",
                        it.fecha, it.raw_fecha, it.has_adjuntos,
                        it.page_index, it.item_index_in_page, it.asunto[:60],
                    )
                    self.res_q.put(("item", {
                        "id":       it.notification_id,
                        "ruc":      it.ruc,
                        "fecha":    str(it.fecha),
                        "raw":      it.raw_fecha,
                        "asunto":   it.asunto[:70],
                        "emisor":   it.emisor[:35],
                        "has_adj":  "sí" if it.has_adjuntos else "no",
                        "pag":      str(it.page_index),
                    }))

                if not items:
                    lg.info("Sin notificaciones en el rango seleccionado.")
                    return

                if self.dry_run:
                    lg.step("DRY-RUN activo — solo listado, sin descarga.")
                    return

                # ── 3. Detalle + descarga ─────────────────────────────
                for idx, item in enumerate(items, 1):
                    if self._stop.is_set():
                        lg.warning("Detenido.")
                        break

                    lg.step(
                        "[ 3/4 ] (%d/%d) %s",
                        idx, len(items), item.asunto[:55],
                    )

                    try:
                        await click_item(page, item)
                    except Exception as exc:
                        lg.error("  click_item falló: %s", exc)
                        continue

                    sc = shot_dir / f"03_{idx:02d}_detalle.png"
                    await _screenshot(page, sc)
                    lg.photo("📷 %s", sc.name)
                    self.res_q.put(
                        ("screenshot", (str(sc), f"03-{idx:02d} Detalle: {item.asunto[:25]}"))
                    )

                    # Metadata del detalle
                    meta = await extract_detail_metadata(page)
                    lg.info("  Emisor (detalle): %s", meta.emisor[:60])
                    lg.info(
                        "  Fecha detalle: %s  |  raw: %r",
                        meta.fecha, meta.fecha_full,
                    )

                    # Detectar discrepancia de fecha
                    if meta.fecha and item.fecha != meta.fecha:
                        lg.warning(
                            "  ⚠ DISCREPANCIA FECHA:  inbox=%s  vs  detalle=%s  "
                            "(raw_inbox=%r)",
                            item.fecha, meta.fecha, item.raw_fecha,
                        )

                    # Adjuntos declarados en el DOM
                    filenames = await list_detail_attachments(page)
                    lg.info(
                        "  Adjuntos declarados (%d): %s", len(filenames), filenames
                    )

                    sc = shot_dir / f"03_{idx:02d}_adjuntos.png"
                    await _screenshot(page, sc)
                    self.res_q.put(
                        ("screenshot", (str(sc), f"03-{idx:02d} Adjuntos: {len(filenames)}"))
                    )

                    # Descarga
                    dest = dl_dir / item.notification_id[:8]
                    lg.step("  Descargando %d adjunto(s)...", len(filenames))
                    try:
                        pdfs = await download_attachments(ctx, page, dest)
                        lg.step("  ✓ %d PDF(s) guardados", len(pdfs))
                        for p in pdfs:
                            lg.info("    · %-42s  %d bytes", p.filename, p.size_bytes)
                    except Exception as exc:
                        lg.error("  ✗ download_attachments: %s", exc)
                        pdfs = []

                    # Clasificación
                    pdf_rows: list[tuple[str, str, int]] = []
                    if pdfs:
                        classified = classify_pdfs([p.path for p in pdfs])
                        lg.step("  Clasificación de PDFs:")
                        for cpdf in classified:
                            sz = cpdf.path.stat().st_size
                            lg.info("    %-44s  →  %s", cpdf.path.name, cpdf.role)
                            pdf_rows.append((cpdf.path.name, cpdf.role, sz))

                        roles = {c.role for c in classified}
                        if "constancia_lectura" not in roles:
                            lg.warning(
                                "  ⚠ SIN constancia_lectura — "
                                "¿la notificación aún no fue marcada como leída en el portal?"
                            )
                        if "constancia_notificacion" not in roles:
                            lg.warning("  ⚠ SIN constancia_notificacion")
                        if "documento_principal" not in roles:
                            lg.warning(
                                "  ⚠ SIN documento_principal — "
                                "revisar nombre de archivo / clasificación"
                            )

                    self.res_q.put(("item_pdfs", (item.notification_id, pdf_rows)))

                    # Volver al inbox
                    try:
                        await page.go_back()
                        await page.wait_for_selector(
                            ".item-notificacion", state="visible", timeout=15_000
                        )
                    except Exception:
                        try:
                            await page.goto("https://casilla.mtc.gob.pe/#/casilla")
                            await page.wait_for_selector(
                                ".item-notificacion", state="visible", timeout=15_000
                            )
                        except Exception as exc2:
                            lg.error(
                                "No se pudo volver al inbox: %s — abortando RUC", exc2
                            )
                            break

            lg.step("[ 4/4 ] Sesión completada ✓  —  log guardado: %s", log_file)

        except Exception as exc:
            lg.error("Error inesperado: %s", exc, exc_info=True)
        finally:
            lg.removeHandler(fh)
            fh.close()


# ── Tkinter App ───────────────────────────────────────────────────────────────
class DebugApp:
    _POLL_MS = 80

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Debug Scraper MTC — Verificación Día a Día")
        root.configure(bg=_BG)
        root.geometry("1380x840")
        root.minsize(920, 650)

        self._log_q: "queue.Queue[tuple[str, str]]"  = queue.Queue()
        self._res_q: "queue.Queue[tuple[str, Any]]"  = queue.Queue()
        self._session: _ScrapeSession | None         = None
        self._items: dict[str, dict[str, Any]]       = {}
        self._shots: list[tuple[str, str]]           = []
        self._all_rucs: list[Any]                    = []
        self._load_err: str                          = ""
        self._last_run_dir: str | None               = None   # carpeta del run más reciente

        self._load_rucs()
        self._setup_logging()
        self._build_ui()
        self._poll()

    # ── Init helpers ─────────────────────────────────────────────────────────

    def _load_rucs(self) -> None:
        try:
            from mtc_bot.config import apply_credential_filter, get_settings
            get_settings()
            apply_credential_filter()
            from mtc_bot.models import load_rucs
            csv_path = _ROOT / "data" / "credentials" / "rucs.csv"
            self._all_rucs = [r for r in load_rucs(csv_path) if r.activo]
        except Exception as exc:
            self._load_err = str(exc)

    def _setup_logging(self) -> None:
        handler = _QueueHandler(self._log_q)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s — %(message)s", "%H:%M:%S"
            )
        )
        root_lg = logging.getLogger()
        root_lg.setLevel(logging.DEBUG)
        for h in root_lg.handlers[:]:
            if isinstance(h, _QueueHandler):
                root_lg.removeHandler(h)
        root_lg.addHandler(handler)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── ttk styles ────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("D.TNotebook",     background=_BG,    borderwidth=0, padding=0)
        style.configure("D.TNotebook.Tab", background=_SURF,  foreground=_SUBTEXT,
                        font=("Consolas", 9), padding=[10, 4])
        style.map("D.TNotebook.Tab",
                  background=[("selected", _BG)],
                  foreground=[("selected", _PRIMARY)])
        style.configure("D.Treeview",         background=_SURF, fieldbackground=_SURF,
                        foreground=_FG, font=("Consolas", 8), rowheight=20)
        style.configure("D.Treeview.Heading", background=_BG,   foreground=_PRIMARY,
                        font=("Consolas", 8, "bold"))
        style.map("D.Treeview",
                  background=[("selected", _PRIMARY)],
                  foreground=[("selected", _BG)])
        style.configure("D.Horizontal.TProgressbar", background=_PRIMARY, troughcolor=_SURF)
        style.configure("D.Vertical.TScrollbar",     background=_SURF2, troughcolor=_SURF)

        # ── Main PanedWindow ──────────────────────────────────────────────
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Left: casillas ────────────────────────────────────────────────
        left = tk.Frame(paned, bg=_BG, width=235)
        left.pack_propagate(False)
        paned.add(left, weight=0)

        tk.Label(
            left, text="CASILLAS", bg=_BG, fg=_PRIMARY,
            font=("Consolas", 10, "bold"),
        ).pack(pady=(10, 4))

        lbf = tk.Frame(left, bg=_BG)
        lbf.pack(fill=tk.BOTH, expand=True, padx=6)
        lbsb = ttk.Scrollbar(lbf, orient=tk.VERTICAL)
        self._ruc_lb = tk.Listbox(
            lbf, selectmode=tk.EXTENDED, bg=_SURF, fg=_FG,
            selectbackground=_PRIMARY, selectforeground=_BG,
            font=("Consolas", 8), activestyle="none",
            yscrollcommand=lbsb.set, relief=tk.FLAT, borderwidth=0,
        )
        lbsb.config(command=self._ruc_lb.yview)
        self._ruc_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lbsb.pack(side=tk.RIGHT, fill=tk.Y)

        for c in self._all_rucs:
            label = c.empresa[:27] + ("…" if len(c.empresa) > 27 else "")
            self._ruc_lb.insert(tk.END, f" {label}")
        if self._all_rucs:
            self._ruc_lb.select_set(0)

        bkw = dict(bg=_SURF, fg=_SUBTEXT, font=("Consolas", 8), relief=tk.FLAT, bd=0)
        tk.Button(
            left, text="Seleccionar todas", **bkw,
            command=lambda: self._ruc_lb.select_set(0, tk.END),
        ).pack(fill=tk.X, padx=6, pady=(4, 0))
        tk.Button(
            left, text="Deseleccionar todas", **bkw,
            command=lambda: self._ruc_lb.selection_clear(0, tk.END),
        ).pack(fill=tk.X, padx=6)

        if self._load_err:
            tk.Label(
                left, text=f"⚠ {self._load_err[:38]}", bg=_BG, fg=_YELLOW,
                font=("Consolas", 7), wraplength=215, justify=tk.LEFT,
            ).pack(padx=6, pady=4)

        # ── Right panel ───────────────────────────────────────────────────
        right = tk.Frame(paned, bg=_BG)
        paned.add(right, weight=1)

        # Controls strip
        ctrl = tk.Frame(right, bg=_SURF, padx=10, pady=8)
        ctrl.pack(fill=tk.X)

        # Row 1: date range + quick buttons
        r1 = tk.Frame(ctrl, bg=_SURF)
        r1.pack(fill=tk.X)

        def lbl(p: tk.Frame, t: str) -> None:
            tk.Label(p, text=t, bg=_SURF, fg=_SUBTEXT, font=("Consolas", 9)).pack(
                side=tk.LEFT
            )

        cal_kw = dict(bg=_SURF2, fg=_FG, font=("Consolas", 10), relief=tk.FLAT, bd=0, padx=4)

        lbl(r1, "Desde:")
        self._since_var = tk.StringVar(value="2026-05-13")
        tk.Entry(
            r1, textvariable=self._since_var, bg=_BG, fg=_FG,
            insertbackground=_FG, font=("Consolas", 9), width=12, relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=(4, 2))
        tk.Button(
            r1, text="📅", **cal_kw,
            command=lambda: _pick_date(self.root, self._since_var),
        ).pack(side=tk.LEFT, padx=(0, 10))

        lbl(r1, "Hasta:")
        self._until_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(
            r1, textvariable=self._until_var, bg=_BG, fg=_FG,
            insertbackground=_FG, font=("Consolas", 9), width=12, relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=(4, 2))
        tk.Button(
            r1, text="📅", **cal_kw,
            command=lambda: _pick_date(self.root, self._until_var),
        ).pack(side=tk.LEFT, padx=(0, 14))

        lbl(r1, "Desde rápido:")
        for label, days in [("Hoy", 0), ("Ayer", 1), ("7d", 7), ("14d", 14), ("30d", 30)]:
            d_val = date.today() - timedelta(days=days)
            tk.Button(
                r1, text=label, bg=_SURF2, fg=_FG,
                font=("Consolas", 8), relief=tk.FLAT, bd=0, padx=5,
                command=lambda d=d_val: self._since_var.set(d.isoformat()),
            ).pack(side=tk.LEFT, padx=1)

        # Row 2: options + buttons
        r2 = tk.Frame(ctrl, bg=_SURF)
        r2.pack(fill=tk.X, pady=(6, 0))

        ckw = dict(
            bg=_SURF, fg=_FG, selectcolor=_BG,
            activebackground=_SURF, activeforeground=_FG,
            font=("Consolas", 9),
        )
        self._headed_var = tk.BooleanVar(value=True)
        self._dryrun_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r2, text="Browser visible", variable=self._headed_var, **ckw).pack(
            side=tk.LEFT
        )
        tk.Checkbutton(
            r2, text="Solo listar (sin descarga)", variable=self._dryrun_var, **ckw,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Run / Stop / Clear
        self._run_btn = tk.Button(
            r2, text="▶  Ejecutar", bg="#1a3a24", fg=_GREEN,
            font=("Consolas", 9, "bold"), relief=tk.FLAT, bd=0, padx=14,
            command=self._run,
        )
        self._run_btn.pack(side=tk.LEFT, padx=(14, 4))

        self._stop_btn = tk.Button(
            r2, text="■  Detener", bg="#3a1a1a", fg=_RED,
            font=("Consolas", 9), relief=tk.FLAT, bd=0, padx=14,
            command=self._stop, state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=4)

        tk.Button(
            r2, text="Limpiar", bg=_SURF2, fg=_FG,
            font=("Consolas", 8), relief=tk.FLAT, bd=0, padx=10,
            command=self._clear,
        ).pack(side=tk.LEFT, padx=4)

        # Progress bar + status
        pf = tk.Frame(r2, bg=_SURF)
        pf.pack(side=tk.RIGHT)
        self._progress = ttk.Progressbar(
            pf, mode="determinate", length=180, style="D.Horizontal.TProgressbar"
        )
        self._progress.pack(side=tk.LEFT)
        self._status_var = tk.StringVar(value="Listo")
        tk.Label(
            pf, textvariable=self._status_var, bg=_SURF, fg=_SUBTEXT,
            font=("Consolas", 8),
        ).pack(side=tk.LEFT, padx=6)

        # ── Notebook ──────────────────────────────────────────────────────
        nb = ttk.Notebook(right, style="D.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=2, pady=(4, 0))

        # ── Tab: Logs ────────────────────────────────────────────────────
        log_tab = tk.Frame(nb, bg=_BG)
        nb.add(log_tab, text="  Logs  ")
        self._log_txt = tk.Text(
            log_tab, bg=_BG, fg=_FG, insertbackground=_FG,
            font=("Consolas", 8), wrap=tk.NONE, relief=tk.FLAT, state=tk.DISABLED,
        )
        lsb_y = ttk.Scrollbar(log_tab, orient=tk.VERTICAL,   command=self._log_txt.yview)
        lsb_x = ttk.Scrollbar(log_tab, orient=tk.HORIZONTAL, command=self._log_txt.xview)
        self._log_txt.configure(yscrollcommand=lsb_y.set, xscrollcommand=lsb_x.set)
        lsb_y.pack(side=tk.RIGHT, fill=tk.Y)
        lsb_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._log_txt.pack(fill=tk.BOTH, expand=True)
        for lvl, col in _LOG_COLORS.items():
            self._log_txt.tag_config(lvl, foreground=col)

        # ── Tab: Notificaciones ───────────────────────────────────────────
        notif_tab = tk.Frame(nb, bg=_BG)
        nb.add(notif_tab, text="  Notificaciones  ")
        cols = (
            "RUC", "Fecha", "Raw fecha", "Asunto",
            "Adj", "Pág", "Principal", "C.Notif", "C.Lectura",
        )
        self._tree = ttk.Treeview(
            notif_tab, columns=cols, show="headings",
            height=22, style="D.Treeview",
        )
        widths  = [110, 88, 148, 300, 40, 40, 80, 80, 80]
        anchors = ["w", "c", "c",  "w", "c", "c", "c", "c", "c"]
        for col, w, anc in zip(cols, widths, anchors):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, minwidth=30, anchor=anc)
        tsb = ttk.Scrollbar(notif_tab, orient=tk.VERTICAL,   command=self._tree.yview)
        tsx = ttk.Scrollbar(notif_tab, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=tsb.set, xscrollcommand=tsx.set)
        tsb.pack(side=tk.RIGHT, fill=tk.Y)
        tsx.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.tag_configure("ok",   foreground=_GREEN)
        self._tree.tag_configure("warn", foreground=_YELLOW)
        self._tree.tag_configure("err",  foreground=_RED)

        # ── Tab: PDFs ─────────────────────────────────────────────────────
        pdf_tab = tk.Frame(nb, bg=_BG)
        nb.add(pdf_tab, text="  PDFs  ")
        self._pdf_txt = tk.Text(
            pdf_tab, bg=_BG, fg=_FG, font=("Consolas", 9),
            relief=tk.FLAT, state=tk.DISABLED,
        )
        psb = ttk.Scrollbar(pdf_tab, orient=tk.VERTICAL, command=self._pdf_txt.yview)
        self._pdf_txt.configure(yscrollcommand=psb.set)
        psb.pack(side=tk.RIGHT, fill=tk.Y)
        self._pdf_txt.pack(fill=tk.BOTH, expand=True)
        self._pdf_txt.tag_config("head",    foreground=_PRIMARY, font=("Consolas", 9, "bold"))
        self._pdf_txt.tag_config("ok",      foreground=_GREEN)
        self._pdf_txt.tag_config("warn",    foreground=_YELLOW)
        self._pdf_txt.tag_config("neutral", foreground=_SUBTEXT)

        # ── Tab: Capturas ─────────────────────────────────────────────────
        cap_tab = tk.Frame(nb, bg=_BG)
        nb.add(cap_tab, text="  Capturas  ")
        cap_hdr = tk.Frame(cap_tab, bg=_BG)
        cap_hdr.pack(fill=tk.X, padx=6, pady=6)
        tk.Label(
            cap_hdr, text="Doble clic para abrir imagen:",
            bg=_BG, fg=_PRIMARY, font=("Consolas", 9, "bold"),
        ).pack(side=tk.LEFT)
        tk.Button(
            cap_hdr, text="Abrir carpeta", bg=_SURF, fg=_FG,
            font=("Consolas", 8), relief=tk.FLAT, bd=0,
            command=self._open_log_folder,
        ).pack(side=tk.RIGHT, padx=4)
        self._cap_lb = tk.Listbox(
            cap_tab, bg=_SURF, fg=_FG, font=("Consolas", 9),
            selectbackground=_PRIMARY, selectforeground=_BG,
            activestyle="none", relief=tk.FLAT,
        )
        self._cap_lb.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._cap_lb.bind("<Double-Button-1>", self._open_screenshot)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _get_selected_rucs(self) -> list[Any]:
        sel = self._ruc_lb.curselection()
        if not sel:
            messagebox.showwarning("Sin selección", "Seleccioná al menos una casilla.")
            return []
        return [self._all_rucs[i] for i in sel]

    def _parse_date(self, var: tk.StringVar, label: str) -> date | None:
        try:
            return date.fromisoformat(var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Fecha inválida",
                f"{label}: usá formato YYYY-MM-DD (ej. 2026-05-25).",
            )
            return None

    def _run(self) -> None:
        if self._session and self._session.running:
            messagebox.showinfo("En curso", "Hay una sesión activa. Detené primero.")
            return
        creds = self._get_selected_rucs()
        if not creds:
            return
        since = self._parse_date(self._since_var, "Desde")
        until = self._parse_date(self._until_var, "Hasta")
        if since is None or until is None:
            return
        if since > until:
            messagebox.showerror(
                "Rango inválido", "'Desde' no puede ser posterior a 'Hasta'."
            )
            return

        self._session = _ScrapeSession(
            creds_list=creds,
            since=since,
            until=until,
            log_q=self._log_q,
            res_q=self._res_q,
            headed=self._headed_var.get(),
            dry_run=self._dryrun_var.get(),
        )
        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._progress.config(maximum=max(len(creds), 1), value=0)
        self._status_var.set(f"Iniciando…  0/{len(creds)}")
        self._session.start()

    def _stop(self) -> None:
        if self._session:
            self._session.stop()
        self._status_var.set("Deteniendo…")
        self._stop_btn.config(state=tk.DISABLED)

    def _clear(self) -> None:
        for w in (self._log_txt, self._pdf_txt):
            w.config(state=tk.NORMAL)
            w.delete("1.0", tk.END)
            w.config(state=tk.DISABLED)
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._cap_lb.delete(0, tk.END)
        self._shots.clear()
        self._items.clear()

    def _open_log_folder(self) -> None:
        # Abre la carpeta del run más reciente; si no hay ninguna, la raíz debug_logs
        if self._last_run_dir and Path(self._last_run_dir).exists():
            folder = Path(self._last_run_dir)
        else:
            folder = _ROOT / "data" / "debug_logs"
            folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            import subprocess
            subprocess.run(["xdg-open", str(folder)], check=False)

    def _open_screenshot(self, _event: Any) -> None:
        sel = self._cap_lb.curselection()
        if not sel or sel[0] >= len(self._shots):
            return
        path = self._shots[sel[0]][0]
        if sys.platform == "win32":
            os.startfile(path)
        else:
            import subprocess
            subprocess.run(["xdg-open", path], check=False)

    # ── Polling loop ──────────────────────────────────────────────────────────

    def _poll(self) -> None:
        # Drain log queue
        try:
            while True:
                level, msg = self._log_q.get_nowait()
                self._append_log(level, msg)
        except queue.Empty:
            pass

        # Drain result queue
        try:
            while True:
                kind, data = self._res_q.get_nowait()
                self._handle_result(kind, data)
        except queue.Empty:
            pass

        self.root.after(self._POLL_MS, self._poll)

    def _append_log(self, level: str, msg: str) -> None:
        tag = level if level in _LOG_COLORS else "INFO"
        self._log_txt.config(state=tk.NORMAL)
        self._log_txt.insert(tk.END, msg + "\n", tag)
        self._log_txt.see(tk.END)
        self._log_txt.config(state=tk.DISABLED)

    def _handle_result(self, kind: str, data: Any) -> None:  # noqa: C901
        if kind == "progress":
            done, total, label = data
            self._progress.config(value=done)
            self._status_var.set(f"{label}  {done}/{total}")

        elif kind == "done":
            self._run_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            n = int(self._progress["maximum"])
            self._status_var.set(f"✓ Listo — {n} casilla(s)")

        elif kind == "run_dir":
            self._last_run_dir = data   # para que "Abrir carpeta" apunte aquí

        elif kind == "screenshot":
            path, label = data
            self._shots.append((path, label))
            self._cap_lb.insert(tk.END, f"  {label}")

        elif kind == "item":
            d = data
            iid = d["id"]
            self._items[iid] = d
            self._tree.insert(
                "", tk.END, iid=iid,
                values=(
                    d["ruc"][:16], d["fecha"], d["raw"][:22],
                    d["asunto"], d["has_adj"], d["pag"],
                    "…", "…", "…",
                ),
            )

        elif kind == "item_pdfs":
            notif_id, pdf_rows = data
            has_p  = any(r == "documento_principal"    for _, r, _ in pdf_rows)
            has_cn = any(r == "constancia_notificacion" for _, r, _ in pdf_rows)
            has_cl = any(r == "constancia_lectura"      for _, r, _ in pdf_rows)
            tag = "ok" if (has_p and has_cn and has_cl) else (
                "warn" if (has_p and has_cn) else "err"
            )
            try:
                old = list(self._tree.item(notif_id)["values"])
                old[6] = "✓" if has_p  else "✗"
                old[7] = "✓" if has_cn else "✗"
                old[8] = "✓" if has_cl else "⚠" if has_p else "✗"
                self._tree.item(notif_id, values=old, tags=(tag,))
            except tk.TclError:
                pass

            # Update PDF tab
            asunto = self._items.get(notif_id, {}).get("asunto", notif_id[:8])
            self._pdf_txt.config(state=tk.NORMAL)
            self._pdf_txt.insert(tk.END, f"\n▸ {asunto[:68]}\n", "head")
            self._pdf_txt.insert(tk.END, "  " + "─" * 62 + "\n", "neutral")
            for fname, role, sz in pdf_rows:
                color = "ok" if role in (
                    "documento_principal",
                    "constancia_notificacion",
                    "constancia_lectura",
                ) else "neutral"
                self._pdf_txt.insert(
                    tk.END,
                    f"  {fname:<44}  {role:<28}  {sz:,} B\n",
                    color,
                )
            if not has_cl:
                self._pdf_txt.insert(
                    tk.END, "  ⚠ Sin constancia_lectura\n", "warn"
                )
            if not has_cn:
                self._pdf_txt.insert(
                    tk.END, "  ⚠ Sin constancia_notificacion\n", "warn"
                )
            self._pdf_txt.config(state=tk.DISABLED)
            self._pdf_txt.see(tk.END)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    root = tk.Tk()
    app = DebugApp(root)
    if app._load_err:
        messagebox.showwarning(
            "Configuración",
            f"No se pudieron cargar los RUCs:\n{app._load_err}\n\n"
            "Verificá que data/credentials/rucs.csv existe y .env está configurado.",
        )
    root.mainloop()


if __name__ == "__main__":
    main()
