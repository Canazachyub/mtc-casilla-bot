---
name: obsidian-writer
description: |
  Workflow para generar notas Markdown en la bóveda Obsidian del usuario
  (carpeta RESOLVE) a partir de notificaciones MTC procesadas. Activá esta
  skill cuando se mencione: escribir nota Obsidian, generar markdown del
  reporte, frontmatter YAML, bóveda RESOLVE, tags Obsidian, Dataview.
  Cubre: estructura de carpetas por año/mes, frontmatter compatible Dataview,
  links a PDFs adjuntos, prevención de overwrites accidentales.
---

# Skill: Obsidian Writer

## Objetivo

Convertir un `Notification + ExtractionResult` en una nota Markdown lista para Obsidian, con frontmatter YAML que Dataview pueda consultar.

## Bóveda destino

```
C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE\
```

> En Linux puede estar montada en otro path. Siempre leer de `OBSIDIAN_VAULT_PATH` en `.env`. NUNCA hardcodear.

## Estructura de carpetas

```
RESOLVE/
├── 2026/
│   ├── 04-Abril/
│   │   ├── 2026-04-28_CARTA-N-000476-CR-2026-SUTRAN.md
│   │   └── 2026-04-29_OFICIO-N-1234-MTC-DGAT.md
│   └── 05-Mayo/
└── _index/
    ├── pendientes.md         (Dataview con todas las notas requiere_respuesta=true)
    └── vencidos.md           (Dataview con plazo_vencimiento < hoy)
```

### Lógica de path

```python
from datetime import date
from pathlib import Path

MESES_ES = {
    1: "01-Enero", 2: "02-Febrero", 3: "03-Marzo", 4: "04-Abril",
    5: "05-Mayo", 6: "06-Junio", 7: "07-Julio", 8: "08-Agosto",
    9: "09-Setiembre", 10: "10-Octubre", 11: "11-Noviembre", 12: "12-Diciembre",
}

def build_note_path(vault_root: Path, notif_date: date, doc_slug: str) -> Path:
    year_folder = str(notif_date.year)
    month_folder = MESES_ES[notif_date.month]
    filename = f"{notif_date.isoformat()}_{doc_slug}.md"
    return vault_root / year_folder / month_folder / filename
```

## Plantilla de la nota

````markdown
---
tipo: notificacion-mtc
fecha_notificacion: 2026-04-28
documento: "CARTA N° 000476-CR-2026-SUTRAN"
documento_slug: CARTA-N-000476-CR-2026-SUTRAN
ruc: "20602194958"
empresa: "CENTRO DE INSPECCIÓN TÉCNICA VEHICULAR ESPINAR SAC"
emisor: SUTRAN
fecha_documento: 2026-04-26
asunto: "Solicitud de remisión de expedientes técnicos"
requiere_respuesta: true
plazo_dias_habiles: 5
plazo_vencimiento: 2026-05-06
estado: pendiente
confianza_ia: alta
modelo_ia: deepseek-chat
pdf_path: "../../../data/merged/20602194958/CARTA-N-000476-CR-2026-SUTRAN.pdf"
tags:
  - casilla-mtc
  - sutran
  - citv
  - pendiente
  - "20602194958"
---

# 📬 CARTA N° 000476-CR-2026-SUTRAN

> **Notificada:** 28 de abril de 2026 · **Vence:** 6 de mayo de 2026 (en 5 días hábiles)
> **Empresa:** CENTRO DE INSPECCIÓN TÉCNICA VEHICULAR ESPINAR SAC (RUC 20602194958)

## 📋 Resumen ejecutivo

Saludos cordiales, en fecha 28 de abril de 2026, se notificó la CARTA N° 000476-CR-2026-SUTRAN, en la que SUTRAN solicita remitir los expedientes técnicos de veintitrés (23) vehículos, y las filmaciones de las inspecciones técnicas de cuatro (4) vehículos, brindando el plazo de 05 días hábiles.

## ⏰ Plazo

| Concepto | Valor |
|---|---|
| **Días hábiles** | 5 |
| **Vence** | martes 6 de mayo de 2026 |
| **Días restantes** | `=dateformat(date(2026-05-06) - date(today), "d")` días |
| **Estado** | 🟡 Pendiente |

## 🎯 Acciones requeridas

- [ ] Remitir expedientes técnicos de 23 vehículos
- [ ] Presentar filmaciones de inspecciones técnicas de 4 vehículos

## 📚 Referencias normativas

- Resolución Directoral N° 12-2021-MTC/18
- D.S. N° 025-2008-MTC

## 📎 Adjuntos

- 📄 [PDF unido](file:///C:/Users/User/Documents/CEREBRO%20DIGITAL/RESOLVE/RESOLVE/../../data/merged/20602194958/CARTA-N-000476-CR-2026-SUTRAN.pdf)
- 🔗 [Ver en Casilla MTC](https://casilla.mtc.gob.pe/#/recibidos)

## 🤖 Análisis IA

| Campo | Valor |
|---|---|
| Modelo | deepseek-chat |
| Confianza | alta |
| Notas del modelo | (sin observaciones) |

---

## 📝 Notas adicionales

<!-- Espacio para notas manuales del equipo -->


---

> *Generado automáticamente por mtc-casilla-bot el 2026-04-28 15:42:00*
````

## Implementación

```python
from pathlib import Path
from datetime import date
import yaml
from jinja2 import Environment, FileSystemLoader

def write_note(
    vault_path: Path,
    notification: Notification,
    extraction: ExtractionResult,
    pdf_relative: str,
    summary: str,
    overwrite: bool = False,
) -> Path:
    """Escribe la nota en la bóveda. Devuelve el path final."""
    note_path = build_note_path(
        vault_path, notification.date, slugify(extraction.documento_nombre)
    )

    if note_path.exists() and not overwrite:
        # No sobrescribir; usar sufijo
        i = 2
        while note_path.exists():
            note_path = note_path.with_stem(f"{note_path.stem}_v{i}")
            i += 1

    note_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "tipo": "notificacion-mtc",
        "fecha_notificacion": notification.date.isoformat(),
        "documento": extraction.documento_nombre,
        "documento_slug": slugify(extraction.documento_nombre),
        "ruc": notification.ruc,
        "empresa": notification.empresa,
        "emisor": extraction.emisor,
        "fecha_documento": (
            extraction.fecha_documento.isoformat() if extraction.fecha_documento else None
        ),
        "asunto": extraction.asunto,
        "requiere_respuesta": extraction.requiere_respuesta,
        "plazo_dias_habiles": extraction.plazo_dias_habiles,
        "plazo_vencimiento": (
            calc_vencimiento(notification.date, extraction.plazo_dias_habiles).isoformat()
            if extraction.plazo_dias_habiles else None
        ),
        "estado": "pendiente" if extraction.requiere_respuesta else "informativo",
        "confianza_ia": extraction.confianza,
        "modelo_ia": notification.modelo_usado,
        "pdf_path": pdf_relative,
        "tags": [
            "casilla-mtc",
            extraction.emisor.lower(),
            "citv",
            "pendiente" if extraction.requiere_respuesta else "informativo",
            notification.ruc,
        ],
    }

    body = render_template("note.md.j2", {
        "fm": frontmatter,
        "summary": summary,
        "extraction": extraction,
        "notification": notification,
    })

    final_content = f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body}"
    note_path.write_text(final_content, encoding="utf-8")
    return note_path
```

## Slugify (compatible con Obsidian)

```python
import re

def slugify(text: str) -> str:
    """Convierte texto a slug válido para Obsidian (sin caracteres problemáticos)."""
    text = text.replace("°", "-N-").replace("º", "-N-")
    text = re.sub(r"[^\w\s-]", "", text)  # quitar puntuación
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-").upper()
```

## Reglas de overwrite

| Caso | Acción |
|---|---|
| Nota nueva | Crear sin más |
| Misma notificación, mismo contenido | NO escribir, logguear "ya existe" |
| Misma notificación, contenido distinto | Crear con sufijo `_v2`, NO sobrescribir |
| `--force` flag CLI | Sobrescribir con backup `.bak` previo |

## Notas índice (Dataview)

Generar **una vez** dos notas en `_index/`:

### `_index/pendientes.md`

````markdown
# 🔥 Notificaciones MTC pendientes

```dataview
TABLE
  fecha_notificacion AS "Notificada",
  documento AS "Documento",
  empresa AS "Empresa",
  plazo_vencimiento AS "Vence",
  (date(plazo_vencimiento) - date(today)).days AS "Días restantes"
FROM "2026" OR "2025"
WHERE tipo = "notificacion-mtc"
  AND requiere_respuesta = true
  AND estado = "pendiente"
SORT plazo_vencimiento ASC
```
````

### `_index/vencidos.md`

````markdown
# ⚠️ Plazos vencidos

```dataview
TABLE WITHOUT ID
  file.link AS "Notificación",
  empresa AS "Empresa",
  plazo_vencimiento AS "Venció",
  (date(today) - date(plazo_vencimiento)).days AS "Días vencido"
FROM "2026" OR "2025"
WHERE tipo = "notificacion-mtc"
  AND requiere_respuesta = true
  AND date(plazo_vencimiento) < date(today)
  AND estado != "completado"
SORT plazo_vencimiento DESC
```
````

## Validación pre-escritura

- [ ] La carpeta de la bóveda existe y es escribible
- [ ] El nombre de archivo no excede 255 chars
- [ ] El YAML del frontmatter es serializable (no tiene objetos Python no-primitivos)
- [ ] Los paths a PDFs son relativos a la bóveda (no absolutos), salvo el link `file://`

## Tests sugeridos

- `test_build_note_path` — verifica estructura año/mes
- `test_slugify` — casos edge con acentos y símbolos
- `test_write_note_no_overwrite` — versión `_v2` cuando ya existe
- `test_frontmatter_yaml_valid` — parsea como YAML válido
- `test_dataview_query_compatible` — campos clave presentes
