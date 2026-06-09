"""Extracción IA de metadata de notificaciones MTC.

Estrategia dual provider:
    * DeepSeek primario (más barato, OpenAI-compatible).
    * Gemini fallback ante errores de rate-limit, timeout o JSON malformado.

Salida validada con Pydantic. Si ambos fallan, lanza ``AIExtractionFailed``.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from mtc_bot.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Límite duro de caracteres para evitar quemar tokens / contexto.
MAX_TEXT_CHARS = 50_000


class ExtractionResult(BaseModel):
    """Schema de la salida del LLM (validado con Pydantic).

    Attributes:
        documento: nombre oficial del documento (ej: "CARTA N° 000476-...").
        emisor: sigla del organismo emisor (SUTRAN, MTC, DGAT, OEFA, ...).
        casilla_origen: sistema que emitió la notificación (MTC, SUTRAN,
            Ministerio Público, Poder Judicial, SUNAT, OSINERGMIN, etc.).
        asunto: 1-2 líneas describiendo el propósito del documento.
        resumen: 2-3 líneas con la síntesis del cuerpo.
        referencia: documento(s) referenciado(s): Hoja de Ruta, Expediente, etc.
        tarea: lista de tareas requeridas (del catálogo de 18 opciones).
        requiere_respuesta: ``True`` si el documento solicita acción del
            destinatario; ``False`` si es solo informativo.
        plazo_dias_habiles: días hábiles otorgados; ``0`` si no aplica.
        confianza: auto-evaluación del modelo sobre la calidad de la
            extracción (``alta`` / ``media`` / ``baja``).
        modelo_ia: nombre del proveedor que respondió (lo agrega el caller).
    """

    documento: str = ""
    emisor: str = ""
    casilla_origen: str = ""
    asunto: str = ""
    resumen: str = ""
    referencia: str = ""
    tarea: list[str] = []
    requiere_respuesta: bool = False
    plazo_dias_habiles: int = 0
    confianza: Literal["alta", "media", "baja"] = "media"
    # Resumen estructurado
    tipo_acto: str = ""
    accion_requerida: str = ""
    consecuencias: str = ""
    fundamento_legal: str = ""
    # Metadata del provider (no proviene del LLM, lo agrega el caller).
    modelo_ia: str = ""


class AIExtractionFailed(Exception):
    """Tanto DeepSeek como Gemini fallaron. El caller decide qué hacer."""


_SYSTEM_PROMPT_INFORME = (
    "Eres un asistente legal experto en notificaciones electrónicas del Perú. "
    "Genera informes profesionales estructurados en Markdown sobre documentos oficiales "
    "de SUTRAN, MTC y otras entidades regulatorias. Sé conciso pero completo."
)

_INFORME_PROMPT_TEMPLATE = """\
Genera un informe profesional en Markdown sobre esta notificación oficial peruana.
Usa EXACTAMENTE estas secciones (omite las que no apliquen al documento):

## Tipo de documento
<tipo: CARTA, OFICIO, RESOLUCIÓN COACTIVA, ACTA DE INSPECCIÓN, etc. + número completo>

## Materia
<1-2 párrafos explicando de qué trata el documento y su contexto>

## Hechos relevantes
- <hecho 1>
- <hecho 2>
(máximo 6 hechos concretos, con fechas y referencias si las hay)

## Infracciones o incumplimientos detectados
- <descripción concisa> (art. y norma si se menciona)
(omitir sección si el documento no describe infracciones)

## Plazos y fechas clave
- Plazo para respuesta/descargo: X días hábiles (si aplica)
- Fecha límite estimada: DD/MM/YYYY
- Otras fechas importantes mencionadas

## Monto en riesgo
<monto de multa, UIT o deuda si se menciona; "No especificado" si no aplica>

## Documentos requeridos en la respuesta
1. <documento 1>
2. <documento 2>
(omitir sección si no se piden documentos)

## Observación clave para la respuesta
<1-2 oraciones con el punto más crítico que debe tenerse en cuenta al redactar la respuesta>

TEXTO DE LA NOTIFICACIÓN:
\"\"\"
{texto}
\"\"\"

INFORME:"""


_SYSTEM_PROMPT = (
    "Eres un asistente legal experto en notificaciones electrónicas del Ministerio "
    "de Transportes y Comunicaciones del Perú (MTC) y SUTRAN. Tu tarea es leer el "
    "texto de una notificación oficial y devolver SOLO un JSON con metadata "
    "estructurada. NO incluyas comentarios, markdown ni texto antes/después del JSON."
)


_TAREAS_CATALOGO = (
    "apelación, descargos, remitir expedientes, subsanar observaciones, "
    "inspección, cumplir con pago, carta de ampliación, cumplo requerimiento, "
    "hacer algo?, nueva solicitud, comunicar en WhatsApp, remitir información, "
    "dar seguimiento, archivar, baja de ing, pago de infracción, no iniciar PAS, carta"
)

_USER_PROMPT_TEMPLATE = """\
Analiza la siguiente notificación oficial peruana y devuelve SOLO un JSON con esta forma exacta:

{{
  "documento": "<nombre oficial completo, ej: CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV>",
  "emisor": "<sigla del organismo que emite — SUTRAN, MTC, OSINERGMIN, INDECOPI, etc.>",
  "casilla_origen": "<sistema electrónico de origen — MTC, SUTRAN, Ministerio Público, Poder Judicial, SUNAT, OSINERGMIN, ONPE, JNE u otro>",
  "asunto": "<1-2 líneas describiendo el propósito del documento>",
  "resumen": "<2-3 líneas con la síntesis del cuerpo del documento>",
  "referencia": "<números de Hoja de Ruta (ej: E-135789-2026), Expediente Administrativo, o cartas previas mencionadas como referencia; vacío si no hay>",
  "tarea": [<lista de tareas requeridas, SOLO usando valores del catálogo>],
  "requiere_respuesta": <true|false — true si exige acción del destinatario>,
  "plazo_dias_habiles": <int — días hábiles desde la notificación; 0 si no aplica>,
  "confianza": "<alta|media|baja — tu nivel de seguridad en la extracción>",
  "tipo_acto": "<tipo del acto administrativo: CARTA, OFICIO, RESOLUCIÓN COACTIVA, RESOLUCIÓN DIRECTORAL, ACTA DE INSPECCIÓN, INFORME, NOTIFICACIÓN DE INFRACCIÓN, REQUERIMIENTO, etc.>",
  "accion_requerida": "<1-2 oraciones describiendo exactamente QUÉ debe hacer el destinatario (no el contexto, la acción concreta)>",
  "consecuencias": "<qué ocurre si no se actúa: multa, inicio de PAS, sanción administrativa, archivo — vacío si no se menciona consecuencia explícita>",
  "fundamento_legal": "<artículos, reglamentos o normas citadas explícitamente, ej: Art. 23 D.S. 025-2008-MTC — vacío si no hay>"
}}

CATÁLOGO DE TAREAS (usa SOLO estos valores exactos en el array "tarea"):
{tareas}

GUÍA DE SELECCIÓN DE TAREAS:
- "comunicar en WhatsApp": incluir SIEMPRE salvo que la notificación sea puramente archival.
- "descargos": el documento abre PAS o solicita presentar descargos.
- "remitir expedientes": pide expedientes técnicos y/o filmaciones de ITV.
- "apelación": se impone sanción/multa con plazo para interponer apelación.
- "pago de infracción": se impone multa que debe pagarse.
- "subsanar observaciones": hay observaciones a subsanar en solicitud.
- "carta de ampliación": plazo es corto (≤3 días hábiles) y se puede pedir más.
- "cumplo requerimiento": ya se va a presentar lo solicitado sin ampliación.
- "remitir información": pide información general (no expedientes técnicos).
- "archivar": notificación informa que el proceso fue archivado (sin acción).
- "dar seguimiento": proceso judicial o PAS en curso sin acción inmediata.
- "cumplir con pago": pide pago de deuda o multa coactiva.
- "baja de ing": hay que tramitar baja de personal en SINARETT.
- "no iniciar PAS": se puede pedir que no se inicie el procedimiento sancionador.
- "nueva solicitud": hay que presentar una nueva solicitud.
- "inspección": hay una inspección programada o en curso.
- "carta": hay que redactar y enviar una carta simple de respuesta.
- "hacer algo?": solo si la acción es completamente incierta.

REGLAS ADICIONALES:
- "documento": incluir el tipo (CARTA, OFICIO, RESOLUCIÓN, ACTA, etc.) + número completo.
- "referencia": extraer SOLO los identificadores explícitamente mencionados como referencia en el documento (no inventar).
- "plazo_dias_habiles": busca "X días hábiles", "X (N) días", etc. Devolvé 0 si no hay plazo.
- "casilla_origen": si el número de documento contiene "MTC/" → "MTC"; "SUTRAN" → "SUTRAN"; "MP-FN" o "MPFN" → "Ministerio Público"; "PNP" → "Ministerio del Interior"; si es SUNAT/OSINERGMIN/INDECOPI/ONPE/JNE → usar ese nombre.
- "tipo_acto": extraer del encabezado o número del documento (CARTA, OFICIO, RESOLUCIÓN, ACTA, etc.).
- "accion_requerida": sintetizar la acción específica pedida al destinatario (no el contexto general).
- "consecuencias": buscar frases como "bajo apercibimiento de...", "de no cumplir...", "se impondrá...", "se iniciará PAS...".
- "fundamento_legal": citar solo normas mencionadas explícitamente en el texto.

TEXTO DE LA NOTIFICACIÓN:
\"\"\"
{texto}
\"\"\"

JSON:"""


def _gemini_auth(api_key: str) -> tuple[dict, dict]:
    """Devuelve (params, headers) según el formato de la key de Gemini.

    - Keys ``AIzaSy...`` → query param ``?key=``.
    - Keys ``AQ.``       → header ``x-goog-api-key`` (nuevo formato Google AI Studio).
    """
    if api_key.startswith("AQ."):
        return {}, {"x-goog-api-key": api_key}
    return {"key": api_key}, {}


def _truncate(texto: str) -> str:
    """Trunca el texto a ``MAX_TEXT_CHARS`` y avisa por log si fue recortado."""
    if len(texto) > MAX_TEXT_CHARS:
        logger.warning(
            "Texto de %d caracteres excede el límite, truncando a %d",
            len(texto),
            MAX_TEXT_CHARS,
        )
        return texto[:MAX_TEXT_CHARS]
    return texto


def _build_user_prompt(texto: str) -> str:
    """Renderiza el template de usuario sustituyendo el texto del documento."""
    return _USER_PROMPT_TEMPLATE.format(texto=texto, tareas=_TAREAS_CATALOGO)


async def extract_with_deepseek(
    settings: Settings,
    texto: str,
    timeout: float = 60.0,  # noqa: ASYNC109 — el SDK acepta timeout per-request
) -> ExtractionResult:
    """Llama a DeepSeek vía openai SDK y devuelve la metadata extraída.

    Args:
        settings: configuración con ``deepseek_api_key`` y ``deepseek_base_url``.
        texto: texto plano del PDF unido (ya truncado por el caller).
        timeout: timeout en segundos para la request.

    Returns:
        ``ExtractionResult`` con ``modelo_ia="deepseek-chat"``.

    Raises:
        openai.OpenAIError: errores de red, rate-limit, autenticación, etc.
        json.JSONDecodeError: si la respuesta no es JSON válido.
        pydantic.ValidationError: si el JSON no respeta el schema.
    """
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url=settings.deepseek_base_url,
    )
    logger.info("Extrayendo de %d caracteres con DeepSeek", len(texto))

    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(texto)},
        ],
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
        response_format={"type": "json_object"},
        timeout=timeout,
    )

    content = resp.choices[0].message.content or ""
    data = json.loads(content)
    result = ExtractionResult.model_validate(data)
    result.modelo_ia = settings.deepseek_model
    return result


async def extract_with_gemini(
    settings: Settings,
    texto: str,
    timeout: float = 60.0,  # noqa: ASYNC109 — httpx.AsyncClient acepta timeout
) -> ExtractionResult:
    """Llama a Gemini vía REST API y devuelve la metadata extraída.

    Args:
        settings: configuración con ``gemini_api_key`` y ``gemini_model``.
        texto: texto plano del PDF unido (ya truncado por el caller).
        timeout: timeout en segundos para la request.

    Returns:
        ``ExtractionResult`` con ``modelo_ia=settings.gemini_model``.

    Raises:
        httpx.HTTPError: errores de red / status code != 2xx.
        json.JSONDecodeError: si la respuesta no es JSON válido.
        pydantic.ValidationError: si el JSON no respeta el schema.
        KeyError: si la respuesta de Gemini no tiene ``candidates``.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": _build_user_prompt(texto)}]}],
        "generationConfig": {
            "temperature": settings.ai_temperature,
            "maxOutputTokens": settings.ai_max_tokens,
            "responseMimeType": "application/json",
        },
    }

    params, headers = _gemini_auth(settings.gemini_api_key.get_secret_value())
    logger.info("Extrayendo de %d caracteres con Gemini", len(texto))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params=params, headers=headers, json=body)
        resp.raise_for_status()
        payload = resp.json()

    raw = payload["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    result = ExtractionResult.model_validate(data)
    result.modelo_ia = settings.gemini_model
    return result


# Errores recuperables que disparan el fallback a Gemini.
_RECOVERABLE_ERRORS: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    json.JSONDecodeError,
    ValidationError,
    ValueError,
    KeyError,
    TimeoutError,
)


async def extract(texto: str, settings: Settings | None = None) -> ExtractionResult:
    """Extrae metadata de una notificación con DeepSeek (fallback Gemini).

    Args:
        texto: texto plano del PDF unido (proviene de
            ``pdf_pipeline.extract_text``).
        settings: ``Settings`` inyectables (default: ``get_settings()``).

    Returns:
        ``ExtractionResult`` validado con campo ``modelo_ia`` indicando cuál
        proveedor respondió.

    Raises:
        AIExtractionFailed: si tanto DeepSeek como Gemini fallan.
    """
    cfg = settings or get_settings()
    texto_norm = _truncate(texto)

    deepseek_error: str | None = None
    try:
        return await extract_with_deepseek(cfg, texto_norm)
    except _RECOVERABLE_ERRORS as exc:
        deepseek_error = f"{type(exc).__name__}: {exc}"
        logger.warning("DeepSeek falló (%s), fallback a Gemini", deepseek_error)
    except Exception as exc:  # noqa: BLE001 — el openai SDK lanza varias jerarquías
        deepseek_error = f"{type(exc).__name__}: {exc}"
        logger.warning("DeepSeek lanzó %s, fallback a Gemini", deepseek_error)

    try:
        return await extract_with_gemini(cfg, texto_norm)
    except _RECOVERABLE_ERRORS as exc:
        gemini_error = f"{type(exc).__name__}: {exc}"
        logger.error(
            "Ambos proveedores IA fallaron. DeepSeek=[%s] Gemini=[%s]",
            deepseek_error,
            gemini_error,
        )
        raise AIExtractionFailed(f"DeepSeek: {deepseek_error} | Gemini: {gemini_error}") from exc
    except Exception as exc:  # noqa: BLE001 — capturar cualquier error remanente
        gemini_error = f"{type(exc).__name__}: {exc}"
        logger.error(
            "Ambos proveedores IA fallaron. DeepSeek=[%s] Gemini=[%s]",
            deepseek_error,
            gemini_error,
        )
        raise AIExtractionFailed(f"DeepSeek: {deepseek_error} | Gemini: {gemini_error}") from exc


async def extract_informe(
    texto: str,
    settings: Settings | None = None,
    timeout: float = 120.0,  # noqa: ASYNC109 — se pasa a httpx, no se usa asyncio.timeout
) -> str:
    """Genera un informe estructurado en Markdown usando Gemini (contexto completo).

    A diferencia de ``extract()``, NO trunca el texto — Gemini soporta hasta 1M tokens,
    adecuado para PDFs de 40+ páginas. Falla silenciosamente: devuelve cadena vacía
    si Gemini falla, sin interrumpir el pipeline.

    Args:
        texto: texto completo del PDF (sin truncar).
        settings: Settings inyectables (default: ``get_settings()``).
        timeout: timeout en segundos.

    Returns:
        Informe en Markdown. Cadena vacía si Gemini falla.
    """
    cfg = settings or get_settings()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.gemini_model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT_INFORME}]},
        "contents": [{"parts": [{"text": _INFORME_PROMPT_TEMPLATE.format(texto=texto)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        },
    }

    params, headers = _gemini_auth(cfg.gemini_api_key.get_secret_value())
    logger.info("Generando informe con Gemini (%d chars)", len(texto))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params=params, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
        informe = payload["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("Informe Gemini OK (%d chars)", len(informe))
        return informe.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini informe falló (%s) — intentando con DeepSeek", type(exc).__name__)

    # Fallback: DeepSeek con texto truncado (no tiene contexto de 1M pero cubre la mayoría)
    texto_ds = _truncate(texto)
    try:
        client_ds = AsyncOpenAI(
            api_key=cfg.deepseek_api_key.get_secret_value(),
            base_url=cfg.deepseek_base_url,
        )
        logger.info("Generando informe con DeepSeek (%d chars)", len(texto_ds))
        resp_ds = await client_ds.chat.completions.create(
            model=cfg.deepseek_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_INFORME},
                {"role": "user", "content": _INFORME_PROMPT_TEMPLATE.format(texto=texto_ds)},
            ],
            temperature=0.2,
            max_tokens=2048,
            timeout=timeout,
        )
        informe = resp_ds.choices[0].message.content or ""
        logger.info("Informe DeepSeek OK (%d chars)", len(informe))
        return informe.strip()
    except Exception as exc2:  # noqa: BLE001
        logger.warning("DeepSeek informe también falló (%s) — informe omitido", type(exc2).__name__)
        return ""
