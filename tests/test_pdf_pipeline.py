"""Tests para ``mtc_bot.pdf_pipeline``.

Cubre:
    * :func:`slug_from_subject` con varios casos (común, tildes, vacío,
      truncado).
    * :func:`classify_pdfs` con nombres reales del portal MTC.

NO cubre :func:`merge_pdfs` ni :func:`extract_text` porque requieren PDFs
reales — eso se valida en e2e con el orquestador.
"""

from __future__ import annotations

from pathlib import Path

from mtc_bot.pdf_pipeline import ClassifiedPdf, classify_pdfs, slug_from_subject

# ─────────────────────────────────────────────────────────────────
# slug_from_subject
# ─────────────────────────────────────────────────────────────────


def test_slug_from_subject_caso_comun() -> None:
    """Asunto típico con tilde, ``N°`` y ``/``."""
    asunto = "NOTIFICACIÓN DE CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV"
    slug = slug_from_subject(asunto)
    assert slug == "CARTA-000476-CR-2026-SUTRAN-06.3.4-SGFSV"


def test_slug_from_subject_resolucion_con_tilde() -> None:
    """El prefijo se quita aunque venga sin tilde y con minúsculas."""
    asunto = "notificacion de RESOLUCIÓN N° 42250038-DGAC"
    slug = slug_from_subject(asunto)
    assert slug == "RESOLUCION-42250038-DGAC"


def test_slug_from_subject_vacio_devuelve_documento() -> None:
    """Si el asunto queda vacío tras limpiar, fallback a ``documento``."""
    assert slug_from_subject("") == "documento"
    assert slug_from_subject("   ") == "documento"
    # Solo un prefijo + caracteres inválidos → vacío → fallback.
    assert slug_from_subject("NOTIFICACIÓN DE ///") == "documento"


def test_slug_from_subject_trunca_a_100_chars() -> None:
    """Asuntos extremadamente largos se truncan a 100 chars."""
    asunto = "NOTIFICACIÓN DE " + "A" * 200
    slug = slug_from_subject(asunto)
    assert len(slug) <= 100
    assert slug.startswith("A")


def test_slug_from_subject_sin_prefijo() -> None:
    """Si no trae el prefijo NOTIFICACIÓN DE, igual normaliza."""
    asunto = "Oficio 123/2026 SUTRAN"
    slug = slug_from_subject(asunto)
    assert slug == "Oficio-123-2026-SUTRAN"


# ─────────────────────────────────────────────────────────────────
# classify_pdfs
# ─────────────────────────────────────────────────────────────────


def test_classify_pdfs_caso_real_3_archivos(tmp_path: Path) -> None:
    """3 PDFs típicos: documento principal + 2 constancias."""
    paths = [
        tmp_path / "000476-CR-2026-SUTRAN-06.3.4-SGFSV.pdf",
        tmp_path / "Constancia_Deposito_11542476.pdf",
        tmp_path / "Constancia_Lectura_11542476.pdf",
    ]
    for p in paths:
        p.touch()

    result = classify_pdfs(paths)

    assert len(result) == 3
    assert isinstance(result[0], ClassifiedPdf)
    assert result[0].role == "documento_principal"
    assert result[1].role == "constancia_notificacion"
    assert result[2].role == "constancia_lectura"


def test_classify_pdfs_caso_4_archivos_con_anexo(tmp_path: Path) -> None:
    """4 PDFs: documento principal, anexo, y 2 constancias."""
    paths = [
        tmp_path / "OFICIO-PRINCIPAL.pdf",
        tmp_path / "Anexo_Tecnico.pdf",
        tmp_path / "Constancia_Notificacion_99.pdf",
        tmp_path / "Constancia_Lectura_99.pdf",
    ]
    for p in paths:
        p.touch()

    result = classify_pdfs(paths)
    roles = [c.role for c in result]
    assert roles == [
        "documento_principal",
        "anexo",
        "constancia_notificacion",
        "constancia_lectura",
    ]


def test_classify_pdfs_dos_principales_segundo_es_anexo(tmp_path: Path) -> None:
    """Si llegan 2 PDFs sin patrón de constancia, el segundo es anexo."""
    paths = [
        tmp_path / "DOC-PRINCIPAL.pdf",
        tmp_path / "DOC-EXTRA.pdf",
        tmp_path / "Constancia_Lectura_1.pdf",
    ]
    for p in paths:
        p.touch()

    result = classify_pdfs(paths)
    assert result[0].role == "documento_principal"
    assert result[1].role == "anexo"
    assert result[2].role == "constancia_lectura"
