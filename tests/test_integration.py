"""End-to-end integration tests — full pipeline from fixtures to reports and trends."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from expense_planner.categorizer import categorize_all
from expense_planner.models import (
    CategorySummary,
    MonthlyReport,
    Transaction,
    TransactionType,
)
from expense_planner.report import generate_report
from expense_planner.trend import generate_trend_report

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# End-to-end: load → categorize → report → verify
# ---------------------------------------------------------------------------


class TestEndToEndSingleMonth:
    """Load fixture JSON, parse, categorize, generate report, verify totals."""

    @pytest.fixture
    def pipeline_report(self, sample_rules_file) -> MonthlyReport:
        """Run the full pipeline from fixture file to MonthlyReport."""
        # 1. Load raw JSON
        raw_data = json.loads((FIXTURES_DIR / "sample_transactions.json").read_text())

        # 2. Parse into Transaction objects, filter splits
        transactions = [Transaction.from_monarch_dict(r) for r in raw_data]
        transactions = [t for t in transactions if not t.is_split_transaction]

        # 3. Categorize
        categorize_all(transactions, sample_rules_file)

        # 4. Generate report
        return generate_report("2026-06", transactions, sample_rules_file)

    def test_income_matches_paychecks_plus_interest(self, pipeline_report):
        """Two paychecks ($5957.92 each) + interest ($0.06)."""
        assert pipeline_report.total_income == Decimal("11915.90")

    def test_expenses_sum(self, pipeline_report):
        """Rent + Groceries + Shopping + Pet Care + Dining."""
        expected = (
            Decimal("3460.00")
            + Decimal("127.43")
            + Decimal("54.99")
            + Decimal("75.00")
            + Decimal("42.50")
        )
        assert pipeline_report.total_expenses == expected

    def test_remittances_sum(self, pipeline_report):
        assert pipeline_report.total_remittances == Decimal("5000.00")

    def test_net_cashflow_formula(self, pipeline_report):
        r = pipeline_report
        assert r.net_cashflow == r.total_income - r.total_expenses - r.total_remittances

    def test_excluded_transactions_stripped(self, pipeline_report):
        for txn in pipeline_report.transactions:
            assert txn.resolved_type != TransactionType.EXCLUDE

    def test_report_has_unknown_category(self, pipeline_report):
        unknown_names = {c.name for c in pipeline_report.unknown_categories}
        assert "Pet Care" in unknown_names

    def test_known_categories_not_unknown(self, pipeline_report):
        unknown_names = {c.name for c in pipeline_report.unknown_categories}
        assert "Housing" not in unknown_names
        assert "Groceries" not in unknown_names

    def test_top_expenses_only_expenses(self, pipeline_report):
        for txn in pipeline_report.top_expenses:
            assert txn.resolved_type == TransactionType.EXPENSE

    def test_expense_categories_sorted(self, pipeline_report):
        amounts = [c.amount for c in pipeline_report.expense_categories]
        assert amounts == sorted(amounts, reverse=True)


# ---------------------------------------------------------------------------
# End-to-end: multiple months → trend report
# ---------------------------------------------------------------------------


class TestEndToEndTrend:
    """Build two monthly reports from slightly different data, run trend analysis."""

    @pytest.fixture
    def two_month_trend(self, sample_rules_file):
        """Create two months of reports and generate a TrendReport."""
        # Load the fixture as "June" data
        raw_data = json.loads((FIXTURES_DIR / "sample_transactions.json").read_text())
        june_txns = [Transaction.from_monarch_dict(r) for r in raw_data]
        june_txns = [t for t in june_txns if not t.is_split_transaction]
        categorize_all(june_txns, sample_rules_file)
        june_report = generate_report("2026-06", june_txns, sample_rules_file)

        # Create a simpler "May" report synthetically
        may_report = MonthlyReport(
            month="2026-05",
            total_income=Decimal("11000"),
            total_expenses=Decimal("4500"),
            total_investments=Decimal("0"),
            total_remittances=Decimal("3000"),
            net_cashflow=Decimal("3500"),
            expense_categories=[
                CategorySummary(name="Housing", amount=Decimal("3460"), count=1),
                CategorySummary(name="Groceries", amount=Decimal("600"), count=5),
                CategorySummary(name="Dining", amount=Decimal("440"), count=8),
            ],
            income_sources=[
                CategorySummary(name="Meta", amount=Decimal("11000"), count=2),
            ],
            investment_categories=[],
            remittance_categories=[
                CategorySummary(name="India Transfer", amount=Decimal("3000"), count=1),
            ],
            unknown_categories=[],
            top_expenses=[],
            transactions=[],
        )

        months = ["2026-05", "2026-06"]
        reports = [may_report, june_report]
        return generate_trend_report(months, reports)

    def test_trend_months(self, two_month_trend):
        assert two_month_trend.months == ["2026-05", "2026-06"]

    def test_income_trend_values(self, two_month_trend):
        t = two_month_trend
        assert t.income_trend["2026-05"] == Decimal("11000")
        assert t.income_trend["2026-06"] == Decimal("11915.90")

    def test_expense_trend_values(self, two_month_trend):
        t = two_month_trend
        assert t.expense_trend["2026-05"] == Decimal("4500")
        assert t.expense_trend["2026-06"] == Decimal("3759.92")

    def test_category_trends_union(self, two_month_trend):
        """All categories from both months should be present."""
        cats = two_month_trend.category_trends
        assert "Housing" in cats
        assert "Groceries" in cats
        assert "Dining" in cats
        assert "India Transfer" in cats

    def test_pet_care_only_in_june(self, two_month_trend):
        """Pet Care is only in June data; May should be zero-filled."""
        cats = two_month_trend.category_trends
        assert "Pet Care" in cats
        assert cats["Pet Care"]["2026-05"] == Decimal("0")
        assert cats["Pet Care"]["2026-06"] == Decimal("75.00")

    def test_shopping_only_in_june(self, two_month_trend):
        cats = two_month_trend.category_trends
        assert "Shopping" in cats
        assert cats["Shopping"]["2026-05"] == Decimal("0")
        assert cats["Shopping"]["2026-06"] == Decimal("54.99")

    def test_net_trend_structure(self, two_month_trend):
        t = two_month_trend
        for month in t.months:
            assert month in t.net_trend

    def test_all_category_months_filled(self, two_month_trend):
        """Every category should have a value for every month (no KeyErrors)."""
        t = two_month_trend
        for cat_name, month_map in t.category_trends.items():
            for month in t.months:
                assert month in month_map, f"{cat_name} missing {month}"
