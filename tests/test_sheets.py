"""Tests for expense_planner.sheets — fixed-row layout + overflow guard.

Regression tests for the section-overflow bug: months with more
transactions than a section could hold were silently truncated,
corrupting the monthly SUM totals (e.g. June 2026 investments).
"""

import pytest

from expense_planner import sheets
from expense_planner.sheets import (
    EXPENSE_END,
    EXPENSE_START,
    INCOME_END,
    INCOME_LABEL,
    INCOME_START,
    INVEST_END,
    INVEST_LABEL,
    INVEST_START,
    SectionOverflowError,
    _fit_to_region,
)


class TestFitToRegion:
    def test_pads_short_list_to_capacity(self):
        rows = [["a", "b", "c", "d"]]
        out = _fit_to_region(rows, 5, "expense", "2026-06")
        assert len(out) == 5
        assert out[0] == ["a", "b", "c", "d"]
        assert out[1:] == [["", "", "", ""]] * 4

    def test_exact_fit_is_unchanged(self):
        rows = [["x", "", "", "1"]] * 3
        out = _fit_to_region(rows, 3, "income", "2026-06")
        assert len(out) == 3
        assert out == rows

    def test_overflow_raises_instead_of_dropping(self):
        rows = [["x", "", "", "1"]] * 15
        with pytest.raises(SectionOverflowError) as exc:
            _fit_to_region(rows, 14, "investment", "2026-06")
        # Message names the section + month so the user knows what to grow
        assert "investment" in str(exc.value)
        assert "2026-06" in str(exc.value)

    def test_never_silently_truncates(self):
        """The old bug: rows[:capacity]. Ensure we raise, not slice."""
        rows = [["r%d" % i, "", "", str(i)] for i in range(20)]
        with pytest.raises(SectionOverflowError):
            _fit_to_region(rows, 14, "investment", "2026-06")


class TestLayoutInvariants:
    def test_sections_do_not_overlap_and_are_ordered(self):
        # Each label sits directly above its section start
        assert INVEST_LABEL == INVEST_START - 1
        assert INCOME_LABEL == INCOME_START - 1
        # Order top-to-bottom: expenses, then investment, then income
        assert EXPENSE_START <= EXPENSE_END < INVEST_LABEL
        assert INVEST_START <= INVEST_END < INCOME_LABEL
        assert INCOME_START <= INCOME_END

    def test_investment_has_20_slots_and_income_follows(self):
        # Per layout spec: investments start at 171 with 20 slots, income below
        assert INVEST_LABEL == 171
        assert (INVEST_END - INVEST_START + 1) == 20
        assert INCOME_LABEL == INVEST_END + 1

    def test_capacities_cover_observed_maxima(self):
        # Observed maxima (Jan-Jul 2026): expenses 133, income 7, investments 17
        assert (EXPENSE_END - EXPENSE_START + 1) >= 133
        assert (INCOME_END - INCOME_START + 1) >= 7
        assert (INVEST_END - INVEST_START + 1) >= 17

    def test_total_rows_covers_all_sections(self):
        assert sheets.TOTAL_ROWS >= INVEST_END
        assert sheets.TOTAL_ROWS >= INCOME_END
