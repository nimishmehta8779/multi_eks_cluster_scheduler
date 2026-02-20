"""
Timezone-aware cron expression utilities.

Provides parsing, validation, and trigger checking for cron expressions
with timezone support.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from croniter import croniter
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def validate_cron(expression: str) -> bool:
    """
    Validate a cron expression.

    Args:
        expression: Cron expression string (5-field).

    Returns:
        True if valid, False otherwise.
    """
    return croniter.is_valid(expression)


def is_triggered(
    cron_expression: str,
    tz_name: str = "UTC",
    check_time: Optional[datetime] = None,
) -> bool:
    """
    Check if a cron expression matches the current minute.

    Args:
        cron_expression: Cron expression string.
        tz_name: Timezone name (IANA).
        check_time: Time to check (defaults to now).

    Returns:
        True if cron triggers for the current minute.
    """
    if not validate_cron(cron_expression):
        logger.warning(
            "Invalid cron expression",
            extra={"cron_expression": cron_expression},
        )
        return False

    from datetime import timedelta
    tz = ZoneInfo(tz_name)
    now = check_time or datetime.now(timezone.utc)
    
    # Normalize to the start of the current minute
    reference_time = now.replace(second=0, microsecond=0)
    local_ref = reference_time.astimezone(tz)

    # Use a time slightly into the minute to ensure get_prev() includes the minute itself
    cron = croniter(cron_expression, local_ref + timedelta(seconds=1))
    prev_trigger = cron.get_prev(datetime)

    return prev_trigger == local_ref


def get_next_trigger(
    cron_expression: str,
    tz_name: str = "UTC",
    from_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Get the next trigger time for a cron expression.

    Args:
        cron_expression: Cron expression string.
        tz_name: Timezone name.
        from_time: Base time (defaults to now).

    Returns:
        Next trigger time in UTC, or None if invalid.
    """
    if not validate_cron(cron_expression):
        return None

    tz = ZoneInfo(tz_name)
    now = from_time or datetime.now(timezone.utc)
    local_now = now.astimezone(tz)

    cron = croniter(cron_expression, local_now)
    next_time = cron.get_next(datetime)

    return next_time.astimezone(timezone.utc)
