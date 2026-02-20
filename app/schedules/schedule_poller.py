"""
Lambda handler for schedule polling.

Triggered by EventBridge every minute. Evaluates enabled schedules,
checks cron expressions, and triggers operations with idempotency.
"""

import logging
from datetime import datetime, timezone

from json_logging import setup_json_logging
from schedules.cron_utils import is_triggered
from schedules.schedule_manager import ScheduleManager
from schedules.schedule_worker import trigger_schedule_operation
from state.state_manager import StateManager

# --- Structured Logging ---
setup_json_logging()
logger = logging.getLogger(__name__)


def handler(event, context):
    """
    Lambda handler triggered by EventBridge every minute.

    Scans all enabled schedules, evaluates cron expressions,
    and triggers operations with idempotency protection.

    Args:
        event: EventBridge event.
        context: Lambda context.

    Returns:
        Dict with evaluation results.
    """
    schedule_manager = ScheduleManager()
    state_manager = StateManager()

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    minute_key = now.strftime("%Y-%m-%dT%H:%M")

    logger.info("Schedule poll started", extra={"minute_key": minute_key})

    schedules = schedule_manager.list_schedules(enabled_only=True)

    triggered_count = 0
    skipped_count = 0
    error_count = 0

    for schedule in schedules:
        schedule_id = schedule.get("schedule_id", "")
        tz_name = schedule.get("time_zone", "UTC")

        # Check paused_until
        paused_until = schedule.get("paused_until")
        if paused_until:
            try:
                pause_dt = datetime.fromisoformat(paused_until)
                if now < pause_dt:
                    logger.info(
                        "Schedule paused, skipping",
                        extra={
                            "schedule_id": schedule_id,
                            "paused_until": paused_until,
                        },
                    )
                    skipped_count += 1
                    continue
                else:
                    # Unpause - resume
                    schedule_manager.update_schedule(
                        schedule_id, {"enabled": True}
                    )
            except (ValueError, TypeError):
                pass

        # Evaluate recurrence
        recurrence = schedule.get("recurrence")
        if recurrence and is_triggered(recurrence, tz_name):
            lock_key = f"schedule:{schedule_id}:scale:{minute_key}"
            if state_manager.acquire_idempotency_lock(lock_key):
                try:
                    result = trigger_schedule_operation(schedule, "scale")
                    schedule_manager.record_execution(
                        schedule_id, "scale",
                        result.get("operation_id", ""),
                        result.get("clusters_queued", 0),
                    )
                    triggered_count += 1
                except Exception as e:
                    logger.error(
                        "Failed to trigger scale operation",
                        extra={
                            "schedule_id": schedule_id,
                            "error": str(e),
                        },
                    )
                    error_count += 1
            else:
                logger.info(
                    "Scale already triggered this minute",
                    extra={"schedule_id": schedule_id},
                )

    logger.info(
        "Schedule poll complete",
        extra={
            "schedules_evaluated": len(schedules),
            "triggered": triggered_count,
            "skipped": skipped_count,
            "errors": error_count,
        },
    )

    return {
        "schedules_evaluated": len(schedules),
        "triggered": triggered_count,
        "skipped": skipped_count,
        "errors": error_count,
    }
