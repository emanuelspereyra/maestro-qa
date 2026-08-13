import time
from collections.abc import Callable


class ProviderError(Exception):
    pass


def with_retries(
    fn: Callable[[], str],
    is_transient: Callable[[Exception], bool],
    max_attempts: int = 3,
    backoff_base: float = 1.0,
) -> str:
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc):
                raise
            attempt += 1
            if attempt >= max_attempts:
                raise ProviderError(f"exhausted {max_attempts} retries") from exc
            time.sleep(backoff_base * (2 ** (attempt - 1)))
