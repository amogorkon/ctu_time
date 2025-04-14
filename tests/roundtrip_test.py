from datetime import datetime, timedelta, timezone

from tqdm import tqdm

from ctu_time.ctu import roundtrip_test, utc_to_ctu

long = 9.1829  # stuttgart


def iterate_over_seconds_in_year(year):
    """Iterates over all seconds in a given year and yields each datetime object.

    Args:
        year: The year for which to iterate (integer).

    Yields:
        datetime.datetime: A datetime object representing each second of the year.
    """
    start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    time_difference = end_date - start_date
    total_seconds = int(time_difference.total_seconds())
    print(f"Total seconds in {year}: {total_seconds}")

    # last 1/10 of total_seconds:
    for i in tqdm(range(total_seconds)):
        yield start_date + timedelta(seconds=i)


print("Testing roundtrip error for every second in 2025...")

try:
    roundtrips = []
    for utc in iterate_over_seconds_in_year(2025):
        x, y, z = roundtrip_test(long, utc), utc, utc_to_ctu(utc, long)
        if x not in [0, 1e-6]:
            roundtrips.append((x, y, z))
except RecursionError as e:
    print("RecursionError:", e, "for", utc)


from pypeduct import pyped


@pyped
def save():
    with open("roundtrip_errors", "w") as f:
        (roundtrips >> map(str) >> "\n".join >> f.writelines)
    with open("roundtrip_exceptions", "w") as f:
        (
            roundtrips
            >> filter(lambda x: isinstance(x, RuntimeError))
            >> map(str)
            >> "\n".join
            >> f.writelines
        )


# save()

print(len(roundtrips))
for x in roundtrips:
    print(x[0], x[1], x[2])

# print("Roundtrips are calculated. Enjoy.")
# print("max:", max(roundtrips))
# print("min:", min(roundtrips))


# import matplotlib.pyplot as plt

# plt.figure(figsize=(10, 5))
# plt.plot([x[1] for x in roundtrips], [x[0] for x in roundtrips], "o", markersize=1)
# plt.xlabel("Datetime")
# plt.ylabel("Roundtrip Error (seconds)")
# plt.show()
