"""
Event type constants for the Redis Pub/Sub job event bus.

All real-time job updates flow through Redis channels (one channel per job:
``job:<job_id>``).  Consumers subscribe to these channels and forward events
to WebSocket clients.  Events carry full data payloads so consumers never
need to read the database or disk to build a response.

Event payload schema
--------------------
Every message published to a channel is a JSON object with the shape:

    {
        "event": "<event_type>",   # one of the constants below
        "job_id": "<uuid>",
        "data": { ... }            # event-specific payload (see below)
    }
"""


# ── Job lifecycle ─────────────────────────────────────────────────────────────

# Job status / progress changed (sent for every db.commit that mutates
# status, progress, or status_message).
#
# data: {
#   "status": str,
#   "progress": int,          # 0-100
#   "status_message": str,
#   "error_message": str | null,
#   "time_started": iso8601 | null,
#   "time_finished": iso8601 | null,
#   "actual_cost": float,
#   "estimated_time": int | null,
# }
JOB_UPDATE = "job_update"

# Job reached a terminal state (completed / failed / cancelled).
# Carries the full final state so the frontend never needs a follow-up REST
# call.
#
# data: {
#   "status": str,
#   "progress": int,
#   "status_message": str,
#   "error_message": str | null,
#   "time_started": iso8601 | null,
#   "time_finished": iso8601 | null,
#   "actual_cost": float,
#   "total_cracked": int,
# }
JOB_FINISHED = "job_finished"


# ── Log streaming ─────────────────────────────────────────────────────────────

# New log lines are available (incremental; always appended on the client).
#
# data: {
#   "lines": [str, ...],
#   "append": bool,   # True = append; False = initial/replace
# }
LOG_UPDATE = "log_update"


# ── Cracked password streaming ────────────────────────────────────────────────

# Pot file changed – new passwords cracked.
#
# data: {
#   "total_cracked": int,
#   "preview": [str, ...],   # last 100 lines
#   "truncated": bool,
# }
POT_UPDATE = "pot_update"


# ── Error ─────────────────────────────────────────────────────────────────────

# An unrecoverable error occurred in the worker.
#
# data: { "message": str }
JOB_ERROR = "job_error"
