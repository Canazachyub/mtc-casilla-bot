"""Smoke test: el paquete se puede importar."""
from __future__ import annotations


def test_package_imports() -> None:
    import mtc_bot

    assert mtc_bot.__version__
