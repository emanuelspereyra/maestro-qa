import httpx


class SonarQubeError(Exception):
    pass


def fetch_findings(
    base_url: str,
    token: str,
    project_key: str,
    client: httpx.Client | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Lee vulnerabilidades y security hotspots ya calculados — nunca dispara un análisis."""
    owns_client = client is None
    http_client = client or httpx.Client(base_url=base_url, auth=(token, ""), timeout=10)
    try:
        issues_response = http_client.get(
            "/api/issues/search",
            params={"componentKeys": project_key, "types": "VULNERABILITY", "resolved": "false"},
        )
        issues_response.raise_for_status()
        hotspots_response = http_client.get(
            "/api/hotspots/search",
            params={"projectKey": project_key, "status": "TO_REVIEW"},
        )
        hotspots_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SonarQubeError(f"No se pudo consultar SonarQube: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()

    issues = issues_response.json().get("issues", [])
    hotspots = hotspots_response.json().get("hotspots", [])
    return {
        "vulnerabilities": [
            {
                "severity": issue.get("severity"),
                "message": issue.get("message"),
                "component": issue.get("component"),
                "line": issue.get("line"),
            }
            for issue in issues
        ],
        "hotspots": [
            {
                "probability": hotspot.get("vulnerabilityProbability"),
                "message": hotspot.get("message"),
                "component": hotspot.get("component"),
                "line": hotspot.get("line"),
            }
            for hotspot in hotspots
        ],
    }
