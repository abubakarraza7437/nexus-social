import zoneinfo
from datetime import datetime
from typing import Literal

_UTC = zoneinfo.ZoneInfo("UTC")


# --------------------------------------------------------------------------- #
# Exceptions                                                                   #
# --------------------------------------------------------------------------- #

class NonExistentTimeError(ValueError):
    """
    Raised when a wall-clock time falls inside a DST spring-forward gap.

    Example: clocks in America/New_York spring forward from 02:00 → 03:00
    on 2026-03-08.  Any time in [02:00, 03:00) on that date does not exist.
    """


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #

def _tz(tz_name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except (zoneinfo.ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"Unknown timezone: {tz_name!r}") from exc


def is_nonexistent(naive_dt: datetime, tz_name: str) -> bool:
    """
    Return True if *naive_dt* falls inside a DST spring-forward gap.

    Detection: attach the timezone, convert to UTC and back to local.
    If the round-trip local time differs from the input, the original
    time was skipped over (i.e. it lives inside the gap).
    """
    tz = _tz(tz_name)
    aware = naive_dt.replace(tzinfo=tz)
    roundtrip = aware.astimezone(_UTC).astimezone(tz)
    # Strip tzinfo/fold for a clean naive comparison
    return roundtrip.replace(tzinfo=None, fold=0) != naive_dt.replace(fold=0)


def is_ambiguous(naive_dt: datetime, tz_name: str) -> bool:
    """
    Return True if *naive_dt* falls inside a DST fall-back fold.

    Detection: a fold time has different UTC offsets depending on fold=0
    (pre-transition, summer time) vs fold=1 (post-transition, winter time).
    """
    tz = _tz(tz_name)
    fold0 = naive_dt.replace(tzinfo=tz, fold=0)
    fold1 = naive_dt.replace(tzinfo=tz, fold=1)
    return fold0.utcoffset() != fold1.utcoffset()


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def localize_to_utc(
    naive_dt: datetime,
    tz_name: str,
    *,
    on_gap: Literal["raise", "push_forward"] = "raise",
    fold: Literal[0, 1] = 0,
) -> datetime:
    """
    Convert a timezone-naive user datetime to a UTC-aware datetime.

    Args:
        naive_dt:     Wall-clock time as entered by the user (no tzinfo).
        tz_name:      IANA timezone name, e.g. "America/New_York".
        on_gap:       What to do when *naive_dt* falls in a spring-forward gap:
                        "raise"        — raise NonExistentTimeError (default,
                                         forces the caller to ask the user for a
                                         valid time).
                        "push_forward" — silently advance to the first valid
                                         UTC instant after the gap ends.
        fold:         Disambiguation for fall-back folds:
                        0 — first occurrence (pre-transition, summer/DST time).
                        1 — second occurrence (post-transition, winter/standard).
                      Ignored for unambiguous and gap times.

    Returns:
        UTC-aware datetime.

    Raises:
        NonExistentTimeError: if *naive_dt* is in a gap and on_gap="raise".
        ValueError:           if *tz_name* is not a valid IANA timezone.
    """
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
    """
    Convert a UTC-aware datetime to a local-aware datetime for display.

    Never store the result — display only.

    Args:
        aware_utc: UTC-aware datetime (tzinfo must be set).
        tz_name:   IANA timezone name.

    Returns:
        Aware datetime in the requested local timezone.
    """
    if aware_utc.tzinfo is None:
        raise ValueError("aware_utc must carry tzinfo.")
    return aware_utc.astimezone(_tz(tz_name))
