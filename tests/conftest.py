"""Configuración compartida de pytest para mtc-casilla-bot."""
from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Backend default para tests asíncronos."""
    return "asyncio"
