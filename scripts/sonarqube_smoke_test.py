"""Prueba manual real: levanta SonarQube en Docker, escanea un directorio y lo mata.

NO probado end-to-end contra un servidor real todavía (specs/015-sonarqube-efimero.md).
Corré esto una vez, con Docker disponible y margen de memoria, antes de confiar en el modo
efímero para un cliente real. No corre en CI (lento, pesado, necesita Docker).

Uso:
    .venv/bin/python scripts/sonarqube_smoke_test.py /ruta/a/un/repo
"""

import sys
from pathlib import Path

from maestro_qa.sonarqube_runtime import run_ephemeral_scan


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: sonarqube_smoke_test.py /ruta/a/un/repo")
        raise SystemExit(2)

    repo_path = Path(sys.argv[1]).resolve()
    findings = run_ephemeral_scan(repo_path, project_key="maestro-qa-smoke-test")
    print(f"Vulnerabilidades: {len(findings['vulnerabilities'])}")
    print(f"Hotspots: {len(findings['hotspots'])}")
    for vuln in findings["vulnerabilities"]:
        print(f"  - [{vuln['severity']}] {vuln['message']} ({vuln['component']}:{vuln['line']})")


if __name__ == "__main__":
    main()
