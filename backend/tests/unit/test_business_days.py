from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.business_days import business_days_add

TZ = "Europe/Berlin"


def test_weekday_plus_one_lands_next_weekday():
    monday = datetime(2026, 3, 2, 10, 0, tzinfo=ZoneInfo(TZ))  # Monday
    assert business_days_add(monday, 1, TZ).weekday() == 1  # Tuesday
    assert business_days_add(monday, 3, TZ).weekday() == 3  # Thursday


def test_friday_plus_three_skips_weekend():
    friday = datetime(2026, 3, 6, 10, 0, tzinfo=ZoneInfo(TZ))
    result = business_days_add(friday, 3, TZ)
    # Fri +1 = Mon; +2 = Tue; +3 = Wed
    assert result.weekday() == 2
    assert result.day == 11


def test_saturday_plus_five_starts_from_next_monday():
    saturday = datetime(2026, 3, 7, 10, 0, tzinfo=ZoneInfo(TZ))
    result = business_days_add(saturday, 5, TZ)
    # Sat +1 = Mon; +2 = Tue; +3 = Wed; +4 = Thu; +5 = Fri
    assert result.weekday() == 4
    assert result.day == 13


def test_sunday_plus_five_starts_from_next_monday():
    sunday = datetime(2026, 3, 8, 10, 0, tzinfo=ZoneInfo(TZ))
    result = business_days_add(sunday, 5, TZ)
    assert result.weekday() == 4
    assert result.day == 13


def test_preserves_time_of_day():
    ts = datetime(2026, 3, 2, 15, 42, 17, tzinfo=ZoneInfo(TZ))
    result = business_days_add(ts, 1, TZ)
    assert (result.hour, result.minute, result.second) == (15, 42, 17)
