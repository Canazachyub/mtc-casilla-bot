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
        asunto: 1-2 líneas describiendo el propósito del documento.
        resumen: 2-3 líneas con la síntesis del cuerpo.
        requiere_respuesta: ``True`` si el documento solicita acción del
            destinatario; ``False`` si es solo informativo.
        plazo_dias_habiles: días hábiles otorgados; ``0`` si no aplica.
        confianza: auto-evaluación del modelo sobre la calidad de la
            extracción (``alta`` / ``media`` / ``baja``).
        modelo_ia: nombre del proveedor que respondió (lo agrega el caller).
    """

    documento: str = ""
    emisor: str = ""
    asunto: str = ""
    resumen: str = ""
    requiere_respuesta: bool = False
    plazo_dias_habiles: int = 0
    confianza: Literal["alta", "media", "baja"] = "media"
    # Metadata del provider (no proviene del LLM, lo agrega el caller).
    modelo_ia: str = ""


class AIExtractionFailed(Exception):
    """Tanto DeepSeek como Gemini fallaron. El caller decide qué hacer."""


_SYSTEM_PROMPT = (
    "Eres un asistente legal experto en notificaciones electrónicas del Ministerio "
    "de Transportes y Comunicaciones del Perú (MTC) y SUTRAN. Tu tarea es leer el "
    "texto de una notificación oficial y devolver SOLO un JSON con metadata "
    "estructurada. NO incluyas comentarios, markdown ni texto antes/después del JSON."
)


_USER_PROMPT_TEMPLATE = """\
Analiza la siguiente notificación y devuelve un JSON con esta forma exacta:

{{
  "documento": "<nombre oficial, ej: CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV>",
  "emisor": "<emisor — SUTRAN, MTC, DGAT, OEFA, etc.>",
  "asunto": "<1-2 líneas describiendo el propósito>",
  "resumen": "<2-3 líneas con la síntesis del cuerpo>",
  "requiere_respuesta": <true|false — true si exige acción del destinatario>,
  "plazo_dias_habiles": <int — días hábiles desde la notificación; 0 si no aplica>,
  "confianza": "<alta|media|baja — tu nivel de seguridad en la extracción>"
}}

REGLAS IMPORTANTES:
- Si el documento dice "PRE-INFORME", "INFORME", "RESOLUCIÓN", "AUTO" o similar,
  eso forma parte del nombre del documento.
- "plazo_dias_habiles": busca frases como "5 días hábiles", "diez (10) días",
  "tres días". Si no menciona plazo, devolvé 0.
- "requiere_respuesta": true si el documento solicita o requiere algo del
  destinatario (descargo, expedientes, comparecencia, etc.). false si es solo
  informativo.
- "confianza": "alta" si todos los campos son claros del texto. "media" si
  dedujiste algo. "baja" si el texto es ambiguo o incompleto.

TEXTO DE LA NOTIFICACIÓN:
\"\"\"
{texto}
\"\"\"

JSON:"""


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
    return _USER_PROMPT_TEMPLATE.format(texto=texto)


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

    logger.info("Extrayendo de %d caracteres con Gemini", len(texto))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            params={"key": settings.gemini_api_key.get_secret_value()},
            json=body,
        )
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
