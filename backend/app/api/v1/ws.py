"""
WebSocket endpoints for real-time job updates.

Architecture
------------
Each WebSocket connection subscribes to a Redis Pub/Sub channel for its job
(``job:<job_id>``).  The Celery worker publishes events to that channel after
every meaningful ``db.commit()``.  This handler forwards those events verbatim
to the connected browser client.

The handler never reads from the database or disk in the hot path – all state
is carried inside the event payloads published by the worker.

Authentication
--------------
WebSockets cannot send Authorization headers, so the JWT is passed as a query
parameter: ``?token=<access_jwt>``.  The token is validated exactly the same
way as the HTTP bearer auth in ``deps.py``.

Endpoints
---------
- ``GET /ws/jobs/{job_id}``  – per-job detail page updates
- ``GET /ws/jobs``           – per-user job list updates (all user's jobs)
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.event_bus import subscribe_to_job, subscribe_to_user_jobs
from app.models.job import Job
from app.models.user import User
from app.schemas.auth import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Auth helpers ──────────────────────────────────────────────────────────────


def _authenticate_ws(token: str, db: Session) -> User | None:
    """Validate a JWT access token and return the matching active User.

    Returns ``None`` on any failure so the caller can close with 4001/4003.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        if token_data.type != "access" or token_data.sub is None:
            return None
    except (JWTError, Exception):
        return None

    user = db.query(User).filter(User.id == UUID(token_data.sub)).first()
    if not user or not user.is_active:
        return None
    return user


# ── Job detail WebSocket ──────────────────────────────────────────────────────


@router.websocket("/jobs/{job_id}")
async def ws_job_detail(
    websocket: WebSocket,
    job_id: UUID,
    token: str = Query(..., description="JWT access token"),
):
    """Stream real-time updates for a single job.

    The client receives JSON objects with the shape::

        {"event": "<type>", "job_id": "<uuid>", "data": {...}}

    See ``app.core.event_types`` for the full event catalogue.

    The connection is closed (code 4001) if the token is invalid or the
    requesting user does not own the job.  It is closed (code 1000) once a
    ``job_finished`` event has been forwarded.
    """
    # Authenticate before accepting to avoid dangling half-open connections
    db = next(get_db())
    try:
        user = _authenticate_ws(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        # Verify the job exists and belongs to this user
        job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
        if job is None:
            await websocket.close(code=4004, reason="Job not found")
            return

        job_id_str = str(job_id)
        user_id_str = str(user.id)
    finally:
        db.close()

    await websocket.accept()
    logger.info("WS connected: job=%s user=%s", job_id_str, user_id_str)

    try:
        async for event in subscribe_to_job(job_id_str):
            try:
                await websocket.send_json(event)
            except Exception:
                # Client disconnected mid-send
                break

            # Close cleanly once the terminal event has been delivered
            if event.get("event") == "job_finished":
                await websocket.close(code=1000)
                break

    except WebSocketDisconnect:
        logger.info("WS disconnected: job=%s user=%s", job_id_str, user_id_str)
    except Exception as exc:
        logger.exception("WS error: job=%s: %s", job_id_str, exc)
        try:
            await websocket.send_json(
                {"event": "error", "job_id": job_id_str, "data": {"message": str(exc)}}
            )
        except Exception:
            pass
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


# ── Job list WebSocket ────────────────────────────────────────────────────────


@router.websocket("/jobs")
async def ws_job_list(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """Stream real-time updates for all of the authenticated user's jobs.

    Subscribes to the per-user Redis channel (``user:<user_id>:jobs``).  Each
    event carries the same payload structure as the per-job channel so the
    jobs-list page can update individual rows without polling.

    The connection stays open until the client disconnects.
    """
    db = next(get_db())
    try:
        user = _authenticate_ws(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        user_id_str = str(user.id)
    finally:
        db.close()

    await websocket.accept()
    logger.info("WS job-list connected: user=%s", user_id_str)

    try:
        async for event in subscribe_to_user_jobs(user_id_str):
            try:
                await websocket.send_json(event)
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info("WS job-list disconnected: user=%s", user_id_str)
    except Exception as exc:
        logger.exception("WS job-list error: user=%s: %s", user_id_str, exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
