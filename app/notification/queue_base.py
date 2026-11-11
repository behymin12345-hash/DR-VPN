"""NATS-free queue abstractions.

Kept import-light on purpose: the notification pipeline is loaded by every
panel process, so these classes must not pull in nats-py (~29MB RSS). The
NATS-backed implementations live in app.notification.nats_queue and are
imported lazily when NATS is enabled.
"""

import asyncio
import heapq
import json
import time
from contextlib import suppress
from itertools import count

QUEUE_MAX_MESSAGES = 10_000
QUEUE_MAX_BYTES = 64 * 1024 * 1024
RETRY_METADATA_RESERVE = 128


class NotificationDelivery:
    """A reservation that is returned to the queue unless explicitly settled."""

    def __init__(self, data: dict):
        self.data = data
        self.settled = False
        self._heartbeat_task = None

    async def ack(self):
        raise NotImplementedError

    async def retry(self, item: dict, delay: float = 0):
        raise NotImplementedError

    async def prepare(self, item: dict):
        """Reserve space for retry metadata before making an external request."""
        raise NotImplementedError

    async def release(self, delay: float = 1):
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
        if not self.settled:
            await self.release()


class NotificationQueue:
    kind = "memory"

    async def enqueue(self, item: dict):
        """Add an item. Raises asyncio.QueueFull when the bounded queue has no room."""
        raise NotImplementedError

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        raise NotImplementedError


class InMemoryNotificationDelivery(NotificationDelivery):
    def __init__(self, queue, data, size, retry_size=0):
        super().__init__(data)
        self.queue = queue
        self.size = size
        self.retry_size = retry_size

    async def ack(self):
        self.queue._size -= self.size
        self.queue._retry_size -= self.retry_size
        self.queue._count -= 1
        self.settled = True

    async def prepare(self, item: dict):
        size = len(json.dumps(item).encode())
        extra = 0 if self.retry_size else RETRY_METADATA_RESERVE
        retry_size = max(self.retry_size, size + extra - self.size)
        if self.queue._retry_size - self.retry_size + retry_size > self.queue.max_bytes:
            raise asyncio.QueueFull
        self.queue._retry_size += retry_size - self.retry_size
        self.retry_size = retry_size
        self.data = item

    async def retry(self, item: dict, delay: float = 0):
        data = json.dumps(item).encode()
        retry_size = max(self.retry_size, len(data) - self.size)
        if self.queue._retry_size - self.retry_size + retry_size > self.queue.max_bytes:
            raise asyncio.QueueFull
        self.queue._retry_size += retry_size - self.retry_size
        self.retry_size = retry_size
        self.queue._put(json.loads(data), self.size, delay, retry_size)
        self.settled = True

    async def release(self, delay: float = 1):
        self.queue._put(self.data, self.size, delay, self.retry_size)
        self.settled = True


class InMemoryNotificationQueue(NotificationQueue):
    def __init__(self, maxsize: int = QUEUE_MAX_MESSAGES, max_bytes: int = QUEUE_MAX_BYTES):
        self.maxsize = maxsize
        self.max_bytes = max_bytes
        self._items = []
        self._sequence = count()
        self._changed = asyncio.Event()
        # Reservations count towards capacity, so retries never need a free slot.
        self._count = 0
        self._size = 0
        # Retry metadata has a separate bounded budget, like the NATS journal.
        # A full input queue must still permit the first delivery to reserve it.
        self._retry_size = 0

    def _put(self, item: dict, size: int, delay: float, retry_size: int = 0):
        heapq.heappush(self._items, (time.monotonic() + max(delay, 0), next(self._sequence), item, size, retry_size))
        self._changed.set()

    async def enqueue(self, item: dict):
        data = json.dumps(item).encode()
        if self._count >= self.maxsize or self._size + len(data) > self.max_bytes:
            raise asyncio.QueueFull
        self._count += 1
        self._size += len(data)
        self._put(json.loads(data), len(data), 0)

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            self._changed.clear()
            now = time.monotonic()
            if self._items and self._items[0][0] <= now:
                _, _, item, size, retry_size = heapq.heappop(self._items)
                return InMemoryNotificationDelivery(self, item, size, retry_size)
            remaining = deadline - now if deadline is not None else None
            if remaining is not None and remaining <= 0:
                return None
            if self._items:
                delay = self._items[0][0] - now
                remaining = min(remaining, delay) if remaining is not None else delay
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=remaining)
            except TimeoutError:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
