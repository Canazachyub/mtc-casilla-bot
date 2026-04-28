# 📋 Catálogo de Plantillas — MTC Casilla Bot

> Este documento se completa en **Fase 2** cuando se importen las plantillas reales del equipo legal.
> Mantenelo actualizado: cada vez que se agrega/modifica una plantilla, actualizar esta tabla.

---

## Plantillas activas

> Llenar cuando templates-agent importe las primeras plantillas reales.

| ID | Nombre | Emisor | Tipo doc | Score promedio | Última edición |
|---|---|---|---|---|---|
| _(vacío)_ | _(pendiente Fase 2)_ | | | | |

### Ejemplo de cómo se verá:

| ID | Nombre | Emisor | Tipo doc | Score promedio | Última edición |
|---|---|---|---|---|---|
| `sutran-solicitud-expedientes` | Respuesta a solicitud de expedientes técnicos | SUTRAN | CARTA, OFICIO | 125 | 2026-04-28 |
| `sutran-descargo-observacion` | Descargo de observación SUTRAN | SUTRAN | OFICIO | 95 | 2026-04-28 |
| `mtc-dgat-presentacion-doc` | Presentación de documentos a DGAT | MTC/DGAT | OFICIO | 80 | 2026-04-28 |
| `generica-acuse-recibo` | Acuse de recibo genérico | (cualquiera) | (cualquiera) | 30 | 2026-04-28 |

---

## Estructura de cada plantilla

Cada `.md` en `RESOLVE/_templates/` tiene:

```yaml
---
template_id: <kebab-case>
nombre: "Descripción legible"
emisor: SUTRAN | MTC | MTC/DGAT | (omitir para genéricas)
tipo_documento: [CARTA, OFICIO, INFORME, RESOLUCION]
keywords_match:
  - palabra clave 1
  - frase exacta a buscar
acciones_match:
  - patrón de acción
prioridad: 1-100  (mayor = se prefiere en empates)
placeholders:
  - lista_de_placeholders
---

Cuerpo de la plantilla con {{placeholders}}.
```

---

## Workflow para agregar una plantilla

1. **Importar** el documento de respuesta real (Word/PDF) que ya use el equipo.
2. **Identificar** partes fijas vs variables.
3. **Convertir** variables a `{{snake_case}}`.
4. **Definir** frontmatter (emisor, keywords, acciones, prioridad).
5. **Probar** con `mtc-bot debug-match --notification-id <ID>` contra ≥3 notificaciones reales.
6. **Iterar** scoring si no matchea bien.
7. **Guardar** en `RESOLVE/_templates/<id>.md`.
8. **Sincronizar** a Drive: `mtc-bot templates sync`.
9. **Actualizar** este catálogo.

---

## Reglas de matching

- Score mínimo: **30 puntos** (configurable en `.env`).
- Score alta calidad: **≥100 puntos** → propuesta sale como 🟢 alta confianza.
- Si NINGUNA plantilla matchea → fallback a `generica-acuse-recibo` con `prioridad=1`.
- `emisor` es **filtro fuerte**: si la plantilla tiene emisor definido y no coincide, score = 0.

---

## Placeholders comunes

### Directos (Python rellena sin IA)

| Placeholder | Origen | Formato |
|---|---|---|
| `{{empresa}}` | rucs.csv | "CITV ESPINAR SAC" |
| `{{empresa_corta}}` | rucs.csv (primera palabra) | "CITV" |
| `{{ruc}}` | rucs.csv | "20602194958" |
| `{{representante_legal}}` | rucs.csv | "Juan Pérez Mamani" |
| `{{documento_referencia}}` | extracción IA | "CARTA N° 000476-CR-2026-SUTRAN" |
| `{{fecha_notificacion}}` | notificación | "28/04/2026" |
| `{{fecha_actual}}` | hoy | "28 de abril de 2026" |
| `{{plazo_dias_habiles}}` | extracción IA | "5" |
| `{{fecha_vencimiento}}` | calculado | "06/05/2026" |
| `{{anio}}` | hoy | "2026" |

### Inferenciales (IA rellena con segunda llamada)

Estos cambian según el documento. Ejemplos:

- `{{cantidad_vehiculos}}` — "veintitrés (23)"
- `{{tipo_archivos}}` — "expedientes técnicos"
- `{{numero_resolucion}}` — "Resolución N° 12-2021-MTC/18"
- `{{articulos_observados}}` — "los artículos 5°, 7° y 12°"
- `{{descargo_breve}}` — "esta empresa cumple con los requisitos..."

### Manuales (placeholder queda como `[X]` para que el usuario complete)

- `{{numero_correlativo}}` — número de oficio interno (correlativo de TELCOM)
- `{{archivos_adjuntos}}` — lista de qué se adjunta

---

## Ejemplo de plantilla (referencia)

Ver [`.claude/skills/response-generator/SKILL.md`](../.claude/skills/response-generator/SKILL.md) sección "Formato de plantilla".

---

## Métricas de calidad (cuando esté en uso)

> Llenar después de Fase 2 con datos reales.

- **Tasa de matching exitoso:** `<X>%` de notificaciones encuentran plantilla con score ≥ 30
- **Confianza promedio:** `<X>` (escala alta=3, media=2, baja=1)
- **Plantillas más usadas:**
  1. ...
  2. ...
- **Plantillas sin uso en 30 días:** considerar archivar

---

## Default representante legal

**Mirella Shirley Camapaza Quispe** (editar en `_templates/_defaults.yaml` si cambia).

> Aplica al placeholder `{{representante_legal}}` cuando el RUC en
> `data/credentials/rucs.csv` no especifica uno propio. El archivo
> `_templates/_defaults.yaml` se creará en Fase 2; por ahora este valor
> queda documentado acá y en el README de la carpeta `_templates/` en la
> bóveda Obsidian.
