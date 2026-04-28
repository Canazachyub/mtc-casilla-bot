# data/templates/ — Copia local sincronizada

Esta carpeta es una **copia local** de las plantillas legales del bot.

## Source of truth

La fuente de verdad NO vive acá. Vive en la bóveda Obsidian del usuario:

```
C:\Users\User\Documents\CEREBRO DIGITAL\RESOLVE\RESOLVE\_templates\
```

Yubert edita las plantillas directamente en Obsidian (frontmatter + cuerpo
con placeholders `{{variable}}`). Esta carpeta solo se usa como caché local
para que el bot Python pueda leer las plantillas sin abrir la bóveda.

## Sincronización

El comando que mantiene esta carpeta al día (Fase 2):

```bash
uv run mtc-bot templates sync
```

Ese comando:

1. Lee los `.md` desde `RESOLVE/_templates/` en la bóveda Obsidian.
2. Copia cada plantilla acá (`data/templates/<id>.md`).
3. Sube las mismas a Drive (`MTC-Casilla-Bot/_templates/`) para que
   Apps Script también pueda leerlas desde la nube.

## Git

Esta carpeta está en `.gitignore`. Solo se versiona el `.gitkeep` y este
README. **Nunca** commitear archivos `.md` reales acá: las plantillas son
propiedad intelectual del equipo legal y se versionan en la bóveda
Obsidian (que puede tener su propio repo privado).

## Estado actual

Vacía. Las plantillas reales se importarán en Fase 2 con material que
provea Yubert.
