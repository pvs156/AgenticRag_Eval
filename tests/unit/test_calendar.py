from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from app.rules.calendar import add_business_days, business_days_between, fed_holidays, is_business_day


def test_fed_holidays_2026():
    expected = {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 9, 7),
        date(2026, 10, 12),
        date(2026, 11, 11),
        date(2026, 11, 26),
        date(2026, 12, 25),
    }
    # July 4, 2026 is a Saturday: the Fed does not observe it on Friday July 3.
    assert fed_holidays(2026) == expected
    assert is_business_day(date(2026, 7, 3))


def test_sunday_holiday_observed_monday():
    # New Year's Day 2023 was a Sunday -> observed Monday Jan 2.
    assert date(2023, 1, 2) in fed_holidays(2023)


def test_juneteenth_only_from_2021():
    assert date(2020, 6, 19) not in fed_holidays(2020)
    assert date(2021, 6, 19) not in fed_holidays(2021)  # Saturday, not moved
    assert date(2022, 6, 20) in fed_holidays(2022)  # Sunday -> Monday


def test_add_business_days_skips_weekend_and_columbus_day():
    # Fri 2026-10-09; Mon 10-12 is Columbus Day.
    assert add_business_days(date(2026, 10, 9), 1) == date(2026, 10, 13)
    assert add_business_days(date(2026, 10, 9), 10) == date(2026, 10, 26)
    assert add_business_days(date(2026, 10, 9), 20) == date(2026, 11, 9)


def test_zero_days_is_identity():
    assert add_business_days(date(2026, 10, 10), 0) == date(2026, 10, 10)


@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)), st.integers(1, 60))
def test_add_then_count_roundtrip(start, n):
    end = add_business_days(start, n)
    assert is_business_day(end)
    assert business_days_between(start, end) == n
