"""
Redis Pub/Sub event bus for real-time job updates.

Architecture
------------
Celery workers call ``publish_job_event()`` after every ``db.commit()`` that
mutates meaningful job state.  The published message is a JSON object (see
``event_types.py`` for the full schema).

FastAPI WebSocket handlers subscribe to the per-job channel and forward
messages directly to connected browser clients.  The handlers never read from
the database or disk in the hot path – all data travels inside the event
payload.

Channels
--------
- ``job:<job_id>``         – per-job channel; WebSocket for the job detail page
- ``user:<user_id>:jobs``  – per-user channel; WebSocket for the jobs list page

Design notes
------------
- A single ``redis.Redis`` connection pool is created lazily and reused.
- ``publish_job_event`` is safe to call from synchronous Celery task code.
- ``subscribe_to_job`` is an async generator for use inside FastAPI async code.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import AsyncGenerator, Optional

import redis
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Synchronous client (used by Celery tasks) ─────────────────────────────────

_sync_client: Optional[redis.Redis] = None
_sync_lock = threading.Lock()


def _get_sync_client() -> redis.Redis:
    """Return a lazily-initialised synchronous Redis client."""
    global _sync_client
    if _sync_client is None:
        with _sync_lock:
            if _sync_client is None:
                _sync_client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )
    return _sync_client


# ── Async client (used by FastAPI WebSocket handlers) ─────────────────────────

_async_pool: Optional[aioredis.ConnectionPool] = None


def _get_async_pool() -> aioredis.ConnectionPool:
    """Return a lazily-initialised async Redis connection pool."""
    global _async_pool
    if _async_pool is None:
        _async_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _async_pool


def get_async_redis() -> aioredis.Redis:
    """Return an async Redis client backed by the shared pool."""
    return aioredis.Redis(connection_pool=_get_async_pool())


# ── Publishing (called by Celery tasks) ───────────────────────────────────────


def publish_job_event(
    job_id: str,
    event_type: str,
    data: dict,
    user_id: Optional[str] = None,
) -> None:
    """Publish a job event to the per-job Redis channel.

    This is a fire-and-forget synchronous call safe to use inside Celery tasks.
    Errors are logged but never raised – a publish failure must never crash the
    worker.

    Always call this *after* ``db.commit()`` so the published state matches
    what is persisted in the database.

    Parameters
    ----------
    job_id:
        UUID string of the job.
    event_type:
        One of the constants from ``app.core.event_types``.
    data:
        Arbitrary JSON-serialisable dict that forms the event payload.
    user_id:
        Optional user UUID.  When provided the event is also published to the
        per-user channel (``user:<user_id>:jobs``) so the jobs-list page can
        stay up to date without polling.
    """
    message = json.dumps(
        {
            "event": event_type,
            "job_id": job_id,
            "data": data,
        }
    )
    try:
        client = _get_sync_client()
        client.publish(f"job:{job_id}", message)
        if user_id:
            client.publish(f"user:{user_id}:jobs", message)
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "Failed to publish event %s for job %s: %s",
            event_type,
            job_id,
            exc,
        )


# ── Subscription (used by FastAPI WebSocket handlers) ─────────────────────────


async def subscribe_to_job(job_id: str) -> AsyncGenerator[dict, None]:
    """Async generator that yields parsed event dicts from the job's channel.

    Each yielded value is a dict with the shape::

        {"event": str, "job_id": str, "data": dict}

    The generator exits when the WebSocket disconnects (caller breaks out) or
    when the connection to Redis is lost.

    Usage::

        async for event in subscribe_to_job(job_id):
            await websocket.send_json(event)
    """
    client = get_async_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(f"job:{job_id}")
    try:
        while True:
            # get_message is non-blocking; timeout=0.1 prevents busy-spinning
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.1
            )
            if message is not None:
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, KeyError) as parse_err:
                    logger.warning("Malformed event message: %s", parse_err)
    finally:
        try:
            await pubsub.unsubscribe(f"job:{job_id}")
            await pubsub.close()
            await client.aclose()
        except Exception:
            pass


async def subscribe_to_user_jobs(user_id: str) -> AsyncGenerator[dict, None]:
    """Async generator for per-user job list updates."""
    client = get_async_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(f"user:{user_id}:jobs")
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.1
            )
            if message is not None:
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, KeyError) as parse_err:
                    logger.warning("Malformed event message: %s", parse_err)
    finally:
        try:
            await pubsub.unsubscribe(f"user:{user_id}:jobs")
            await pubsub.close()
            await client.aclose()
        except Exception:
            pass
