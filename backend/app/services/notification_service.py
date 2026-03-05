"""
Microsoft Teams webhook notification service.

Sends Adaptive Card notifications when cracking jobs reach a terminal state
(completed or failed). The card @mentions the job owner by their email address
using the Teams msteams.entities mention format documented in notify.txt.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


def _build_job_card(job: Job, user_email: str) -> dict:
    """
    Build a Microsoft Teams Adaptive Card payload for a job terminal notification.

    The card follows the format shown in notify.txt – it uses the msteams.entities
    mention block so that Teams properly resolves the @mention for the user.
    """
    # Determine status-specific copy and colour accent
    if job.status == JobStatus.COMPLETED:
        status_label = "Completed"
        status_color = "Good"  # green in Adaptive Cards
        headline = f'Job "{job.name}" has completed.'
    elif job.status == JobStatus.FAILED:
        status_label = "Failed"
        status_color = "Attention"  # red in Adaptive Cards
        error_snippet = (job.error_message or "Unknown error")[:200]
        headline = f'Job "{job.name}" failed: {error_snippet}'
    else:
        # Cancelled – unlikely to be called but handled for safety
        status_label = "Cancelled"
        status_color = "Warning"  # yellow
        headline = f'Job "{job.name}" was cancelled.'

    # Duration string (only available when both timestamps are set)
    duration_str = ""
    if job.time_started and job.time_finished:
        ts = job.time_started
        tf = job.time_finished
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if tf.tzinfo is None:
            tf = tf.replace(tzinfo=timezone.utc)
        delta = tf - ts
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            duration_str = f"{hours}h {minutes}m {seconds}s"
        else:
            duration_str = f"{minutes}m {seconds}s"

    # Cost string
    cost_str = f"${float(job.actual_cost):.4f}" if job.actual_cost else "N/A"

    # @mention tag used both in the TextBlock and in the entities list
    mention_tag = f"<at>{user_email}</at>"

    body = [
        {
            "type": "TextBlock",
            "text": f"VPK Job {status_label}",
            "weight": "Bolder",
            "size": "Large",
            "color": status_color,
        },
        {
            "type": "TextBlock",
            "text": headline,
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"Hi {mention_tag}, your cracking job has reached a terminal state.",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Job Name", "value": job.name},
                {"title": "Status", "value": status_label},
                {"title": "Hash Type", "value": job.hash_type or "N/A"},
                {"title": "Duration", "value": duration_str or "N/A"},
                {"title": "Cost", "value": cost_str},
                {"title": "Created By", "value": user_email},
            ],
        },
    ]

    # Add a timestamp footer
    finished_at = job.time_finished or datetime.now(timezone.utc)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    body.append(
        {
            "type": "TextBlock",
            "text": f"Finished at {finished_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "isSubtle": True,
            "size": "Small",
        }
    )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.0",
                    "body": body,
                    "msteams": {
                        "entities": [
                            {
                                "type": "mention",
                                "text": mention_tag,
                                "mentioned": {
                                    "id": user_email,
                                    "name": user_email,
                                },
                            }
                        ]
                    },
                },
            }
        ],
    }


def _build_test_card() -> dict:
    """Build a simple test Adaptive Card to verify webhook connectivity."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "VPK Webhook Test",
                            "weight": "Bolder",
                            "size": "Large",
                        },
                        {
                            "type": "TextBlock",
                            "text": "Your Microsoft Teams webhook is configured correctly. "
                            "You will receive notifications here when cracking jobs complete or fail.",
                            "wrap": True,
                        },
                    ],
                },
            }
        ],
    }


def send_job_notification(
    job: Job,
    user_email: str,
    webhook_url: str,
) -> None:
    """
    Post a Teams Adaptive Card notification for a terminal job event.

    This function is intentionally non-raising – any failure is logged as a
    warning so it never blocks job completion from being recorded.

    Args:
        job:          The completed/failed Job ORM instance.
        user_email:   Email address of the user who created the job.
        webhook_url:  The Microsoft Teams incoming webhook URL.
    """
    if not webhook_url:
        logger.debug("Teams webhook URL not configured, skipping notification")
        return

    try:
        payload = _build_job_card(job, user_email)
        response = httpx.post(
            webhook_url,
            json=payload,
            timeout=10.0,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 200:
            logger.info(
                f"Teams notification sent for job {job.id} (status={job.status.value}) "
                f"to user {user_email}"
            )
        else:
            logger.warning(
                f"Teams webhook returned non-200 for job {job.id}: "
                f"HTTP {response.status_code} – {response.text[:200]}"
            )
    except Exception as exc:
        logger.warning(f"Failed to send Teams notification for job {job.id}: {exc}")


def send_test_notification(webhook_url: str) -> dict:
    """
    Send a test card to the webhook and return a status/message dict.

    Returns:
        {"status": "success"|"error", "message": str}
    """
    if not webhook_url:
        return {"status": "error", "message": "No webhook URL provided"}

    try:
        payload = _build_test_card()
        response = httpx.post(
            webhook_url,
            json=payload,
            timeout=10.0,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 200:
            return {
                "status": "success",
                "message": "Test notification sent successfully to Microsoft Teams",
            }
        else:
            return {
                "status": "error",
                "message": f"Teams webhook returned HTTP {response.status_code}: {response.text[:200]}",
            }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "message": "Connection timed out – check the webhook URL and your network",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to reach Teams webhook: {exc}",
        }
