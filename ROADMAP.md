# 🗺️ ROADMAP — MTC Casilla Bot

> Plan de evolución por fases. Las fases son **incrementales**: cada una agrega valor sobre la anterior. NO empezar Fase 2 antes de tener Fase 1 funcionando end-to-end.

---

## 🎯 Visión global

| Fase | Foco | Entregable principal |
|---|---|---|
| **0** | Setup + foundations | Estructura, config, credenciales, primer login |
| **1** | MVP del pipeline | De notificación nueva → nota Drive + Sheet + frontend básico |
| **2** | Sistema de plantillas | Propuestas de respuesta editables desde el frontend |
| **3** | IA en la nube | Regeneración desde Apps Script sin Python local |
| **4** | Productividad | Editor avanzado, exportación Word/PDF, notificaciones |
| **5** | Multi-cliente | Onboarding de nuevas empresas, white-label, multi-tenant |

---

## ✅ FASE 0 — Setup (días 1-2)

**Owner:** backend-python-agent · cloud-google-agent

- [ ] Estructura del proyecto (`src/`, `tests/`, `.claude/`)
- [ ] `pyproject.toml` con uv
- [ ] `config.py` que carga `.env` y CSV de RUCs
- [ ] Service account de Google creado y JSON guardado
- [ ] Sheet "MTC Casilla DB" con los 3 tabs (notificaciones, logs, rucs)
- [ ] Carpeta Drive "MTC-Casilla-Bot/" creada y compartida con SA
- [ ] Apps Script Web App deployado (endpoints health + summary funcionan)
- [ ] Frontend abre, conecta con la API, muestra "0 notificaciones"
- [ ] Test de login MTC para 1 RUC funciona (`mtc-bot test-login`)

**Criterio de Done Fase 0:** correr `mtc-bot doctor` devuelve todo verde.

---

## 🚀 FASE 1 — MVP del pipeline (días 3-7)

**Owner:** backend-python-agent + cloud-google-agent + qa-agent

- [ ] Scraper completo: login (directo + Clave SOL), inbox, descarga
- [ ] PDF pipeline: merge ordenado + rename + extracción texto
- [ ] AI Extractor: DeepSeek primario, Gemini fallback, schema Pydantic
- [ ] Drive uploader: estructura `YYYY/MM/RUC/` automática
- [ ] Sheet writer: append + idempotencia por `id` único
- [ ] Obsidian writer (opcional pero recomendado): nota .md con frontmatter
- [ ] CLI `mtc-bot run --since today` ejecuta el pipeline end-to-end
- [ ] Idempotencia: re-ejecutar no duplica
- [ ] Frontend: lista, filtros, detalle con PDF embebido
- [ ] Tests: ≥70% coverage en módulos críticos
- [ ] QA pass: 0 críticos, ≤2 mayores

**Criterio de Done Fase 1:** una notificación que llegó hoy aparece en el frontend en <5 minutos después de correr `mtc-bot run`.

---

## ✉️ FASE 2 — Sistema de plantillas (días 8-12)

**Owner:** templates-agent + backend-python-agent + frontend-agent

- [ ] Estructura `RESOLVE/_templates/` con primeras 5 plantillas reales:
  - `sutran-solicitud-expedientes.md`
  - `sutran-solicitud-filmaciones.md`
  - `sutran-descargo-observacion.md`
  - `sutran-cumplimiento-resolucion.md`
  - `generica-acuse-recibo.md`
- [ ] `response_generator.py` con scoring + matcher
- [ ] Sincronización plantillas Obsidian → Drive (`mtc-bot sync-templates`)
- [ ] Pipeline integra rellenado tras la extracción IA
- [ ] Sheet ampliado con columnas:
  - `template_id`
  - `propuesta_respuesta`
  - `propuesta_calidad` (alta/media/baja)
  - `estado_propuesta` (borrador/aprobada/enviada)
- [ ] Frontend muestra propuesta editable en modal detalle
- [ ] Frontend con botones: 💾 Guardar · ✅ Aprobar · 📋 Copiar
- [ ] Apps Script con endpoint `?action=update_proposal` (POST con token)
- [ ] Tests: matcher con ≥3 casos reales históricos

**Criterio de Done Fase 2:** una notificación SUTRAN típica llega → 30 segundos después hay propuesta de respuesta lista para revisar y editar en el frontend.

---

## ☁️ FASE 3 — IA en la nube (días 13-15)

**Owner:** cloud-google-agent + frontend-agent

> El equipo legal puede regenerar/editar respuestas SIN tener Python corriendo. Útil para revisar desde móvil, desde otra máquina, o un domingo.

- [ ] Apps Script con `UrlFetchApp` a DeepSeek
- [ ] Apps Script con `UrlFetchApp` a Gemini
- [ ] API keys en `PropertiesService.getScriptProperties()`
- [ ] Token `X-Bot-Token` validado para POSTs
- [ ] Endpoint `?action=regenerate&id=X&model=deepseek|gemini`
- [ ] Frontend con botones 🔄 DeepSeek y 🤖 Gemini
- [ ] Loading state durante regeneración (puede tardar 5-15s)
- [ ] Manejo de timeout / error con mensaje claro
- [ ] Logging de regeneraciones en tab `logs` del Sheet (quién, cuándo, qué cambió)

**Criterio de Done Fase 3:** desde el celular, abrir el frontend (GH Pages), abrir una notif, click "Regenerar con Gemini", ver propuesta nueva en 10 segundos.

---

## 🛠️ FASE 4 — Productividad (días 16-21)

**Owner:** frontend-agent + templates-agent

- [ ] Editor enriquecido (textarea → contenteditable con bullets, bold, etc.)
- [ ] Diff visual entre versiones de la propuesta
- [ ] Exportar a Word (`.docx`) usando `python-docx` (con membrete)
- [ ] Exportar a PDF (vía `python-docx` + LibreOffice headless)
- [ ] Crear Google Doc desde la propuesta (botón "Abrir como Doc")
- [ ] Sistema de comentarios por notificación
- [ ] Marcar como "enviada" + tracking de fecha de respuesta
- [ ] Notificaciones por correo (Gmail API) cuando aparece notif urgente (<2 días)
- [ ] Telegram bot opcional (`mtc-bot notify --telegram`)
- [ ] Vista calendario con plazos
- [ ] Métricas: tiempo promedio de respuesta, % completado a tiempo

**Criterio de Done Fase 4:** se puede llevar todo el ciclo (recepción → análisis → propuesta → revisión → exportación → envío manual → tracking) desde el dashboard sin abrir Word ni Drive manualmente.

---

## 🏢 FASE 5 — Multi-cliente (mes 2)

**Owner:** todos

> Si TELCOM ENERGY quiere ofrecer esto como servicio a otros CITV o empresas reguladas.

- [ ] Onboarding wizard para agregar nuevo RUC
- [ ] Multi-tenancy: cada empresa ve solo sus notificaciones
- [ ] Auth en frontend (Google Sign-In + whitelist)
- [ ] Personalización de plantillas por empresa
- [ ] Dashboards por empresa
- [ ] Reportes mensuales (PDF) generados automáticamente
- [ ] SLA monitoring: alertas si una notificación no fue procesada en N horas

---

## 🔮 Ideas futuras (sin fecha)

- **OCR para escaneados** (Tesseract o Gemini Vision)
- **Voice notes**: dictar comentarios de revisión a la nota
- **Búsqueda semántica** de notificaciones similares (embeddings)
- **Auto-aprende plantillas**: si Yubert edita la propuesta, aprender los cambios para futuras notif similares
- **Integración con casillas de OTRAS entidades** (OEFA, INDECOPI, OSITRAN)
- **App móvil nativa** (después de Fase 4 si hay demanda)

---

## 📋 Reglas de evolución

1. **No saltar fases.** Si Fase 1 está al 80%, no empezar Fase 2 — terminar primero.
2. **Cada fase debe tener QA pass** (qa-agent) antes de declararse done.
3. **Cada fase debe ser deployable.** Si la Fase 2 se demora, la Fase 1 sigue siendo útil.
4. **Decision Log obligatorio** en `CLAUDE.md` para cada cambio arquitectónico.
5. **No agregar features fuera del roadmap** sin discutirlo. La velocidad viene de la disciplina, no de improvisar.

---

## 🤖 Asignación de agentes por fase

| Fase | backend-python | cloud-google | frontend | templates | qa |
|---|:-:|:-:|:-:|:-:|:-:|
| 0 | ✓✓✓ | ✓✓✓ | ✓ | — | ✓ |
| 1 | ✓✓✓ | ✓✓ | ✓✓ | — | ✓✓ |
| 2 | ✓✓ | ✓ | ✓✓ | ✓✓✓ | ✓✓ |
| 3 | ✓ | ✓✓✓ | ✓✓ | ✓ | ✓ |
| 4 | ✓✓ | ✓ | ✓✓✓ | ✓✓ | ✓✓ |
| 5 | ✓✓ | ✓✓ | ✓✓ | ✓✓ | ✓✓✓ |

> ✓ = involucrado · ✓✓ = activo · ✓✓✓ = lead

---

## 💸 Estimación de costos (mensual, 50 notificaciones)

| Servicio | Costo |
|---|---|
| DeepSeek API | <$0.10 USD |
| Gemini Flash API | gratis (tier free) |
| Google Drive (storage PDFs) | gratis (incluido en Workspace) |
| Apps Script | gratis |
| GitHub Pages (frontend) | gratis |
| **Total** | **<$0.10 USD/mes** |

> Los costos escalan linealmente con el volumen de notificaciones. Para 500/mes: ~$1 USD/mes.
