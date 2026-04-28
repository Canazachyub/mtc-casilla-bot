---
name: response-generator
description: |
  Workflow para generar PROPUESTAS DE RESPUESTA editables a partir de
  plantillas Obsidian + extracción IA de la notificación. Activá esta skill
  cuando se mencione: plantilla de respuesta, propuesta editable, generar
  borrador, template Obsidian, response template, redactar respuesta,
  matching de plantilla. La salida son drafts modificables que se muestran
  en el frontend, NO comunicaciones automatizadas.
---

# Skill: Response Generator (sistema de plantillas)

## Filosofía

Yubert y su equipo ya redactan respuestas a SUTRAN/MTC siguiendo patrones casi idénticos según el tipo de solicitud. **La IA no inventa el formato; rellena placeholders en plantillas que ya están escritas correctamente.**

```
Notificación
   ├─ Extracción IA → entiende QUÉ pide el documento
   │
   ├─ Template matcher → elige la plantilla correcta
   │   (basado en emisor + tipo de solicitud + acciones requeridas)
   │
   ├─ Plantilla Obsidian + contexto → IA rellena placeholders
   │
   └─ Propuesta de respuesta editable
       ├─ Se muestra en el frontend
       ├─ Usuario edita / aprueba
       └─ Exportable a Word / PDF / Drive Doc
```

## Bóveda de plantillas (Obsidian)

Las plantillas viven en una **subcarpeta dedicada** dentro de la bóveda RESOLVE:

```
RESOLVE/
├── _templates/                      ← plantillas (no notificaciones)
│   ├── README.md                    (índice + reglas de matching)
│   ├── sutran-solicitud-expedientes.md
│   ├── sutran-solicitud-filmaciones.md
│   ├── sutran-descargo-observacion.md
│   ├── sutran-cumplimiento-resolucion.md
│   ├── mtc-dgat-presentacion-documentos.md
│   ├── mtc-respuesta-informativa.md
│   └── generica-acuse-recibo.md
└── 2026/...                          ← notificaciones procesadas
```

> ¿Por qué Obsidian y no en Drive directo? Porque es **la fuente de verdad editable** por Yubert. Dataview puede listarlas, los enlaces internos `[[plantilla-X]]` funcionan, y los cambios se versionan con git si la bóveda está en repo.

## Formato de plantilla

Cada plantilla es un `.md` con **frontmatter de matching** + **cuerpo con placeholders**:

```markdown
---
template_id: sutran-solicitud-expedientes
nombre: "Respuesta a SUTRAN — solicitud de expedientes técnicos"
emisor: SUTRAN
tipo_documento: [CARTA, OFICIO]                  # cualquiera de estos matchea
keywords_match:                                  # palabras clave del asunto/resumen
  - expediente
  - expedientes técnicos
  - remisión de documentos
  - vehiculos a inspeccionar
acciones_match:                                  # frases de "acciones_requeridas"
  - remitir expediente
  - presentar documentación
prioridad: 10                                    # mayor = se prefiere si hay empate

placeholders:
  - empresa                                      # ya viene del contexto
  - representante_legal                          # se autocompleta del CSV de RUCs
  - documento_referencia                         # ej: "CARTA N° 000476-CR-2026-SUTRAN"
  - fecha_notificacion
  - cantidad_vehiculos                           # IA debe extraer del texto
  - tipo_archivos                                # ej: "expedientes técnicos"
  - plazo_dias_habiles
  - fecha_vencimiento
---

OFICIO N° {{numero_correlativo}}-{{anio}}-{{empresa_corta}}

Lima, {{fecha_actual}}

Señores
SUPERINTENDENCIA DE TRANSPORTE TERRESTRE DE PERSONAS, CARGA Y MERCANCÍAS — SUTRAN
Presente.-

ASUNTO: Remisión de {{tipo_archivos}} solicitados mediante {{documento_referencia}}

REFERENCIA: {{documento_referencia}} de fecha {{fecha_notificacion}}

De nuestra consideración:

Mediante el presente, en atención al documento de la referencia, en el cual su
representada solicita la remisión de los {{tipo_archivos}} de
{{cantidad_vehiculos}} vehículos, dentro del plazo de {{plazo_dias_habiles}} días
hábiles, cumplimos con remitir adjunto al presente lo solicitado.

Sin otro particular, quedamos a su disposición para cualquier consulta adicional.

Atentamente,

________________________________
{{representante_legal}}
{{empresa}}
RUC: {{ruc}}
```

## Tipos de placeholders

| Placeholder | Origen | Resuelto por |
|---|---|---|
| `{{empresa}}` | CSV de RUCs | Python directo |
| `{{ruc}}` | CSV de RUCs | Python directo |
| `{{representante_legal}}` | CSV de RUCs (campo nuevo a agregar) | Python directo |
| `{{documento_referencia}}` | Extracción IA | Python directo |
| `{{fecha_notificacion}}` | Notificación | Python directo (formato `dd/mm/yyyy`) |
| `{{plazo_dias_habiles}}` | Extracción IA | Python directo |
| `{{fecha_vencimiento}}` | Calculado | Python directo |
| `{{fecha_actual}}` | hoy | Python directo |
| `{{cantidad_vehiculos}}` | Extracción IA contextual | **IA — segunda llamada** |
| `{{tipo_archivos}}` | Extracción IA contextual | **IA — segunda llamada** |
| `{{numero_correlativo}}` | Manual / Sheet | Usuario al editar |

> Hay **dos tipos**: los **directos** (Python sustituye con regex) y los **inferenciales** (necesitan IA porque hay que entender el documento).

## Flujo de matching

### Paso 1: indexar plantillas

Al iniciar el bot, leer todas las `_templates/*.md` y construir un índice en memoria:

```python
@dataclass
class Template:
    template_id: str
    nombre: str
    path: Path
    emisor: str | None
    tipo_documento: list[str]
    keywords_match: list[str]
    acciones_match: list[str]
    prioridad: int
    placeholders: list[str]
    body: str  # contenido sin frontmatter

def load_templates(templates_dir: Path) -> list[Template]:
    """Lee todas las plantillas y devuelve la lista parseada."""
    templates = []
    for md_path in templates_dir.glob("*.md"):
        if md_path.name == "README.md":
            continue
        fm, body = parse_frontmatter(md_path.read_text(encoding="utf-8"))
        templates.append(Template(
            template_id=fm["template_id"],
            nombre=fm["nombre"],
            path=md_path,
            emisor=fm.get("emisor"),
            tipo_documento=fm.get("tipo_documento", []),
            keywords_match=fm.get("keywords_match", []),
            acciones_match=fm.get("acciones_match", []),
            prioridad=fm.get("prioridad", 0),
            placeholders=fm.get("placeholders", []),
            body=body,
        ))
    return templates
```

### Paso 2: scoring de matching

```python
def score_template(t: Template, extraction: ExtractionResult) -> int:
    """Devuelve un score de qué tan bien matchea la plantilla con la extracción."""
    score = 0

    # Emisor (obligatorio si está definido)
    if t.emisor:
        if t.emisor.upper() != extraction.emisor.upper():
            return 0
        score += 50

    # Tipo de documento
    if t.tipo_documento:
        doc_upper = extraction.documento_nombre.upper()
        if any(td.upper() in doc_upper for td in t.tipo_documento):
            score += 30

    # Keywords (sumá 5 puntos por cada match)
    blob = (extraction.asunto + " " + extraction.resumen).lower()
    for kw in t.keywords_match:
        if kw.lower() in blob:
            score += 5

    # Acciones
    for action_pattern in t.acciones_match:
        for action in extraction.acciones_requeridas:
            if action_pattern.lower() in action.lower():
                score += 10

    # Prioridad (desempate)
    score += t.prioridad

    return score


def find_best_template(extraction: ExtractionResult, templates: list[Template]) -> Template | None:
    """Devuelve la plantilla con mayor score, o None si nada superó el umbral."""
    scored = [(score_template(t, extraction), t) for t in templates]
    scored = [(s, t) for s, t in scored if s > 30]  # umbral mínimo
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]
```

### Paso 3: relleno de placeholders

```python
async def fill_template(
    template: Template,
    extraction: ExtractionResult,
    notification: Notification,
    ruc_data: RucCredentials,
    document_text: str,
) -> str:
    """Sustituye los placeholders de la plantilla con datos reales."""

    # Placeholders directos
    direct = {
        "empresa": ruc_data.empresa,
        "ruc": ruc_data.ruc,
        "representante_legal": ruc_data.representante_legal or "[COMPLETAR]",
        "documento_referencia": extraction.documento_nombre,
        "fecha_notificacion": notification.date.strftime("%d/%m/%Y"),
        "fecha_actual": date.today().strftime("%d de %B de %Y"),
        "plazo_dias_habiles": str(extraction.plazo_dias_habiles or "—"),
        "fecha_vencimiento": (
            calc_vencimiento(notification.date, extraction.plazo_dias_habiles).strftime("%d/%m/%Y")
            if extraction.plazo_dias_habiles else "—"
        ),
        "anio": str(notification.date.year),
        "empresa_corta": ruc_data.empresa.split()[0],
        "numero_correlativo": "[COMPLETAR]",  # manual
    }

    # Placeholders inferenciales (los que faltan después de los directos)
    inferential = [p for p in template.placeholders if p not in direct]
    if inferential:
        ai_values = await ai_fill_inferential_placeholders(
            placeholders=inferential,
            template_body=template.body,
            document_text=document_text,
            extraction=extraction,
        )
        direct.update(ai_values)

    # Sustitución
    body = template.body
    for key, val in direct.items():
        body = body.replace(f"{{{{{key}}}}}", str(val))

    # Marcar placeholders no resueltos para que el usuario complete
    body = re.sub(r"\{\{(\w+)\}\}", r"[\1]", body)

    return body
```

### Paso 4: IA rellena los placeholders inferenciales

```python
INFERENTIAL_SYSTEM = """Sos un asistente que extrae datos específicos de un documento legal/administrativo peruano para rellenar placeholders en una plantilla de respuesta.

Devolvés SIEMPRE un JSON con los valores extraídos. Si un valor no se puede determinar con certeza, usá un texto entre corchetes describiendo qué falta, ej: "[COMPLETAR: cantidad de vehículos]"."""

INFERENTIAL_USER_TEMPLATE = """Plantilla de respuesta:
─────────
{template_body}
─────────

Documento original notificado:
─────────
{document_text}
─────────

Contexto ya extraído:
- Emisor: {emisor}
- Asunto: {asunto}
- Resumen: {resumen}
- Acciones requeridas: {acciones}

Devolvé un JSON con los valores para estos placeholders:
{placeholders_list}

Ejemplo de respuesta:
{{"cantidad_vehiculos": "veintitrés (23)", "tipo_archivos": "expedientes técnicos"}}"""

async def ai_fill_inferential_placeholders(
    placeholders: list[str],
    template_body: str,
    document_text: str,
    extraction: ExtractionResult,
) -> dict:
    response = await deepseek_client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": INFERENTIAL_SYSTEM},
            {
                "role": "user",
                "content": INFERENTIAL_USER_TEMPLATE.format(
                    template_body=template_body[:5000],
                    document_text=document_text[:15000],
                    emisor=extraction.emisor,
                    asunto=extraction.asunto,
                    resumen=extraction.resumen,
                    acciones="; ".join(extraction.acciones_requeridas),
                    placeholders_list=", ".join(placeholders),
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)
```

## Output: la propuesta

El resultado de `fill_template()` se persiste en **dos lugares**:

1. **Sheet "MTC Casilla DB"**, columna `propuesta_respuesta` (texto largo, hasta 50000 chars).
2. **Obsidian**, en la nota de la notificación, sección `## ✉️ Propuesta de respuesta`.

Y se muestra en el **frontend**, en la vista detalle, dentro de un `<textarea>` editable con botones:

- **💾 Guardar cambios** → POST a Apps Script → actualiza el Sheet
- **🔄 Regenerar con DeepSeek** → llama a Apps Script → IA → Sheet → frontend recarga
- **🤖 Regenerar con Gemini** → idem con otro modelo
- **📄 Exportar a Word** → genera `.docx` con `python-docx` (Fase 2.5)
- **✅ Marcar como definitiva** → cambia `estado_propuesta` a `aprobada`

## Generación en la nube (Apps Script + IA)

Para que el equipo pueda regenerar respuestas SIN tener el bot Python corriendo, Apps Script puede llamar directamente a DeepSeek/Gemini con `UrlFetchApp`:

```javascript
// appscript/Code.gs (extensión)

function regenerateResponse_(notifId, model) {
  const apiKey = PropertiesService.getScriptProperties().getProperty(
    model === 'gemini' ? 'GEMINI_API_KEY' : 'DEEPSEEK_API_KEY'
  );
  if (!apiKey) throw new Error('API key no configurada');

  const detail = handleDetail_({ id: notifId });
  if (detail.error) throw new Error(detail.error);

  const template = loadTemplateFromDrive_(detail.template_id);
  const documentText = loadDocumentTextFromDrive_(detail.drive_file_id);

  const url = model === 'gemini'
    ? `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`
    : 'https://api.deepseek.com/v1/chat/completions';

  const payload = buildPayload_(template, documentText, detail);

  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: model === 'deepseek' ? { Authorization: 'Bearer ' + apiKey } : {},
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const result = parseAIResponse_(resp.getContentText(), model);
  updateNotifField_(notifId, 'propuesta_respuesta', result);
  return { ok: true, model, length: result.length };
}
```

> Las API keys en Apps Script viven en `PropertiesService.getScriptProperties()`, NO en `Code.gs`. Configurar desde el editor: **Project settings → Script properties → Add property**.

## Storage de plantillas en Drive (sincronizadas con Obsidian)

Para que **tanto Python como Apps Script** puedan acceder a las plantillas, sincronizarlas a Drive:

```
Drive: MTC-Casilla-Bot/_templates/
       ├── sutran-solicitud-expedientes.md
       └── ...
```

Opciones de sync:
- **Manual**: Yubert copia los `.md` actualizados a Drive cuando edita una plantilla
- **Auto (recomendado)**: comando `mtc-bot sync-templates` que sube los .md de Obsidian a Drive
- **Apps Script puro**: edita plantillas desde el frontend (Fase 3)

## Tests sugeridos

- `test_score_template_emisor_match`
- `test_score_template_keywords_count`
- `test_find_best_template_returns_highest_score`
- `test_fill_template_replaces_direct_placeholders`
- `test_fill_template_marks_unresolved_with_brackets`
- `test_load_templates_skips_readme`
- `test_inferential_ai_returns_valid_json` (con mock)

## Indicador de calidad en el frontend

La propuesta se muestra con un **badge de calidad**:

- 🟢 **Alta confianza**: todos los placeholders resueltos, IA con confianza alta, plantilla matcheó score > 100
- 🟡 **Revisar**: 1-2 placeholders no resueltos o IA confianza media
- 🔴 **Baja calidad**: muchos `[COMPLETAR]`, o plantilla matcheó con score bajo, o no matcheó ninguna

Esto ayuda al equipo a priorizar qué propuestas revisar primero.
