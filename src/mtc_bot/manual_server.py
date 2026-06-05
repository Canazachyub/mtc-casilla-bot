"""Servidor local del dashboard: sirve el frontend estático y expone
POST /api/manual para ingesta manual de PDFs externos (WhatsApp / Gmail).

Uso:
    uv run mtc-bot serve [--port 8080]
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_LIMA = ZoneInfo("America/Lima")


def create_app(frontend_dir: Path) -> FastAPI:
    """Crea y configura la aplicación FastAPI."""

    app = FastAPI(title="MTC Casilla Bot — Dashboard local", docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Endpoint de procesado manual ────────────────────────────────────────

    @app.post("/api/manual")
    async def process_manual(
        empresa: str = Form(...),
        ruc: str = Form(default=""),
        contexto: str = Form(default=""),
        fecha: str = Form(default=""),
        pdf: UploadFile = File(...),
    ) -> JSONResponse:
        """Procesa un PDF externo con el mismo pipeline que las casillas automáticas.

        Args:
            empresa: nombre de la empresa (ej: "ESPINAR SAC (ESPINAR)").
            ruc: RUC de la empresa (puede ser vacío para tareas sin RUC).
            contexto: texto del WhatsApp / Gmail que acompañó al PDF.
            fecha: fecha de la notificación (ISO YYYY-MM-DD; vacío → hoy).
            pdf: archivo PDF combinado (doc principal + constancias).
        """
        from mtc_bot.ai_extractor import AIExtractionFailed
        from mtc_bot.ai_extractor import extract as ai_extract
        from mtc_bot.ai_extractor import extract_informe as ai_extract_informe
        from mtc_bot.config import get_settings
        from mtc_bot.google.drive_uploader import upload_pdf
        from mtc_bot.google.sheets_writer import append_notificacion
        from mtc_bot.pdf_pipeline import extract_text

        cfg = get_settings()

        # 1) Guardar PDF temporalmente
        pdf_bytes = await pdf.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="El PDF está vacío.")

        pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
        ruc_safe = ruc.strip() or "MANUAL"
        sheet_id = f"manual__{ruc_safe}__{pdf_hash}"

        # data/downloads/manual/<hash> relativo al directorio de trabajo del bot
        project_root = Path(cfg.google_service_account_json).parent.parent
        manual_dir = project_root / "data" / "downloads" / "manual" / pdf_hash
        manual_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = manual_dir / (pdf.filename or "documento.pdf")
        pdf_path.write_bytes(pdf_bytes)
        logger.info("PDF manual guardado: %s (%d bytes)", pdf_path.name, len(pdf_bytes))

        # 2) Extraer texto del PDF
        try:
            pdf_text = extract_text(pdf_path, max_pages=None)
        except Exception as exc:
            logger.warning("extract_text falló: %s", exc)
            pdf_text = ""

        # 3) Construir contexto combinado para la IA
        texto_partes: list[str] = []
        if contexto.strip():
            texto_partes.append(f"=== CONTEXTO (WhatsApp / Gmail) ===\n{contexto.strip()}")
        if empresa.strip():
            texto_partes.append(f"Empresa: {empresa.strip()}")
        if pdf_text.strip():
            texto_partes.append(f"=== TEXTO DEL PDF ===\n{pdf_text}")
        texto_completo = "\n\n".join(texto_partes)

        # 4) Extracción IA metadata (DeepSeek primario)
        try:
            extraction = await ai_extract(texto_completo, cfg)
        except AIExtractionFailed as exc:
            logger.error("AI extraction failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Extracción IA falló: {exc}") from exc

        # 5) Informe estructurado (Gemini → DeepSeek fallback)
        informe = await ai_extract_informe(pdf_text or texto_completo, cfg)

        # 6) Renombrar PDF con nombre extraído por IA
        doc_name = extraction.documento or (pdf.filename or "documento")
        try:
            from mtc_bot.pdf_pipeline import rename_merged
            final_pdf = rename_merged(pdf_path, doc_name)
        except Exception:
            final_pdf = pdf_path

        # 7) Upload a Drive
        fecha_dt = _parse_fecha(fecha)
        drive_file_id = ""
        drive_view_url = ""
        try:
            uploaded = upload_pdf(
                cfg.google_service_account_json,
                cfg.drive_root_folder_id,
                final_pdf,
                ruc_safe,
                fecha_dt,
                oauth_json_path=cfg.oauth_credentials_json,
                oauth_token_path=cfg.oauth_token_json,
                oauth_login_hint=cfg.google_oauth_hint,
            )
            drive_file_id = uploaded.file_id
            drive_view_url = uploaded.view_url
        except Exception as exc:
            logger.warning("Drive upload falló (continuando sin Drive): %s", exc)

        # 8) Calcular plazo de vencimiento
        from mtc_bot.cli import _estimate_vencimiento
        plazo_venc = _estimate_vencimiento(fecha_dt, extraction.plazo_dias_habiles)

        # 9) Append al Sheet
        timestamp = datetime.now(tz=_LIMA).isoformat(timespec="seconds")
        row: dict = {
            "id": sheet_id,
            "timestamp_proceso": timestamp,
            "fecha_notificacion": fecha_dt.isoformat(),
            "lectura_notificacion": fecha_dt.isoformat(),
            "ruc": ruc_safe,
            "empresa": empresa.strip(),
            "sede": "",
            "documento": extraction.documento or doc_name,
            "emisor": extraction.emisor,
            "casilla_origen": extraction.casilla_origen or "MANUAL",
            "asunto": extraction.asunto,
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
            "informe": informe,
            "drive_file_id": drive_file_id,
            "drive_view_url": drive_view_url,
            "estado": "pendiente",
        }
        try:
            append_notificacion(
                cfg.google_service_account_json,
                cfg.sheet_id,
                "notificaciones",
                row,
            )
        except Exception as exc:
            logger.error("Sheet append falló: %s", exc)
            raise HTTPException(status_code=500, detail=f"Error guardando en Sheet: {exc}") from exc

        logger.info("Notificación manual creada: %s", sheet_id)
        return JSONResponse({"ok": True, "id": sheet_id, "notification": {
            "id": sheet_id,
            "empresa": empresa.strip(),
            "ruc": ruc_safe,
            "documento": row["documento"],
            "emisor": extraction.emisor,
            "asunto": extraction.asunto,
            "tipo_acto": extraction.tipo_acto,
            "plazo_dias_habiles": extraction.plazo_dias_habiles,
            "plazo_vencimiento": str(plazo_venc) if plazo_venc else "",
            "informe": informe[:500] + "..." if len(informe) > 500 else informe,
            "drive_view_url": drive_view_url,
            "fecha_notificacion": fecha_dt.isoformat(),
        }})

    # ─── Archivos estáticos del frontend ─────────────────────────────────────
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    else:
        logger.warning("Directorio frontend no encontrado: %s", frontend_dir)

    return app


def _parse_fecha(fecha_str: str) -> date:
    """Parsea ISO date string o devuelve hoy si está vacío/inválido."""
    if fecha_str:
        try:
            return date.fromisoformat(fecha_str)
        except ValueError:
            pass
    return date.today()
