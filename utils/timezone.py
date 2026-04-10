import zoneinfo
from datetime import datetime
from typing import Literal

_UTC = zoneinfo.ZoneInfo("UTC")


# Exceptions

class NonExistentTimeError(ValueError):
    """
    Raised when a wall-clock time falls inside a DST spring-forward gap.

    Example: clocks in America/New_York spring forward from 02:00 → 03:00
    on 2026-03-08.  Any time in [02:00, 03:00) on that date does not exist.
    """


# Internal helpers

def _tz(tz_name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except (zoneinfo.ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"Unknown timezone: {tz_name!r}") from exc


def is_nonexistent(naive_dt: datetime, tz_name: str) -> bool:

    tz = _tz(tz_name)
    aware = naive_dt.replace(tzinfo=tz)
    roundtrip = aware.astimezone(_UTC).astimezone(tz)
    # Strip tzinfo/fold for a clean naive comparison
    return roundtrip.replace(tzinfo=None, fold=0) != naive_dt.replace(fold=0)


def is_ambiguous(naive_dt: datetime, tz_name: str) -> bool:

    tz = _tz(tz_name)
    fold0 = naive_dt.replace(tzinfo=tz, fold=0)
    fold1 = naive_dt.replace(tzinfo=tz, fold=1)
    return fold0.utcoffset() != fold1.utcoffset()


# Public API

def localize_to_utc(
    naive_dt: datetime,
    tz_name: str,
    *,
    on_gap: Literal["raise", "push_forward"] = "raise",
    fold: Literal[0, 1] = 0,
) -> datetime:

    if naive_dt.tzinfo is not None:
        raise ValueError(
            "naive_dt must not carry tzinfo — pass a plain wall-clock time."
        )

    tz = _tz(tz_name)

    if is_nonexistent(naive_dt, tz_name):
        if on_gap == "raise":
            raise NonExistentTimeError(
                f"{naive_dt.isoformat()} does not exist in {tz_name!r}: "
                "the clocks spring forward over this time. "
                "Pass on_gap='push_forward' to advance to the next valid time, "
                "or ask the user to choose a different time."
            )
        # push_forward: let zoneinfo's natural behaviour handle it.
        # For a gap, replace() with the pre-transition offset already produces
        # a UTC instant past the gap — i.e. the time after the clocks land.

    aware = naive_dt.replace(tzinfo=tz, fold=fold)
    return aware.astimezone(_UTC)


def utc_to_local(aware_utc: datetime, tz_name: str) -> datetime:

    if aware_utc.tzinfo is None:
        raise ValueError("aware_utc must carry tzinfo.")
    return aware_utc.astimezone(_tz(tz_name))
