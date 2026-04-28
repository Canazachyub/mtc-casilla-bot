---
name: mtc-scraper
description: |
  Workflow para scraping del portal Casilla Electrónica MTC (casilla.mtc.gob.pe).
  Activá esta skill SIEMPRE que el usuario mencione: login MTC, casilla MTC,
  Clave SOL, descarga de notificaciones, SUTRAN, scraping del portal MTC,
  o cualquier interacción con casilla.mtc.gob.pe / api-seguridad.sunat.gob.pe.
  Cubre: login (directo y vía Clave SOL), navegación al inbox, listado de
  notificaciones nuevas, click en notificación, descarga de adjuntos PDF.
  NO usar para otras tareas de scraping no relacionadas con MTC/SUNAT.
---

# Skill: MTC Scraper

## URLs canónicas

- **Login directo:** `https://casilla.mtc.gob.pe/#/auth/login`
- **Login vía Clave SOL (OAuth SUNAT):** `https://api-seguridad.sunat.gob.pe/v1/clientessol/028ee021-0258-487e-a75d-8a6087e6d915/oauth2/login?originalUrl=https://casilla.mtc.gob.pe/#/auth/login&state=sunat`
- **Inbox (post-login):** `https://casilla.mtc.gob.pe/#/recibidos` o equivalente

## Modo de autenticación

El portal acepta dos rutas de autenticación. El CSV de credenciales debe indicar cuál usar por RUC con la columna `auth_method` (valores: `direct` | `clave_sol`).

### Ruta A: Login directo (`auth_method=direct`)

Campos del formulario en `casilla.mtc.gob.pe/#/auth/login`:
1. **Tipo de Persona** — dropdown con opción `PERSONA JURIDICA` (default para CITV)
2. **RUC** — 11 dígitos
3. **Nro. Documento** — DNI del representante legal
4. **Contraseña** — clave de la casilla

Botón: `Iniciar sesión` (azul, principal).

### Ruta B: Login vía Clave SOL (`auth_method=clave_sol`)

1. Hacer click en "Iniciar sesión con Clave SOL" en la pantalla de login del MTC.
2. Es redirigido a `api-seguridad.sunat.gob.pe`.
3. Llenar en la pantalla "Bienvenido — Ingresa los datos de tu Clave SOL":
   - Tab activo: `RUC` (no `DNI`)
   - **RUC** (11 dígitos)
   - **Usuario** (alfanumérico SOL)
   - **Contraseña** (clave SOL)
4. Click en `Entrar`.
5. SUNAT redirige de vuelta a la casilla MTC ya autenticado.

## Selectores estables (verificar antes de hardcodear)

> ⚠️ Los selectores pueden cambiar. **Antes de hardcodearlos en código, verificá con el HTML real** (pedile a Yubert que abra DevTools y pegue los selectores actuales). Estos son orientativos:

```python
# Login directo
SEL_TIPO_PERSONA = "mat-select[formcontrolname='tipoPersona']"
SEL_RUC          = "input[formcontrolname='ruc']"
SEL_DOC          = "input[formcontrolname='nroDoc']"
SEL_PASS         = "input[formcontrolname='password']"
BTN_INICIAR      = "button:has-text('Iniciar sesión')"
BTN_CLAVE_SOL    = "button:has-text('Clave SOL')"

# Login Clave SOL
SEL_SOL_RUC      = "input[placeholder='RUC']"
SEL_SOL_USER     = "input[placeholder='Usuario']"
SEL_SOL_PASS     = "input[placeholder='Contraseña']"
BTN_SOL_ENTRAR   = "button:has-text('Entrar')"

# Inbox
SEL_INBOX_LIST   = "ul.notification-list > li"      # ajustar
SEL_NOTIF_FECHA  = ".notif-date"                    # ajustar
SEL_NOTIF_LINK   = "a.notif-link"                   # ajustar
SEL_ATTACH_PDF   = "div[class*='attachment']:has(.pdf-icon)"
```

## Flujo de scraping (pseudo-código)

```python
async def process_ruc(ruc_config: RucConfig) -> list[Notification]:
    """Procesa todas las notificaciones nuevas de un RUC."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not settings.headed,
            downloads_path=settings.downloads_dir / ruc_config.ruc,
        )
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # 1. Login según método
        if ruc_config.auth_method == "direct":
            await login_direct(page, ruc_config)
        else:
            await login_clave_sol(page, ruc_config)

        # 2. Verificar que el login funcionó
        await page.wait_for_url("**/recibidos*", timeout=15000)

        # 3. Listar notificaciones nuevas (últimas 48h)
        notifications = await scan_inbox(page, since=timedelta(hours=48))

        # 4. Para cada notificación: abrir, descargar adjuntos, cerrar
        results = []
        for notif in notifications:
            if is_already_processed(notif.id):
                continue
            attachments = await download_attachments(page, notif)
            results.append(Notification(**notif, attachments=attachments))

        await context.close()
        await browser.close()
        return results
```

## Reglas de oro

1. **Una sesión a la vez por RUC.** No paralelizar el mismo RUC en múltiples browsers; el portal puede invalidar la sesión.
2. **Esperar con `wait_for_*`, no con `sleep`.** Usar `wait_for_url`, `wait_for_selector`, `wait_for_load_state`.
3. **Capturar trazas** en caso de fallo (`tracing.start(snapshots=True, screenshots=True)`) en `playwright-traces/`.
4. **Detectar errores de credenciales** explícitamente: si aparece "Usuario o contraseña incorrectos", logguear con nivel WARNING y marcar el RUC como `auth_failed` en el índice.
5. **Idempotencia:** ANTES de descargar, chequear `data/processed/index.json` — si la notificación ya fue procesada (por su ID único o asunto+fecha), saltar.
6. **Descarga por `expect_download`:**
   ```python
   async with page.expect_download() as dl_info:
       await page.click(attachment_locator)
   download = await dl_info.value
   await download.save_as(target_path)
   ```
7. **Logging de cada paso:** `logger.info("Login OK ruc=%s", ruc)`, `logger.debug("Selector encontrado: %s", sel)`.

## Detección de "notificaciones nuevas"

El portal marca las no leídas con un estilo distinto (negrita, dot azul). Estrategias:
- **Por estado leído/no leído:** preferir clase CSS si existe (`.unread`, `.no-leido`).
- **Por fecha:** filtrar las que estén dentro del rango `--since` (today / yesterday / 48h).
- **Por índice local:** comparar IDs de notificación contra `data/processed/index.json`.

Combinar las tres: una notificación se procesa si `(no leída OR dentro del rango)` AND `id no está en el índice`.

## Manejo de errores

| Error | Estrategia |
|---|---|
| Timeout en selector | Reintentar 1 vez con `wait_for_selector(state='attached', timeout=20000)`. Si persiste, capturar screenshot y abortar este RUC. |
| Login falla | Logguear, no reintentar (puede bloquear la cuenta). Marcar RUC como `auth_failed`. |
| Captcha aparece | Pausar y avisar. NO intentar resolverlo automáticamente. |
| Descarga corrupta (size=0) | Reintentar 2 veces. Si persiste, marcar adjunto como `corrupt` y continuar. |
| Sesión SUNAT expira durante OAuth | Limpiar cookies y reintentar el flujo completo desde login. |

## Configuración recomendada de Playwright

```python
browser = await p.chromium.launch(
    headless=settings.headless,
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ],
    slow_mo=100 if settings.headed else 0,
)
context = await browser.new_context(
    accept_downloads=True,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    locale="es-PE",
    timezone_id="America/Lima",
    viewport={"width": 1366, "height": 768},
)
context.set_default_timeout(settings.playwright_timeout_ms)
```

## Testing del scraper

- **Tests unitarios:** mockear `playwright.async_api` con stubs.
- **Tests de integración:** usar `playwright-codegen` para grabar un flujo real, guardar como fixture HAR.
- **Smoke test manual:** comando `uv run mtc-bot test-login --ruc <X>` que solo intenta loguear y reporta éxito/fallo.

## Referencias

- Playwright Python docs: https://playwright.dev/python/
- Mejores prácticas selectores: usar `page.get_by_role()`, `page.get_by_label()` antes que CSS selectors frágiles.
