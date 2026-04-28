---
name: pdf-pipeline
description: |
  Workflow para manipulación de PDFs en el bot MTC: unión ordenada de adjuntos,
  renombrado según el nombre del documento, extracción de texto. Activá esta
  skill cuando el usuario mencione: merge PDF, unir PDFs, extraer texto de PDF,
  renombrar PDFs de notificaciones, ordenar constancias. NO usar para creación
  de PDFs desde cero, OCR, o firma digital.
---

# Skill: PDF Pipeline

## Objetivo

Tomar 3 o 4 PDFs descargados de una notificación MTC y producir UN solo PDF final con:
- Orden estricto de páginas
- Nombre derivado del documento principal
- Texto extraído para análisis IA

## Orden estricto del merge

**Esta regla es inviolable.** Cualquier desviación rompe el formato esperado por el equipo legal.

| Posición | Tipo de documento | Cómo identificarlo |
|---|---|---|
| **1°** (siempre) | Documento principal | NO contiene "constancia" en el nombre. Es el oficio/carta/informe/resolución sustantivo. |
| **2°** (si hay 4) | Anexo del documento | Cualquier PDF intermedio que no sea constancia. Mantener orden alfabético si hay varios. |
| **Penúltimo** | Constancia de Notificación Electrónica | Nombre contiene `Constancia_Deposito` o `Constancia de Notificación` |
| **Último** | Constancia de Lectura | Nombre contiene `Constancia_Lectura` o `Constancia de Lectura` |

### Lógica de clasificación

```python
from enum import IntEnum
from pathlib import Path

class PdfRole(IntEnum):
    """Orden de prioridad para el merge."""
    DOCUMENTO_PRINCIPAL = 1
    ANEXO = 2
    CONSTANCIA_NOTIFICACION = 8
    CONSTANCIA_LECTURA = 9

def classify_pdf(filename: str) -> PdfRole:
    """Determina el rol del PDF a partir del nombre del archivo."""
    name_lower = filename.lower()
    if "constancia_lectura" in name_lower or "constancia de lectura" in name_lower:
        return PdfRole.CONSTANCIA_LECTURA
    if "constancia_deposito" in name_lower or "constancia de notificacion" in name_lower:
        return PdfRole.CONSTANCIA_NOTIFICACION
    # Heurística: si tiene "Anexo" en el nombre, es anexo
    if "anexo" in name_lower:
        return PdfRole.ANEXO
    # Por defecto, asumir documento principal (suele ser el primero alfabéticamente)
    return PdfRole.DOCUMENTO_PRINCIPAL
```

> ⚠️ **Caso edge:** si hay múltiples archivos clasificados como `DOCUMENTO_PRINCIPAL`, conservar orden alfabético entre ellos. Si hay 0, fallar con error claro.

## Implementación de merge

```python
from pypdf import PdfWriter, PdfReader
from pathlib import Path

def merge_attachments(pdfs: list[Path], output_path: Path) -> Path:
    """Une los PDFs en el orden correcto y devuelve el path del archivo final."""
    if not pdfs:
        raise ValueError("Lista de PDFs vacía")

    # Ordenar por (rol, nombre) para tener determinismo
    sorted_pdfs = sorted(pdfs, key=lambda p: (classify_pdf(p.name), p.name))

    writer = PdfWriter()
    for pdf_path in sorted_pdfs:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            writer.add_page(page)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)

    return output_path
```

## Renombrado del archivo final

El nombre debe derivar del documento principal. Reglas:

1. **Sanitizar:** quitar caracteres inválidos para Windows: `<>:"/\|?*` y espacios duplicados.
2. **Reemplazar `°`** por `-N-` o por `-` simple. Ejemplo: `CARTA N° 000476-CR-2026` → `CARTA-N-000476-CR-2026`.
3. **Mayúsculas:** mantener el formato original del documento (suele estar en mayúsculas).
4. **Extensión:** `.pdf`.
5. **Longitud máxima:** 120 caracteres (margen para Windows MAX_PATH).

```python
import re

def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Convierte un nombre de documento a filename válido en Windows."""
    # Reemplazar el símbolo de grado/ordinal
    name = name.replace("°", "-N-").replace("º", "-N-")
    # Quitar caracteres inválidos
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    # Espacios y guiones múltiples
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "-")
    name = re.sub(r"-+", "-", name)
    # Truncar
    if len(name) > max_len:
        name = name[:max_len].rsplit("-", 1)[0]
    return name + ".pdf"
```

### Origen del nombre

El nombre del documento se obtiene de **dos fuentes**, en este orden de prioridad:

1. **Subject de la notificación en la casilla** (más confiable):
   `NOTIFICACIÓN DE CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV` → extraer `CARTA-N-000476-CR-2026-SUTRAN`
2. **Análisis IA del PDF unido** (fallback): el modelo extrae el `documento` del frontmatter.

Si ambas fuentes discrepan, **preferir el subject** y logguear la discrepancia para revisión manual.

## Extracción de texto

Para el análisis IA solo necesitamos el texto del **documento principal** (no de las constancias, que son repetitivas).

```python
import pdfplumber

def extract_text(pdf_path: Path, only_pages: range | None = None) -> str:
    """Extrae texto de un PDF. Si only_pages está dado, solo de esas páginas."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        page_indices = only_pages if only_pages else range(len(pdf.pages))
        for i in page_indices:
            if i < len(pdf.pages):
                txt = pdf.pages[i].extract_text() or ""
                pages_text.append(txt)
    return "\n\n".join(pages_text)
```

**Optimización:** extraer texto **solo del documento principal antes del merge** (no del PDF unido), porque las constancias agregan ruido al análisis.

## Caso especial: PDFs escaneados (sin texto extraíble)

Si `extract_text` devuelve un string vacío o muy corto (<100 chars) para un PDF de varias páginas, probablemente es un escaneo. Opciones:

1. **Avisar al usuario** (no fallar silenciosamente): logguear `WARNING: PDF parece escaneado, sin OCR`.
2. **Fallback a Gemini Vision:** Gemini puede leer PDFs escaneados como imágenes. En ese caso, mandar el PDF directo a Gemini en lugar del texto.
3. **No agregar OCR local** en esta versión (Tesseract complica el deploy en Windows). Documentar como limitación conocida.

## Validación post-merge

Antes de declarar el merge exitoso:

- [ ] El archivo final existe y tiene tamaño > 0
- [ ] Tiene al menos N páginas (sumar páginas de los inputs)
- [ ] La primera página corresponde al documento principal (heurística: contiene texto, no es solo una constancia)
- [ ] Si hay constancias, están al final (página N-1 y N)

```python
def validate_merge(merged_pdf: Path, expected_min_pages: int) -> bool:
    if not merged_pdf.exists() or merged_pdf.stat().st_size == 0:
        return False
    reader = PdfReader(merged_pdf)
    if len(reader.pages) < expected_min_pages:
        return False
    return True
```

## Tests sugeridos

- `test_classify_pdf` con varios nombres de archivo (con/sin acentos, mayúsculas/minúsculas)
- `test_sanitize_filename` con casos: símbolos `°`, espacios múltiples, caracteres inválidos Windows
- `test_merge_attachments_order` con 3 y 4 PDFs de fixture
- `test_merge_attachments_empty_raises`
- `test_extract_text_scanned_returns_empty`

## Estructura de carpetas resultantes

```
data/
├── downloads/
│   └── 20602194958/
│       └── 2026-04-28/
│           └── notif_476/
│               ├── 000476-CR-2026-SUTRAN-06.3.4-SGFSV.pdf
│               ├── Constancia_Deposito_11542476.pdf
│               └── Constancia_Lectura_11542476.pdf
└── merged/
    └── 20602194958/
        └── CARTA-N-000476-CR-2026-SUTRAN.pdf       ← OUTPUT FINAL
```
