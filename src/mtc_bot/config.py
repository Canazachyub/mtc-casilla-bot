"""Configuración global del bot MTC.

Carga variables desde el archivo `.env` ubicado en la raíz del proyecto y
expone un singleton `Settings` validado con Pydantic. Incluye también el
filtro de credenciales que se aplica al logger raíz para evitar fugas.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Raíz del proyecto: src/mtc_bot/config.py -> ../../..
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
SECRET_TAIL_REVEALED = 4


# ─────────────────────────────────────────────────────────────────
# Filtro de credenciales (sanitización de logs)
# ─────────────────────────────────────────────────────────────────


class CredentialFilter(logging.Filter):
    """Reemplaza patrones que parezcan credenciales en mensajes de log."""

    PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"password['\"]?\s*[:=]\s*['\"][^'\"]+"), "password=***"),
        (re.compile(r"sol_clave['\"]?\s*[:=]\s*['\"][^'\"]+"), "sol_clave=***"),
        (re.compile(r"DEEPSEEK_API_KEY\s*=\s*sk-[\w]+"), "DEEPSEEK_API_KEY=sk-***"),
        (re.compile(r"GEMINI_API_KEY\s*=\s*[\w-]+"), "GEMINI_API_KEY=***"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Aplica los patrones de redacción al mensaje del registro."""
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — el logging no debe romper la app
            return True
        for pattern, replacement in self.PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()
        return True


def apply_credential_filter() -> None:
    """Instala el ``CredentialFilter`` en el logger raíz (idempotente)."""
    root = logging.getLogger()
    if not any(isinstance(f, CredentialFilter) for f in root.filters):
        root.addFilter(CredentialFilter())


# ─────────────────────────────────────────────────────────────────
# Helpers de resolución de paths
# ─────────────────────────────────────────────────────────────────


def _resolve_relative(value: Path | str | None) -> Path | None:
    """Resuelve una ruta relativa respecto a ``PROJECT_ROOT``.

    Args:
        value: ruta absoluta, relativa o ``None``.

    Returns:
        ``Path`` absoluto o ``None`` si la entrada era nula.
    """
    if value is None:
        return None
    p = Path(value)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


# ─────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Configuración del bot leída de ``.env`` y variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─ APIs IA ─
    deepseek_api_key: SecretStr = Field(...)
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    gemini_api_key: SecretStr = Field(...)
    gemini_model: str = "gemini-2.5-flash"

    # ─ Google ─
    google_service_account_json: Path = Field(default=Path("data/credentials/service-account.json"))
    drive_root_folder_id: str = Field(...)
    drive_templates_folder: str = "_templates"
    sheet_id: str = Field(...)
    sheet_tab_notificaciones: str = "notificaciones"
    sheet_tab_logs: str = "logs"
    sheet_tab_rucs: str = "rucs"

    # ─ Apps Script ─
    appscript_api_url: str = ""
    appscript_token: SecretStr | None = None

    # ─ Obsidian ─
    obsidian_vault_path: Path | None = None
    obsidian_templates_folder: str = "_templates"
    enable_obsidian_writer: bool = True

    # ─ OAuth Drive upload ─
    oauth_credentials_json: Path = Field(default=Path("data/credentials/oauth-credentials.json"))
    oauth_token_json: Path = Field(default=Path("data/credentials/oauth-token.json"))
    google_oauth_hint: str = ""  # email hint para el selector de cuenta OAuth

    # ─ MTC scraper ─
    mtc_credentials_csv: Path = Field(default=Path("data/credentials/rucs.csv"))
    playwright_timeout_ms: int = Field(default=30000, validation_alias="PLAYWRIGHT_TIMEOUT")
    mtc_bot_headed: bool = Field(default=False, validation_alias="MTC_BOT_HEADED")
    max_concurrent_rucs: int = 1
    max_retries: int = 3

    # ─ Plantillas ─
    template_match_min_score: int = 30
    template_match_high_score: int = 100

    # ─ IA params ─
    ai_temperature: float = 0.1
    ai_max_tokens: int = 1024
    ai_timeout_seconds: int = 60

    # ─ Logging ─
    log_level: str = "INFO"
    log_file: Path | None = None

    # ── Validators ─────────────────────────────────────────────

    @field_validator(
        "google_service_account_json",
        "mtc_credentials_csv",
        "oauth_credentials_json",
        "oauth_token_json",
        mode="after",
    )
    @classmethod
    def _resolve_required_path(cls, v: Path) -> Path:
        """Convierte rutas relativas a absolutas relativas al root."""
        return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()

    @field_validator("obsidian_vault_path", "log_file", mode="after")
    @classmethod
    def _resolve_optional_path(cls, v: Path | None) -> Path | None:
        if v is None:
            return None
        return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve el singleton de ``Settings`` (cacheado).

    Returns:
        Instancia única de ``Settings``.
    """
    return Settings()  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────
# Auditoría
# ─────────────────────────────────────────────────────────────────


def _mask_secret(secret: SecretStr | None, prefix: str = "") -> str:
    """Devuelve una representación enmascarada de un ``SecretStr``.

    Args:
        secret: el secreto a enmascarar (puede ser ``None``).
        prefix: prefijo conocido (ej. ``"sk-"``) que se preserva al inicio.

    Returns:
        String tipo ``"sk-***...a3f7"`` o ``"<no seteado>"``.
    """
    if secret is None:
        return "<no seteado>"
    raw = secret.get_secret_value()
    if not raw:
        return "<vacío>"
    last4 = raw[-SECRET_TAIL_REVEALED:] if len(raw) >= SECRET_TAIL_REVEALED else "***"
    head = prefix if prefix and raw.startswith(prefix) else ""
    return f"{head}***...{last4}"


def audit_print_settings(settings: Settings) -> None:
    """Imprime un audit log de las variables sensibles, ya enmascaradas.

    Cumple con la política descrita en ``.claude/rules/credentials.md``.
    """
    logger.info(
        "[config] DEEPSEEK_API_KEY: cargada (%s)",
        _mask_secret(settings.deepseek_api_key, prefix="sk-"),
    )
    logger.info(
        "[config] GEMINI_API_KEY: cargada (%s)",
        _mask_secret(settings.gemini_api_key, prefix="AIz"),
    )
    if settings.appscript_token is not None:
        logger.info(
            "[config] APPSCRIPT_TOKEN: cargado (%s)",
            _mask_secret(settings.appscript_token),
        )
    else:
        logger.info("[config] APPSCRIPT_TOKEN: <no seteado>")

    logger.info("[config] SHEET_ID: %s", settings.sheet_id)
    logger.info("[config] DRIVE_ROOT_FOLDER_ID: %s", settings.drive_root_folder_id)
    logger.info(
        "[config] SERVICE_ACCOUNT_JSON: %s (existe: %s)",
        settings.google_service_account_json,
        settings.google_service_account_json.exists(),
    )
    logger.info(
        "[config] OBSIDIAN_VAULT_PATH: %s",
        settings.obsidian_vault_path or "<no seteado>",
    )
    logger.info(
        "[config] MTC_CREDENTIALS_CSV: %s (existe: %s)",
        settings.mtc_credentials_csv,
        settings.mtc_credentials_csv.exists(),
    )
