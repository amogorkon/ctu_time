from datetime import datetime, timezone

from hypothesis import strategies as st

from ctu_time import (
    calc_noon_utc,
    utc_to_ctu,
)

# Hypothesis strategies
longitudes = st.floats(min_value=-180, max_value=180, allow_nan=False)
dates = st.dates(
    min_value=datetime(2000, 1, 1, tzinfo=timezone.utc).date(),
    max_value=datetime(2100, 1, 1, tzinfo=timezone.utc).date(),
)
times = st.datetimes(timezones=st.none())  # use naive UTC datetimes


@st.composite
def aware_datetimes(draw):
    return draw(times)


@st.composite
def ctu_components(draw):
    return (draw(longitudes), draw(dates))


# Edge case tests
def test_polar_longitude():
    """Should handle 180° longitude (International Date Line)"""
    utc_time = datetime(2025, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    ctu_time = utc_to_ctu(utc_time, 180.0)
    assert 0 <= ctu_time[0].hour <= 23, "Polar longitude hour invalid"


def test_leap_year():
    """Feb 29 should produce valid CTU time"""
    noon = calc_noon_utc(0.0, datetime(2024, 2, 29))
    assert noon.month == 2 and noon.day == 29, "Leap year handling failed"
