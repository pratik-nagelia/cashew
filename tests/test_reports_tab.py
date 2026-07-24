"""Tests for expense_planner.reports_tab — table formulas + chart ranking."""

from expense_planner.reports_tab import (
    REPORT_SUBCATEGORIES,
    _build_parent_category_table,
    _build_subcategory_table,
    _rank_top_indices,
)


class TestRankTopIndices:
    def test_picks_highest_totals_first(self):
        # row totals: [3, 30, 5, 50, 1]
        values = [[3], [10, 20], [5], [50], [1]]
        assert _rank_top_indices(values, 5, 3) == [3, 1, 2]

    def test_selection_is_non_contiguous(self):
        # The old bug picked the first N alphabetically; ensure we pick by size.
        values = [[100], [1], [99], [2], [98]]
        assert _rank_top_indices(values, 5, 3) == [0, 2, 4]

    def test_ignores_non_numeric_cells(self):
        values = [["", "5", None], ["x", "y"], [10]]
        # row0 = 5, row1 = 0, row2 = 10
        assert _rank_top_indices(values, 3, 2) == [2, 0]

    def test_ties_keep_original_order(self):
        values = [[5], [5], [5]]
        assert _rank_top_indices(values, 3, 3) == [0, 1, 2]

    def test_top_n_larger_than_rows(self):
        values = [[1], [2]]
        assert _rank_top_indices(values, 2, 10) == [1, 0]


class TestTotalRowsReferenceCorrectRows:
    """Regression: TOTAL rows summed list-relative rows, not sheet rows."""

    def test_subcategory_total_uses_sheet_rows(self):
        months = [1, 2]
        start_row = 8  # header row
        rows = _build_subcategory_table(months, REPORT_SUBCATEGORIES, start_row)
        total = rows[-1]
        first = start_row + 1
        last = start_row + len(REPORT_SUBCATEGORIES)
        assert total[1] == f"=SUM(B{first}:B{last})"
        assert total[2] == f"=SUM(C{first}:C{last})"

    def test_parent_total_uses_sheet_rows(self):
        months = [1]
        rows = _build_parent_category_table(months, REPORT_SUBCATEGORIES, 8, 31)
        total = rows[-1]
        num_parents = len(rows) - 2  # minus header, minus total
        assert total[1] == f"=SUM(B32:B{31 + num_parents})"
