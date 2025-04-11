from datetime import datetime, time, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ctu_time import (
    calculate_high_noon_utc,
    calculate_midnight_adjustment,
    ctu_to_utc,
    utc_to_ctu,
)

# Hypothesis strategies
longitudes = st.floats(min_value=-180, max_value=180, allow_nan=False)
dates = st.dates(
    min_value=datetime(2000, 1, 1).date(), max_value=datetime(2100, 1, 1).date()
)
times = st.datetimes(timezones=st.none())  # use naive UTC datetimes


@st.composite
def aware_datetimes(draw):
    return draw(times)


@st.composite
def ctu_components(draw):
    return (draw(longitudes), draw(dates))


# Core property: Solar noon invariant
@given(longitudes, dates)
def test_solar_noon_is_12ctu(longitude, date):
    """12:00:00 CTU must always equal calculated solar noon"""
    noon_utc = calculate_high_noon_utc(longitude, datetime.combine(date, time()))
    ctu_time = utc_to_ctu(noon_utc, longitude)
    assert ctu_time == time(12, 0, 0), f"Solar noon failure: {noon_utc} → {ctu_time}"


# Bidirectional conversion property
@given(aware_datetimes(), longitudes)
def test_ctu_utc_roundtrip(utc_time, longitude):
    """UTC → CTU → UTC should recover original time within 1 sec tolerance"""
    try:
        ctu = utc_to_ctu(utc_time, longitude)
        reconstructed = ctu_to_utc(ctu, utc_time, longitude)
    except Exception as e:
        pytest.fail(f"Roundtrip failed: {e}")

    # Allow 1-second tolerance for time->datetime conversion
    assert abs((reconstructed - utc_time).total_seconds()) <= 1, (
        f"Roundtrip mismatch: {utc_time} → {ctu} → {reconstructed}"
    )


# Midnight adjustment property
@given(ctu_components())
def test_midnight_adjustment_consistency(params):
    """Midnight adjustment should match solar day drift"""
    longitude, date = params
    base_date = datetime.combine(date, time())
    delta = calculate_midnight_adjustment(longitude, base_date)
    expected = (
        calculate_high_noon_utc(longitude, base_date + timedelta(days=1))
        - calculate_high_noon_utc(longitude, base_date)
    ).total_seconds() - 86400

    assert abs(delta - expected) < 1e-6, "Adjustment doesn't match solar day drift"


# Edge case tests
def test_polar_longitude():
    """Should handle 180° longitude (International Date Line)"""
    utc_time = datetime(2025, 4, 10, 12, 0)
    ctu_time = utc_to_ctu(utc_time, 180.0)
    assert 0 <= ctu_time.hour <= 23, "Polar longitude hour invalid"


def test_leap_year():
    """Feb 29 should produce valid CTU time"""
    noon = calculate_high_noon_utc(0.0, datetime(2024, 2, 29))
    assert noon.month == 2 and noon.day == 29, "Leap year handling failed"
