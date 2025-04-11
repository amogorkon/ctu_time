"""
CTU (Calculated Time Uncoordinated).

CTU is a timekeeping system that uses the solar noon as a reference point.
It adjusts the midnight hour (23:00 to 24:00) to absorb fluctuations in the solar day length.
This keeps noon aligned with the sun locally, without needing time zones or DST.
"""

import math
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache


@lru_cache(maxsize=365)
def calculate_high_noon_utc(longitude: float, date: datetime) -> datetime:
    """Calculate the UTC datetime of solar noon for a given date and longitude."""
    n = date.timetuple().tm_yday
    B = math.radians(360 / 365.2422 * (n - 81))
    eot = (
        9.87 * math.sin(2 * B)
        - 7.53 * math.cos(B)
        - 1.5 * math.sin(B)
        + 0.21 * math.cos(2 * B)
    )
    eot_minutes = eot
    eot_hours = eot_minutes / 60
    longitude_offset = longitude / 15
    solar_noon_utc_hours = 12 - (longitude_offset + eot_hours)
    total_seconds = solar_noon_utc_hours * 3600
    return datetime(date.year, date.month, date.day) + timedelta(seconds=total_seconds)


def calculate_midnight_adjustment(longitude: float, date: datetime) -> float:
    """Calculate the difference between two consecutive solar noons from 86400 seconds."""
    today_noon = calculate_high_noon_utc(longitude, date)
    tomorrow_noon = calculate_high_noon_utc(longitude, date + timedelta(days=1))
    solar_day_length = (tomorrow_noon - today_noon).total_seconds()
    return solar_day_length - 86400  # Adjustment to apply to the midnight hour


def utc_to_ctu(utc_time: datetime, longitude: float) -> time:
    """Convert UTC datetime to CTU time."""
    assert utc_time.tzinfo == timezone.utc, "Requires UTC datetime"
    utc_time = utc_time.replace(tzinfo=None)  # Strip timezone for compatibility
    date = utc_time.date()
    today_noon = calculate_high_noon_utc(longitude, datetime.combine(date, time()))
    yesterday_noon = calculate_high_noon_utc(
        longitude, datetime.combine(date, time()) - timedelta(days=1)
    )

    if utc_time >= today_noon:
        ref_noon = today_noon
        schedule_date = date
    else:
        ref_noon = yesterday_noon
        schedule_date = date - timedelta(days=1)

    elapsed = (utc_time - ref_noon).total_seconds()
    midnight_adjust = calculate_midnight_adjustment(
        longitude, datetime.combine(schedule_date, time())
    )
    standard_day = 23 * 3600
    midnight_duration = 3600 + midnight_adjust

    if elapsed <= standard_day:
        ctu_seconds = elapsed + 12 * 3600
    else:
        time_into_midnight = elapsed - standard_day
        scaled_seconds = (time_into_midnight / midnight_duration) * 3600
        ctu_seconds = 23 * 3600 + scaled_seconds

    ctu_seconds %= 86400

    # High-precision rounding
    h, rem = divmod(int(ctu_seconds), 3600)
    m, s = divmod(rem, 60)
    μs = int(round((ctu_seconds % 1) * 1e6))

    # Handle rounding overflow
    if μs == 1_000_000:
        μs = 0
        s += 1
        if s == 60:
            s = 0
            m += 1
            if m == 60:
                m = 0
                h = (h + 1) % 24

    return time(hour=h, minute=m, second=s, microsecond=μs)


def ctu_to_utc(ctu_time: time, ctu_date: datetime, longitude: float) -> datetime:
    """Convert CTU time back to UTC datetime."""
    ctu_secs = (
        ctu_time.hour * 3600
        + ctu_time.minute * 60
        + ctu_time.second
        + ctu_time.microsecond / 1e6
    )
    noon_utc = calculate_high_noon_utc(longitude, ctu_date)
    midnight_adjust = calculate_midnight_adjustment(longitude, ctu_date)

    standard_day = 23 * 3600
    if ctu_secs < standard_day:
        delta = timedelta(seconds=ctu_secs - 12 * 3600)
    else:
        time_into_midnight = ctu_secs - standard_day
        scaled = (time_into_midnight / 3600) * (3600 + midnight_adjust)
        delta = timedelta(seconds=(standard_day - 12 * 3600) + scaled)

    result = noon_utc + delta
    return result.replace(tzinfo=timezone.utc)


def now(longitude: float) -> time:
    return utc_to_ctu(datetime.now(timezone.utc), longitude)


def roundtrip_test(longitude: float):
    """Validate CTU <=> UTC conversions with minimal error."""
    utc_now = datetime.now(timezone.utc)
    ctu = utc_to_ctu(utc_now, longitude)
    back = ctu_to_utc(ctu, utc_now, longitude)
    diff = abs((utc_now - back).total_seconds())
    print(f"Roundtrip error: {diff:.6f} seconds")


if __name__ == "__main__":
    print("Local:", datetime.now().time())
    print("UTC:", datetime.now(timezone.utc).time())
    long = 9.1829  # Stuttgart
    print("CTU:", now(long))
    roundtrip_test(long)
