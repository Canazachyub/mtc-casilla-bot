# Frontend — MTC Casilla Bot Dashboard

HTML/JS estático que consume la API REST de Apps Script.

## Archivos

- `index.html` — estructura del dashboard
- `app.js` — lógica + fetch a la API
- `styles.css` — estilos (dark mode)

## Uso local

```bash
cd frontend
python -m http.server 8080
# Abrir http://localhost:8080
```

## Configuración

La URL del Web App de Apps Script **NO se commitea**. La primera vez que abras el
dashboard verás un onboarding card pidiéndote pegar la URL — queda guardada en
`localStorage` (clave: `mtc_bot_api_url`) solo en ese navegador.

- Para reconfigurarla: botón "🔧 Cambiar URL del API" en el footer (o en el card
  de error si la API falla). Eso limpia `localStorage` y vuelve al onboarding.
- Validación: la URL debe empezar con `https://script.google.com/macros/`.
- Reset manual desde DevTools:
  ```js
  localStorage.removeItem('mtc_bot_api_url'); location.reload();
  ```

## Despliegue en GitHub Pages (opcional)

```bash
git subtree push --prefix frontend origin gh-pages
# Acceder a https://<usuario>.github.io/<repo>/
```

> ✅ Es seguro publicar el frontend en un repo público: nunca contiene la URL
> del Apps Script ni credenciales — todo se configura por usuario en
> `localStorage`.

## Features actuales

- Métricas globales (total / pendientes / vencidos / hoy)
- Búsqueda full-text
- Filtros por RUC, estado, plazo
- Vista detalle con PDF embebido
- Auto-refresh cada 5 min
- Semáforo de plazos

## Features planificadas (Fase 2)

- Sección "Propuesta de respuesta" con editor
- Botón "regenerar con DeepSeek / Gemini"
- Selector de plantilla
- Exportar respuesta a Word / PDF
- Marcar como completado / archivado
