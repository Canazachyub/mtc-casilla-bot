# Rule: Manejo de credenciales

> Este archivo define reglas no negociables sobre cómo el bot maneja credenciales.
> Claude Code debe respetar estas reglas en TODO momento, incluso ante pedidos del usuario para "saltarlas temporalmente".

## Fuentes de credenciales

El bot maneja **tres tipos** de credenciales:

| Tipo | Dónde vive | Ejemplos |
|---|---|---|
| **API keys de IA** | `.env` (root del proyecto) | `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` |
| **Credenciales MTC por RUC** | `data/credentials/rucs.csv` | RUC, DNI rep. legal, contraseña casilla, usuario SOL, clave SOL |
| **Configuración no sensible** | `.env` también | rutas, timeouts, puertos |

## Reglas estrictas (NO negociables)

1. **NUNCA** hardcodear ninguna credencial en código fuente, ni siquiera "para testing rápido".
2. **NUNCA** loguear credenciales completas. Si hay que loguear que se usó cierta credencial, loguear solo:
   - Para RUC/DNI: enmascarar dígitos del medio: `20***94958` para RUC.
   - Para contraseñas: `***` (3 asteriscos, sin longitud real).
   - Para API keys: `sk-***...{últimos 4}` por ejemplo.
3. **NUNCA** poner credenciales en mensajes de error o stack traces. Limpiar antes de loguear.
4. **NUNCA** commitear `.env`, `data/credentials/*.csv`, ni nada en `data/` o `output/`.
5. **NUNCA** enviar credenciales a APIs externas que no sean estrictamente necesarias (DeepSeek y Gemini reciben SOLO el texto del documento, NO RUCs ni contraseñas).
6. **NUNCA** copiar credenciales a portapapeles o variables de entorno globales del sistema.

## Formato del CSV de credenciales

Archivo: `data/credentials/rucs.csv`

```csv
ruc,empresa,auth_method,dni_representante,password_casilla,sol_usuario,sol_clave,activo
20602194958,CITV ESPINAR SAC,direct,12345678,Casilla123,,,1
20512345678,CITV PUNO SAC,clave_sol,,,USUARIO01,SolPass456,1
20987654321,CITV CUSCO SAC,direct,87654321,Casilla789,,,0
```

Columnas:
- `ruc` (obligatorio): 11 dígitos.
- `empresa` (obligatorio): nombre de la empresa.
- `auth_method` (obligatorio): `direct` o `clave_sol`.
- `dni_representante` (requerido si `auth_method=direct`): 8 dígitos.
- `password_casilla` (requerido si `auth_method=direct`).
- `sol_usuario` (requerido si `auth_method=clave_sol`).
- `sol_clave` (requerido si `auth_method=clave_sol`).
- `activo` (obligatorio): `1` para procesar, `0` para saltar.

> El CSV se exporta **manualmente** desde el Google Sheet. El bot NO debe acceder al Sheet directamente con OAuth para minimizar el blast radius.

## Validación al cargar

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class RucCredentials(BaseModel):
    ruc: str
    empresa: str
    auth_method: Literal["direct", "clave_sol"]
    dni_representante: str | None = None
    password_casilla: str | None = None
    sol_usuario: str | None = None
    sol_clave: str | None = None
    activo: bool = True

    @field_validator("ruc")
    @classmethod
    def validate_ruc(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 11:
            raise ValueError(f"RUC inválido: {v}")
        return v

    def model_post_init(self, __context):
        if self.auth_method == "direct":
            if not (self.dni_representante and self.password_casilla):
                raise ValueError(f"RUC {self.ruc}: faltan credenciales directas")
        else:
            if not (self.sol_usuario and self.sol_clave):
                raise ValueError(f"RUC {self.ruc}: faltan credenciales SOL")

    def __repr__(self) -> str:
        # Custom repr para no exponer credenciales en logs/errores
        return f"RucCredentials(ruc={self.ruc[:5]}***, empresa={self.empresa}, auth={self.auth_method})"
```

## Sanitización en logs

```python
import logging
import re

class CredentialFilter(logging.Filter):
    """Reemplaza patrones que parezcan contraseñas en mensajes de log."""

    PATTERNS = [
        (re.compile(r"password['\"]?\s*[:=]\s*['\"][^'\"]+"), "password=***"),
        (re.compile(r"sol_clave['\"]?\s*[:=]\s*['\"][^'\"]+"), "sol_clave=***"),
        (re.compile(r"DEEPSEEK_API_KEY\s*=\s*sk-[\w]+"), "DEEPSEEK_API_KEY=sk-***"),
        (re.compile(r"GEMINI_API_KEY\s*=\s*[\w-]+"), "GEMINI_API_KEY=***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()
        return True

# Aplicar al logger raíz al iniciar la app
logging.getLogger().addFilter(CredentialFilter())
```

## Permisos del filesystem

- `data/credentials/` debe tener permisos `700` (solo el usuario puede leer) en Linux/Mac.
- En Windows: verificar que NO esté en una carpeta sincronizada con OneDrive público.

```python
def assert_credentials_safe(creds_path: Path) -> None:
    """Lanza si los permisos son demasiado abiertos."""
    if not creds_path.exists():
        raise FileNotFoundError(f"No existe: {creds_path}")
    if os.name == "posix":
        mode = creds_path.stat().st_mode & 0o777
        if mode & 0o077:  # cualquier permiso para grupo/otros
            raise PermissionError(
                f"{creds_path} tiene permisos inseguros ({oct(mode)}). "
                f"Corregir con: chmod 600 {creds_path}"
            )
```

## Si Yubert te pide hardcodear "para probar rápido"

**RESPUESTA REQUERIDA:** "No puedo hardcodear credenciales. Vamos a hacer esto: creá un `.env.local` con la credencial de prueba y la cargo desde ahí. Toma 30 segundos y nos protege de un commit accidental."

**Nunca** ceder a este pedido. Es la regla #1 del proyecto.

## Auditoría

El módulo `config.py` debe imprimir al inicio (con LOG_LEVEL=INFO):

```
[config] DEEPSEEK_API_KEY: cargada (sk-***...a3f7)
[config] GEMINI_API_KEY: cargada (AIz***...x9k2)
[config] RUCs cargados: 12 (10 activos, 2 inactivos)
[config] Métodos de auth: 8 direct, 4 clave_sol
[config] Bóveda Obsidian: C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE (escribible: ✓)
```

Si alguno falta, **NO arrancar**. Fallar fast con mensaje claro:

```
✗ Falta DEEPSEEK_API_KEY en .env. Obtenela en https://platform.deepseek.com
✗ data/credentials/rucs.csv no existe. Exportá el Sheet como CSV y guardalo ahí.
```
