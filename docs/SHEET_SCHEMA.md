# 📊 Schema del Google Sheet "MTC Casilla DB"

> Este Sheet es la **base de datos canónica** del bot. Crearlo manualmente la primera vez con los tabs y headers exactos descritos abajo.

## Crear el Sheet

1. Drive → **New → Google Sheets**
2. Renombrar a `MTC Casilla DB`
3. Crear los 3 tabs descritos abajo
4. Compartir con el email del service account (permiso **Editor**)
5. Compartir con Yubert + equipo legal (permiso **Viewer** o **Editor** según rol)
6. Copiar el ID de la URL: `https://docs.google.com/spreadsheets/d/<ESTE_ID>/edit`
7. Pegar en `.env` como `SHEET_ID=...`

---

## Tab 1: `notificaciones`

DB principal. **Una fila por notificación procesada.**

### Headers (fila 1)

| Columna | Tipo | Descripción | Origen |
|---|---|---|---|
| `id` | string | ID único: `<ruc>__<casilla_notif_id>` | Bot Python |
| `timestamp_proceso` | datetime | Cuándo el bot procesó la notif | Bot Python |
| `fecha_notificacion` | date | Cuándo llegó a la casilla | Casilla MTC |
| `ruc` | string (11d) | RUC del destinatario | Bot Python |
| `empresa` | string | Razón social | CSV de RUCs |
| `documento` | string | Nombre del documento ("CARTA N° 000476-...") | Extracción IA |
| `emisor` | string | "SUTRAN", "MTC", "DGAT", etc. | Extracción IA |
| `asunto` | string | 1-2 líneas del propósito | Extracción IA |
| `resumen` | string | 2-3 líneas con la síntesis | Extracción IA |
| `requiere_respuesta` | bool | True si exige acción | Extracción IA |
| `plazo_dias_habiles` | int | Días hábiles desde notificación | Extracción IA |
| `plazo_vencimiento` | date | Fecha exacta de vencimiento | Calculado |
| `confianza_ia` | enum | `alta` / `media` / `baja` | Extracción IA |
| `modelo_ia` | string | "deepseek-chat" / "gemini-2.5-flash" | Bot Python |
| `drive_file_id` | string | ID del PDF en Drive | Drive uploader |
| `drive_view_url` | string | URL `drive.google.com/file/d/.../view` | Drive uploader |
| `template_id` | string | ID de la plantilla matcheada (Fase 2) | Response generator |
| `propuesta_respuesta` | text | Borrador editable (Fase 2) | Response generator |
| `propuesta_calidad` | enum | `alta` / `media` / `baja` (Fase 2) | Response generator |
| `estado_propuesta` | enum | `borrador` / `aprobada` / `enviada` (Fase 2) | Manual |
| `estado` | enum | `pendiente` / `en-proceso` / `completado` / `vencido` | Manual |
| `notas` | text | Comentarios manuales del equipo | Manual |
| `fecha_respuesta` | date | Cuándo se respondió (Fase 4) | Manual |
| `link_respuesta` | string | URL al doc de respuesta enviado (Fase 4) | Manual |

### Recomendaciones de formato

- Aplicar **filtro** a la fila 1 (Data → Create a filter)
- **Congelar** primera fila (View → Freeze → 1 row)
- **Validación de datos** en columnas enum:
  - `requiere_respuesta`: Checkbox
  - `confianza_ia`, `propuesta_calidad`: List of items (alta, media, baja)
  - `estado_propuesta`: borrador, aprobada, enviada
  - `estado`: pendiente, en-proceso, completado, vencido

### Reglas de formato condicional (sugeridas)

- `plazo_vencimiento` < hoy AND `estado` != "completado" → fondo rojo
- `plazo_vencimiento` - hoy <= 2 días → fondo naranja
- `confianza_ia` = "baja" → texto en cursiva

---

## Tab 2: `logs`

Auditoría de runs y errores.

### Headers

| Columna | Tipo | Descripción |
|---|---|---|
| `timestamp` | datetime | Cuando ocurrió |
| `nivel` | enum | INFO / WARNING / ERROR |
| `ruc` | string | RUC asociado (si aplica) |
| `mensaje` | string | Mensaje principal |
| `contexto_json` | string | JSON con info adicional |

> El bot Python escribe acá vía `gspread`. Apps Script también escribe acá ante errores de la API.

---

## Tab 3: `rucs` ⚠️ RESTRICTED

**NUNCA exponer este tab via Apps Script.** Permisos: solo Yubert + service account.

### Headers

| Columna | Tipo | Descripción | Requerido cuando |
|---|---|---|---|
| `ruc` | string (11d) | RUC | siempre |
| `empresa` | string | Razón social | siempre |
| `auth_method` | enum | `direct` o `clave_sol` | siempre |
| `dni_representante` | string (8d) | DNI del representante legal | `auth_method=direct` |
| `password_casilla` | string | Contraseña de la casilla MTC | `auth_method=direct` |
| `sol_usuario` | string | Usuario SOL | `auth_method=clave_sol` |
| `sol_clave` | string | Clave SOL | `auth_method=clave_sol` |
| `representante_legal` | string | Nombre completo (para plantillas) | siempre |
| `activo` | bool | Si procesar este RUC | siempre |

### Política de seguridad

- ⛔ Tab oculto (Sheet → Right click tab → Hide sheet)
- ⛔ Restringir vista: solo Yubert
- ⛔ NO exponer en NINGÚN endpoint Apps Script
- ⛔ Exportar a CSV solo bajo `data/credentials/` (gitignored)
- ⛔ Permisos del CSV local: `chmod 600` en Linux/Mac

---

## Migraciones del schema

Si se agrega/cambia un header:

1. **NO renombrar** columnas existentes (rompe el bot).
2. Agregar al final.
3. Actualizar este documento.
4. Notificar al backend-python-agent y al cloud-google-agent.
5. Bump versión en `CLAUDE.md` Decision Log.

---

## Backup recomendado

- **Diario** (automático): Drive ya hace versioning, no hace falta backup adicional.
- **Semanal**: descarga manual a `.xlsx` por si Drive falla → guardar en otro storage.
- **Crítico**: si el Sheet tiene >1000 filas, considerar migrar a SQLite local con sync periódico.
