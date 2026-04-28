# Rule: Convenciones de Playwright

> Reglas y patrones que el código del scraper DEBE seguir.

## Setup base

```python
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from contextlib import asynccontextmanager

@asynccontextmanager
async def browser_session(headless: bool = True, downloads_path: Path | None = None):
    """Context manager que asegura cierre limpio del browser."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox" if os.name == "posix" else "",
            ],
            slow_mo=100 if not headless else 0,
        )
        context = await browser.new_context(
            accept_downloads=True,
            locale="es-PE",
            timezone_id="America/Lima",
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.set_default_timeout(settings.playwright_timeout_ms)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
```

## Selectores: orden de preferencia

1. **`get_by_role`** — más estable, accesible por defecto:
   ```python
   await page.get_by_role("button", name="Iniciar sesión").click()
   ```

2. **`get_by_label`** — para inputs:
   ```python
   await page.get_by_label("RUC").fill(ruc)
   ```

3. **`get_by_placeholder`** — para inputs sin label:
   ```python
   await page.get_by_placeholder("Contraseña").fill(password)
   ```

4. **`get_by_text`** — para texto visible:
   ```python
   await page.get_by_text("Iniciar sesión con Clave SOL").click()
   ```

5. **CSS selector con `formcontrolname`** (Angular) — solo si lo anterior no aplica:
   ```python
   await page.locator("input[formcontrolname='ruc']").fill(ruc)
   ```

6. **XPath** — último recurso, frágil. Documentar bien:
   ```python
   # Solo si no hay otra opción. Comentar QUÉ representa el elemento.
   await page.locator("xpath=//div[contains(@class, 'notif')][1]").click()
   ```

## Esperas: nunca `sleep`

```python
# ❌ MAL
await asyncio.sleep(3)

# ✅ BIEN
await page.wait_for_url("**/recibidos*", timeout=15000)
await page.wait_for_load_state("networkidle")
await page.wait_for_selector(".inbox-loaded", state="visible")
```

Excepción: `slow_mo` en modo headed para debugging visual está OK.

## Manejo de descargas

```python
async def download_attachment(page: Page, locator: str, target_dir: Path) -> Path:
    """Descarga el archivo al hacer click en `locator` y devuelve el path final."""
    target_dir.mkdir(parents=True, exist_ok=True)

    async with page.expect_download(timeout=30000) as download_info:
        await page.locator(locator).click()

    download = await download_info.value
    suggested = download.suggested_filename
    target = target_dir / suggested
    await download.save_as(target)

    # Validar tamaño no-cero
    if target.stat().st_size == 0:
        target.unlink()
        raise ValueError(f"Descarga vacía para {suggested}")

    return target
```

## Tracing para debug

Activar tracing **solo en modo debug** o si hay un fallo, no en cada run normal:

```python
async def with_tracing(context: BrowserContext, output_path: Path):
    """Context manager que activa tracing y lo guarda al salir."""
    await context.tracing.start(snapshots=True, screenshots=True, sources=True)
    try:
        yield
    finally:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await context.tracing.stop(path=output_path)
```

Uso:
```python
if settings.debug or login_failed:
    trace_path = Path(f"playwright-traces/{ruc}_{datetime.now():%Y%m%d_%H%M%S}.zip")
    async with with_tracing(context, trace_path):
        ...
```

Ver el trace después: `playwright show-trace playwright-traces/<archivo>.zip`

## Detección de errores específicos del portal

```python
async def detect_login_error(page: Page) -> str | None:
    """Devuelve el mensaje de error si el login falló, None si OK."""
    error_selectors = [
        ".mat-error",
        ".error-message",
        "[role='alert']",
    ]
    for sel in error_selectors:
        try:
            element = page.locator(sel).first
            if await element.is_visible(timeout=1000):
                return await element.inner_text()
        except Exception:
            continue
    return None
```

## Reintentos

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from playwright.async_api import TimeoutError as PlaywrightTimeout

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(PlaywrightTimeout),
    reraise=True,
)
async def open_inbox(page: Page) -> None:
    await page.goto("https://casilla.mtc.gob.pe/#/recibidos")
    await page.wait_for_selector(SEL_INBOX_LIST, timeout=10000)
```

> Reintentos solo en errores **transitorios** (timeout, network error). NO en errores de credenciales o validación.

## Cookies y sesión

- **NO persistir cookies entre runs.** Cada ejecución hace login fresh.
- Razón: las sesiones MTC pueden invalidarse en el servidor sin previo aviso, y trabajar con cookies viejas genera errores opacos.
- Si en el futuro se quiere optimizar, persistir solo el `storage_state` y validar al iniciar:
  ```python
  context = await browser.new_context(storage_state="data/sessions/ruc.json")
  # Verificar que la sesión sigue válida antes de usarla
  ```

## Headed mode para debugging

Cuando algo falla y necesitamos ver qué pasa:

```bash
MTC_BOT_HEADED=1 uv run mtc-bot run --ruc 20602194958
```

En código:
```python
headless = not settings.headed  # default True
slow_mo = 200 if settings.headed else 0  # ralentizar para ver
```

## Checklist antes de declarar el scraper "listo"

- [ ] No hay selectores hardcodeados que dependan de IDs autogenerados
- [ ] Todas las esperas usan `wait_for_*`, no `sleep`
- [ ] Login exitoso valida con `wait_for_url` que llegamos al inbox
- [ ] Login fallido detecta el error y NO reintenta indefinidamente
- [ ] Descargas validan tamaño no-cero
- [ ] Tracing se activa automáticamente ante fallos
- [ ] Cleanup del browser en `finally`, siempre
- [ ] Logs no contienen credenciales (filtrados por `CredentialFilter`)
- [ ] Tests con HAR o stubs cubren al menos: login OK, login falló, inbox vacío, 1 notificación, 4 adjuntos
