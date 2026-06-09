"""Pipeline de manipulación de PDFs descargados de la Casilla MTC.

Funciones:
    * :func:`classify_pdfs`: detecta el rol de cada PDF por nombre (documento
      principal, constancia notificación, constancia lectura, anexo).
    * :func:`merge_pdfs`: une los PDFs en el orden estricto.
    * :func:`extract_text`: extrae texto del PDF unido para mandarlo a IA.
    * :func:`slug_from_subject`: genera un nombre de archivo "limpio" desde el
      asunto.
    * :func:`rename_merged`: renombra el PDF unido con el nombre del documento.

Orden estricto del merge (regla inviolable):
    1. Documento principal.
    2. Anexos (en orden alfabético).
    3. Constancia de notificación electrónica (penúltimo).
    4. Constancia de lectura (último).

Estrategia de extracción de texto (extract_text):
    * pdfplumber con layout=True → preserva orden de columnas y tablas.
    * Extracción de tablas → se incluyen como texto estructurado.
    * Limpieza de artefactos → números de página, watermarks, whitespace.
    * Detección de PDF escaneado → alerta en log + fallback OCR opcional.
    * Fallback OCR con pytesseract (requiere: pip install pytesseract pdf2image
      + Tesseract-OCR instalado en el sistema con idioma spa).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pdfplumber
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

PdfRole = Literal[
    "documento_principal",
    "constancia_notificacion",
    "constancia_lectura",
    "anexo",
]

# Patrones para clasificar por nombre (case-insensitive).
_RE_CONSTANCIA_LECTURA = re.compile(
    r"constancia[_\s\-]*(?:de[_\s\-]*)?lectura",
    re.IGNORECASE,
)
_RE_CONSTANCIA_NOTIF = re.compile(
    r"constancia[_\s\-]*(?:de[_\s\-]*)?(?:notificacion|notificación|deposito|depósito)",
    re.IGNORECASE,
)
_RE_ANEXO = re.compile(r"\banexo\b", re.IGNORECASE)

# Prefijo "NOTIFICACIÓN DE " para el slug.
_RE_PREFIJO_NOTIF = re.compile(
    r"^\s*notificaci[oó]n\s+de\s+",
    re.IGNORECASE,
)

_RE_SLUG_INVALIDOS = re.compile(r"[^A-Za-z0-9._\-]")
_RE_GUIONES_DUPLICADOS = re.compile(r"-{2,}")

_SLUG_MAX_LEN = 100
_RENAME_MAX_COLISIONES = 999

# Densidad mínima de texto (chars/página) para considerar que el PDF NO está escaneado.
# Por debajo de este umbral, se activa el fallback OCR.
_MIN_CHARS_PER_PAGE = 80


@dataclass(slots=True, frozen=True)
class ClassifiedPdf:
    """PDF descargado con su rol identificado dentro de la notificación.

    Attributes:
        path: ruta al PDF en disco.
        role: rol detectado (``documento_principal``, ``constancia_notificacion``,
            ``constancia_lectura`` o ``anexo``).
    """

    path: Path
    role: PdfRole


def _classify_one(filename: str, *, has_main: bool) -> PdfRole:
    """Detecta el rol de un PDF a partir de su nombre."""
    if _RE_CONSTANCIA_LECTURA.search(filename):
        return "constancia_lectura"
    if _RE_CONSTANCIA_NOTIF.search(filename):
        return "constancia_notificacion"
    if _RE_ANEXO.search(filename):
        return "anexo"
    return "anexo" if has_main else "documento_principal"


def classify_pdfs(pdf_paths: list[Path]) -> list[ClassifiedPdf]:
    """Clasifica una lista de PDFs según su nombre.

    El primero que NO matchee patrones de constancia/anexo se considera
    ``documento_principal``. Si hay más de uno sin clasificar, los siguientes
    se etiquetan como ``anexo``.

    Args:
        pdf_paths: lista de paths de PDFs descargados.

    Returns:
        Lista de :class:`ClassifiedPdf` en el mismo orden de entrada.
    """
    classified: list[ClassifiedPdf] = []
    has_main = False
    for path in pdf_paths:
        role = _classify_one(path.name, has_main=has_main)
        if role == "documento_principal":
            has_main = True
        classified.append(ClassifiedPdf(path=path, role=role))
    return classified


_MERGE_ORDER: dict[PdfRole, int] = {
    "documento_principal": 1,
    "anexo": 2,
    "constancia_notificacion": 8,
    "constancia_lectura": 9,
}


def merge_pdfs(pdf_paths: list[Path], output: Path) -> Path:
    """Une PDFs en el orden estricto exigido por el equipo legal.

    Orden: documento principal → anexos (alfabético) → constancia notificación
    → constancia lectura.

    Args:
        pdf_paths: lista de PDFs a unir (cualquier orden de entrada).
        output: path destino del PDF unido.

    Returns:
        El path ``output`` si la operación fue exitosa.

    Raises:
        ValueError: si la lista está vacía o no hay documento principal.
        OSError: si falla la lectura de algún PDF o la escritura del destino.
    """
    if not pdf_paths:
        raise ValueError("Lista de PDFs vacía: nada que unir.")

    classified = classify_pdfs(pdf_paths)

    if not any(c.role == "documento_principal" for c in classified):
        raise ValueError(
            "No se detectó documento principal entre los PDFs. "
            f"Archivos recibidos: {[p.name for p in pdf_paths]}"
        )

    if not any(c.role == "constancia_notificacion" for c in classified):
        logger.warning("Merge sin constancia de notificación electrónica (output=%s)", output.name)
    if not any(c.role == "constancia_lectura" for c in classified):
        logger.warning("Merge sin constancia de lectura (output=%s)", output.name)

    sorted_pdfs = sorted(
        classified,
        key=lambda c: (_MERGE_ORDER[c.role], c.path.name.lower()),
    )

    logger.info(
        "Merge: %d PDFs en orden %s → %s",
        len(sorted_pdfs),
        [c.role for c in sorted_pdfs],
        output.name,
    )

    writer = PdfWriter()
    try:
        for item in sorted_pdfs:
            reader = PdfReader(str(item.path))
            for page in reader.pages:
                writer.add_page(page)

        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as fh:
            writer.write(fh)
    finally:
        writer.close()

    return output


# ─────────────────────────────────────────────────────────────────
# Helpers de extracción de texto
# ─────────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Limpia artefactos comunes en texto extraído de PDFs gubernamentales peruanos.

    - Normaliza saltos de línea.
    - Colapsa líneas que son solo números de página.
    - Elimina marcadores "Página X de Y" / "Page X of Y".
    - Colapsa whitespace excesivo sin destruir la estructura de párrafos.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Eliminar líneas que son solo dígitos (número de página)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    # Eliminar "Página X de Y" en cualquier capitalización
    text = re.sub(r"[Pp][áa]gina\s+\d+\s+de\s+\d+", "", text)
    text = re.sub(r"[Pp]age\s+\d+\s+of\s+\d+", "", text)
    # Colapsar más de 2 saltos de línea consecutivos
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Colapsar espacios múltiples dentro de una línea (preservar el salto)
    text = re.sub(r"[ \t]{3,}", "  ", text)
    return text.strip()


def _extract_page_text(page) -> str:
    """Extrae texto de una página con layout=True y agrega tablas detectadas.

    ``layout=True`` le indica a pdfplumber que preserve el orden de lectura
    multi-columna, en lugar de extraer el texto en el orden interno del PDF
    (que suele estar desordenado en documentos con columnas).
    """
    # layout=True: preserva posicionamiento espacial → mejor orden de lectura
    raw = page.extract_text(layout=True) or ""

    # Extraer tablas y agregarlas si tienen contenido
    table_parts: list[str] = []
    try:
        tables = page.extract_tables()
        for table in (tables or []):
            rows = []
            for row in table:
                cells = [str(c or "").strip() for c in row]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                table_parts.append("\n".join(rows))
    except Exception as exc:  # noqa: BLE001 — tablas opcionales, no abortar
        logger.debug("Error extrayendo tablas: %s", exc)

    parts = [raw] if raw.strip() else []
    parts.extend(table_parts)
    return "\n\n".join(parts)


def _configure_tesseract() -> None:
    """Configura la ruta al ejecutable de Tesseract en Windows si no está en PATH."""
    import sys  # noqa: PLC0415
    if sys.platform != "win32":
        return
    import shutil  # noqa: PLC0415

    import pytesseract  # noqa: PLC0415
    if shutil.which("tesseract"):
        return  # ya está en PATH
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            return
    logger.warning("Tesseract no encontrado en rutas conocidas de Windows.")


def _try_ocr(pdf_path: Path, max_pages: int) -> str:
    """Intenta extraer texto por OCR con pytesseract (fallback para PDFs escaneados).

    Args:
        pdf_path: PDF a procesar.
        max_pages: número máximo de páginas a procesar.

    Returns:
        Texto extraído por OCR, o cadena vacía si el módulo no está disponible
        o si OCR también falla.
    """
    try:
        import pytesseract  # noqa: PLC0415
        from pdf2image import convert_from_path  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "PDF escaneado detectado pero pytesseract/pdf2image no están instalados. "
            "Para activar OCR: uv pip install pytesseract pdf2image"
        )
        return ""

    _configure_tesseract()

    # Verificar que idioma 'spa' está disponible; si no, usar solo 'eng'
    try:
        langs_disponibles = pytesseract.get_languages()
        lang = "spa+eng" if "spa" in langs_disponibles else "eng"
        if "spa" not in langs_disponibles:
            logger.warning(
                "Idioma 'spa' no disponible en Tesseract, usando solo 'eng'. "
                "Descargá spa.traineddata desde https://github.com/tesseract-ocr/tessdata"
            )
    except Exception:  # noqa: BLE001
        lang = "spa+eng"

    try:
        logger.info(
            "Iniciando OCR (%s) sobre %s (primeras %d páginas)", lang, pdf_path.name, max_pages
        )
        images = convert_from_path(str(pdf_path), first_page=1, last_page=max_pages, dpi=200)
        chunks: list[str] = []
        for i, img in enumerate(images, start=1):
            text = pytesseract.image_to_string(img, lang=lang) or ""
            if text.strip():
                chunks.append(f"--- Página {i} (OCR) ---\n\n{text.strip()}")
        result = "\n\n".join(chunks)
        if result:
            logger.info("OCR exitoso: %d caracteres extraídos de %s", len(result), pdf_path.name)
        else:
            logger.warning("OCR no produjo texto en %s", pdf_path.name)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR falló en %s: %s", pdf_path.name, exc)
        return ""


# ─────────────────────────────────────────────────────────────────
# Función principal de extracción
# ─────────────────────────────────────────────────────────────────

def extract_text(pdf_path: Path, max_pages: int | None = 30) -> str:
    """Extrae texto del PDF unido para enviarlo a la IA.

    Estrategia:
        1. pdfplumber con ``layout=True`` → preserva multi-columna.
        2. Extrae y agrega tablas por página.
        3. Limpia artefactos (números de página, watermarks, whitespace).
        4. Si la densidad de texto es < ``_MIN_CHARS_PER_PAGE`` chars/página
           → el PDF probablemente está escaneado → fallback OCR con pytesseract.

    Args:
        pdf_path: PDF a procesar (el merged que incluye los 3 PDFs).
        max_pages: tope defensivo. ``None`` = sin límite (para informe completo).

    Returns:
        Texto plano concatenado, separado por ``"\\n\\n--- Página N ---\\n\\n"``.
        Cadena vacía solo si tanto la extracción digital como el OCR fallaron.

    Raises:
        FileNotFoundError: si el PDF no existe.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")

    chunks: list[str] = []
    pages_processed = 0

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if max_pages is not None and total_pages > max_pages:
            logger.warning(
                "PDF con %d páginas, truncando a %d (path=%s)",
                total_pages,
                max_pages,
                pdf_path.name,
            )
        limit = total_pages if max_pages is None else min(total_pages, max_pages)

        for idx in range(limit):
            try:
                page_text = _extract_page_text(pdf.pages[idx])
            except (ValueError, OSError) as exc:
                logger.warning(
                    "Error extrayendo texto de página %d en %s: %s",
                    idx + 1,
                    pdf_path.name,
                    exc,
                )
                continue

            pages_processed += 1
            if not page_text.strip():
                continue
            chunks.append(f"--- Página {idx + 1} ---\n\n{page_text}")

    raw_text = "\n\n".join(chunks)
    cleaned  = _clean_text(raw_text)

    # Detección de PDF escaneado: si la densidad de texto es muy baja, intentar OCR.
    if pages_processed > 0:
        avg_chars = len(cleaned) / pages_processed
        if avg_chars < _MIN_CHARS_PER_PAGE:
            logger.warning(
                "PDF posiblemente escaneado (%.0f chars/página promedio, umbral=%d). "
                "Activando OCR en %s",
                avg_chars,
                _MIN_CHARS_PER_PAGE,
                pdf_path.name,
            )
            ocr_text = _try_ocr(pdf_path, max_pages)
            if ocr_text:
                return _clean_text(ocr_text)
            # Si OCR también falla, devolver lo poco que se extrajo
            logger.error(
                "Sin texto utilizable en %s. La IA recibirá contexto mínimo.",
                pdf_path.name,
            )

    if not cleaned:
        logger.warning(
            "No se pudo extraer texto de %s (¿PDF escaneado sin OCR configurado?)",
            pdf_path.name,
        )

    return cleaned


# ─────────────────────────────────────────────────────────────────
# Slug y renombrado
# ─────────────────────────────────────────────────────────────────

def slug_from_subject(asunto: str) -> str:
    """Genera un slug de archivo a partir del asunto de la notificación.

    Reglas aplicadas en orden:
        1. Quitar prefijo "NOTIFICACIÓN DE " (con/sin tilde, case-insensitive).
        2. Normalizar Unicode (NFKD) y descartar diacríticos.
        3. Reemplazar ``N°`` / ``N º`` por nada (preferimos limpiar).
        4. Reemplazar ``/`` y espacios por ``-``.
        5. Eliminar caracteres no alfanuméricos excepto ``-``, ``_`` y ``.``.
        6. Colapsar guiones consecutivos y trimear bordes.
        7. Truncar a 100 caracteres.
        8. Si el resultado queda vacío, devolver ``"documento"``.

    Examples:
        >>> slug_from_subject(
        ...     "NOTIFICACIÓN DE CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV"
        ... )
        'CARTA-000476-CR-2026-SUTRAN-06.3.4-SGFSV'
        >>> slug_from_subject("Notificacion Electronica MTC.")
        'Electronica-MTC.'
        >>> slug_from_subject("")
        'documento'

    Args:
        asunto: asunto crudo de la notificación.

    Returns:
        Slug seguro para usar como nombre de archivo (sin extensión).
    """
    if not asunto:
        return "documento"

    text = asunto.strip()

    # 1) Quitar prefijo "NOTIFICACIÓN DE ".
    text = _RE_PREFIJO_NOTIF.sub("", text)

    # 2) Normalizar Unicode y descartar diacríticos.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # 3) Quitar marcadores "N°" / "N º".
    text = re.sub(r"N\s*[°ºo]\s*", "", text, flags=re.IGNORECASE)

    # 4) Reemplazar separadores por guion.
    text = text.replace("/", "-").replace("\\", "-")
    text = re.sub(r"\s+", "-", text)

    # 5) Eliminar caracteres no permitidos.
    text = _RE_SLUG_INVALIDOS.sub("", text)

    # 6) Colapsar guiones y trimear bordes.
    text = _RE_GUIONES_DUPLICADOS.sub("-", text)
    text = text.strip("-_.")

    # 7) Truncar.
    if len(text) > _SLUG_MAX_LEN:
        text = text[:_SLUG_MAX_LEN].rstrip("-_.")

    # 8) Fallback si quedó vacío.
    if not text:
        return "documento"

    return text


def rename_merged(merged_pdf: Path, asunto: str) -> Path:
    """Renombra el PDF unido a ``<slug>.pdf`` derivado del asunto.

    Si en el destino ya existe un archivo con el mismo nombre, agrega un
    sufijo incremental: ``-2.pdf``, ``-3.pdf``, etc. (hasta 999).

    Args:
        merged_pdf: PDF unido (ej: ``merged.pdf``).
        asunto: asunto del cual derivar el nombre.

    Returns:
        Nuevo path del PDF renombrado.

    Raises:
        FileNotFoundError: si ``merged_pdf`` no existe.
    """
    if not merged_pdf.exists():
        raise FileNotFoundError(f"No existe el PDF unido: {merged_pdf}")

    slug = slug_from_subject(asunto)
    target = merged_pdf.with_name(f"{slug}.pdf")

    if target.resolve() == merged_pdf.resolve():
        return merged_pdf

    counter = 2
    while target.exists():
        target = merged_pdf.with_name(f"{slug}-{counter}.pdf")
        counter += 1
        if counter > _RENAME_MAX_COLISIONES:
            raise OSError(
                f"No se pudo encontrar un nombre libre para '{slug}.pdf' "
                f"en {merged_pdf.parent} (más de {_RENAME_MAX_COLISIONES} "
                f"colisiones)."
            )

    merged_pdf.rename(target)
    logger.info("PDF renombrado: %s → %s", merged_pdf.name, target.name)
    return target
