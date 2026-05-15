# Guía de Operaciones — MTC Casilla Bot

## Archivos esenciales del sistema

```
C:\PROGRAMACION\RESOLVE\Resolve\
│
├── .env                                  ← API keys y configuración global
├── data\credentials\
│   ├── rucs.csv                          ← ⭐ LISTA DE EMPRESAS/RUCs (agregar aquí)
│   ├── service-account.json              ← Credenciales Google (no tocar)
│   └── oauth-credentials.json            ← Credenciales Drive (no tocar)
│
├── scripts\
│   ├── run-daily.ps1                     ← Script que ejecuta el bot
│   └── instalar-tarea-programada.ps1     ← Instala la automatización
│
└── logs\
    └── run-YYYY-MM-DD.log                ← Log de cada ejecución diaria
```

---

## Automatización activa

| Tarea | Hora | Qué hace |
|---|---|---|
| `MTC-Casilla-Bot-Daily` | **8:00 AM** | Revisa notificaciones nuevas |
| `MTC-Casilla-Bot-Evening` | **6:00 PM** | Revisa notificaciones del día |

El bot **no duplica** notificaciones — si ya procesó una, la salta.

---

## Cómo agregar un nuevo RUC / empresa

### 1. Abrí el archivo CSV

```
C:\PROGRAMACION\RESOLVE\Resolve\data\credentials\rucs.csv
```

Abrilo con Excel o Notepad. La primera fila son los encabezados:

```
ruc, empresa, auth_method, dni_representante, password_casilla, sol_usuario, sol_clave, representante_legal, activo, sede
```

### 2. Agregá una fila nueva al final

Existen **dos tipos de autenticación** según cómo accede cada empresa a la Casilla MTC:

---

#### Tipo A — Clave SOL (la mayoría de empresas)
Usa el usuario y clave SOL de SUNAT.

```
ruc,empresa,auth_method,dni_representante,password_casilla,sol_usuario,sol_clave,representante_legal,activo,sede
20601234567,MI NUEVA EMPRESA SAC,clave_sol,,,MIUSUARIOSOL,MiClaveSol123,Juan Pérez García,1,Lima
```

| Campo | Valor |
|---|---|
| `ruc` | 11 dígitos exactos |
| `empresa` | Razón social (puede incluir sede entre paréntesis) |
| `auth_method` | `clave_sol` |
| `dni_representante` | **dejar vacío** |
| `password_casilla` | **dejar vacío** |
| `sol_usuario` | Usuario SOL de SUNAT |
| `sol_clave` | Clave SOL de SUNAT |
| `representante_legal` | Nombre completo del rep. legal |
| `activo` | `1` para activar, `0` para desactivar |
| `sede` | Ciudad/sede (ej: Lima, Callao, Puno) |

---

#### Tipo B — Direct (acceso directo con DNI + contraseña)
Algunas empresas usan DNI del representante + contraseña propia de la casilla.

```
ruc,empresa,auth_method,dni_representante,password_casilla,sol_usuario,sol_clave,representante_legal,activo,sede
20601234568,OTRA EMPRESA EIRL,direct,12345678,MiPass2024,,,,Juan Quispe López,1,Puno
```

| Campo | Valor |
|---|---|
| `auth_method` | `direct` |
| `dni_representante` | DNI 8 dígitos del representante legal |
| `password_casilla` | Contraseña de la casilla MTC |
| `sol_usuario` | **dejar vacío** |
| `sol_clave` | **dejar vacío** |

---

### 3. Verificá que el bot reconoce el nuevo RUC

```powershell
cd C:\PROGRAMACION\RESOLVE\Resolve
uv run mtc-bot doctor
```

Debe aparecer en la sección "Credenciales MTC (CSV)" con el conteo actualizado.

### 4. Prueba manual (opcional)

```powershell
uv run mtc-bot run --since today --dry-run
```

El `--dry-run` muestra qué haría sin hacer nada real. Verificá que aparece la nueva empresa.

### 5. Nada más — el bot la incluye automáticamente

A las 8:00 AM y 6:00 PM el script ya procesará el nuevo RUC junto con los demás.

---

## Desactivar temporalmente un RUC

Cambiá `activo` de `1` a `0` en el CSV. El bot lo saltea sin borrarlo.

```
20601234567,MI EMPRESA SAC,clave_sol,,,USUARIO,CLAVE,Juan Pérez,0,Lima
                                                                    ↑ cambiar a 0
```

---

## Ver logs de ejecución

```powershell
# Log de hoy
Get-Content "C:\PROGRAMACION\RESOLVE\Resolve\logs\run-$(Get-Date -Format 'yyyy-MM-dd').log"

# Log de una fecha específica
Get-Content "C:\PROGRAMACION\RESOLVE\Resolve\logs\run-2026-05-16.log"
```

---

## Ejecutar manualmente (sin esperar las 8 AM)

```powershell
# Opción 1: directo (ves el output en pantalla)
cd C:\PROGRAMACION\RESOLVE\Resolve
powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1

# Opción 2: vía Task Scheduler (corre en background)
Start-ScheduledTask -TaskName 'MTC-Casilla-Bot-Daily'
```

---

## Cambiar la hora de ejecución

```powershell
# Como Administrador — cambia la tarea de mañana a las 7:00 AM
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
Set-ScheduledTask -TaskName 'MTC-Casilla-Bot-Daily' -Trigger $trigger
```

---

## Resumen del flujo diario (automático)

```
8:00 AM / 6:00 PM
    └─ Doctor check (verifica configuración)
    └─ Login a cada RUC en casilla.mtc.gob.pe
    └─ Detecta notificaciones nuevas del día
        └─ Si hay nuevas:
            ├─ Descarga PDFs adjuntos
            ├─ Une PDFs en un solo archivo
            ├─ Extrae texto (con OCR si está escaneado)
            ├─ IA analiza: resumen, tarea, plazo, tipo de acto...
            ├─ Sube PDF unido a Google Drive (YYYY/MM-Mes/RUC/)
            └─ Agrega fila al Google Sheet "MTC Casilla DB"
    └─ Reprocess: actualiza campos IA faltantes en notificaciones existentes
    └─ Guarda log en logs\run-YYYY-MM-DD.log
```

Resultado visible en: **canazachyub.github.io/mtc-casilla-bot**
