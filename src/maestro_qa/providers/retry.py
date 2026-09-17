import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class ProviderError(Exception):
    pass


def with_retries(
    fn: Callable[[], T],
    is_transient: Callable[[Exception], bool],
    max_attempts: int = 3,
    backoff_base: float = 1.0,
) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc):
                raise
            last_exc = exc
            attempt += 1
            if attempt >= max_attempts:
                detail = f" ({type(last_exc).__name__}: {last_exc})" if last_exc is not None else ""
                raise ProviderError(f"exhausted {max_attempts} retries{detail}") from last_exc
            time.sleep(backoff_base * (2 ** (attempt - 1)))
