"""Business-day arithmetic.

Regulation E defines a business day per institution (12 CFR 1005.2(d): days the offices are open for
substantially all business functions). We cannot know a given bank's schedule, so we assume the common
case: Monday-Friday, excluding Federal Reserve holidays. Fed convention: a holiday falling on Sunday is
observed the following Monday; a holiday falling on Saturday is NOT moved to Friday. The assumption is
surfaced to users in every deadline that uses business days.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

BUSINESS_DAY_ASSUMPTION = (
    "Business days assume Monday to Friday excluding Federal Reserve holidays; the regulation lets each "
    "institution define its own business days (12 CFR 1005.2(d)), so the bank's actual date may differ."
)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@cache
def fed_holidays(year: int) -> frozenset[date]:
    mon, thu = 0, 3
    fixed = [date(year, 1, 1), date(year, 7, 4), date(year, 11, 11), date(year, 12, 25)]
    if year >= 2021:
        fixed.append(date(year, 6, 19))  # Juneteenth
    # Sunday -> observed Monday; Saturday -> not observed (already a non-business day).
    observed = {d + timedelta(days=1) if d.weekday() == 6 else d for d in fixed if d.weekday() != 5}
    floating = {
        _nth_weekday(year, 1, mon, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, mon, 3),  # Washington's Birthday
        _last_weekday(year, 5, mon),  # Memorial Day
        _nth_weekday(year, 9, mon, 1),  # Labor Day
        _nth_weekday(year, 10, mon, 2),  # Columbus Day
        _nth_weekday(year, 11, thu, 4),  # Thanksgiving
    }
    return frozenset(observed | floating)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in fed_holidays(d.year)


def add_business_days(start: date, n: int) -> date:
    """The date that is n business days after `start` (start itself is not counted)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    d = start
    while n:
        d += timedelta(days=1)
        if is_business_day(d):
            n -= 1
    return d


def business_days_between(start: date, end: date) -> int:
    """Count of business days in (start, end]."""
    if end <= start:
        return 0
    return sum(is_business_day(start + timedelta(days=i)) for i in range(1, (end - start).days + 1))
