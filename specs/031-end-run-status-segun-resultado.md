# 031 — end-run status refleja resultado real del run

## Problema
`_end_history` en `orchestrator.py` hardcodea `--status COMPLETED` para el evento
`end-run` sin importar si algún agente terminó con error. En qa-history real
(`/root/repos/processia/qa-history`): 1 run con 15 eventos, 10 agentes FAILED
(9 "exhausted 3 retries", 1 KeyError `delivery_status`), 3 EXECUTED, pero
`runs.status` y `end-run.status` quedaron COMPLETED — contradictorio con la
evidencia de los eventos.

## Alcance
- Cambiar `_end_history` para que reciba la lista de `AgentResult` y use
  `FAILED` como status si **cualquier** agente tiene `error=True`, `COMPLETED`
  si ninguno falló.
- Agregar test que reproduzca el escenario: run con al menos un agente FAILED
  termina con end-run FAILED.

**Fuera de esta spec:** agregar `error_code` o `summary` al evento end-run
(specs #2 y #4 ya cubren esos campos en eventos de agentes); mejorar el
dashboard; tocar vendor.

## Diseño

`_end_history` pasa de recibir solo `run_id` a recibir `run_id` + `results`:

```python
def _end_history(history_dir: Path, run_id: str, results: list[AgentResult]) -> None:
    status = "FAILED" if any(r.error for r in results) else "COMPLETED"
    ...
```

El cambio es mínimo: una línea nueva para derivar el status, y la firma de la
función. El caller en `run()` ya tiene `results` disponible.

## Criterios de aceptación
- Un run con todos los agentes exitosos termina con end-run `COMPLETED`.
- Un run con al menos un agente FAILED termina con end-run `FAILED`.
- Los eventos intermedios de agentes no se modifican (EXECUTED/FAILED
  individuales quedan igual).
- Suite completa sigue en verde.

## Fuera de alcance / backlog
- **error_code / summary en end-run** — cubierto por PRs #2 y #4.
- **Dashboard** — `scripts/dashboard.py` ya existe, se adapta cuando haga falta.
- **Runs sin history_dir** — no cambian nada (el parámetro sigue siendo opt-in).
