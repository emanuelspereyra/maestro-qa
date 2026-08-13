"""Prueba manual de conectividad real. No corre en CI (necesita una API key real y gasta
tokens). Uso:

    MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
        .venv/bin/python scripts/smoke_test.py
"""

from maestro_qa.providers import get_provider


def main() -> None:
    provider = get_provider()
    response = provider.complete(
        system="Sos un asistente de QA. Respondé en una sola palabra.",
        messages=[{"role": "user", "content": "Respondé solo: OK"}],
    )
    print(f"Respuesta del proveedor: {response!r}")


if __name__ == "__main__":
    main()
