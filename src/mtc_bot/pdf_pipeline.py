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

# Patrones para clasificar por nombre (case-insensitive). Los nombres reales
# que llegan del portal MTC son del estilo:
#   - "Constancia_Deposito_11542476.pdf"
#   - "Constancia_Notificacion_11542476.pdf"
#   - "Constancia_Lectura_11542476.pdf"
#   - "000476-CR-2026-SUTRAN-06.3.4-SGFSV.pdf" (documento principal)
_RE_CONSTANCIA_LECTURA = re.compile(
    r"constancia[_\s\-]*(?:de[_\s\-]*)?lectura",
    re.IGNORECASE,
)
_RE_CONSTANCIA_NOTIF = re.compile(
    r"constancia[_\s\-]*(?:de[_\s\-]*)?(?:notificacion|notificación|deposito|depósito)",
    re.IGNORECASE,
)
_RE_ANEXO = re.compile(r"\banexo\b", re.IGNORECASE)

# Prefijo "NOTIFICACIÓN DE " (con o sin tilde, mayús/minús, espacios variables).
_RE_PREFIJO_NOTIF = re.compile(
    r"^\s*notificaci[oó]n\s+de\s+",
    re.IGNORECASE,
)

# Caracteres permitidos en el slug final.
_RE_SLUG_INVALIDOS = re.compile(r"[^A-Za-z0-9._\-]")
_RE_GUIONES_DUPLICADOS = re.compile(r"-{2,}")

_SLUG_MAX_LEN = 100

# Tope defensivo para evitar bucles infinitos al renombrar con sufijo
# incremental cuando ya existen archivos con el slug deseado.
_RENAME_MAX_COLISIONES = 999


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
    """Detecta el rol de un PDF a partir de su nombre.

    Args:
        filename: nombre del archivo (sin importar el path).
        has_main: si ya se asignó un ``documento_principal``. Si ``True``, el
            siguiente "documento sin clasificar" se etiqueta como ``anexo``.

    Returns:
        El rol asignado.
    """
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
        Lista de :class:`ClassifiedPdf` en el mismo orden de entrada (sin
        reordenar). El reordenamiento para el merge se hace en
        :func:`merge_pdfs`.
    """
    classified: list[ClassifiedPdf] = []
    has_main = False
    for path in pdf_paths:
        role = _classify_one(path.name, has_main=has_main)
        if role == "documento_principal":
            has_main = True
        classified.append(ClassifiedPdf(path=path, role=role))
    return classified


# Orden de mezcla por rol — números más bajos van primero.
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

    Si falta alguno de los roles "esperados" (constancias), se registra un
    warning y se une lo disponible. Si NO hay documento principal, se falla
    con :class:`ValueError`.

    Args:
        pdf_paths: lista de PDFs a unir (cualquier orden de entrada).
        output: path destino del PDF unido. Se crea el directorio padre si
            no existe.

    Returns:
        El path ``output`` si la operación fue exitosa.

    Raises:
        ValueError: si la lista está vacía o no hay documento principal.
        OSError: si falla la lectura de algún PDF o la escritura del destino.
    """
    if not pdf_paths:
        raise ValueError("Lista de PDFs vacía: nada que unir.")

    classified = classify_pdfs(pdf_paths)

    # Validación: tiene que haber al menos un documento principal.
    if not any(c.role == "documento_principal" for c in classified):
        raise ValueError(
            "No se detectó documento principal entre los PDFs. "
            f"Archivos recibidos: {[p.name for p in pdf_paths]}"
        )

    # Warnings por roles esperados ausentes.
    if not any(c.role == "constancia_notificacion" for c in classified):
        logger.warning(
            "Merge sin constancia de notificación electrónica (output=%s)",
            output.name,
        )
    if not any(c.role == "constancia_lectura" for c in classified):
        logger.warning(
            "Merge sin constancia de lectura (output=%s)",
            output.name,
        )

    # Orden estricto: por rol y luego alfabético por nombre.
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


def extract_text(pdf_path: Path, max_pages: int = 30) -> str:
    """Extrae texto del PDF unido usando :mod:`pdfplumber`.

    Si una página falla en extraerse (PDF mal formado, página escaneada sin
    texto), se registra un warning y se continúa con la siguiente.

    Args:
        pdf_path: PDF a procesar.
        max_pages: tope defensivo. PDFs más largos se truncan.

    Returns:
        Texto plano concatenado, separado por
        ``"\\n\\n--- Página N ---\\n\\n"``. Cadena vacía si no se pudo extraer
        nada (probable PDF escaneado).

    Raises:
        FileNotFoundError: si el PDF no existe.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")

    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if total_pages > max_pages:
            logger.warning(
                "PDF con %d páginas, truncando a %d (path=%s)",
                total_pages,
                max_pages,
                pdf_path.name,
            )
        limit = min(total_pages, max_pages)
        for idx in range(limit):
            try:
                page_text = pdf.pages[idx].extract_text() or ""
            except (ValueError, OSError) as exc:
                logger.warning(
                    "Error extrayendo texto de página %d en %s: %s",
                    idx + 1,
                    pdf_path.name,
                    exc,
                )
                continue
            if not page_text.strip():
                continue
            chunks.append(f"--- Página {idx + 1} ---\n\n{page_text}")

    if not chunks:
        logger.warning(
            "No se pudo extraer texto de %s (¿PDF escaneado sin OCR?)",
            pdf_path.name,
        )

    return "\n\n".join(chunks)


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

    # 3) Quitar marcadores "N°" / "N º" (con o sin espacio).
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
