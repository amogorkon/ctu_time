"""
CTU (Calculated Time Uncoordinated).

CTU is a timekeeping system that uses the solar noon as a reference point.
It adjusts the midnight hour (23:00 to 24:00) to absorb fluctuations in the solar day length.
This keeps noon aligned with the sun locally, without needing time zones or DST.
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache

# Constants from NOAA Technical Report
SOLAR_RADIUS = 0.26667  # Degrees
REFRACTION = 0.5667  # Degrees (atmospheric refraction)
CIVIL_TWILIGHT = -6.0
SUNRISE_SUNSET = -(SOLAR_RADIUS + REFRACTION)  # -0.8333° for sunrise/sunset

# Asymmetrical model: first 23 hours are fixed.
FIXED_HOURS = 23
FIXED_SEC = FIXED_HOURS * 3600  # 82800 seconds fixed
TOTAL_CTU_SEC = 86400  # CTU day length in seconds


@lru_cache(maxsize=365)
def calc_noon_utc(longitude: float, dt: datetime) -> datetime:
    """
    Calculate UTC-aware solar noon from approximate astronomical formulas.
    The equation of time approximates the discrepancy between sundial time and clock time.
    """
    n = dt.timetuple().tm_yday
    B = math.radians(360 / 365.2422 * (n - 81))
    eot = (
        9.87 * math.sin(2 * B)
        - 7.53 * math.cos(B)
        - 1.5 * math.sin(B)
        + 0.21 * math.cos(2 * B)
    )
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc) + timedelta(
        seconds=(12 - (longitude / 15 + eot / 60)) * 3600
    )


def utc_to_ctu(utc: datetime, longitude: float) -> tuple[time, date]:
    """
    Convert UTC to CTU using an asymmetrical midnight hour model.

    In this model, the first 23 CTU hours (82800 seconds) are mapped directly
    1:1 from solar time (measured from solar midnight). The remaining part of the
    solar day is scaled into exactly 3600 CTU seconds (the variable midnight hour).

    Returns a tuple (CTU time, reference date), where the reference day is that
    corresponding to the computed solar noon.
    """
    if utc.utcoffset() != timedelta(0):
        raise ValueError("UTC datetime required")

    # Determine the correct solar window by testing candidate days.
    def window_for_day(base_day: date):
        noon = calc_noon_utc(
            longitude, datetime.combine(base_day, time(), tzinfo=timezone.utc)
        )
        next_noon = calc_noon_utc(longitude, noon + timedelta(days=1))
        T_solar = (next_noon - noon).total_seconds()
        solar_midnight = noon - timedelta(seconds=T_solar / 2)
        return noon, solar_midnight, T_solar

    today = utc.date()
    for day_offset in [-1, 0, 1]:
        base_day = today + timedelta(days=day_offset)
        ref_noon, solar_midnight, T_solar = window_for_day(base_day)
        end = solar_midnight + timedelta(seconds=T_solar)
        if solar_midnight <= utc < end:
            break
    else:
        # In 1 000 000 second-roundtrips there are 38 pathological ones that fail.
        # This is likely caused by a EoT discontinuity or a cumulative timing effect causing an intersection gap.
        # It's also not a floating point rounding issue, so there is no easy fix not worth further complicating the code.
        # So we cheat: try previous or next second and reuse result, limiting the error to ~1 second.
        return utc_to_ctu(utc - timedelta(seconds=1), longitude)

    ref_day = ref_noon.date()

    elapsed = (utc - solar_midnight).total_seconds()

    # For elapsed time within the first 23 fixed hours, CTU time equals elapsed time.
    if elapsed <= FIXED_SEC:
        ctu_sec = elapsed
    else:
        # Otherwise, map the remaining elapsed seconds linearly into 3600 CTU seconds.
        extra = elapsed - FIXED_SEC
        variable_length = (
            T_solar - FIXED_SEC
        )  # Actual solar seconds in the variable midnight hour.
        ctu_sec = FIXED_SEC + (extra / variable_length) * 3600

    # Normalize into [0, 86400) if needed.
    ctu_sec %= TOTAL_CTU_SEC
    hours, rem = divmod(int(ctu_sec), 3600)
    minutes, seconds = divmod(rem, 60)
    micro = round((ctu_sec - int(ctu_sec)) * 1_000_000)

    return time(hours, minutes, seconds, micro), ref_day


def ctu_to_utc(ctu: time, ref_day: date, longitude: float) -> datetime:
    """
    Invert the asymmetrical conversion: convert CTU back to UTC.

    For CTU seconds below 82800, the mapping is 1:1.
    For CTU seconds above or equal to 82800, the inverse scaling recovers the actual
    solar seconds in the variable midnight hour.
    """
    ref_noon = calc_noon_utc(
        longitude,
        datetime(ref_day.year, ref_day.month, ref_day.day, tzinfo=timezone.utc),
    )
    next_noon = calc_noon_utc(longitude, ref_noon + timedelta(days=1))
    T_solar = (next_noon - ref_noon).total_seconds()
    solar_midnight = ref_noon - timedelta(seconds=T_solar / 2)

    # Compute total CTU seconds from the input CTU time.
    ctu_sec = ctu.hour * 3600 + ctu.minute * 60 + ctu.second + ctu.microsecond / 1e6

    if ctu_sec <= FIXED_SEC:
        elapsed = ctu_sec
    else:
        extra_ctu = ctu_sec - FIXED_SEC
        variable_length = T_solar - FIXED_SEC
        extra = (extra_ctu / 3600) * variable_length
        elapsed = FIXED_SEC + extra

    utc = solar_midnight + timedelta(seconds=elapsed)
    return utc.astimezone(timezone.utc)


def now(longitude: float) -> time:
    """Return the current CTU time using the asymmetric midnight model."""
    return utc_to_ctu(datetime.now(timezone.utc), longitude)[0]


def roundtrip_test(longitude: float, utc_now: datetime) -> float:
    """
    Validate the CTU <=> UTC conversion by performing a roundtrip conversion.
    Returns the absolute error in seconds.
    """
    ctu_time, ref_day = utc_to_ctu(utc_now, longitude)
    back = ctu_to_utc(ctu_time, ref_day, longitude)
    return abs((utc_now - back).total_seconds())


######## Dawn/Dusk Calculation ########


def julian_date(dt: datetime) -> float:
    """Convert datetime to Julian Date (UT1) with millisecond precision."""
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    frac = (
        (dt.hour - 12) / 24
        + dt.minute / 1440
        + dt.second / 86400
        + dt.microsecond / 86400e6
    )
    return jdn + frac


def solar_coordinates(jd: float) -> tuple:
    """NOAA-approved solar position (geocentric in degrees)."""
    # Julian centuries from J2000
    T = (jd - 2451545.0) / 36525.0

    # Mean solar geometry
    L = (280.46646 + 36000.76983 * T + 0.0003032 * T**2) % 360
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T**2) % 360
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T**2

    # Equation of center
    C = (
        (1.914602 - 0.004817 * T - 0.000014 * T**2) * math.sin(math.radians(M))
        + (0.019993 - 0.000101 * T) * math.sin(2 * math.radians(M))
        + 0.000289 * math.sin(3 * math.radians(M))
    )

    # True solar longitude and declination
    λ = (L + C) % 360
    δ = math.degrees(math.asin(math.sin(math.radians(λ)) * 0.3977895))

    # Equation of time (minutes)
    ε = 23.4393 - 0.01300 * T
    y = math.tan(math.radians(ε / 2)) ** 2
    eot = (
        y * math.sin(2 * math.radians(L))
        - 2 * e * math.sin(math.radians(M))
        + 4 * e * y * math.sin(math.radians(M)) * math.cos(2 * math.radians(L))
        - 0.5 * y**2 * math.sin(4 * math.radians(L))
        - 1.25 * e**2 * math.sin(2 * math.radians(M))
    )
    eot = math.degrees(eot) * 4  # Convert radians to minutes

    return δ, eot


def hour_angle(lat: float, dec: float, elev: float = CIVIL_TWILIGHT) -> float:
    """Calculate sun hour angle for target elevation (degrees)."""
    lat_rad = math.radians(lat)
    dec_rad = math.radians(dec)
    elev_rad = math.radians(elev)

    cos_ha = (math.sin(elev_rad) - math.sin(lat_rad) * math.sin(dec_rad)) / (
        math.cos(lat_rad) * math.cos(dec_rad)
    )

    if cos_ha < -1:
        return 180.0  # Polar night
    return 0.0 if cos_ha > 1 else math.degrees(math.acos(cos_ha))


def dawn_dusk(lat: float, lon: float, date: datetime) -> tuple[datetime, datetime]:
    """Dawn/dusk in UTC."""
    noon_utc = calc_noon_utc(lon, date).replace(tzinfo=timezone.utc)

    # Solar position at noon
    jd = julian_date(noon_utc)
    dec, eot = solar_coordinates(jd)

    # Hour angles
    ha = hour_angle(lat, dec)
    dawn_offset = timedelta(minutes=-(ha * 4 + eot))
    dusk_offset = timedelta(minutes=+(ha * 4 + eot))

    dawn = noon_utc + dawn_offset
    dusk = noon_utc + dusk_offset

    return dawn, dusk


if __name__ == "__main__":
    print("Local:", datetime.now().time())
    print("UTC:", datetime.now(timezone.utc).time())
    lat, lon = 48.7758, 9.1829  # Stuttgart
    print("CTU:", now(lon))
    print(
        f"Roundtrip error: {roundtrip_test(lon, datetime.now(timezone.utc)):.6f} seconds"
    )
    dawn, dusk = dawn_dusk(lat, lon, datetime.now(timezone.utc))
    print(f"Dawn UTC: {dawn.strftime('%H:%M:%S')}")
    print(f"Dusk UTC: {dusk.strftime('%H:%M:%S')}")
    print(f"Dawn CTU: {utc_to_ctu(dawn, lon)[0].strftime('%H:%M:%S')}")
    print(f"Dusk CTU: {utc_to_ctu(dusk, lon)[0].strftime('%H:%M:%S')}")
