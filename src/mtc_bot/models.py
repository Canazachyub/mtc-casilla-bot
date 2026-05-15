"""Modelos de dominio Pydantic v2 para el bot MTC.

Incluye:
    * ``RucCredentials`` — credenciales de un RUC (carga desde CSV).
    * ``Attachment`` — adjunto de una notificación.
    * ``Notification`` — notificación procesada que se persiste en Sheets/Drive.
    * ``load_rucs`` — helper para cargar el CSV de RUCs.
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_REPRESENTANTE_LEGAL: str = "Mirella Shirley Camapaza Quispe"

RUC_LENGTH = 11
DNI_LENGTH = 8


# ─────────────────────────────────────────────────────────────────
# Credenciales por RUC
# ─────────────────────────────────────────────────────────────────


class RucCredentials(BaseModel):
    """Credenciales de un RUC para autenticarse en la Casilla MTC.

    Attributes:
        ruc: 11 dígitos del Registro Único de Contribuyentes.
        empresa: razón social.
        auth_method: ``direct`` (DNI + pass) o ``clave_sol`` (usuario + clave SOL).
        dni_representante: DNI 8d (requerido si ``auth_method='direct'``).
        password_casilla: contraseña casilla (requerido si ``auth_method='direct'``).
        sol_usuario: usuario SOL (requerido si ``auth_method='clave_sol'``).
        sol_clave: clave SOL (requerido si ``auth_method='clave_sol'``).
        representante_legal: nombre completo del representante legal,
            usado en plantillas. Si el CSV no lo trae, se aplica el default.
        activo: ``True`` para procesar este RUC en el ciclo.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    ruc: str
    empresa: str
    auth_method: Literal["direct", "clave_sol"]
    dni_representante: str | None = None
    password_casilla: str | None = None
    sol_usuario: str | None = None
    sol_clave: str | None = None
    representante_legal: str = DEFAULT_REPRESENTANTE_LEGAL
    activo: bool = True
    sede: str = ""

    @field_validator("ruc")
    @classmethod
    def _validate_ruc(cls, v: str) -> str:
        if not v.isdigit() or len(v) != RUC_LENGTH:
            raise ValueError(f"RUC inválido (debe ser 11 dígitos): {v}")
        return v

    @field_validator("dni_representante")
    @classmethod
    def _validate_dni(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not v.isdigit() or len(v) != DNI_LENGTH:
            raise ValueError(f"DNI inválido (debe ser 8 dígitos): {v}")
        return v

    @field_validator("representante_legal", mode="before")
    @classmethod
    def _default_representante(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return DEFAULT_REPRESENTANTE_LEGAL
        return v

    def model_post_init(self, __context: Any) -> None:
        """Valida coherencia entre ``auth_method`` y campos requeridos."""
        if self.auth_method == "direct":
            if not (self.dni_representante and self.password_casilla):
                raise ValueError(
                    f"RUC {self.ruc}: faltan credenciales directas "
                    f"(dni_representante + password_casilla)"
                )
        elif not (self.sol_usuario and self.sol_clave):
            raise ValueError(f"RUC {self.ruc}: faltan credenciales SOL (sol_usuario + sol_clave)")

    def __repr__(self) -> str:
        """Repr enmascarado: nunca expone credenciales sensibles."""
        return (
            f"RucCredentials(ruc={self.ruc[:5]}***, "
            f"empresa={self.empresa!r}, auth={self.auth_method})"
        )

    __str__ = __repr__


# ─────────────────────────────────────────────────────────────────
# Adjuntos
# ─────────────────────────────────────────────────────────────────


AttachmentRole = Literal[
    "documento_principal",
    "constancia_notificacion",
    "constancia_lectura",
    "anexo",
]


class Attachment(BaseModel):
    """Archivo adjunto descargado de una notificación.

    Attributes:
        filename: nombre original del archivo en el portal.
        path: ruta local al archivo descargado (si ya se descargó).
        role: rol del adjunto en el merge (orden importa).
        size_bytes: tamaño del archivo en bytes (si se conoce).
    """

    filename: str
    path: Path | None = None
    role: AttachmentRole
    size_bytes: int | None = None


# ─────────────────────────────────────────────────────────────────
# Notificación procesada
# ─────────────────────────────────────────────────────────────────


NotificationEstado = Literal["pendiente", "en_revision", "respondida", "archivada"]

NotificationProgreso = Literal["NO INICIADO", "AGENDAR", "EN REVISIÓN", "PRESENTADO"]

TAREAS_VALIDAS: frozenset[str] = frozenset({
    "apelación", "descargos", "remitir expedientes", "subsanar observaciones",
    "inspección", "cumplir con pago", "carta de ampliación", "cumplo requerimiento",
    "hacer algo?", "nueva solicitud", "comunicar en WhatsApp", "remitir información",
    "dar seguimiento", "archivar", "baja de ing", "pago de infracción",
    "no iniciar PAS", "carta",
})


class Notification(BaseModel):
    """Notificación procesada del portal MTC.

    Una instancia se persiste como una fila del tab ``notificaciones`` del
    Sheet "MTC Casilla DB" y como un PDF unido en Drive.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    ruc: str
    empresa: str
    sede: str = ""
    fecha_notificacion: datetime
    lectura_notificacion: datetime | None = None
    documento: str
    emisor: str = ""
    casilla_origen: str = ""
    asunto: str = ""
    referencia: str = ""
    resumen: str = ""
    tipo_acto: str = ""
    accion_requerida: str = ""
    consecuencias: str = ""
    fundamento_legal: str = ""
    tarea: list[str] = Field(default_factory=list)
    plazo_vencimiento: date | None = None
    dias_restantes: int | None = None
    progreso: NotificationProgreso = "NO INICIADO"
    requiere_respuesta: bool = False
    notas: str = ""
    confianza_ia: float | None = None
    modelo_ia: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    drive_file_id: str = ""
    drive_view_url: str = ""
    estado: NotificationEstado = "pendiente"
    representante_legal: str = DEFAULT_REPRESENTANTE_LEGAL
    procesado_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────
# Loader del CSV
# ─────────────────────────────────────────────────────────────────


def _parse_bool(value: str | None) -> bool:
    """Convierte un string del CSV en bool. Acepta ``1``, ``true``, ``yes``, ``si``."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "y"}


def load_rucs(csv_path: Path) -> list[RucCredentials]:
    """Carga el CSV de credenciales y devuelve una lista de ``RucCredentials``.

    Args:
        csv_path: ruta absoluta al archivo CSV.

    Returns:
        Lista de credenciales validadas.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si una fila no pasa la validación.
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"No existe el CSV de credenciales: {csv_path}. "
            "Exportá el tab 'rucs' del Sheet 'MTC Casilla DB' como CSV "
            "y colocalo en esa ruta."
        )

    rucs: list[RucCredentials] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):  # fila 1 = header
            try:
                payload: dict[str, Any] = {
                    "ruc": (row.get("ruc") or "").strip(),
                    "empresa": (row.get("empresa") or "").strip(),
                    "auth_method": (row.get("auth_method") or "").strip(),
                    "dni_representante": (row.get("dni_representante") or "").strip() or None,
                    "password_casilla": (row.get("password_casilla") or "").strip() or None,
                    "sol_usuario": (row.get("sol_usuario") or "").strip() or None,
                    "sol_clave": (row.get("sol_clave") or "").strip() or None,
                    "activo": _parse_bool(row.get("activo")),
                "sede": (row.get("sede") or "").strip(),
                }
                rep = (row.get("representante_legal") or "").strip()
                if rep:
                    payload["representante_legal"] = rep
                rucs.append(RucCredentials(**payload))
            except Exception as exc:
                raise ValueError(f"Error en fila {idx} del CSV {csv_path.name}: {exc}") from exc

    activos = sum(1 for r in rucs if r.activo)
    direct = sum(1 for r in rucs if r.auth_method == "direct")
    sol = sum(1 for r in rucs if r.auth_method == "clave_sol")
    logger.info("Cargados %d RUCs (%d activos)", len(rucs), activos)
    logger.info("Métodos de auth: %d direct, %d clave_sol", direct, sol)
    return rucs
