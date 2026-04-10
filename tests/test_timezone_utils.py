"""
Tests — utils.timezone
======================
Covers UTC conversion and DST edge cases.

DST reference dates (America/New_York):
  Spring forward: 2026-03-08 02:00 → 03:00  (gap:  [02:00, 03:00) doesn't exist)
  Fall back:      2026-11-01 02:00 → 01:00  (fold: [01:00, 02:00) occurs twice)
"""

import zoneinfo
from datetime import datetime, timezone as dt_tz

import pytest

from utils.timezone import (
    NonExistentTimeError,
    is_ambiguous,
    is_nonexistent,
    localize_to_utc,
    utc_to_local,
)

UTC = dt_tz.utc
ET = "America/New_York"    # UTC-5 (EST) / UTC-4 (EDT)
LON = "Europe/London"      # UTC+0 (GMT) / UTC+1 (BST)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def utc(year, month, day, hour, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=dt_tz.utc)


# --------------------------------------------------------------------------- #
# Normal (non-DST) conversions                                                 #
# --------------------------------------------------------------------------- #

class TestNormalConversion:
    def test_standard_time_et(self):
        # January: ET is EST (UTC-5)
        naive = datetime(2026, 1, 15, 9, 0)
        result = localize_to_utc(naive, ET)
        assert result == utc(2026, 1, 15, 14, 0)
        assert result.tzinfo == zoneinfo.ZoneInfo("UTC")

    def test_summer_time_et(self):
        # July: ET is EDT (UTC-4)
        naive = datetime(2026, 7, 15, 9, 0)
        result = localize_to_utc(naive, ET)
        assert result == utc(2026, 7, 15, 13, 0)

    def test_utc_timezone_is_identity(self):
        naive = datetime(2026, 6, 1, 12, 0)
        result = localize_to_utc(naive, "UTC")
        assert result == utc(2026, 6, 1, 12, 0)

    def test_positive_offset_timezone(self):
        # Asia/Kolkata is UTC+5:30 (no DST)
        naive = datetime(2026, 4, 1, 8, 30)
        result = localize_to_utc(naive, "Asia/Kolkata")
        assert result == utc(2026, 4, 1, 3, 0)

    def test_midnight_boundary(self):
        # 00:30 ET in January → previous day 05:30 UTC
        naive = datetime(2026, 1, 20, 0, 30)
        result = localize_to_utc(naive, ET)
        assert result == utc(2026, 1, 20, 5, 30)


# --------------------------------------------------------------------------- #
# Spring-forward gap  (2026-03-08 in America/New_York)                        #
# --------------------------------------------------------------------------- #

class TestSpringForwardGap:
    def test_time_just_before_gap_is_not_gap(self):
        # 01:59 exists (still EST, UTC-5)
        naive = datetime(2026, 3, 8, 1, 59)
        assert not is_nonexistent(naive, ET)
        result = localize_to_utc(naive, ET)
        assert result == utc(2026, 3, 8, 6, 59)

    def test_time_just_after_gap_is_not_gap(self):
        # 03:00 exists (now EDT, UTC-4)
        naive = datetime(2026, 3, 8, 3, 0)
        assert not is_nonexistent(naive, ET)
        result = localize_to_utc(naive, ET)
        assert result == utc(2026, 3, 8, 7, 0)

    def test_is_nonexistent_detects_gap(self):
        assert is_nonexistent(datetime(2026, 3, 8, 2, 0), ET)
        assert is_nonexistent(datetime(2026, 3, 8, 2, 30), ET)
        assert is_nonexistent(datetime(2026, 3, 8, 2, 59), ET)

    def test_gap_raises_by_default(self):
        naive = datetime(2026, 3, 8, 2, 30)
        with pytest.raises(NonExistentTimeError, match="does not exist"):
            localize_to_utc(naive, ET)

    def test_gap_raises_with_explicit_on_gap_raise(self):
        naive = datetime(2026, 3, 8, 2, 0)
        with pytest.raises(NonExistentTimeError):
            localize_to_utc(naive, ET, on_gap="raise")

    def test_gap_push_forward(self):
        # 02:30 doesn't exist — push_forward should land AFTER the gap (≥ 03:00 EDT)
        # zoneinfo uses the pre-gap offset (EST, UTC-5):
        # 02:30 EST = 07:30 UTC → maps back to 03:30 EDT (past the gap)
        naive = datetime(2026, 3, 8, 2, 30)
        result = localize_to_utc(naive, ET, on_gap="push_forward")
        assert result >= utc(2026, 3, 8, 7, 0), "Result must be past the end of the gap"

    def test_gap_push_forward_start_of_gap(self):
        naive = datetime(2026, 3, 8, 2, 0)
        result = localize_to_utc(naive, ET, on_gap="push_forward")
        assert result >= utc(2026, 3, 8, 7, 0)

    def test_normal_day_is_not_gap(self):
        # Same time on a non-transition day
        assert not is_nonexistent(datetime(2026, 3, 9, 2, 30), ET)

    def test_london_spring_forward_gap(self):
        # Europe/London: 2026-03-29 01:00 → 02:00
        assert is_nonexistent(datetime(2026, 3, 29, 1, 30), LON)
        with pytest.raises(NonExistentTimeError):
            localize_to_utc(datetime(2026, 3, 29, 1, 30), LON)


# --------------------------------------------------------------------------- #
# Fall-back fold  (2026-11-01 in America/New_York)                            #
# --------------------------------------------------------------------------- #

class TestFallBackFold:
    def test_time_before_fold_is_not_ambiguous(self):
        # 00:59 only occurs once (EDT)
        assert not is_ambiguous(datetime(2026, 11, 1, 0, 59), ET)

    def test_time_after_fold_is_not_ambiguous(self):
        # 02:00 only occurs once (EST)
        assert not is_ambiguous(datetime(2026, 11, 1, 2, 0), ET)

    def test_is_ambiguous_detects_fold(self):
        assert is_ambiguous(datetime(2026, 11, 1, 1, 0), ET)
        assert is_ambiguous(datetime(2026, 11, 1, 1, 30), ET)
        assert is_ambiguous(datetime(2026, 11, 1, 1, 59), ET)

    def test_fold_default_uses_pre_transition_dst_time(self):
        # fold=0 → first 1:30 AM = EDT (UTC-4) → 05:30 UTC
        naive = datetime(2026, 11, 1, 1, 30)
        result = localize_to_utc(naive, ET, fold=0)
        assert result == utc(2026, 11, 1, 5, 30)

    def test_fold_1_uses_post_transition_standard_time(self):
        # fold=1 → second 1:30 AM = EST (UTC-5) → 06:30 UTC
        naive = datetime(2026, 11, 1, 1, 30)
        result = localize_to_utc(naive, ET, fold=1)
        assert result == utc(2026, 11, 1, 6, 30)

    def test_fold_produces_different_utc_times(self):
        naive = datetime(2026, 11, 1, 1, 0)
        pre = localize_to_utc(naive, ET, fold=0)
        post = localize_to_utc(naive, ET, fold=1)
        assert pre != post
        assert (post - pre).total_seconds() == 3600  # exactly 1 hour apart

    def test_fold_start_boundary(self):
        # Exactly at 01:00 — first occurrence is EDT (UTC-4) → 05:00 UTC
        naive = datetime(2026, 11, 1, 1, 0)
        result = localize_to_utc(naive, ET, fold=0)
        assert result == utc(2026, 11, 1, 5, 0)

    def test_london_fall_back_fold(self):
        # Europe/London: 2026-10-25 02:00 → 01:00
        assert is_ambiguous(datetime(2026, 10, 25, 1, 30), LON)


# --------------------------------------------------------------------------- #
# utc_to_local                                                                 #
# --------------------------------------------------------------------------- #

class TestUtcToLocal:
    def test_basic_round_trip(self):
        naive = datetime(2026, 7, 15, 9, 0)
        utc_dt = localize_to_utc(naive, ET)
        local = utc_to_local(utc_dt, ET)
        assert local.replace(tzinfo=None) == naive

    def test_converts_to_correct_offset_winter(self):
        # 14:00 UTC → 09:00 EST (UTC-5)
        aware = utc(2026, 1, 15, 14, 0)
        local = utc_to_local(aware, ET)
        assert local.hour == 9
        assert local.utcoffset().total_seconds() == -5 * 3600

    def test_converts_to_correct_offset_summer(self):
        # 13:00 UTC → 09:00 EDT (UTC-4)
        aware = utc(2026, 7, 15, 13, 0)
        local = utc_to_local(aware, ET)
        assert local.hour == 9
        assert local.utcoffset().total_seconds() == -4 * 3600

    def test_raises_for_naive_input(self):
        naive = datetime(2026, 1, 1, 12, 0)
        with pytest.raises(ValueError, match="tzinfo"):
            utc_to_local(naive, ET)


# --------------------------------------------------------------------------- #
# Input validation                                                             #
# --------------------------------------------------------------------------- #

class TestInputValidation:
    def test_raises_for_aware_input_to_localize(self):
        aware = datetime(2026, 1, 1, 12, 0, tzinfo=dt_tz.utc)
        with pytest.raises(ValueError, match="naive_dt must not carry tzinfo"):
            localize_to_utc(aware, ET)

    def test_raises_for_invalid_timezone(self):
        naive = datetime(2026, 1, 1, 9, 0)
        with pytest.raises(ValueError, match="Unknown timezone"):
            localize_to_utc(naive, "Not/ATimezone")

    def test_raises_for_invalid_timezone_in_utc_to_local(self):
        with pytest.raises(ValueError, match="Unknown timezone"):
            utc_to_local(utc(2026, 1, 1, 12), "Not/ATimezone")
