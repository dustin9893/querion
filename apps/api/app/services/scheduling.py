"""Cron helpers for report schedules: validate, compute the next runs, describe in Vietnamese."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Asia/Ho_Chi_Minh"
MAX_PREVIEW = 5

WEEKDAY_VI = {"0": "CN", "1": "T2", "2": "T3", "3": "T4", "4": "T5", "5": "T6", "6": "T7", "7": "CN"}


class ScheduleError(Exception):
    """Invalid cron or timezone — shown to the admin editing the schedule."""


def tzinfo(name: str | None):
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError(f"Múi giờ không hợp lệ: {name}")


def validate_cron(expr: str) -> str:
    from croniter import croniter

    expr = " ".join((expr or "").split())
    if len(expr.split(" ")) != 5:
        raise ScheduleError("Biểu thức cron phải có 5 phần: phút giờ ngày tháng thứ")
    if not croniter.is_valid(expr):
        raise ScheduleError(f"Biểu thức cron không hợp lệ: {expr}")
    return expr


def next_runs(expr: str, tz_name: str | None = DEFAULT_TZ, count: int = MAX_PREVIEW,
              after: datetime | None = None) -> list[datetime]:
    """The next `count` fire times, in UTC. Cron fields are read in the schedule's timezone."""
    from croniter import croniter

    expr = validate_cron(expr)
    tz = tzinfo(tz_name)
    base = (after or datetime.now(timezone.utc)).astimezone(tz)
    it = croniter(expr, base)
    return [it.get_next(datetime).astimezone(timezone.utc) for _ in range(max(1, count))]


def next_run_at(expr: str, tz_name: str | None = DEFAULT_TZ, after: datetime | None = None) -> datetime:
    return next_runs(expr, tz_name, 1, after)[0]


def describe_cron(expr: str) -> str:
    """A short Vietnamese description for the schedule list ("08:00 các ngày T2–T6")."""
    try:
        expr = validate_cron(expr)
    except ScheduleError:
        return expr
    minute, hour, dom, month, dow = expr.split(" ")
    at = f"{hour.zfill(2)}:{minute.zfill(2)}" if hour.isdigit() and minute.isdigit() else f"cron {expr}"
    if dow == "1-5" and dom == "*":
        return f"{at} các ngày làm việc (T2–T6)"
    if dow != "*" and dom == "*":
        days = "/".join(WEEKDAY_VI.get(d, d) for d in dow.replace("-", ",").split(","))
        return f"{at} hằng tuần vào {days}"
    if dom != "*" and month == "*":
        return f"{at} ngày {dom} hằng tháng"
    if dom == "*" and dow == "*" and month == "*":
        return f"{at} hằng ngày"
    return f"cron {expr}"
