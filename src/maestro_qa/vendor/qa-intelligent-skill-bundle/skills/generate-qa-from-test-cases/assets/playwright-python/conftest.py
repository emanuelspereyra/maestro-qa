from __future__ import annotations

import os

import pytest

from qa_environment import QAEnvironmentError, resolve_setting, target_environment


def pytest_configure(config: pytest.Config) -> None:
    try:
        selected = target_environment()
    except QAEnvironmentError as exc:
        raise pytest.UsageError(str(exc)) from exc
    config._qa_target_environment = selected  # type: ignore[attr-defined]


def pytest_report_header(config: pytest.Config) -> str:
    selected = getattr(config, "_qa_target_environment", None) or target_environment()
    return f"QA target environment: {selected}"


@pytest.fixture(scope="session")
def qa_target_environment(pytestconfig: pytest.Config) -> str:
    return (
        getattr(pytestconfig, "_qa_target_environment", None)
        or target_environment()
    )


@pytest.fixture(scope="session")
def base_url(qa_target_environment: str) -> str:
    try:
        value = resolve_setting("FRONTEND_URL", qa_target_environment)
    except QAEnvironmentError as exc:
        raise pytest.UsageError(str(exc)) from exc
    assert value is not None
    return value.rstrip("/")


@pytest.fixture(scope="session")
def api_base_url(qa_target_environment: str) -> str:
    try:
        value = resolve_setting("API_BASE_URL", qa_target_environment)
    except QAEnvironmentError as exc:
        raise pytest.UsageError(str(exc)) from exc
    assert value is not None
    return value.rstrip("/")


@pytest.fixture(scope="session")
def qa_run_id(qa_target_environment: str) -> str:
    return os.environ.get("QA_RUN_ID", f"local-{qa_target_environment}-run")
