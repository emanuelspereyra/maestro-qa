# Datos de prueba y bases

## Contenido

- Contrato y fuentes de restricciones
- SQL Server
- MongoDB y otras NoSQL
- Datos manuales
- Salidas JSON y CSV
- Inventario visible y recibos de seed
- Dependencias de APIs de terceros
- Consultas de verificación posteriores
- Paralelismo y cleanup

## Contrato de datos

Crear un `dataset_id` por caso o grupo compatible. Incluir:

- Semilla.
- Entidades.
- Cantidades.
- Campos válidos, inválidos y límite.
- Relaciones.
- Destino.
- Método de setup.
- `qa_run_id`.
- Método y orden de cleanup.
- Campos identificadores y visibles que pueden mostrarse sin revelar secretos.

Usar `scripts/generate_dataset.py` con `assets/dataset-spec.template.json`.

## Dependencias de APIs de terceros

Si parte del dataset solo puede obtenerse mediante un proveedor externo, leer [external-service-mocking.md](external-service-mocking.md) y elegir explícitamente:

- Sandbox real para demostrar la integración efectiva.
- Mock contractual para probar de forma determinista la lógica propia, persistencia, reintentos y manejo de errores.
- Fixture sanitizado si solo se necesita un payload y no puede levantarse un servidor.
- `BLOCKED_DATA_SETUP` si no existe contrato confiable ni vía autorizada.

Derivar el mock de evidencia versionada, iniciarlo en loopback con `scripts/mock_api_server.py` y seleccionar escenarios desde la suite. Mantener casos separados contra el sandbox real. En el dataset y el historial guardar servicio, modo, escenario y versión de contrato; nunca copiar credenciales o PII del tercero.

## Salidas JSON y CSV

Generar siempre dos representaciones sincronizadas:

- JSON canónico con dataset, entidades, relaciones, semilla y `qa_run_id`.
- CSV para consumo manual, importaciones y revisión.

Ejecutar:

```bash
python scripts/generate_dataset.py dataset-spec.json \
  --output qa-artifacts/data/dataset.json \
  --csv-dir qa-artifacts/data/dataset-csv
```

Para varias tablas o colecciones, generar:

```text
dataset.json
dataset-csv/
├── users.csv
├── items.csv
└── manifest.csv
```

Crear un CSV por entidad para no mezclar columnas incompatibles. Usar `manifest.csv` para registrar `dataset_id`, `run_id`, entidad, archivo, tabla o colección y cantidad de filas.

Generar además `dataset-inventory.json`, `dataset-inventory.csv` y `dataset-inventory.md`. El inventario debe mostrar entidad, tabla o colección, cantidad, identificadores y campos visibles sanitizados.

Conservar columnas de claves primarias, foráneas y `qa_run_id`. Representar `null` como celda vacía. Serializar objetos y listas NoSQL como JSON compacto dentro de una celda. Usar UTF-8, encabezados estables y saltos de línea deterministas.

Tratar el JSON como fuente canónica. Si JSON y CSV difieren, bloquear el seed o la ejecución hasta regenerar ambos desde la misma semilla.

## Inventario visible y recibos de seed

Distinguir siempre:

- `GENERATED_NOT_INSERTED`: los registros existen en los artefactos, no en la base.
- `PLANNED_NOT_INSERTED`: el dry-run muestra qué se insertaría.
- `INSERTED`: la transacción terminó con commit y el recibo refleja registros realmente insertados.
- `CLEANED`: el cleanup confirmó cuántos registros eliminó por destino.

Después de generar datos, mostrar una tabla equivalente a:

```text
Estado                 Entidad  Tabla/Colección  Cantidad  Identificadores
GENERATED_NOT_INSERTED users    dbo.users        2         id, email
GENERATED_NOT_INSERTED items    dbo.items        2         id, owner_id
```

El resumen visible no reemplaza los artefactos. Enlazar siempre:

- Dataset JSON canónico con los registros sintéticos completos.
- CSV por entidad.
- `manifest.csv` con destino y cantidad.
- Inventario JSON/CSV/Markdown sanitizado.
- Recibo de seed o cleanup cuando se ejecutó una escritura.

Definir en cada entidad `identifier_fields`, `display_fields` y `sensitive_fields`. No mostrar ni guardar en inventarios passwords, tokens, cookies, credenciales o connection strings aunque aparezcan por error en el dataset.

Generar o reconstruir el inventario con:

```bash
python scripts/data_inventory.py qa-artifacts/data/dataset.json \
  --output qa-artifacts/data/dataset-inventory.json \
  --csv qa-artifacts/data/dataset-inventory.csv \
  --markdown qa-artifacts/data/dataset-inventory.md
```

En dry-run y seed, solicitar un recibo:

```bash
python scripts/db_tool.py seed-mssql \
  --dataset qa-artifacts/data/dataset.json \
  --receipt qa-artifacts/data/receipts/<run_id>-seed.json
```

Sin `--execute`, el recibo debe decir `PLANNED_NOT_INSERTED`. Para insertar, mantener además `QA_ALLOW_DB_WRITE=true`, `--execute`, `--allow-write` y el ambiente autorizado.

Después del commit, registrar un evento de historial por tabla o colección con `module=data`, `action=seed-inserted`, `target=<tabla_o_colección>`, `dataset_id`, cantidad, estado de evento `EXECUTED`, `metadata.data_status=INSERTED` y ruta del recibo. Si el driver devuelve IDs generados por la base, conservarlos sanitizados; de lo contrario, usar los identificadores presentes en el dataset y verificar por `qa_run_id` o clave segura.

## Consultas de verificación posteriores

Después de ejecutar los casos y antes del cleanup, generar las consultas que permiten revisar exactamente los datos del run:

```bash
python scripts/generate_verification_queries.py \
  qa-artifacts/data/dataset.json \
  --output-dir qa-artifacts/data/verification/<run_id>
```

Conservar:

```text
qa-artifacts/data/verification/<run_id>/
├── sql-server.sql
├── mongodb.js
├── manifest.json
└── README.md
```

El script debe:

- Generar `COUNT` y detalle por tabla o colección.
- Filtrar por `qa_run_id` o, como alternativa segura, por identificadores exactos presentes en el dataset.
- Bloquear cualquier entidad que no tenga un filtro acotado.
- Proyectar únicamente campos no sensibles.
- No incluir connection strings, usuarios ni contraseñas.
- Marcar los artefactos `GENERATED_NOT_EXECUTED`.

No ejecutar las consultas automáticamente. Si el cliente solicita ejecutarlas, usar conexión de solo lectura y registrar el resultado por separado. Después del cleanup, conservar los mismos archivos: un conteo cero sirve para comprobar la limpieza; si se autorizó diferirla, el detalle permite inspeccionar los registros hasta su vencimiento.

Registrar `verification-queries-generated` con `module=data`, ruta del manifest, ambiente, `dataset_id`, `run_id` y estado del cleanup. Si no hubo dataset o base, registrar `NOT_APPLICABLE` o el bloqueo concreto en vez de crear consultas amplias.

## Fuente de restricciones

Priorizar:

1. Requisitos aprobados.
2. Contratos OpenAPI/JSON Schema.
3. Esquema y constraints.
4. Modelos y validaciones del código.
5. Comportamiento observado.

Registrar contradicciones. No generar datos inválidos como setup de un caso positivo.

## SQL Server

### Acceso

Solicitar:

- Ambiente no productivo.
- Nombre de variable con connection string por ambiente.
- Usuario de lectura para introspección.
- Usuario de escritura separado para seed y cleanup.

No pedir valores secretos en chat.

Auditar el `.env` del proyecto que ejecutará `db_tool.py`. Las conexiones deben llegar desde variables del proceso o un `.env` local ignorado y protegido; no copiar connection strings entre repositorios ni al historial.

Resolver las conexiones desde `QA_<AMBIENTE>_DB_READ_CONNECTION` y `QA_<AMBIENTE>_DB_WRITE_CONNECTION`, usando el ambiente de `QA_TARGET_ENV`. `--environment` puede sobrescribirlo para una invocación y `--connection-env` puede seleccionar explícitamente otro nombre de variable, sin incluir su valor.

### Introspección

Usar `scripts/db_tool.py introspect-mssql`. Leer:

- Schemas, tablas y columnas.
- Tipos, nullability y longitudes.
- PK y FK.
- Índices y constraints disponibles.

No leer filas de negocio salvo necesidad justificada y autorización.

```bash
export QA_TARGET_ENV=main
export QA_ALLOWED_ENVIRONMENTS=dev,main,qa,staging
# Configurar QA_MAIN_DB_READ_CONNECTION en el gestor de secretos.

python scripts/db_tool.py --require-env-file introspect-mssql \
  --output qa-knowledge/database/main-schema.json
```

### Seed

Usar `scripts/db_tool.py seed-mssql`:

- Dry-run por defecto.
- Identificadores validados.
- Queries parametrizadas.
- Transacción única y rollback ante error.
- Orden de entidades definido por dependencias.

Exigir:

- Ambiente permitido por `QA_ALLOWED_ENVIRONMENTS`.
- Ambiente habilitado explícitamente en `QA_ALLOWED_DB_WRITE_ENVIRONMENTS`.
- `QA_ALLOW_DB_WRITE=true`.
- `--execute`.
- `--allow-write`.

La lista de escritura predeterminada no incluye `main`, `prod` ni `production`.

### Cleanup

Eliminar solo registros etiquetados con el `qa_run_id` conocido y tablas listadas en el dataset. Ejecutar en orden inverso.

No ejecutar cleanup si la tabla no tiene un campo de run ID o una clave explícita segura.

## MongoDB y documentos

Usar `scripts/db_tool.py introspect-mongodb` para colecciones, índices y validators.

Para seed:

- Generar documentos con `_qa_run_id`.
- Respetar validators.
- Usar `insert_many`.
- Registrar IDs.

Para cleanup:

- Filtrar únicamente por `_qa_run_id`.
- No usar filtros vacíos.

## Otras NoSQL

No asumir compatibilidad. Solicitar motor y usar su driver Python. Adaptar:

- Claves y particiones.
- Consistencia.
- Índices.
- TTL.
- Relaciones implícitas.
- Operación segura de cleanup.

Si no existe adaptador, generar JSON/NDJSON y un plan, no afirmar que fue insertado.

Además del JSON o NDJSON canónico, exportar una vista CSV por colección. Conservar estructuras anidadas como JSON compacto dentro de la celda sin aplanarlas de forma ambigua.

## Datos manuales

Para un tester manual, entregar:

- Dataset legible.
- IDs y usuarios.
- Método seguro para obtener credenciales.
- Fecha de expiración.
- Pasos de cleanup.

No incluir contraseñas en el tablero o historial.

## Paralelismo

Evitar colisiones con:

- Prefijos por `run_id`.
- Valores únicos deterministas.
- Tenant o namespace de QA.
- Cleanup idempotente.

Registrar residuos y bloquear reutilización si pueden contaminar resultados.
