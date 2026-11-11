"""NATS-backed notification queues.

Importing this module pulls in nats-py (~29MB RSS), so it is loaded lazily:
queue_manager only imports it when NATS is enabled.
"""

import asyncio
import json
from uuid import uuid4

import nats
from nats import errors as nats_errors
from nats.js.api import AckPolicy, ConsumerConfig, DiscardPolicy, RawStreamMsg, RetentionPolicy, StreamConfig
from nats.js.client import JetStreamContext
from nats.js.errors import APIError, NotFoundError

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context
from app.notification.queue_base import (
    QUEUE_MAX_BYTES,
    QUEUE_MAX_MESSAGES,
    RETRY_METADATA_RESERVE,
    NotificationDelivery,
    NotificationQueue,
)
from app.utils.logger import get_logger

logger = get_logger("Notification")

PUBLISH_TIMEOUT_MAX_ATTEMPTS = 3
PUBLISH_TIMEOUT_BASE_DELAY = 0.1
ACK_WAIT = 60
# JetStream "store failed" error. With DiscardPolicy.NEW a stream at its limits
# rejects a publish with this code and "maximum messages/bytes exceeded".
JS_STREAM_STORE_FAILED = 10077


def is_stream_full_error(error: APIError) -> bool:
    return error.err_code == JS_STREAM_STORE_FAILED and "maximum" in (error.description or "")


class NatsNotificationDelivery(NotificationDelivery):
    def __init__(self, queue, message, data, checkpoint=None):
        super().__init__(data)
        self.queue = queue
        self.message = message
        self.checkpoint = checkpoint
        self._owner = None
        self._lease_lost = False

    @property
    def checkpoint_subject(self):
        return f"{self.queue.RETRY_SUBJECT}.{self.message.metadata.sequence.stream}"

    async def __aenter__(self):
        self._owner = asyncio.current_task()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return self

    async def __aexit__(self, *args):
        try:
            await super().__aexit__(*args)
        finally:
            if self._lease_lost and not self._owner.uncancel():
                raise RuntimeError("Notification reservation renewal failed")

    async def ack(self):
        if self.checkpoint is not None:
            await self._save_checkpoint(self.data, completed=True)
        await self.message.ack_sync()
        self.settled = True
        # Existing LimitsPolicy streams cannot be converted to WorkQueuePolicy.
        # Delete completed messages explicitly without recreating the durable.
        if self.queue._retention == RetentionPolicy.LIMITS:
            try:
                await self.queue._js.delete_msg(self.queue.STREAM_NAME, self.message.metadata.sequence.stream)
            except Exception:
                logger.exception("Could not remove acknowledged notification from stream")
        if self.checkpoint is not None:
            try:
                await self.queue._js.delete_msg(self.queue.RETRY_STREAM, self.checkpoint.seq)
            except Exception:
                logger.exception("Could not remove completed notification retry state")

    async def _save_checkpoint(self, item: dict, completed: bool = False):
        data = json.dumps({"data": item, "completed": completed}).encode()
        revision = self.checkpoint.seq if self.checkpoint is not None else 0
        size = len(self.checkpoint.data) if self.checkpoint is not None else len(data) + RETRY_METADATA_RESERVE
        if len(data) > size:
            raise ValueError("Notification retry metadata exceeded its reservation")
        # Fixed-size records never consume more capacity on retry. Reserve half
        # the journal for updates: older brokers count both versions transiently.
        headers = {"Nats-Expected-Last-Subject-Sequence": str(revision).zfill(20)}
        data = data.ljust(size)
        if self.checkpoint is None:
            info = await self.queue._js.stream_info(self.queue.RETRY_STREAM)
            stored_size_bound = size + len(self.checkpoint_subject.encode()) + 1024
            if info.state.bytes + stored_size_bound >= info.config.max_bytes // 2:
                raise asyncio.QueueFull
            # Guard the capacity check across scheduler processes, including
            # concurrent updates to other checkpoints.
            headers["Nats-Expected-Last-Sequence"] = str(info.state.last_seq).zfill(20)
        ack = await self.queue._js.publish(self.checkpoint_subject, data, headers=headers)
        self.checkpoint = RawStreamMsg(subject=self.checkpoint_subject, data=data, seq=ack.seq)
        self.data = item

    async def prepare(self, item: dict):
        if self.checkpoint is None:
            try:
                await self._save_checkpoint(item)
            except asyncio.QueueFull:
                await self.queue._prune_retry_state()
                raise
            except APIError as error:
                # Failed cleanup after a crash must not permanently occupy slots.
                if error.code == 503 or error.err_code == 10071:
                    await self.queue._prune_retry_state()
                    raise asyncio.QueueFull from error
                raise

    async def retry(self, item: dict, delay: float = 0):
        await self._save_checkpoint(item)
        await self.release(delay)

    async def release(self, delay: float = 1):
        await self.message.nak(delay=max(delay, 0.01))
        self.settled = True

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(ACK_WAIT / 3)
            if self.settled:
                return
            try:
                await self.message.in_progress()
                await self.queue._nc.flush(timeout=ACK_WAIT / 6)
            except Exception:
                logger.exception("Could not extend notification acknowledgement deadline")
                self._lease_lost = True
                self._owner.cancel()
                return


class NatsNotificationQueue(NotificationQueue):
    kind = "nats"

    def __init__(
        self,
        stream_name: str = "NOTIFICATIONS",
        subject: str = "notifications.queue",
        consumer_name: str = "notification_workers",
    ):
        self.STREAM_NAME = stream_name
        self.SUBJECT = subject
        self.CONSUMER_NAME = consumer_name
        self.RETRY_STREAM = f"{stream_name}_RETRY_STATE"
        self.RETRY_SUBJECT = f"{subject}.retry_state"
        self._prune_sequence = 1
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
        self._consumer: JetStreamContext.PullSubscription | None = None
        self._retention = RetentionPolicy.WORK_QUEUE

    async def initialize(self, create_consumer: bool = True):
        if not is_nats_enabled():
            raise RuntimeError("NATS is not enabled")
        self._nc = await create_nats_client()
        if not self._nc:
            raise RuntimeError("Failed to create NATS client")
        try:
            self._js = await get_jetstream_context(self._nc)
            await self._initialize_stream(create_consumer)
        except BaseException:
            await self._nc.close()
            self._nc = self._js = self._consumer = None
            raise

    async def _initialize_stream(self, create_consumer: bool):
        try:
            info = await self._js.stream_info(self.STREAM_NAME)
        except NotFoundError:
            # add_stream is idempotent when several producers start together.
            info = await self._js.add_stream(
                StreamConfig(
                    name=self.STREAM_NAME,
                    subjects=[self.SUBJECT],
                    retention=RetentionPolicy.WORK_QUEUE,
                    discard=DiscardPolicy.NEW,
                    max_msgs=QUEUE_MAX_MESSAGES,
                    max_bytes=QUEUE_MAX_BYTES,
                )
            )

        self._retention = info.config.retention
        if info.config.subjects != [self.SUBJECT] or info.state.consumer_count > 1:
            raise RuntimeError(f"Notification stream {self.STREAM_NAME} must have a dedicated subject and consumer")
        if self._retention not in (RetentionPolicy.LIMITS, RetentionPolicy.WORK_QUEUE):
            raise RuntimeError(f"Unsupported notification retention policy: {self._retention}")
        consumer = None
        if info.state.consumer_count:
            # Never delete messages owned by a different durable consumer.
            consumer = await self._js.consumer_info(self.STREAM_NAME, self.CONSUMER_NAME)
        if self._retention == RetentionPolicy.LIMITS and consumer is not None:
            # Only the contiguous acknowledged prefix is safe to purge.
            await self._js.purge_stream(self.STREAM_NAME, seq=consumer.ack_floor.stream_seq + 1)
            info = await self._js.stream_info(self.STREAM_NAME)

        config = info.config
        # Never shrink below an existing backlog during an upgrade, and preserve
        # explicit operator limits. Reject new messages instead of evicting work.
        if config.max_msgs is None or config.max_msgs <= 0:
            config.max_msgs = max(QUEUE_MAX_MESSAGES, info.state.messages)
        if config.max_bytes is None or config.max_bytes <= 0:
            config.max_bytes = max(QUEUE_MAX_BYTES, info.state.bytes)
        config.discard = DiscardPolicy.NEW
        await self._js.update_stream(config)

        if create_consumer:
            await self._initialize_retry_state(config)
            consumer_config = (
                consumer.config
                if consumer is not None
                else ConsumerConfig(durable_name=self.CONSUMER_NAME, filter_subject=self.SUBJECT)
            )
            consumer_config.ack_policy = AckPolicy.EXPLICIT
            consumer_config.ack_wait = ACK_WAIT
            # Delayed NAKs still count as pending at the broker. They must not
            # prevent ready messages elsewhere in the bounded stream from running.
            consumer_config.max_ack_pending = config.max_msgs
            await self._js.add_consumer(self.STREAM_NAME, consumer_config)
            self._consumer = await self._js.pull_subscribe(
                subject=self.SUBJECT, durable=self.CONSUMER_NAME, stream=self.STREAM_NAME
            )

    async def _initialize_retry_state(self, config):
        retry_config = StreamConfig(
            name=self.RETRY_STREAM,
            subjects=[f"{self.RETRY_SUBJECT}.*"],
            retention=RetentionPolicy.LIMITS,
            discard=DiscardPolicy.NEW,
            max_msgs=config.max_msgs,
            max_bytes=config.max_bytes,
            max_msgs_per_subject=1,
            num_replicas=config.num_replicas,
            storage=config.storage,
        )
        try:
            info = await self._js.stream_info(self.RETRY_STREAM)
        except NotFoundError:
            await self._js.add_stream(retry_config)
        else:
            if (
                info.config.subjects != retry_config.subjects
                or info.state.consumer_count
                or info.config.retention != RetentionPolicy.LIMITS
                or info.config.max_msgs_per_subject != 1
                or info.config.discard != DiscardPolicy.NEW
                or info.config.discard_new_per_subject
                or info.config.max_age
                or not info.config.max_msgs
                or info.config.max_msgs < 0
                or not info.config.max_bytes
                or info.config.max_bytes < 0
            ):
                raise RuntimeError(f"Incompatible notification retry stream {self.RETRY_STREAM}")
            if info.state.bytes >= info.config.max_bytes // 2:
                # Reclaim stale checkpoints before rejecting recoverable state.
                # Bound startup recovery by the observed number of records.
                self._prune_sequence = 1
                await self._prune_retry_state(limit=info.state.messages)
                info = await self._js.stream_info(self.RETRY_STREAM)
                if info.state.bytes >= info.config.max_bytes // 2:
                    raise RuntimeError(f"Insufficient notification retry headroom in {self.RETRY_STREAM}")
                return
        await self._prune_retry_state()

    async def _prune_retry_state(self, limit: int = 100):
        """Incrementally reclaim checkpoints whose original message was acknowledged."""
        for _ in range(limit):
            try:
                checkpoint = await self._js.get_msg(
                    self.RETRY_STREAM, seq=self._prune_sequence, subject=f"{self.RETRY_SUBJECT}.*", next=True
                )
            except NotFoundError:
                self._prune_sequence = 1
                break
            self._prune_sequence = checkpoint.seq + 1
            original_sequence = int(checkpoint.subject.rsplit(".", 1)[1])
            try:
                await self._js.get_msg(self.STREAM_NAME, seq=original_sequence)
            except NotFoundError:
                await self._js.delete_msg(self.RETRY_STREAM, checkpoint.seq)

    async def _publish(self, data: bytes, message_id: str):
        if not self._js:
            raise RuntimeError("JetStream context not available")
        for attempt in range(PUBLISH_TIMEOUT_MAX_ATTEMPTS):
            try:
                await self._js.publish(self.SUBJECT, data, headers={"Nats-Msg-Id": message_id})
                return
            except (TimeoutError, nats_errors.TimeoutError):
                if attempt == PUBLISH_TIMEOUT_MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(PUBLISH_TIMEOUT_BASE_DELAY * (2**attempt))

    async def enqueue(self, item: dict):
        try:
            await self._publish(json.dumps(item).encode(), uuid4().hex)
        except APIError as error:
            if is_stream_full_error(error):
                raise asyncio.QueueFull from error
            raise

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        if not self._consumer:
            raise RuntimeError("Consumer not available")
        try:
            messages = await self._consumer.fetch(1, timeout=timeout if timeout is not None else 1)
        except (TimeoutError, nats_errors.TimeoutError):
            return None
        if not messages:
            return None
        message = messages[0]
        checkpoint = None
        try:
            data = json.loads(message.data)
            if not isinstance(data, dict):
                raise TypeError("Notification must be an object")
        except (ValueError, TypeError):
            logger.error("Discarding malformed notification in %s", self.STREAM_NAME)
            await NatsNotificationDelivery(self, message, {}).ack()
            return None
        try:
            try:
                checkpoint = await self._js.get_msg(
                    self.RETRY_STREAM, subject=f"{self.RETRY_SUBJECT}.{message.metadata.sequence.stream}"
                )
            except NotFoundError:
                pass
            if checkpoint is not None:
                state = json.loads(checkpoint.data)
                delivery = NatsNotificationDelivery(self, message, state["data"], checkpoint)
                if state["completed"]:
                    await delivery.ack()
                    return None
                return delivery
            return NatsNotificationDelivery(self, message, data)
        except BaseException:
            await message.nak(delay=1)
            raise
