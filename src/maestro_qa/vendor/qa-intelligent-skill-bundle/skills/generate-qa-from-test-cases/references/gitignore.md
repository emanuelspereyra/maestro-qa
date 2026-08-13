# Protección de archivos con `.gitignore`

## Alcance

Auditar por separado los proyectos frontend, backend, automatización y performance. Ejecutar la auditoría después de obtener cada proyecto local y repetirla cuando la skill genere un nuevo tipo de artefacto.

La skill administra únicamente el bloque delimitado por:

```text
# BEGIN QA SKILL MANAGED
# END QA SKILL MANAGED
```

Conservar todas las reglas existentes fuera de ese bloque. No reemplazar el archivo completo.

## Auditoría y preview

Ejecutar primero sin `--apply`:

```bash
python scripts/gitignore_manager.py \
  --project frontend \
  --project backend \
  --project qa-automation \
  --project qa-performance
```

El reporte identifica:

- Stacks detectados.
- Patrones planificados y faltantes.
- Archivos sensibles candidatos, sin leer ni mostrar sus valores.
- Archivos sensibles que Git ya está siguiendo.
- Proyectos cuyo escaneo quedó truncado.

Mostrar el preview antes de modificar repositorios obtenidos del cliente. Después aplicar:

```bash
python scripts/gitignore_manager.py \
  --project frontend \
  --project backend \
  --project qa-automation \
  --project qa-performance \
  --apply
```

La operación es idempotente: repetirla no duplica reglas.

## Reglas administradas

Agregar solo reglas pertinentes:

- Secretos locales: `.env`, variantes de ambiente, claves y certificados privados.
- Excepciones versionables: `.env.example`, `.env.sample` y `.env.template`.
- Archivos locales de sistema, editor y logs runtime.
- QA: evidencias, historial runtime, resultados y reportes de Playwright.
- Python: entornos virtuales, caches, coverage y bytecode.
- Node/Playwright: dependencias, caches, builds, coverage y runtime local.
- Java/REST Assured: `target/`, `.gradle/` y builds.
- .NET: `bin/`, `obj/`, `.vs/` y `TestResults/`.

Cuando se detecta un archivo de credenciales específico, por ejemplo un `credentials.json` real, agregar su ruta exacta. No usar reglas amplias como `*.json`, `*.csv`, `config/` o `data/`.

Mantener versionados:

- `qa-project.yaml`, porque contiene configuración no sensible.
- `qa-knowledge/`, porque conserva el modelo y trazabilidad del producto.
- `.env.example`, `.env.sample` y `.env.template`, siempre sin valores secretos.
- Casos de prueba y código de automatización.
- Fixtures o datasets que el equipo haya aprobado como fuente.

## Archivos ya versionados

`.gitignore` no deja de seguir un archivo que ya fue agregado a Git y no elimina secretos del historial.

Si el reporte devuelve `BLOCKED_TRACKED_SENSITIVE`:

1. No afirmar que el problema quedó resuelto.
2. Informar únicamente la ruta, nunca el valor.
3. Detener commits o publicaciones que puedan exponerlo.
4. Solicitar autorización para retirarlo del índice mediante el flujo del repositorio.
5. Recomendar rotar o revocar la credencial.
6. Si llegó al historial remoto, coordinar una limpieza de historial según la política del cliente.

La skill no ejecuta automáticamente `git rm --cached`, no reescribe historial y no rota secretos.

## Patrones adicionales

Agregar una regla específica solo después de revisar el archivo:

```bash
python scripts/gitignore_manager.py \
  --project qa-automation \
  --extra-pattern "/tmp/local-session.json"
```

Evitar rutas absolutas, valores secretos y nombres generados desde credenciales. Registrar solo el patrón y el resultado.

## Estados

- `READY`: no hay cambios ni bloqueos.
- `CHANGES_REQUIRED`: el preview encontró reglas faltantes.
- `UPDATED`: se actualizó el bloque administrado.
- `BLOCKED_TRACKED_SENSITIVE`: Git ya sigue un archivo sensible.
- `ERROR`: el archivo no se pudo leer o el bloque está mal formado.

Registrar eventos `gitignore-audit`, `gitignore-updated` y `tracked-sensitive` con `values_exposed=false`.
