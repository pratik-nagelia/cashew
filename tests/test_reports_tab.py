"""Tests for expense_planner.reports_tab — table formulas + chart ranking."""

import yaml

from expense_planner.hierarchy import (
    build_subcategory_emoji_map,
    get_subcategories_by_type,
    load_hierarchy,
    load_subcategory_emoji,
)
from expense_planner.reports_tab import (
    _build_parent_category_table,
    _build_subcategory_table,
    _rank_top_indices,
    report_subcategories,
)
from expense_planner.sheets import EXPENSE_END, EXPENSE_START, _col_letter, _month_col_offset

REPORT_SUBCATEGORIES = report_subcategories()


def _write_hierarchy(tmp_path):
    """A small hierarchy whose YAML order is deliberately not alphabetical."""
    path = tmp_path / "h.yaml"
    path.write_text(yaml.safe_dump({
        "hierarchy": {
            "Shopping": {"emoji": "🛍️", "type": "expense", "subcategories": ["Shopping", "Clothing"]},
            "Food": {"emoji": "🍽️", "type": "expense", "subcategories": ["Groceries", "Dining"]},
            "Other": {"emoji": "❓", "type": "expense", "subcategories": ["Uncategorized"]},
            "Income": {"emoji": "💰", "type": "income", "subcategories": ["Paycheck"]},
            "Investment": {"emoji": "📈", "type": "investment", "subcategories": ["Stocks"]},
            "Transfers": {"emoji": "🔁", "type": "exclude", "subcategories": ["Transfer"]},
        },
        "subcategory_emoji": {"Clothing": "👔", "Groceries": "🛒", "Transfer": "🔁"},
    }, sort_keys=False, allow_unicode=True))
    return str(path)


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


class TestReportRowsComeFromTheHierarchy:
    def test_report_subcategories_are_expense_subcategories_in_yaml_order(self, tmp_path):
        hierarchy = load_hierarchy(_write_hierarchy(tmp_path))
        assert report_subcategories(hierarchy) == [
            "Shopping", "Clothing", "Groceries", "Dining", "Uncategorized",
        ]

    def test_exclude_income_investment_get_no_report_row(self, tmp_path):
        hierarchy = load_hierarchy(_write_hierarchy(tmp_path))
        subs = report_subcategories(hierarchy)
        assert not {"Transfer", "Paycheck", "Stocks"} & set(subs)
        rows = _build_parent_category_table([1], subs, 8, 20, hierarchy)
        labels = [r[0] for r in rows[1:-1]]
        assert labels == ["🛍️ Shopping", "🍽️ Food", "❓ Other"]

    def test_real_report_rows_match_real_expense_subcategories(self):
        hierarchy = load_hierarchy()
        assert REPORT_SUBCATEGORIES == get_subcategories_by_type("expense", hierarchy)
        exclude = set(get_subcategories_by_type("exclude", hierarchy))
        assert exclude and not exclude & set(REPORT_SUBCATEGORIES)

    def test_subcategory_rows_sumifs_the_emoji_name_sync_writes(self, tmp_path):
        path = _write_hierarchy(tmp_path)
        hierarchy = load_hierarchy(path)
        emoji_map = build_subcategory_emoji_map(hierarchy, load_subcategory_emoji(path))
        subs = report_subcategories(hierarchy)
        rows = _build_subcategory_table([3], subs, 8, emoji_map)
        # Shopping has no own emoji: it takes its parent's.
        assert [r[0] for r in rows[1:-1]] == [
            "🛍️ Shopping", "👔 Clothing", "🛒 Groceries", "🍽️ Dining", "❓ Uncategorized",
        ]
        amt = _col_letter(_month_col_offset(3) + 3)
        cat = _col_letter(_month_col_offset(3) + 1)
        assert rows[2][1] == (
            f"=SUMIFS('FY-26-Auto'!{amt}{EXPENSE_START}:{amt}{EXPENSE_END},"
            f"'FY-26-Auto'!{cat}{EXPENSE_START}:{cat}{EXPENSE_END},\"👔 Clothing\")"
        )

    def test_parent_rows_sum_their_subcategory_rows_and_unknowns_go_to_other(self, tmp_path):
        hierarchy = load_hierarchy(_write_hierarchy(tmp_path))
        subs = report_subcategories(hierarchy) + ["Pets"]  # not in the hierarchy
        # Subcategory header on row 8 -> data rows 9..14 in `subs` order.
        rows = _build_parent_category_table([1], subs, 8, 20, hierarchy)
        by_label = {r[0]: r[1] for r in rows[1:-1]}
        assert by_label["🛍️ Shopping"] == "=B9+B10"
        assert by_label["🍽️ Food"] == "=B11+B12"
        assert by_label["❓ Other"] == "=B13+B14"
