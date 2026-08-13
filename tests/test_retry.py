import pytest

from maestro_qa.providers.retry import ProviderError, with_retries


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, TransientError)


def test_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("rate limited")
        return "ok"

    result = with_retries(flaky, is_transient=_is_transient, backoff_base=0)
    assert result == "ok"
    assert calls["n"] == 3


def test_raises_provider_error_after_exhausting_retries():
    def always_fails():
        raise TransientError("still rate limited")

    with pytest.raises(ProviderError):
        with_retries(always_fails, is_transient=_is_transient, max_attempts=3, backoff_base=0)


def test_non_transient_error_propagates_immediately():
    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        raise PermanentError("invalid api key")

    with pytest.raises(PermanentError):
        with_retries(bad_request, is_transient=_is_transient, backoff_base=0)
    assert calls["n"] == 1
