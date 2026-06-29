"""Tests for expense_planner.report — deterministic report generation."""

from decimal import Decimal

import pytest

from expense_planner.models import (
    CategorySummary,
    MonthlyReport,
    Transaction,
    TransactionType,
)
from expense_planner.report import generate_report


# ---------------------------------------------------------------------------
# generate_report with fixture data
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Test generate_report using the shared fixture data.

    Fixture transaction summary (14 parsed, split filtered):
      INCOME:     txn_001 (+5957.92), txn_002 (+5957.92) → total_income = 11915.84
      INVESTMENT: txn_003 (+0.06 Interest → FDs)
      EXPENSE:    txn_004 (-3460), txn_005 (-127.43), txn_006 (-54.99),
                  txn_012 (-75.00 Pet Care), txn_015 (-42.50 Dining) → total_expenses = 3759.92
      REMITTANCE: txn_007 (-3000), txn_008 (-2000) → total_remittances = 5000.00
      EXCLUDE:    txn_009 (-2000 Transfer), txn_010 (-1000 Transfer),
                  txn_011 (-450 CC Payment), txn_013 (-200 hidden) → 4 excluded
    """

    @pytest.fixture
    def report(self, categorized_transactions, sample_rules_file) -> MonthlyReport:
        return generate_report("2026-06", categorized_transactions, sample_rules_file)

    def test_total_income(self, report):
        expected = Decimal("5957.92") + Decimal("5957.92")
        assert report.total_income == expected

    def test_total_expenses(self, report):
        expected = (
            Decimal("3460.00")
            + Decimal("127.43")
            + Decimal("54.99")
            + Decimal("75.00")
            + Decimal("42.50")
        )
        assert report.total_expenses == expected

    def test_total_remittances(self, report):
        assert report.total_remittances == Decimal("5000.00")

    def test_net_cashflow(self, report):
        """net_cashflow = income - expenses - investments - remittances."""
        expected = report.total_income - report.total_expenses - report.total_investments - report.total_remittances
        assert report.net_cashflow == expected

    def test_net_cashflow_value(self, report):
        income = Decimal("11915.84")
        expenses = Decimal("3759.92")
        investments = Decimal("-0.06")  # Interest $0.06 inflow → -amount = -0.06
        remittances = Decimal("5000.00")
        assert report.net_cashflow == income - expenses - investments - remittances

    def test_month_label(self, report):
        assert report.month == "2026-06"

    def test_excluded_not_in_transactions(self, report):
        """EXCLUDE transactions should not appear in report.transactions."""
        for txn in report.transactions:
            assert txn.resolved_type != TransactionType.EXCLUDE

    def test_kept_transaction_count(self, report):
        """14 parsed - 4 excluded = 10 kept."""
        assert len(report.transactions) == 10


# ---------------------------------------------------------------------------
# Expense categories
# ---------------------------------------------------------------------------


class TestExpenseCategories:
    @pytest.fixture
    def report(self, categorized_transactions, sample_rules_file) -> MonthlyReport:
        return generate_report("2026-06", categorized_transactions, sample_rules_file)

    def test_sorted_by_amount_descending(self, report):
        amounts = [c.amount for c in report.expense_categories]
        assert amounts == sorted(amounts, reverse=True)

    def test_housing_is_first(self, report):
        """Rent -> Housing ($3460) should be the largest expense category."""
        assert report.expense_categories[0].name == "Housing"
        assert report.expense_categories[0].amount == Decimal("3460.00")

    def test_groceries_present(self, report):
        names = [c.name for c in report.expense_categories]
        assert "Groceries" in names

    def test_category_counts(self, report):
        cat_map = {c.name: c for c in report.expense_categories}
        # Only one Groceries txn (the split was filtered out)
        assert cat_map["Groceries"].count == 1
        assert cat_map["Housing"].count == 1

    def test_unknown_category_detected(self, report):
        """Pet Care is not in rules — should appear in unknown_categories."""
        unknown_names = [c.name for c in report.unknown_categories]
        assert "Pet Care" in unknown_names

    def test_known_categories_not_in_unknown(self, report):
        """Housing, Groceries, etc. should NOT appear in unknown."""
        unknown_names = {c.name for c in report.unknown_categories}
        assert "Housing" not in unknown_names
        assert "Groceries" not in unknown_names
        assert "Shopping" not in unknown_names


# ---------------------------------------------------------------------------
# Income sources
# ---------------------------------------------------------------------------


class TestIncomeSources:
    @pytest.fixture
    def report(self, categorized_transactions, sample_rules_file) -> MonthlyReport:
        return generate_report("2026-06", categorized_transactions, sample_rules_file)

    def test_income_sources_present(self, report):
        names = [s.name for s in report.income_sources]
        assert "Paycheck" in names

    def test_paycheck_income_correct(self, report):
        paycheck = [s for s in report.income_sources if s.name == "Paycheck"][0]
        # _aggregate_by_category uses -t.amount; income amounts are positive,
        # so the aggregated value is negative
        assert paycheck.amount == -(Decimal("5957.92") * 2)
        assert paycheck.count == 2


# ---------------------------------------------------------------------------
# Remittance categories
# ---------------------------------------------------------------------------


class TestRemittanceCategories:
    @pytest.fixture
    def report(self, categorized_transactions, sample_rules_file) -> MonthlyReport:
        return generate_report("2026-06", categorized_transactions, sample_rules_file)

    def test_remittance_categories_present(self, report):
        names = [c.name for c in report.remittance_categories]
        assert "India Transfer" in names

    def test_remittance_total(self, report):
        india = [c for c in report.remittance_categories if c.name == "India Transfer"][0]
        assert india.amount == Decimal("5000.00")
        assert india.count == 2

    def test_remittances_separate_from_expenses(self, report):
        """India Transfer should not appear in expense_categories."""
        expense_names = {c.name for c in report.expense_categories}
        assert "India Transfer" not in expense_names


# ---------------------------------------------------------------------------
# Top 10 expenses
# ---------------------------------------------------------------------------


class TestTopExpenses:
    @pytest.fixture
    def report(self, categorized_transactions, sample_rules_file) -> MonthlyReport:
        return generate_report("2026-06", categorized_transactions, sample_rules_file)

    def test_top_expenses_sorted_by_abs_amount(self, report):
        amounts = [abs(t.amount) for t in report.top_expenses]
        assert amounts == sorted(amounts, reverse=True)

    def test_top_expense_is_rent(self, report):
        assert report.top_expenses[0].merchant == "The Modern Apartments"
        assert abs(report.top_expenses[0].amount) == Decimal("3460.00")

    def test_max_10(self, report):
        assert len(report.top_expenses) <= 10

    def test_only_expense_type(self, report):
        """Top expenses should only contain EXPENSE transactions."""
        for txn in report.top_expenses:
            assert txn.resolved_type == TransactionType.EXPENSE


# ---------------------------------------------------------------------------
# Edge case: empty transaction list
# ---------------------------------------------------------------------------


class TestEmptyReport:
    def test_empty_transactions(self, sample_rules_file):
        report = generate_report("2026-06", [], sample_rules_file)
        assert report.total_income == Decimal("0")
        assert report.total_expenses == Decimal("0")
        assert report.total_remittances == Decimal("0")
        assert report.net_cashflow == Decimal("0")
        assert report.expense_categories == []
        assert report.income_sources == []
        assert report.remittance_categories == []
        assert report.unknown_categories == []
        assert report.top_expenses == []
        assert report.transactions == []
        assert report.month == "2026-06"
