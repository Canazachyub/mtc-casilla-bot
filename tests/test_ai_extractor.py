"""Tests para ``mtc_bot.ai_extractor``.

Cubre:
    * Happy path con DeepSeek OK.
    * Fallback a Gemini cuando DeepSeek falla.
    * Fallo total → ``AIExtractionFailed``.

Las APIs externas se mockean: NO se hacen llamadas reales a DeepSeek/Gemini.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from mtc_bot.ai_extractor import (
    AIExtractionFailed,
    ExtractionResult,
    extract,
    extract_with_deepseek,
    extract_with_gemini,
)  # isort: skip

# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _build_settings() -> Any:
    """Devuelve un mock de ``Settings`` con los campos que usa el módulo."""
    settings = MagicMock()
    settings.deepseek_api_key = SecretStr("sk-test-deepseek-key")
    settings.deepseek_base_url = "https://api.deepseek.test"
    settings.deepseek_model = "deepseek-chat"
    settings.gemini_api_key = SecretStr("AIz-test-gemini-key")
    settings.gemini_model = "gemini-2.5-flash"
    settings.ai_temperature = 0.1
    settings.ai_max_tokens = 1024
    settings.ai_timeout_seconds = 60
    return settings


@pytest.fixture
def fake_settings() -> Any:
    return _build_settings()


@pytest.fixture
def sample_text() -> str:
    return (
        "CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV\n"
        "Asunto: Solicitud de descargo. Plazo 5 días hábiles."
    )


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    return {
        "documento": "CARTA N° 000476-CR-2026-SUTRAN/06.3.4-SGFSV",
        "emisor": "SUTRAN",
        "asunto": "Solicitud de descargo",
        "resumen": "SUTRAN solicita descargo en 5 días hábiles.",
        "requiere_respuesta": True,
        "plazo_dias_habiles": 5,
        "confianza": "alta",
    }


# ─────────────────────────────────────────────────────────────────
# ExtractionResult básico
# ─────────────────────────────────────────────────────────────────


def test_extraction_result_defaults() -> None:
    result = ExtractionResult()
    assert result.documento == ""
    assert result.requiere_respuesta is False
    assert result.plazo_dias_habiles == 0
    assert result.confianza == "media"
    assert result.modelo_ia == ""


# ─────────────────────────────────────────────────────────────────
# Happy path: DeepSeek responde OK
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_with_deepseek_happy_path(
    fake_settings: Any, sample_text: str, sample_payload: dict[str, Any]
) -> None:
    """DeepSeek devuelve JSON válido y se mapea a ExtractionResult."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(sample_payload)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("mtc_bot.ai_extractor.AsyncOpenAI", return_value=mock_client):
        result = await extract_with_deepseek(fake_settings, sample_text)

    assert result.documento == sample_payload["documento"]
    assert result.emisor == "SUTRAN"
    assert result.plazo_dias_habiles == 5
    assert result.requiere_respuesta is True
    assert result.confianza == "alta"
    assert result.modelo_ia == "deepseek-chat"
    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_uses_deepseek_first(
    fake_settings: Any, sample_text: str, sample_payload: dict[str, Any]
) -> None:
    """``extract`` usa DeepSeek y no llama a Gemini cuando DeepSeek funciona."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(sample_payload)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    gemini_spy = AsyncMock()

    with patch("mtc_bot.ai_extractor.AsyncOpenAI", return_value=mock_client), patch(
        "mtc_bot.ai_extractor.extract_with_gemini", gemini_spy
    ):
        result = await extract(sample_text, settings=fake_settings)

    assert result.modelo_ia == "deepseek-chat"
    gemini_spy.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────
# Fallback: DeepSeek falla → Gemini OK
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_falls_back_to_gemini(
    fake_settings: Any, sample_text: str, sample_payload: dict[str, Any]
) -> None:
    """DeepSeek lanza error → Gemini responde OK → modelo_ia = gemini."""
    deepseek_stub = AsyncMock(side_effect=httpx.ConnectError("simulated"))

    gemini_text = json.dumps(sample_payload)

    def httpx_handler(request: httpx.Request) -> httpx.Response:
        body = {
            "candidates": [
                {"content": {"parts": [{"text": gemini_text}]}},
            ]
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(httpx_handler)

    # Reemplazamos AsyncClient por uno que use MockTransport.
    original_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    with patch(
        "mtc_bot.ai_extractor.extract_with_deepseek", deepseek_stub
    ), patch("mtc_bot.ai_extractor.httpx.AsyncClient", patched_client):
        result = await extract(sample_text, settings=fake_settings)

    assert result.modelo_ia == "gemini-2.5-flash"
    assert result.documento == sample_payload["documento"]
    assert result.plazo_dias_habiles == 5
    deepseek_stub.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_with_gemini_happy_path(
    fake_settings: Any, sample_text: str, sample_payload: dict[str, Any]
) -> None:
    """Gemini devuelve JSON válido envuelto en candidates."""
    gemini_text = json.dumps(sample_payload)

    def handler(request: httpx.Request) -> httpx.Response:
        # Verificamos que la API key se mande como query param.
        assert "key" in dict(request.url.params)
        body = {
            "candidates": [
                {"content": {"parts": [{"text": gemini_text}]}},
            ]
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    with patch("mtc_bot.ai_extractor.httpx.AsyncClient", patched_client):
        result = await extract_with_gemini(fake_settings, sample_text)

    assert result.modelo_ia == "gemini-2.5-flash"
    assert result.emisor == "SUTRAN"


# ─────────────────────────────────────────────────────────────────
# Fallo total: ambos proveedores caen
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_raises_when_both_providers_fail(
    fake_settings: Any, sample_text: str
) -> None:
    """DeepSeek + Gemini fallan → AIExtractionFailed."""
    deepseek_stub = AsyncMock(side_effect=httpx.ConnectError("ds-down"))
    gemini_stub = AsyncMock(side_effect=httpx.ConnectError("gem-down"))

    with (
        patch("mtc_bot.ai_extractor.extract_with_deepseek", deepseek_stub),
        patch("mtc_bot.ai_extractor.extract_with_gemini", gemini_stub),
        pytest.raises(AIExtractionFailed) as exc_info,
    ):
        await extract(sample_text, settings=fake_settings)

    msg = str(exc_info.value)
    assert "DeepSeek" in msg
    assert "Gemini" in msg
    deepseek_stub.assert_awaited_once()
    gemini_stub.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────
# Truncado de texto
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_truncates_long_text(
    fake_settings: Any, sample_payload: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Texto > 50k caracteres se trunca y se loguea warning."""
    long_text = "x" * 60_000

    captured: dict[str, str] = {}

    async def fake_deepseek(
        settings: Any,
        texto: str,
        timeout: float = 60.0,  # noqa: ASYNC109 — firma coincide con la real
    ) -> ExtractionResult:
        captured["texto"] = texto
        result = ExtractionResult.model_validate(sample_payload)
        result.modelo_ia = "deepseek-chat"
        return result

    with caplog.at_level("WARNING", logger="mtc_bot.ai_extractor"), patch(
        "mtc_bot.ai_extractor.extract_with_deepseek", side_effect=fake_deepseek
    ):
        await extract(long_text, settings=fake_settings)

    assert len(captured["texto"]) == 50_000
    assert any("truncando" in rec.message.lower() for rec in caplog.records)
