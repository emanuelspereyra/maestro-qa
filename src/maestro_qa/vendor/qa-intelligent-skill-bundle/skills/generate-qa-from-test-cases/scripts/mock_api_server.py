#!/usr/bin/env python3
"""Run a local, contract-driven mock for third-party APIs used by QA tests."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class CatalogError(ValueError):
    pass


def load_catalog(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CatalogError("The mock catalog must be a JSON object")
    routes = raw.get("routes")
    if not isinstance(routes, list) or not routes:
        raise CatalogError("'routes' must be a non-empty list")

    seen: set[tuple[str, str]] = set()
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise CatalogError(f"routes[{index}] must be an object")
        method = str(route.get("method", "")).upper()
        path_value = route.get("path")
        scenarios = route.get("scenarios")
        if method not in SUPPORTED_METHODS:
            raise CatalogError(f"routes[{index}].method is unsupported: {method!r}")
        if not isinstance(path_value, str) or not path_value.startswith("/"):
            raise CatalogError(f"routes[{index}].path must start with '/'")
        route_key = (method, path_value)
        if route_key in seen:
            raise CatalogError(f"Duplicate route: {method} {path_value}")
        seen.add(route_key)
        if not isinstance(scenarios, dict) or not scenarios:
            raise CatalogError(f"routes[{index}].scenarios must be a non-empty object")
        default = route.get("default_scenario", raw.get("default_scenario", "success"))
        if default not in scenarios:
            raise CatalogError(
                f"Default scenario {default!r} does not exist for {method} {path_value}"
            )
        for scenario_name, scenario in scenarios.items():
            if not isinstance(scenario_name, str) or not scenario_name:
                raise CatalogError(f"Invalid scenario name in {method} {path_value}")
            if not isinstance(scenario, dict):
                raise CatalogError(
                    f"Scenario {scenario_name!r} in {method} {path_value} must be an object"
                )
            status = scenario.get("status", 200)
            if not isinstance(status, int) or not 100 <= status <= 599:
                raise CatalogError(
                    f"Scenario {scenario_name!r} has invalid HTTP status {status!r}"
                )
            delay_ms = scenario.get("delay_ms", 0)
            if not isinstance(delay_ms, int) or not 0 <= delay_ms <= 60000:
                raise CatalogError(
                    f"Scenario {scenario_name!r} delay_ms must be between 0 and 60000"
                )
            headers = scenario.get("headers", {})
            if not isinstance(headers, dict):
                raise CatalogError(f"Scenario {scenario_name!r} headers must be an object")
            for name, value in headers.items():
                if (
                    not isinstance(name, str)
                    or not HEADER_NAME.fullmatch(name)
                    or name.lower() in HOP_BY_HOP_HEADERS
                    or not isinstance(value, (str, int, float))
                ):
                    raise CatalogError(
                        f"Scenario {scenario_name!r} contains an unsafe response header"
                    )
    return raw


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def route_index(catalog: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(route["method"]).upper(), str(route["path"])): route
        for route in catalog["routes"]
    }


def response_bytes(body: Any) -> tuple[bytes, str]:
    if body is None:
        return b"", "application/json; charset=utf-8"
    if isinstance(body, (dict, list, bool, int, float)):
        return (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )
    return str(body).encode("utf-8"), "text/plain; charset=utf-8"


def make_handler(
    catalog: dict[str, Any],
    *,
    max_request_bytes: int,
    log_requests: bool,
    forced_scenario: str | None,
) -> type[BaseHTTPRequestHandler]:
    routes = route_index(catalog)
    service = str(catalog.get("service") or "third-party-mock")
    contract_version = str(catalog.get("contract_version") or "unspecified")
    global_default = str(catalog.get("default_scenario") or "success")

    class MockHandler(BaseHTTPRequestHandler):
        server_version = "QAContractMock/1.0"

        def log_message(self, format_string: str, *args: object) -> None:
            # BaseHTTPRequestHandler logs the complete request target, including
            # its query string. Keep it disabled and emit only the sanitized
            # method/path/scenario record below when requested.
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-QA-Mock-Service", service)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _discard_request_body(self) -> bool:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                self._send_json(400, {"error": "invalid-content-length"})
                return False
            if length < 0 or length > max_request_bytes:
                self._send_json(413, {"error": "request-too-large"})
                return False
            if length:
                self.rfile.read(length)
            return True

        def _handle(self) -> None:
            parsed = urlsplit(self.path)
            if self.command == "GET" and parsed.path == "/__qa_mock__/health":
                self._send_json(
                    200,
                    {
                        "status": "ready",
                        "service": service,
                        "contract_version": contract_version,
                        "mode": "contract-mock",
                    },
                )
                return

            if not self._discard_request_body():
                return
            route = routes.get((self.command, parsed.path))
            if route is None:
                self._send_json(
                    404,
                    {
                        "error": "mock-route-not-found",
                        "method": self.command,
                        "path": parsed.path,
                    },
                )
                return

            query = parse_qs(parsed.query, keep_blank_values=True)
            requested = self.headers.get("X-QA-Mock-Scenario")
            if not requested:
                requested = next(iter(query.get("qa_scenario", [])), None)
            scenario_name = str(
                forced_scenario
                or requested
                or route.get("default_scenario")
                or global_default
            )
            scenarios = route["scenarios"]
            scenario = scenarios.get(scenario_name)
            if scenario is None:
                self._send_json(
                    400,
                    {
                        "error": "mock-scenario-not-found",
                        "scenario": scenario_name,
                        "available_scenarios": sorted(scenarios),
                    },
                )
                return

            delay_ms = int(scenario.get("delay_ms", 0))
            if delay_ms:
                time.sleep(delay_ms / 1000)
            status = int(scenario.get("status", 200))
            body, default_content_type = response_bytes(scenario.get("body"))
            headers = {
                str(name): str(value)
                for name, value in scenario.get("headers", {}).items()
            }
            if not any(name.lower() == "content-type" for name in headers):
                headers["Content-Type"] = default_content_type

            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-QA-Mock-Service", service)
            self.send_header("X-QA-Mock-Scenario", scenario_name)
            self.send_header("X-QA-Mock-Contract-Version", contract_version)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            if log_requests:
                print(
                    json.dumps(
                        {
                            "method": self.command,
                            "path": parsed.path,
                            "scenario": scenario_name,
                            "status": status,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle
        do_HEAD = _handle
        do_OPTIONS = _handle

    return MockHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-nonlocal", action="store_true")
    parser.add_argument("--log-requests", action="store_true")
    parser.add_argument(
        "--scenario",
        help="Force one scenario for application calls that cannot send the QA header",
    )
    parser.add_argument("--max-request-bytes", type=int, default=1_048_576)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        catalog = load_catalog(args.catalog)
        if not 0 <= args.port <= 65535:
            raise CatalogError("port must be between 0 and 65535")
        if args.max_request_bytes < 0:
            raise CatalogError("max-request-bytes must not be negative")
        if not args.allow_nonlocal and not is_loopback_host(args.host):
            raise CatalogError(
                "Refusing a non-loopback bind; use --allow-nonlocal only in an isolated QA network"
            )
        if args.scenario:
            missing_routes = [
                f"{str(route['method']).upper()} {route['path']}"
                for route in catalog["routes"]
                if args.scenario not in route["scenarios"]
            ]
            if missing_routes:
                raise CatalogError(
                    f"Forced scenario {args.scenario!r} is missing from: "
                    + ", ".join(missing_routes)
                )
    except (OSError, json.JSONDecodeError, CatalogError) as exc:
        print(f"ERROR: {exc}")
        return 1

    summary = {
        "status": "VALIDATED" if args.check else "READY",
        "service": str(catalog.get("service") or "third-party-mock"),
        "contract_version": str(catalog.get("contract_version") or "unspecified"),
        "routes": len(catalog["routes"]),
        "host": args.host,
        "port": args.port,
        "request_bodies_logged": False,
        "forced_scenario": args.scenario,
    }
    if args.check:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    handler = make_handler(
        catalog,
        max_request_bytes=args.max_request_bytes,
        log_requests=args.log_requests,
        forced_scenario=args.scenario,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    summary["port"] = server.server_address[1]
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
