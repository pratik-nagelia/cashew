"""Tests for expense_planner.models — data classes and parsing."""

from datetime import date
from decimal import Decimal

import pytest

from expense_planner.models import (
    CategorySummary,
    MonthlyReport,
    Transaction,
    TransactionType,
)


# ---------------------------------------------------------------------------
# TransactionType enum
# ---------------------------------------------------------------------------


class TestTransactionType:
    def test_enum_values(self):
        assert TransactionType.INCOME.value == "income"
        assert TransactionType.EXPENSE.value == "expense"
        assert TransactionType.REMITTANCE.value == "remittance"
        assert TransactionType.TRANSFER.value == "transfer"
        assert TransactionType.EXCLUDE.value == "exclude"

    def test_enum_member_count(self):
        assert len(TransactionType) == 6


# ---------------------------------------------------------------------------
# Transaction.from_monarch_dict
# ---------------------------------------------------------------------------


class TestTransactionFromMonarchDict:
    """Test the single translation point from Monarch JSON to Transaction."""

    @pytest.fixture
    def paycheck_raw(self) -> dict:
        return {
            "id": "txn_001",
            "date": "2026-06-15",
            "amount": 5957.92,
            "merchant": {"name": "Meta", "id": "m1"},
            "category": {"name": "Paychecks", "id": "c1"},
            "account": {"displayName": "Chase Checking", "id": "a1"},
            "pending": False,
            "isRecurring": True,
            "hideFromReports": False,
            "plaidName": "META PLATFORMS INC",
            "tags": [{"name": "salary"}],
            "notes": None,
            "isSplitTransaction": False,
            "needsReview": False,
        }

    def test_basic_fields(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.id == "txn_001"
        assert txn.merchant == "Meta"
        assert txn.category == "Paychecks"
        assert txn.category_id == "c1"
        assert txn.account == "Chase Checking"
        assert txn.account_id == "a1"
        assert txn.plaid_name == "META PLATFORMS INC"
        assert txn.is_recurring is True
        assert txn.pending is False
        assert txn.hide_from_reports is False
        assert txn.is_split_transaction is False
        assert txn.needs_review is False
        assert txn.notes is None

    def test_date_parsing(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.date == date(2026, 6, 15)

    def test_month_derived_from_date(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.month == "2026-06"

    def test_month_january(self):
        raw = {
            "id": "x",
            "date": "2026-01-03",
            "amount": 100,
            "merchant": {"name": "A", "id": "m"},
            "category": {"name": "B", "id": "c"},
            "account": {"displayName": "C", "id": "a"},
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.month == "2026-01"

    def test_amount_is_decimal(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert isinstance(txn.amount, Decimal)

    def test_amount_precision(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.amount == Decimal("5957.92")

    def test_negative_amount_preserved(self):
        raw = {
            "id": "x",
            "date": "2026-06-01",
            "amount": -3460.00,
            "merchant": {"name": "Landlord", "id": "m"},
            "category": {"name": "Rent", "id": "c"},
            "account": {"displayName": "Checking", "id": "a"},
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.amount == Decimal("-3460.0")
        assert txn.amount < 0

    def test_tags_parsed(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.tags == ["salary"]

    def test_empty_tags(self):
        raw = {
            "id": "x",
            "date": "2026-06-01",
            "amount": 10,
            "merchant": {"name": "A", "id": "m"},
            "category": {"name": "B", "id": "c"},
            "account": {"displayName": "C", "id": "a"},
            "tags": [],
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.tags == []

    def test_none_tags_becomes_empty_list(self):
        raw = {
            "id": "x",
            "date": "2026-06-01",
            "amount": 10,
            "merchant": {"name": "A", "id": "m"},
            "category": {"name": "B", "id": "c"},
            "account": {"displayName": "C", "id": "a"},
            "tags": None,
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.tags == []

    def test_missing_merchant_defaults_to_unknown(self):
        raw = {
            "id": "x",
            "date": "2026-06-01",
            "amount": 10,
            "merchant": None,
            "category": {"name": "B", "id": "c"},
            "account": {"displayName": "C", "id": "a"},
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.merchant == "Unknown"

    def test_missing_category_defaults_to_uncategorized(self):
        raw = {
            "id": "x",
            "date": "2026-06-01",
            "amount": 10,
            "merchant": {"name": "A", "id": "m"},
            "category": None,
            "account": {"displayName": "C", "id": "a"},
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.category == "Uncategorized"

    def test_resolved_fields_default_none(self, paycheck_raw):
        txn = Transaction.from_monarch_dict(paycheck_raw)
        assert txn.resolved_type is None
        assert txn.resolved_category is None

    def test_hide_from_reports_flag(self):
        raw = {
            "id": "x",
            "date": "2026-06-14",
            "amount": -200,
            "merchant": {"name": "Store", "id": "m"},
            "category": {"name": "Shopping", "id": "c"},
            "account": {"displayName": "Amex", "id": "a"},
            "hideFromReports": True,
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.hide_from_reports is True

    def test_split_transaction_flag(self):
        raw = {
            "id": "x",
            "date": "2026-06-16",
            "amount": -89.50,
            "merchant": {"name": "TJ", "id": "m"},
            "category": {"name": "Groceries", "id": "c"},
            "account": {"displayName": "Amex", "id": "a"},
            "isSplitTransaction": True,
        }
        txn = Transaction.from_monarch_dict(raw)
        assert txn.is_split_transaction is True


# ---------------------------------------------------------------------------
# CategorySummary
# ---------------------------------------------------------------------------


class TestCategorySummary:
    def test_creation(self):
        cs = CategorySummary(name="Housing", amount=Decimal("3460.00"), count=1)
        assert cs.name == "Housing"
        assert cs.amount == Decimal("3460.00")
        assert cs.count == 1

    def test_zero_count(self):
        cs = CategorySummary(name="Empty", amount=Decimal("0"), count=0)
        assert cs.count == 0
        assert cs.amount == Decimal("0")


# ---------------------------------------------------------------------------
# Fixture-based parsing
# ---------------------------------------------------------------------------


class TestFixtureParsing:
    def test_total_raw_count(self, sample_raw_data):
        """Fixture has 15 total transactions."""
        assert len(sample_raw_data) == 15

    def test_split_filtered_out(self, sample_raw_data, sample_transactions):
        """Split transactions should be filtered at parse time."""
        split_count = sum(1 for r in sample_raw_data if r.get("isSplitTransaction"))
        assert split_count == 1
        assert len(sample_transactions) == len(sample_raw_data) - split_count

    def test_all_have_month(self, sample_transactions):
        for txn in sample_transactions:
            assert txn.month == "2026-06"
