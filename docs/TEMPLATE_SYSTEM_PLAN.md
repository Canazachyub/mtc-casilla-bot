# Plan: Sistema de Plantillas Avanzado con Google Docs

> **Estado:** Diseño — pendiente aprobación  
> **Scope:** Fase 2.5 — entre plantillas básicas (Fase 2) y respuestas automáticas (Fase 3)

---

## 1. Resumen del sistema

Cada plantilla es un **Google Doc** con `{{PLACEHOLDERS}}`. Cuando el usuario genera una respuesta:

1. Apps Script **copia** el Doc original (no lo modifica)
2. Reemplaza todos los `{{PLACEHOLDER}}` con datos reales de la notificación
3. `{{RESPUESTA_IA}}` es reemplazado por el texto generado por **DeepSeek**
4. Exporta la copia como `.docx` (base64)
5. La copia temporal se **elimina** automáticamente
6. El browser descarga el `.docx` completo listo para enviar

**¿Cuántas plantillas?** Sin límite práctico. 20 plantillas × N entidades = filas en el Sheet. Funciona igual con 5 o 500.

---

## 2. Estructura de placeholders

### 2.1 Placeholders automáticos (de los datos de la notificación)

| Placeholder | Fuente | Ejemplo |
|---|---|---|
| `{{EMPRESA}}` | `detail.empresa` | CITV ESPINAR SAC |
| `{{RUC}}` | `detail.ruc` | 20602194958 |
| `{{CIUDAD}}` | deducido del RUC/empresa | Espinar, Cusco |
| `{{FECHA_HOY}}` | fecha actual | 15/05/2026 |
| `{{ANIO}}` | año actual | 2026 |
| `{{FECHA_NOTIFICACION}}` | `detail.fecha_notificacion` | 10/05/2026 |
| `{{NUMERO_DOCUMENTO}}` | `detail.numero_documento` | 001026-CR-2026 |
| `{{TIPO_DOCUMENTO}}` | `detail.tipo_documento` | CARTA |
| `{{EMISOR}}` | `detail.emisor` | SUTRAN |
| `{{ASUNTO}}` | `detail.asunto` | Solicita expedientes... |
| `{{PLAZO_VENCIMIENTO}}` | `detail.plazo_vencimiento` | 20/05/2026 |
| `{{NUMERO_RESPUESTA}}` | generado automático | 001 |
| `{{REPRESENTANTE_LEGAL}}` | campo del Sheet `rucs` o manual | Juan Pérez Torres |

### 2.2 Placeholders manuales (el usuario los ingresa en el panel)

| Placeholder | Descripción | Quién lo llena |
|---|---|---|
| `{{JUSTIFICACION}}` | Argumentos del representante legal | Trabajador (textarea) |
| `{{NUMERO_RESPUESTA_MANUAL}}` | Si quiere numerar manualmente | Trabajador (input) |
| `{{OBSERVACIONES}}` | Notas adicionales | Trabajador (opcional) |

### 2.3 Placeholder IA (generado por DeepSeek)

| Placeholder | Descripción |
|---|---|
| `{{RESPUESTA_IA}}` | Sección completa reescrita por DeepSeek (1–3 páginas) |

> **Regla:** Un Doc puede tener TODOS los placeholders automáticos + 1 `{{RESPUESTA_IA}}` + los manuales que quiera.

---

## 3. Catálogo de plantillas (20 tipos)

Cada plantilla se almacena en la pestaña `plantillas` del Sheet con su propio Google Doc.

### Categorías sugeridas

| # | ID | Nombre | Tipo documento que activa |
|---|---|---|---|
| 1 | `descargo-carta` | Descargo ante Carta SUTRAN | CARTA |
| 2 | `descargo-informe` | Descargo ante Informe SUTRAN | INFORME |
| 3 | `descargo-resolucion` | Descargo ante Resolución | RESOLUCIÓN |
| 4 | `solicitud-expediente` | Solicitud de acceso al expediente | general |
| 5 | `solicitud-prorroga` | Solicitud de prórroga de plazo | general |
| 6 | `cumplimiento-subsanacion` | Carta de cumplimiento / subsanación | RESOLUCIÓN |
| 7 | `cumplimiento-levantamiento` | Levantamiento de observaciones | CARTA/INFORME |
| 8 | `apelacion-sancion` | Apelación ante sanción económica | RESOLUCIÓN |
| 9 | `recurso-reconsideracion` | Recurso de reconsideración | RESOLUCIÓN |
| 10 | `recurso-apelacion` | Recurso de apelación ante segunda instancia | RESOLUCIÓN |
| 11 | `presentacion-documentos` | Presentación de documentos sustentatorios | general |
| 12 | `justificacion-incumplimiento` | Justificación de incumplimiento temporal | CARTA |
| 13 | `informacion-cronograma` | Información de cronograma de inspecciones | CARTA |
| 14 | `acreditacion-equipos` | Acreditación de equipos calibrados | INFORME |
| 15 | `acreditacion-personal` | Acreditación de personal certificado | INFORME |
| 16 | `comunicado-suspension` | Comunicado de suspensión temporal de operaciones | general |
| 17 | `solicitud-inspeccion` | Solicitud de nueva fecha de inspección | general |
| 18 | `respuesta-fiscalizacion` | Respuesta a acción de fiscalización | ACTA |
| 19 | `descargo-acta` | Descargo ante Acta de Fiscalización | ACTA |
| 20 | `comunicado-reinicio` | Comunicado de reinicio de operaciones | general |

> Podés agregar/quitar/renombrar. El sistema no tiene límite.

---

## 4. Schema actualizado: pestaña `plantillas`

| Columna | Descripción | Ejemplo |
|---|---|---|
| `id` | ID único | `descargo-carta` |
| `nombre` | Nombre legible | Descargo ante Carta SUTRAN |
| `descripcion` | Descripción breve | Descargo estándar para cartas de SUTRAN |
| `tipo_documento` | Filtra por tipo de notificación | `carta`, `informe`, `resolucion`, `general` |
| `google_doc_id` | ID del Google Doc base | `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms` |
| `seccion_ia` | Descripción de qué debe generar DeepSeek | "Redactar sección II Fundamentos del Descargo" |
| `campos_manuales` | Campos adicionales que el usuario debe ingresar (JSON) | `["REPRESENTANTE_LEGAL","NUMERO_RESPUESTA"]` |
| `activo` | Si aparece en el dropdown | `TRUE` |

---

## 5. Panel de respuesta actualizado (frontend)

```
┌─────────────────────────────────────────────────────────┐
│ ✍️ Generar Respuesta                                     │
├─────────────────────────────────────────────────────────┤
│ Notificación: CARTA N° 001026-CR-2026-SUTRAN            │
│                                                         │
│ [1] Plantilla: [Descargo ante Carta SUTRAN ▼]           │
│                                                         │
│ [2] Campos del documento:                               │
│     Representante Legal: [________________]             │
│     N° de respuesta:     [001            ]              │
│                                                         │
│ [3] Instrucciones para la IA:                           │
│     ┌─────────────────────────────────────────────┐     │
│     │ Describí qué debe escribir DeepSeek en la   │     │
│     │ sección {{RESPUESTA_IA}} del documento...   │     │
│     └─────────────────────────────────────────────┘     │
│                                                         │
│ [✨ Generar y armar documento]                           │
│                                                         │
│ ──── Vista previa del texto IA ────                     │
│ ┌─────────────────────────────────────────────────┐     │
│ │ (editable — solo la sección generada)           │     │
│ └─────────────────────────────────────────────────┘     │
│                                                         │
│ [⬇ Descargar Word completo (31 págs.)]                  │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Flujo Apps Script

```javascript
// handleGenerateResponse_ actualizado
1. Leer notificación del Sheet (detail)
2. Obtener template del Sheet (google_doc_id, seccion_ia)
3. Llamar DeepSeek → genera texto para {{RESPUESTA_IA}}
4. Copiar Google Doc → DriveApp.getFileById(docId).makeCopy()
5. Abrir copia → DocumentApp.openById(copyId)
6. Reemplazar TODOS los {{PLACEHOLDER}} en el cuerpo:
   - Body.replaceText('{{EMPRESA}}', detail.empresa)
   - Body.replaceText('{{RUC}}', detail.ruc)
   - ... (todos los automáticos)
   - Body.replaceText('{{RESPUESTA_IA}}', textoGenerado)
7. Guardar y cerrar el Doc
8. Exportar como .docx → DriveApp.getFileById(copyId)
                              .getAs('application/vnd...wordprocessingml...')
9. Convertir a base64 → Utilities.base64Encode(blob.getBytes())
10. Eliminar la copia → DriveApp.getFileById(copyId).setTrashed(true)
11. Retornar { ok, respuesta_ia, docx_base64, filename }
```

---

## 7. Cómo preparar cada Google Doc

1. Creá el Doc normalmente en Google Drive con el formato completo (logo, membrete, 30 páginas)
2. Donde va la sección variable, escribí `{{RESPUESTA_IA}}`
3. Donde va el nombre de la empresa: `{{EMPRESA}}`
4. Para la fecha: `{{FECHA_HOY}}`
5. Para el número de documento que llegó: `{{NUMERO_DOCUMENTO}}`
6. Para el número de tu respuesta: `{{NUMERO_RESPUESTA}}`
7. (etc. según la tabla de placeholders arriba)
8. Copiá el ID del Doc (URL: `docs.google.com/document/d/**ESTE_ID**/edit`)
9. Pegalo en la columna `google_doc_id` del Sheet

> **Importante:** El Doc debe estar en el Drive del mismo usuario que desplegó el Apps Script (canazach12@gmail.com). Permisos: al menos "Editor".

---

## 8. Fases de implementación

### Fase A — Base (1 sesión) ✅ ya hecho
- [x] Plantillas en Sheet con texto template
- [x] DeepSeek llena los corchetes
- [x] Descarga Word básico

### Fase B — Google Docs como base (siguiente)
- [ ] Agregar columnas `google_doc_id`, `seccion_ia`, `campos_manuales` al Sheet
- [ ] Actualizar `handleGenerateResponse_` para copiar el Doc y reemplazar placeholders
- [ ] Actualizar frontend: inputs dinámicos para `campos_manuales`
- [ ] Descargar el `.docx` completo (base64 → saveAs)
- [ ] Prueba con 1 plantilla real

### Fase C — Catálogo completo (2–3 sesiones)
- [ ] 20 Google Docs preparados por Yubert
- [ ] 20 filas en pestaña `plantillas`
- [ ] Filtro automático por `tipo_documento` (solo muestra plantillas relevantes)
- [ ] Campo `representante_legal` por RUC en Sheet `rucs`

### Fase D — Pulido (opcional)
- [ ] Preview del Doc antes de descargar (iframe)
- [ ] Historial de respuestas generadas por notificación
- [ ] Numeración automática de respuestas (correlativo por empresa)

---

## 9. Lo que Yubert necesita preparar

1. **Los 20 Google Docs** con los placeholders insertados
2. **Los IDs** de cada Doc (de la URL)
3. **Confirmar el representante legal** por cada RUC (para el campo `{{REPRESENTANTE_LEGAL}}`)
4. **Confirmar la ciudad** por cada empresa (para `{{CIUDAD}}`)

> Con eso, la implementación técnica toma 1 sesión de trabajo.

---

## 10. Decisiones pendientes

| Pregunta | Opciones | Recomendación |
|---|---|---|
| ¿Plantillas compartidas o por entidad? | Shared (1 Doc para todas) vs. per-RUC | **Shared** — más fácil de mantener |
| ¿Cómo manejar `{{REPRESENTANTE_LEGAL}}`? | Manual cada vez / guardado por RUC | **Guardado en Sheet `rucs`** |
| ¿Numeración de respuestas? | Manual / automática por empresa | **Manual primero**, auto después |
| ¿Guardar copia de respuesta generada? | Solo descarga / guardar en Drive | **Solo descarga** en Fase B |
