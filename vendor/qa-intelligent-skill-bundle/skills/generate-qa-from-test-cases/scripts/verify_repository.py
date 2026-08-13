#!/usr/bin/env python3
"""Verify read-only Git repository access without prompting for secrets."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def sanitize_url(value: str) -> str:
    if "://" not in value:
        return value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def has_embedded_http_credentials(value: str) -> bool:
    if not value.lower().startswith(("http://", "https://")):
        return False
    parsed = urlsplit(value)
    return parsed.username is not None or parsed.password is not None


def detect_provider(value: str) -> str:
    lowered = value.lower()
    providers = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",
        "dev.azure.com": "azure-devops",
        "visualstudio.com": "azure-devops",
    }
    for host, provider in providers.items():
        if host in lowered:
            return provider
    return "other"


def categorize(stderr: str, returncode: int, branch: str) -> str:
    lowered = stderr.lower()
    authentication_markers = (
        "authentication failed",
        "could not read username",
        "could not read password",
        "terminal prompts disabled",
        "permission denied (publickey)",
        "invalid username or password",
        "authentication required",
    )
    authorization_markers = (
        "access denied",
        "forbidden",
        "not authorized",
        "authorization failed",
        "insufficient permission",
    )
    network_markers = (
        "could not resolve host",
        "failed to connect",
        "network is unreachable",
        "connection timed out",
        "operation timed out",
        "connection refused",
    )
    not_found_markers = (
        "repository not found",
        "does not appear to be a git repository",
        "not found",
    )
    if any(marker in lowered for marker in authentication_markers):
        return "authentication"
    if any(marker in lowered for marker in authorization_markers):
        return "authorization"
    if any(marker in lowered for marker in network_markers):
        return "network"
    if any(marker in lowered for marker in not_found_markers):
        return "not_found"
    if branch and returncode == 2:
        return "branch_not_found"
    return "unknown"


def result(
    repository: str,
    branch: str,
    provider: str,
    status: str,
    category: str,
    message: str,
    returncode: Optional[int] = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "repository": repository,
        "branch": branch,
        "provider": provider,
        "status": status,
        "category": category,
        "message": message,
        "auth_required": category in {"authentication", "authorization"},
    }
    if returncode is not None:
        payload["returncode"] = returncode
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Git repository and branch access without cloning or prompting."
    )
    parser.add_argument("--url", required=True, help="Repository URL without credentials")
    parser.add_argument("--branch", default="", help="Branch to verify")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    repository = sanitize_url(args.url)
    provider = detect_provider(repository)

    if has_embedded_http_credentials(args.url):
        print(
            json.dumps(
                result(
                    repository,
                    args.branch,
                    provider,
                    "BLOCKED",
                    "unsafe_url",
                    "Remove embedded credentials and configure authentication outside the URL.",
                ),
                ensure_ascii=False,
            )
        )
        return 2

    git = shutil.which("git")
    if not git:
        print(
            json.dumps(
                result(
                    repository,
                    args.branch,
                    provider,
                    "BLOCKED",
                    "git_missing",
                    "Git is not available in this environment.",
                ),
                ensure_ascii=False,
            )
        )
        return 2

    command = [git, "ls-remote", "--heads", "--exit-code", args.url]
    if args.branch:
        command.append(f"refs/heads/{args.branch}")

    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "never"
    ssh_command = environment.get("GIT_SSH_COMMAND", "ssh")
    environment["GIT_SSH_COMMAND"] = (
        f"{ssh_command} -o BatchMode=yes -o ConnectTimeout=10"
    )

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(args.timeout, 1),
            env=environment,
        )
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                result(
                    repository,
                    args.branch,
                    provider,
                    "BLOCKED",
                    "timeout",
                    "Repository verification timed out.",
                ),
                ensure_ascii=False,
            )
        )
        return 2

    if completed.returncode == 0:
        print(
            json.dumps(
                result(
                    repository,
                    args.branch,
                    provider,
                    "VERIFIED",
                    "ok",
                    "Read-only repository access verified.",
                    completed.returncode,
                ),
                ensure_ascii=False,
            )
        )
        return 0

    category = categorize(completed.stderr, completed.returncode, args.branch)
    messages = {
        "authentication": "Authentication is missing or invalid; connect the provider and retry.",
        "authorization": "The authenticated identity lacks repository access.",
        "network": "The repository host could not be reached.",
        "not_found": "The repository was not found or its URL is incorrect.",
        "branch_not_found": "The requested branch was not found.",
        "unknown": "Repository access could not be verified.",
    }
    print(
        json.dumps(
            result(
                repository,
                args.branch,
                provider,
                "BLOCKED",
                category,
                messages[category],
                completed.returncode,
            ),
            ensure_ascii=False,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
