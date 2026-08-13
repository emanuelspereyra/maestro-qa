# 015 — SonarQube efímero (levantar, escanear, matar) por invocación

## Problema
CDA no tiene ningún servidor SonarQube corriendo todavía (spec 014 asumía uno ya
existente). Emanuel pidió explícitamente que el agente `seguridad` levante SonarQube en
Docker, escanee, lea los resultados y mate el contenedor — evaluado el costo (latencia de
arranque, memoria compartida con Vaultwarden/cron en el VPS, sin repo real todavía) y
decidido construirlo igual.

## Advertencia que hay que remarcarle a Emanuel, no ocultar
**Esto no se probó contra una instancia real de SonarQube en esta sesión** — arrancar un
contenedor real en el VPS de producción (que ya corre Vaultwarden y los crons de Autopilot)
para probarlo tenía un costo/riesgo que no se tomó sin pedirlo explícitamente. El código
sigue el flujo documentado de bootstrap de SonarQube (usuario admin por defecto, generación
de token, polling del Compute Engine) de memoria, no verificado end-to-end. Antes de
confiar en esto para un cliente real, correr el smoke test manual (`scripts/
sonarqube_smoke_test.py`, ver Diseño) una vez con Docker disponible y margen de memoria.

## Alcance
Cubre la extensión pedida sobre CDA-82 (spec 014):
- `sonarqube_runtime.run_ephemeral_scan(repo_path, project_key)`: levanta SonarQube en
  Docker, espera que esté `UP`, resetea el password default de `admin`, crea el proyecto,
  genera un token, corre `sonar-scanner` (también en Docker, sin instalarlo en el host)
  contra `repo_path`, espera que termine el análisis, lee los hallazgos con
  `sonarqube.fetch_findings()` (spec 014, sin cambios) y **siempre** para y borra el
  contenedor al final (`try/finally`), incluso si algo falló en el medio.
- `seguridad` usa este modo si `MAESTRO_SONARQUBE_EPHEMERAL=true` y
  `MAESTRO_SONARQUBE_SCAN_PATH` están configurados — opt-in explícito, nunca por default.
  Si no están, sigue con el modo de spec 014 (leer de un servidor ya corriendo) o sin
  SonarQube, igual que antes.

**Fuera de esta spec:**
- Clonar el repo del cliente automáticamente — `MAESTRO_SONARQUBE_SCAN_PATH` asume que ya
  hay un checkout local; clonar es trabajo de onboarding (spec 009), no de esto.
- Pool de contenedores o scans concurrentes — un contenedor a la vez, nombre único por
  corrida pero puerto fijo (colisiona si dos corridas se superponen). Techo conocido.

## Diseño

**Por qué sigue siendo opt-in y no reemplaza spec 014:** levantar SonarQube tarda minutos
(arranque + análisis), no segundos — corre bien como acción explícita, mal como parte
invisible de cada ticket. El flag existe para que quien lo prenda sepa que está aceptando
ese costo.

**Bootstrap de admin:** SonarQube nuevo trae `admin`/`admin` y fuerza cambio de password.
Se asume instancia recién creada (imagen `sonarqube:community` sin volumen persistente) —
si el cambio de password falla porque ya se hizo antes, se ignora (instancia reusada, no es
el caso esperado con contenedores efímeros nuevos cada vez).

**Scanner en Docker, no en el host:** evita instalar `sonar-scanner` como dependencia del
sistema. Corre con `--network host` para llegar al contenedor de SonarQube por
`localhost:<puerto>` — asume Linux (no funciona igual en Docker Desktop de Mac/Windows, no
es el caso de este VPS).

**Smoke test manual:** `scripts/sonarqube_smoke_test.py` (nuevo, mismo espíritu que
`scripts/smoke_test.py` del LLM) — corre `run_ephemeral_scan` contra un directorio real,
imprime los hallazgos. No corre en CI ni en la suite automática por el mismo motivo que el
smoke test del LLM: es lento, pesado, y necesita Docker con memoria disponible.

**Cleanup garantizado:** `docker stop`+`docker rm` van en el `finally` del orquestador
principal — se ejecutan aunque falle el arranque, el análisis o la lectura de resultados.
Es la propiedad de seguridad más importante de esta spec: nunca dejar un contenedor
huérfano corriendo en el VPS.

## Criterios de aceptación
- Con todos los pasos internos mockeados (sin Docker real), `run_ephemeral_scan` respeta el
  orden: arrancar → esperar ready → bootstrap admin → crear proyecto → token → scanner →
  esperar análisis → leer hallazgos → parar/borrar contenedor.
- Si cualquier paso intermedio lanza una excepción, el contenedor se para y se borra igual
  (verificado con un mock que falla a propósito en un paso intermedio).
- `seguridad` sin las 2 variables de entorno de modo efímero se comporta exactamente igual
  que con spec 014 (sin romper ningún test existente).
- Ningún test de la suite automática levanta un contenedor Docker real.

## Fuera de alcance / backlog
- **Validación real contra Docker** — pendiente, ver advertencia arriba. Correr el smoke
  test manual antes de un uso real con un cliente.
- **Clonado automático del repo** — depende de onboarding (spec 009).
- **Pool/concurrencia de scans** — un caso de uso a la vez por ahora.
