"""Light bridge-memory state.

The bridge's in-process defaults live here so that every importer (node
manager, routers, jobs) can read the current store/worker-id without loading
nats-py. The NATS-backed implementation in app.node.nats_memory writes its
initialized store/coordinator back here.
"""

import os
from uuid import uuid4

WORKER_ID = f"{os.getpid()}:{uuid4().hex[:8]}"

_user_sync_store = None
_lifecycle_coordinator = None


def get_bridge_memory() -> tuple[object | None, object | None, str]:
    return _user_sync_store, _lifecycle_coordinator, WORKER_ID


async def clear_bridge_memory_for_node(node_id: int | str) -> None:
    nid = str(node_id)
    if _user_sync_store is not None:
        await _user_sync_store.clear(nid)
        await _user_sync_store.clear_full_sync(nid)
    if _lifecycle_coordinator is not None:
        await _lifecycle_coordinator.clear(nid)


def set_bridge_memory(store, coordinator) -> None:
    global _user_sync_store, _lifecycle_coordinator
    _user_sync_store = store
    _lifecycle_coordinator = coordinator


def reset_bridge_memory() -> None:
    global _user_sync_store, _lifecycle_coordinator
    _user_sync_store = None
    _lifecycle_coordinator = None
