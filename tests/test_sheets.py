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
        # Per layout spec: investments sit directly below the expense block
        # with 20 slots, income below that.
        assert INVEST_LABEL == EXPENSE_END + 1
        assert (INVEST_END - INVEST_START + 1) == 20
        assert INCOME_LABEL == INVEST_END + 1

    def test_capacities_cover_observed_maxima(self):
        # Observed maxima (Jan-Sep 2026): expenses 185 (Aug, the travel month),
        # income 7, investments 17
        assert (EXPENSE_END - EXPENSE_START + 1) >= 185
        assert (INCOME_END - INCOME_START + 1) >= 7
        assert (INVEST_END - INVEST_START + 1) >= 17

    def test_total_rows_covers_all_sections(self):
        assert sheets.TOTAL_ROWS >= INVEST_END
        assert sheets.TOTAL_ROWS >= INCOME_END


class TestCategoriesComeFromTheHierarchy:
    """Dropdowns and emoji names are derived from category_hierarchy.yaml."""

    @staticmethod
    def _hierarchy(tmp_path):
        import yaml

        from expense_planner.hierarchy import load_hierarchy, load_subcategory_emoji

        path = tmp_path / "h.yaml"
        path.write_text(yaml.safe_dump({
            "hierarchy": {
                "Travel": {"emoji": "✈️", "type": "expense", "subcategories": ["Travel", "Charity"]},
                "Food": {"emoji": "🍽️", "type": "expense", "subcategories": ["Groceries"]},
                "Income": {"emoji": "💰", "type": "income", "subcategories": ["Paycheck", "Business Income"]},
                "Investment": {"emoji": "📈", "type": "investment", "subcategories": ["Stocks", "FDs"]},
                "Transfers": {"emoji": "🔁", "type": "exclude", "subcategories": ["Transfer"]},
            },
            "subcategory_emoji": {"Groceries": "🛒", "Stocks": "📊", "Transfer": "🔁"},
        }, sort_keys=False, allow_unicode=True))
        return load_hierarchy(str(path)), load_subcategory_emoji(str(path))

    def test_dropdowns_are_per_type_in_yaml_order(self, tmp_path):
        from expense_planner.hierarchy import build_subcategory_emoji_map

        hierarchy, sub_emoji = self._hierarchy(tmp_path)
        emoji_map = build_subcategory_emoji_map(hierarchy, sub_emoji)
        assert sheets.dropdown_categories(hierarchy, emoji_map) == {
            "expense": ["✈️ Travel", "✈️ Charity", "🛒 Groceries"],
            "income": ["💰 Paycheck", "💰 Business Income"],
            "investment": ["📊 Stocks", "📈 FDs"],
        }

    def test_exclude_parents_are_in_no_dropdown(self, tmp_path):
        hierarchy, _ = self._hierarchy(tmp_path)
        values = [v for vs in sheets.dropdown_categories(hierarchy).values() for v in vs]
        assert not any("Transfer" in v for v in values)

    def test_subcategory_without_emoji_uses_its_parents(self, tmp_path):
        from expense_planner.hierarchy import build_subcategory_emoji_map

        hierarchy, sub_emoji = self._hierarchy(tmp_path)
        emoji_map = build_subcategory_emoji_map(hierarchy, sub_emoji)
        assert sheets._emoji_category("Charity", emoji_map) == "✈️ Charity"
        assert sheets._emoji_category("Groceries", emoji_map) == "🛒 Groceries"

    def test_unknown_category_stays_plain(self):
        assert sheets._emoji_category("Pets", {}) == "Pets"
        assert sheets._emoji_category("Pets") == "Pets"

    def test_every_real_subcategory_gets_an_emoji_prefix(self):
        from expense_planner.hierarchy import load_hierarchy

        for info in load_hierarchy().values():
            for sub in info["subcategories"]:
                name = sheets._emoji_category(sub)
                assert name != sub and name.endswith(f" {sub}"), sub

    def test_every_category_the_real_rules_assign_gets_an_emoji(self):
        from expense_planner.categorizer import load_rules
        from expense_planner.hierarchy import HIERARCHY_FILE

        rules = load_rules(str(HIERARCHY_FILE.parent / "rules.yaml"))
        for section in ("investment_rules", "income_rules", "expense_overrides"):
            for rule in rules.get(section) or []:
                cat = rule["assign_category"]
                assert sheets._emoji_category(cat) != cat, (section, cat)

    def test_real_dropdowns_match_real_hierarchy_by_type(self):
        from expense_planner.hierarchy import get_subcategories_by_type, load_hierarchy

        hierarchy = load_hierarchy()
        dropdowns = sheets.dropdown_categories()
        for section in ("expense", "income", "investment"):
            plain = [v.split(" ", 1)[1] for v in dropdowns[section]]
            assert plain == get_subcategories_by_type(section, hierarchy)
