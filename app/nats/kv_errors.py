"""NATS KV error helpers importable without nats-py.

The panel checks these on every cache-load failure, including deployments
where NATS is disabled — so detection must not import the nats library.
"""


def is_kv_miss(exc: BaseException) -> bool:
    """True when JetStream KV has no value yet (first boot / deleted key).

    Matches by exception class name and message so it works with and without
    nats-py loaded (nats.js.errors.KeyNotFoundError / KeyDeletedError).
    """
    if type(exc).__name__ in ("KeyNotFoundError", "KeyDeletedError"):
        return True
    text = str(exc).lower()
    return "key not found" in text or "key deleted" in text
