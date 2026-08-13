# Archivos `.env` y credenciales

## Contenido

- Alcance
- Auditoría
- Creación segura
- Variables faltantes
- Ejecución
- Estados y evidencia

## Alcance

Auditar por separado:

- Repositorio o módulo frontend.
- Repositorio o módulo backend.
- Proyecto de automatización QA.
- Proyecto de performance cuando tenga configuración propia.

Usar `.env` por defecto. Respetar otro nombre solo cuando el proyecto lo documente, por ejemplo `.env.test` o `.env.local`.

## Auditoría

Ejecutar primero en modo lectura:

```bash
python scripts/env_file_manager.py \
  --project frontend \
  --project backend \
  --project qa-automation \
  --qa-environment dev,main,qa \
  --qa-setting FRONTEND_URL \
  --qa-setting API_BASE_URL \
  --qa-setting TEST_USERNAME \
  --qa-setting TEST_PASSWORD
```

El script debe:

- Buscar `.env`.
- Buscar `.env.example`, `.env.sample`, `.env.template` y variantes equivalentes.
- Extraer nombres requeridos desde ejemplos y referencias del código.
- Expandir los settings necesarios para cada `--qa-environment`.
- Informar variables configuradas, faltantes o con placeholder.
- Identificar variables potencialmente secretas por nombre.
- Verificar que `.env` esté ignorado por Git.
- No imprimir, registrar ni devolver valores.

Conservar solo nombres, fuentes y estados en el historial. No leer un `.env` para copiar sus valores al chat, documentación, tablero o artefactos.

## Creación segura

Si falta `.env`, mostrar primero el proyecto, template seleccionado y nombres requeridos. Después crear:

```bash
python scripts/gitignore_manager.py --project frontend --apply

python scripts/env_file_manager.py \
  --project frontend \
  --project backend \
  --create
```

Reglas:

- No sobrescribir un `.env` existente.
- Preferir el example del mismo proyecto.
- Copiar estructura, comentarios y valores públicos de ejemplo.
- Vaciar contraseñas, tokens, connection strings y otros campos secretos.
- Agregar variables referenciadas por el código que no aparezcan en el template.
- Crear con permisos `0600`.
- Bloquear la creación si el archivo no está ignorado. Usar `gitignore_manager.py` para mantener el bloque administrado del proyecto.
- No versionar `.env`.
- No crear credenciales reales ni inventar usuarios, contraseñas o tokens.

Si no hay example, generar un `.env` mínimo con los nombres descubiertos y valores vacíos. Marcarlo `CREATED_INCOMPLETE`.

## Variables faltantes

Resolver en este orden:

1. Variables no secretas ya presentes y vigentes.
2. URLs confirmadas en `qa-knowledge/environment-routes.json`.
3. Valores no secretos documentados en ejemplos, CI/CD o runbooks.
4. Secretos disponibles en el entorno actual o gestor de secretos autorizado.
5. Preguntar únicamente por el nombre faltante y el mecanismo seguro de provisión.

Para valores no secretos, preguntar de a una cuando no exista evidencia:

```text
Falta QA_MAIN_API_BASE_URL en qa-automation/.env.
No encontré un valor confirmado en el catálogo de rutas. ¿Cuál es la URL o dónde está documentada?
```

Para secretos, no pedir el valor en chat:

```text
Falta QA_MAIN_TEST_PASSWORD.
¿La vas a configurar mediante gestor de secretos, variable del proceso o terminal local?
```

Si el valor ya está cargado en el proceso, materializarlo sin mostrarlo:

```bash
python scripts/env_file_manager.py \
  --project qa-automation \
  --materialize-from-process
```

No pasar secretos mediante `--required`, argumentos `KEY=VALUE`, URLs, nombres de archivos ni comandos que queden en el historial del shell.

## Ejecución

El proyecto Playwright carga `.env` sin ejecutar shell y sin sobrescribir variables ya presentes en el proceso. `QA_ENV_FILE` puede seleccionar otro archivo aprobado.

Ejecutar preflight:

```bash
python scripts/preflight.py \
  --require-env-file \
  --require-route-catalog \
  --require-frontend \
  --require-api
```

Bloquear cuando:

- Falta `.env`.
- `.env` no está ignorado por Git.
- Sus permisos permiten lectura de grupo u otros.
- Falta una variable obligatoria.
- Una variable conserva un placeholder.
- El ambiente no coincide con el catálogo de rutas.

No cargar automáticamente `.env` del frontend dentro del backend ni viceversa. Cada proceso utiliza el archivo de su proyecto.

## Estados y evidencia

Estados:

- `READY`
- `MISSING_ENV_FILE`
- `CREATED_INCOMPLETE`
- `INCOMPLETE`
- `UNSAFE_NOT_GITIGNORED`
- `UNSAFE_PERMISSIONS`
- `BLOCKED_UNIGNORED`
- `BLOCKED_AUTH`
- `BLOCKED_PREFLIGHT`

Registrar:

- Proyecto y ruta relativa.
- Example utilizado.
- Nombres requeridos.
- Nombres faltantes o con placeholder.
- Permisos y estado de Git ignore.
- Ambiente y `run_id`.

Registrar `values_exposed=false`. Nunca registrar valores, hashes reversibles, longitudes ni fragmentos de secretos.
