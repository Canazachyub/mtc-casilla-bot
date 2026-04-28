# 🎯 PROMPT INICIAL — MTC Casilla Bot

> Pegá este mensaje **completo** como tu primer prompt en Claude Code después de copiar TODOS los archivos del kit a la raíz del proyecto. Este prompt orienta a Claude Code para que use 5 sub-agentes especializados en paralelo y respete el roadmap por fases.

---

## 📋 Antes de pegar el prompt

```powershell
# 1. Crear carpeta y copiar todos los archivos del kit adentro
mkdir mtc-casilla-bot
cd mtc-casilla-bot
# Copiar contenido del ZIP aquí (NO la carpeta entera, su contenido)

# 2. Inicializar git
git init
git add .
git commit -m "chore: kit inicial Claude Code v3 (Drive + AppScript + plantillas)"

# 3. Abrir Claude Code
claude

# 4. Pegar el prompt de abajo como primer mensaje
```

---

## 🚀 Pegá esto:

```
Hola Claude. Vamos a construir un sistema completo: "mtc-casilla-bot" — automatización de notificaciones de la Casilla MTC del Perú con IA, almacenamiento en Drive, API REST en Apps Script, y un dashboard web.

Tenés a tu disposición 5 sub-agentes especializados en .claude/agents/:
1. backend-python-agent — scraper, PDFs, IA local, CLI
2. cloud-google-agent — Drive, Sheets, Apps Script Web App
3. frontend-agent — HTML/JS estático del dashboard
4. templates-agent — sistema de plantillas y propuestas de respuesta
5. qa-agent — tests, code review, verificación de seguridad

Tu rol es ORQUESTADOR. NO escribas código vos directamente; delegá a los agentes especializados con la Task tool, en paralelo cuando las tareas sean independientes.

═══════════════════════════════════════════════════════════════
PASO 1 — LECTURA OBLIGATORIA (hacelo vos, NO delegues)
═══════════════════════════════════════════════════════════════

Antes de hacer NADA, leé en este orden:
1. CLAUDE.md (memoria del proyecto)
2. ROADMAP.md (fases y planificación)
3. README.md (visión general)
4. .claude/rules/credentials.md (regla de oro de seguridad)
5. .claude/rules/playwright.md (convenciones scraper)
6. .claude/skills/mtc-scraper/SKILL.md
7. .claude/skills/pdf-pipeline/SKILL.md
8. .claude/skills/ai-extractor/SKILL.md
9. .claude/skills/drive-uploader/SKILL.md
10. .claude/skills/appscript-api/SKILL.md
11. .claude/skills/response-generator/SKILL.md
12. .claude/skills/obsidian-writer/SKILL.md (opcional, fase 1)
13. Cada uno de los 5 agentes en .claude/agents/

═══════════════════════════════════════════════════════════════
PASO 2 — CONFIRMACIÓN ANTES DE EMPEZAR (NO escribas código)
═══════════════════════════════════════════════════════════════

Después de leer todo, devolveme:

A. Resumen en 5-7 líneas de lo que entendiste sobre el proyecto.

B. Listado de DUDAS que tenés. Específicamente:
   - ¿La ruta de la bóveda Obsidian es correcta?
     C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE
   - ¿Cuántos RUCs voy a procesar inicialmente?
   - ¿Tengo plantillas legales reales que vas a importar (Fase 2), o las
     voy a redactar después?
   - ¿Querés Obsidian writer activo desde Fase 1 o solo Drive/Sheet?
   - ¿El Google Sheet "MTC Casilla DB" lo creo yo manualmente o me das
     un script para crearlo?

C. Plan de FASE 0 (setup) en bullets, ANTES de empezar a codear.
   Incluí qué agentes vas a invocar y en qué orden.

D. Lista de cosas que necesitás de mí (Yubert) ANTES de Fase 1:
   - Service account JSON de Google
   - .env con DEEPSEEK_API_KEY y GEMINI_API_KEY
   - data/credentials/rucs.csv con credenciales
   - URL del Apps Script una vez deployado
   - ID de la carpeta de Drive raíz
   - ID del Google Sheet

ESPERÁ MI VISTO BUENO antes de pasar al Paso 3.

═══════════════════════════════════════════════════════════════
PASO 3 — EJECUCIÓN POR FASES CON AGENTES EN PARALELO
═══════════════════════════════════════════════════════════════

Cuando yo apruebe el plan, ejecutá según ROADMAP.md, fase por fase.

Para cada hito, IDENTIFICÁ qué tareas son INDEPENDIENTES (pueden
correr en paralelo) y cuáles dependen de otras. Usá la Task tool
para invocar agentes en PARALELO siempre que sea posible.

EJEMPLO de paralelismo en Fase 0:

  Tarea A: backend-python-agent → setup pyproject.toml + estructura
  Tarea B: cloud-google-agent   → schema del Sheet + deploy Apps Script
  Tarea C: frontend-agent       → estructura HTML + conexión a la API
  → estas 3 son INDEPENDIENTES, lanzalas en paralelo

  Después:
  Tarea D: backend-python-agent → módulo config.py (depende de A y B)
  Tarea E: qa-agent              → revisar lo entregado por A, B, C
  → D y E pueden ir en paralelo

REGLAS DE ORQUESTACIÓN:
- Nunca lances 2 agentes que tocarán los mismos archivos al mismo tiempo
  (esperá que termine uno antes de lanzar el otro).
- Después de CADA hito, invocá qa-agent para review.
- Si un agente devuelve "necesito X de otro agente", coordinálo VOS.
- Después de cada fase: commit con mensaje descriptivo, mostrame qué
  cambió, esperá visto bueno para la siguiente fase.

═══════════════════════════════════════════════════════════════
RESTRICCIONES NO NEGOCIABLES
═══════════════════════════════════════════════════════════════

❌ NUNCA hardcodear credenciales (API keys, passwords, RUCs personales)
❌ NUNCA commitear .env, data/credentials/, service-account.json
❌ NUNCA exponer el Sheet "rucs" via endpoints públicos
❌ NUNCA hacer git push --force sobre main
❌ NUNCA implementar features de fases futuras sin aprobación
❌ NUNCA escribir código directamente vos — siempre vía sub-agente
❌ NUNCA inventar selectores Playwright sin verificar con HTML real
❌ NUNCA saltar a Fase 2 si Fase 1 no está completa y QA-aprobada

✅ SIEMPRE leer skills relevantes ANTES de delegar
✅ SIEMPRE delegar a sub-agentes con instrucciones explícitas
✅ SIEMPRE invocar qa-agent al final de cada hito
✅ SIEMPRE preferir paralelismo cuando las tareas son independientes
✅ SIEMPRE preguntar antes de operaciones destructivas
✅ SIEMPRE actualizar el "Estado actual" en CLAUDE.md al final de sesión

═══════════════════════════════════════════════════════════════
CONTEXTO PERSONAL (para vos, Claude)
═══════════════════════════════════════════════════════════════

- Soy Yubert Canaza, basado en Puno, Perú.
- Trabajo en TELCOM ENERGY supervisando CITV (Centros de Inspección
  Técnica Vehicular) clientes de SUTRAN.
- Tengo experiencia previa con Python (Streamlit), Apps Script
  (EncuestaPe, SimulaUNA), Playwright/scraping, e integraciones IA.
- Hablo español, conversame en español. Código en inglés.
- Estoy en Windows 11 (PowerShell por defecto, WSL2 disponible).
- Prefiero ver pasos pequeños y verificables antes que diff gigantes.
- Si algo te genera dudas, PREGUNTÁ. No asumas.

Empezá ahora con el PASO 1 (lectura). NO empieces con código todavía.
```

---

## 🔄 Después del primer mensaje

### Cuando Claude termine la lectura y te dé el plan

Revisalo. Probablemente te pregunte cosas como:

| Pregunta | Respuesta sugerida |
|---|---|
| "¿Cuántos RUCs procesás?" | Dale el número real (ej: "12 RUCs activos") |
| "¿Plantillas reales o las redactamos?" | Decile si tenés Word/PDFs de respuestas previas o las construyen ahora |
| "¿Obsidian writer en Fase 1?" | Sí (te da backup local + Dataview) |
| "¿Creo el Sheet o me das script?" | "Creámoslo manualmente en Fase 0 con el schema que está en el SKILL" |

### Lo que SÍ tenés que hacer manualmente (Yubert)

1. **Crear el Google Sheet** con los 3 tabs según schema → te paso el ID
2. **Crear la carpeta Drive** "MTC-Casilla-Bot" → te paso el ID
3. **Crear el service account** en GCP → me paso el JSON a `data/credentials/`
4. **Compartir Sheet y Drive** con el email del SA (permiso Editor)
5. **Obtener API keys** DeepSeek y Gemini → al `.env`
6. **Llenar `data/credentials/rucs.csv`** con los RUCs reales
7. **Después de Fase 0**: deployar el Apps Script y pasarle a Claude la URL

### Una vez que Fase 1 esté lista

Para cada nuevo hito grande, podés decirle a Claude:

```
Procedé con Fase 2. Importá las plantillas que están en
RESOLVE/_templates_legales_v0/ que ya tengo redactadas.
Asigná templates-agent como lead y backend-python-agent + frontend-agent
en paralelo.
```

---

## ✅ Checklist final antes de pegar el prompt

- [ ] Estructura del kit copiada a la raíz del proyecto
- [ ] `git init` y primer commit hecho
- [ ] `.env` creado a partir de `.env.example` (con valores reales o placeholders)
- [ ] `data/credentials/` existe (vacía está OK)
- [ ] Bóveda Obsidian RESOLVE existe y la ruta es correcta
- [ ] Tenés DeepSeek API key y Gemini API key obtenidas
- [ ] Tenés acceso a tu Google Cloud Console (para crear el SA después)
- [ ] Claude Code abre la carpeta sin errores

Si todo lo de arriba está ✓, **pegá el prompt y mandá**.
