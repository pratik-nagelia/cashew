"""Tests for expense_planner.trend — multi-month trend analysis."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from expense_planner.models import CategorySummary, MonthlyReport, Transaction, TransactionType
from expense_planner.trend import compute_months_back, generate_trend_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(
    month: str,
    income: Decimal = Decimal("10000"),
    expenses: Decimal = Decimal("5000"),
    remittances: Decimal = Decimal("2000"),
    expense_cats: list[CategorySummary] | None = None,
    remittance_cats: list[CategorySummary] | None = None,
) -> MonthlyReport:
    """Build a minimal MonthlyReport for trend testing."""
    if expense_cats is None:
        expense_cats = [
            CategorySummary(name="Housing", amount=Decimal("3000"), count=1),
            CategorySummary(name="Groceries", amount=Decimal("1500"), count=4),
            CategorySummary(name="Dining", amount=Decimal("500"), count=3),
        ]
    if remittance_cats is None:
        remittance_cats = [
            CategorySummary(name="India Transfer", amount=remittances, count=2),
        ]

    return MonthlyReport(
        month=month,
        total_income=income,
        total_expenses=expenses,
        total_investments=Decimal("0"),
        total_remittances=remittances,
        net_cashflow=income - expenses - remittances,
        expense_categories=expense_cats,
        income_sources=[CategorySummary(name="Meta", amount=income, count=2)],
        investment_categories=[],
        remittance_categories=remittance_cats,
        unknown_categories=[],
        top_expenses=[],
        transactions=[],
    )


# ---------------------------------------------------------------------------
# generate_trend_report
# ---------------------------------------------------------------------------


class TestGenerateTrendReport:
    @pytest.fixture
    def three_month_reports(self):
        months = ["2026-04", "2026-05", "2026-06"]
        reports = [
            _make_report("2026-04", income=Decimal("10000"), expenses=Decimal("4000"), remittances=Decimal("3000")),
            _make_report("2026-05", income=Decimal("10000"), expenses=Decimal("5500"), remittances=Decimal("2000")),
            _make_report("2026-06", income=Decimal("11000"), expenses=Decimal("6000"), remittances=Decimal("5000")),
        ]
        return months, reports

    def test_months_preserved(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        assert trend.months == ["2026-04", "2026-05", "2026-06"]

    def test_monthly_reports_preserved(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        assert len(trend.monthly_reports) == 3

    def test_income_trend(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        assert trend.income_trend["2026-04"] == Decimal("10000")
        assert trend.income_trend["2026-05"] == Decimal("10000")
        assert trend.income_trend["2026-06"] == Decimal("11000")

    def test_expense_trend(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        assert trend.expense_trend["2026-04"] == Decimal("4000")
        assert trend.expense_trend["2026-05"] == Decimal("5500")
        assert trend.expense_trend["2026-06"] == Decimal("6000")

    def test_remittance_trend(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        assert trend.remittance_trend["2026-04"] == Decimal("3000")
        assert trend.remittance_trend["2026-06"] == Decimal("5000")

    def test_net_trend(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        # net = income - expenses - remittances
        assert trend.net_trend["2026-04"] == Decimal("10000") - Decimal("4000") - Decimal("3000")
        assert trend.net_trend["2026-05"] == Decimal("10000") - Decimal("5500") - Decimal("2000")
        assert trend.net_trend["2026-06"] == Decimal("11000") - Decimal("6000") - Decimal("5000")

    def test_category_trends_includes_all(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        # All 3 expense categories + 1 remittance category present
        assert "Housing" in trend.category_trends
        assert "Groceries" in trend.category_trends
        assert "Dining" in trend.category_trends
        assert "India Transfer" in trend.category_trends

    def test_category_trend_values(self, three_month_reports):
        months, reports = three_month_reports
        trend = generate_trend_report(months, reports)
        housing = trend.category_trends["Housing"]
        # All 3 months have the same Housing data ($3000) in our fixture
        assert housing["2026-04"] == Decimal("3000")
        assert housing["2026-05"] == Decimal("3000")
        assert housing["2026-06"] == Decimal("3000")


class TestMissingCategoryMonths:
    def test_missing_category_fills_zero(self):
        """If a category appears in only some months, missing months get Decimal('0')."""
        months = ["2026-04", "2026-05"]
        reports = [
            _make_report(
                "2026-04",
                expense_cats=[
                    CategorySummary(name="Housing", amount=Decimal("3000"), count=1),
                    CategorySummary(name="Travel", amount=Decimal("800"), count=1),
                ],
            ),
            _make_report(
                "2026-05",
                expense_cats=[
                    CategorySummary(name="Housing", amount=Decimal("3000"), count=1),
                    # No Travel in May
                ],
            ),
        ]
        trend = generate_trend_report(months, reports)
        assert trend.category_trends["Travel"]["2026-04"] == Decimal("800")
        assert trend.category_trends["Travel"]["2026-05"] == Decimal("0")

    def test_new_category_in_later_month(self):
        """A category appearing only in month 2 should have 0 for month 1."""
        months = ["2026-04", "2026-05"]
        reports = [
            _make_report(
                "2026-04",
                expense_cats=[
                    CategorySummary(name="Housing", amount=Decimal("3000"), count=1),
                ],
            ),
            _make_report(
                "2026-05",
                expense_cats=[
                    CategorySummary(name="Housing", amount=Decimal("3000"), count=1),
                    CategorySummary(name="Education", amount=Decimal("1500"), count=1),
                ],
            ),
        ]
        trend = generate_trend_report(months, reports)
        assert trend.category_trends["Education"]["2026-04"] == Decimal("0")
        assert trend.category_trends["Education"]["2026-05"] == Decimal("1500")


class TestSingleMonth:
    def test_single_month_trend(self):
        months = ["2026-06"]
        reports = [_make_report("2026-06")]
        trend = generate_trend_report(months, reports)
        assert trend.months == ["2026-06"]
        assert len(trend.income_trend) == 1
        assert "Housing" in trend.category_trends


# ---------------------------------------------------------------------------
# compute_months_back
# ---------------------------------------------------------------------------


class TestComputeMonthsBack:
    @patch("expense_planner.trend.date")
    def test_three_months_from_june(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 21)
        result = compute_months_back(3)
        assert result == ["2026-04", "2026-05", "2026-06"]

    @patch("expense_planner.trend.date")
    def test_one_month(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 15)
        result = compute_months_back(1)
        assert result == ["2026-06"]

    @patch("expense_planner.trend.date")
    def test_wraps_across_year_boundary(self, mock_date):
        mock_date.today.return_value = date(2026, 2, 10)
        result = compute_months_back(4)
        assert result == ["2025-11", "2025-12", "2026-01", "2026-02"]

    @patch("expense_planner.trend.date")
    def test_twelve_months(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 1)
        result = compute_months_back(12)
        assert len(result) == 12
        assert result[0] == "2025-07"
        assert result[-1] == "2026-06"

    @patch("expense_planner.trend.date")
    def test_january_wraps_properly(self, mock_date):
        mock_date.today.return_value = date(2026, 1, 15)
        result = compute_months_back(3)
        assert result == ["2025-11", "2025-12", "2026-01"]
