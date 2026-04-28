---
name: ai-extractor
description: |
  Workflow para análisis IA de notificaciones MTC con DeepSeek (primario) y
  Gemini (fallback). Activá esta skill cuando el usuario mencione: extracción
  estructurada, análisis IA del documento, resumen de notificación, detectar
  plazo, prompt de extracción, DeepSeek API, Gemini API. Cubre: prompt
  engineering para JSON estructurado, parseo robusto, fallback automático,
  validación con Pydantic.
---

# Skill: AI Extractor

## Objetivo

Dado el texto de una notificación MTC (carta/oficio/informe/resolución), producir un objeto estructurado y validado con:

```python
class ExtractionResult(BaseModel):
    documento_nombre: str          # "CARTA N° 000476-CR-2026-SUTRAN"
    emisor: str                    # "SUTRAN"
    fecha_documento: date | None   # fecha del documento, no de la notificación
    asunto: str                    # 1-2 líneas
    resumen: str                   # 2-3 líneas máx
    requiere_respuesta: bool
    plazo_dias_habiles: int | None # None si no hay plazo
    plazo_descripcion: str | None  # ej: "5 días hábiles desde la notificación"
    acciones_requeridas: list[str] # bullet list de qué hay que hacer
    referencias_normativas: list[str]  # leyes/resoluciones citadas
    confianza: Literal["alta", "media", "baja"]
    notas_modelo: str | None       # observaciones del propio modelo
```

## Estrategia de modelos

```
Texto → DeepSeek (deepseek-chat) ─┬─ JSON válido + Pydantic OK → return
                                  ├─ JSON inválido → retry 1x con prompt más estricto
                                  └─ Sigue fallando → fallback a Gemini
                                                     ├─ JSON OK → return
                                                     └─ Falla → return con confianza="baja" + notas
```

## Por qué DeepSeek primero

- ~10x más barato que GPT-4 / Claude Opus
- Latencia baja en español
- API compatible OpenAI (mismo SDK con base_url custom)
- Soporta `response_format={"type": "json_object"}` para JSON forzado

## Por qué Gemini como fallback

- Diferente provider → si DeepSeek tiene outage, seguimos
- Maneja PDFs escaneados como imágenes (en caso edge donde no hay texto)
- Cuota gratuita generosa

## Prompt de extracción (DeepSeek)

```python
SYSTEM_PROMPT = """Eres un asistente experto en análisis de documentos legales y administrativos peruanos, específicamente notificaciones de SUTRAN y el MTC dirigidas a Centros de Inspección Técnica Vehicular (CITV).

Tu tarea es extraer información estructurada de un documento y devolverla EXCLUSIVAMENTE en formato JSON válido, sin texto adicional, sin markdown, sin backticks.

Reglas:
1. Si un campo no se puede determinar con certeza, usá null (no inventes).
2. El "documento_nombre" debe respetar el formato original (ej: "CARTA N° 000476-CR-2026-SUTRAN").
3. El "emisor" suele ser SUTRAN, MTC, DGAT, etc. Extraer la sigla.
4. Para "plazo_dias_habiles", solo contar días hábiles explícitos. Si dice "5 días" sin especificar, asumir hábiles. Si dice "calendario", convertir a hábiles aproximado y notarlo en notas_modelo.
5. "requiere_respuesta" es true si el documento solicita acción concreta del destinatario (remitir, presentar, descargar, comparecer). Es false si es solo informativo.
6. "acciones_requeridas" debe ser una lista de strings cortos (max 100 chars cada uno) en infinitivo: "Remitir expedientes técnicos de 23 vehículos", "Presentar filmaciones de inspecciones", etc.
7. "confianza" = "alta" si el texto es claro y completo; "media" si hay ambigüedad; "baja" si el documento parece truncado o ilegible.
8. La fecha del documento NO es la fecha de notificación (la última suele estar en la constancia, no en el documento principal).

Schema esperado:
{
  "documento_nombre": "string",
  "emisor": "string",
  "fecha_documento": "YYYY-MM-DD or null",
  "asunto": "string",
  "resumen": "string (2-3 líneas)",
  "requiere_respuesta": true/false,
  "plazo_dias_habiles": integer or null,
  "plazo_descripcion": "string or null",
  "acciones_requeridas": ["string", ...],
  "referencias_normativas": ["string", ...],
  "confianza": "alta|media|baja",
  "notas_modelo": "string or null"
}
"""

USER_PROMPT_TEMPLATE = """Analizá el siguiente documento notificado vía Casilla MTC y devolvé el JSON estructurado.

Asunto de la notificación (de la casilla): {subject}
RUC destinatario: {ruc}
Fecha de notificación: {notif_date}

────── INICIO DEL DOCUMENTO ──────
{document_text}
────── FIN DEL DOCUMENTO ──────

Devolvé únicamente el JSON, nada más."""
```

## Llamada a DeepSeek (cliente OpenAI compatible)

```python
from openai import AsyncOpenAI
from pydantic import ValidationError
import json

client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,  # https://api.deepseek.com
)

async def extract_with_deepseek(
    document_text: str,
    subject: str,
    ruc: str,
    notif_date: str,
) -> ExtractionResult:
    response = await client.chat.completions.create(
        model=settings.deepseek_model,  # deepseek-chat
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    subject=subject,
                    ruc=ruc,
                    notif_date=notif_date,
                    document_text=document_text[:30000],  # truncar si es enorme
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
        timeout=settings.ai_timeout_seconds,
    )
    raw = response.choices[0].message.content
    data = json.loads(raw)
    return ExtractionResult.model_validate(data)
```

## Llamada a Gemini (fallback)

```python
import httpx

async def extract_with_gemini(
    document_text: str, subject: str, ruc: str, notif_date: str
) -> ExtractionResult:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "parts": [
                    {
                        "text": USER_PROMPT_TEMPLATE.format(
                            subject=subject, ruc=ruc,
                            notif_date=notif_date,
                            document_text=document_text[:30000],
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": settings.ai_temperature,
            "responseMimeType": "application/json",
            "maxOutputTokens": settings.ai_max_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        resp = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        raw = body["candidates"][0]["content"]["parts"][0]["text"]
        return ExtractionResult.model_validate(json.loads(raw))
```

## Lógica de fallback con retry

```python
async def extract(
    document_text: str, subject: str, ruc: str, notif_date: str
) -> tuple[ExtractionResult, str]:
    """Devuelve (resultado, modelo_usado)."""
    # Intento 1: DeepSeek
    try:
        result = await extract_with_deepseek(document_text, subject, ruc, notif_date)
        return result, "deepseek-chat"
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("DeepSeek devolvió formato inválido, retry estricto: %s", e)
        # Intento 2: DeepSeek con prompt más estricto
        try:
            result = await extract_with_deepseek_strict(...)
            return result, "deepseek-chat-retry"
        except Exception:
            pass
    except Exception as e:
        logger.warning("DeepSeek falló (%s), fallback a Gemini", e)

    # Fallback: Gemini
    try:
        result = await extract_with_gemini(document_text, subject, ruc, notif_date)
        return result, settings.gemini_model
    except Exception as e:
        logger.error("Gemini también falló: %s", e)

    # Último recurso: resultado vacío con baja confianza
    return ExtractionResult(
        documento_nombre=subject,
        emisor="DESCONOCIDO",
        fecha_documento=None,
        asunto=subject,
        resumen="No se pudo analizar el documento automáticamente.",
        requiere_respuesta=True,  # asumir lo peor
        plazo_dias_habiles=None,
        plazo_descripcion=None,
        acciones_requeridas=["Revisar manualmente el documento"],
        referencias_normativas=[],
        confianza="baja",
        notas_modelo="Fallaron tanto DeepSeek como Gemini",
    ), "fallback"
```

## Generación del texto resumen final

A partir de `ExtractionResult`, generar el texto en el formato que pide Yubert:

```python
from babel.dates import format_date
from datetime import date

def render_summary(
    result: ExtractionResult, notif_date: date, ruc_empresa: str
) -> str:
    """Genera el resumen tipo correo del usuario."""
    fecha_str = format_date(notif_date, format="d 'de' MMMM 'de' y", locale="es")

    plazo_frase = ""
    if result.plazo_dias_habiles:
        plazo_str = f"{result.plazo_dias_habiles:02d}".lstrip("0") or "1"
        plazo_frase = f", brindando el plazo de {plazo_str} días hábiles"

    acciones_frase = ""
    if result.acciones_requeridas:
        if len(result.acciones_requeridas) == 1:
            acciones_frase = result.acciones_requeridas[0].lower()
        else:
            acciones_frase = (
                ", ".join(a.lower() for a in result.acciones_requeridas[:-1])
                + f", y {result.acciones_requeridas[-1].lower()}"
            )

    return (
        f"Saludos cordiales, en fecha {fecha_str}, se notificó la "
        f"{result.documento_nombre}, en la que {result.emisor} {acciones_frase}"
        f"{plazo_frase}."
    )
```

## Cálculo del plazo (días hábiles Perú)

Los días hábiles excluyen sábados, domingos y feriados nacionales del Perú. Usar la librería `holidays`:

```python
from datetime import date, timedelta
import holidays

PE_HOLIDAYS = holidays.country_holidays("PE")

def add_business_days(start: date, days: int) -> date:
    """Suma días hábiles peruanos."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in PE_HOLIDAYS:
            added += 1
    return current
```

## Tests sugeridos

- `test_extract_with_real_fixture` — usar PDFs reales anonimizados de fixtures
- `test_fallback_to_gemini_when_deepseek_returns_invalid_json` (mockear)
- `test_render_summary_format` — verificar formato exacto pedido por Yubert
- `test_plazo_dias_habiles` — feriados nacionales correctamente excluidos
- `test_extraction_result_validates_dates`

## Costos estimados

DeepSeek (`deepseek-chat`):
- Input: ~$0.14 / 1M tokens
- Output: ~$0.28 / 1M tokens
- Por notificación promedio (~3000 tokens entrada + 500 salida): **~$0.0006 USD**

Gemini Flash:
- Tier gratuito generoso
- En tier pago: ~$0.075/1M input, $0.30/1M output

Para 50 notificaciones/mes: **menos de $0.05 USD/mes** con DeepSeek.
