"""Shared pytest fixtures for expense-planner tests."""

import json
from pathlib import Path

import pytest

from expense_planner.categorizer import categorize_all
from expense_planner.models import Transaction

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_raw_data() -> list[dict]:
    """Load raw Monarch API response fixture."""
    path = FIXTURES_DIR / "sample_transactions.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def sample_transactions(sample_raw_data) -> list[Transaction]:
    """Parse raw data into Transaction objects, filtering out splits."""
    all_txns = [Transaction.from_monarch_dict(raw) for raw in sample_raw_data]
    # Filter split transactions at parse time (as the real pipeline does)
    return [t for t in all_txns if not t.is_split_transaction]


@pytest.fixture
def sample_rules_file() -> str:
    """Path to test rules YAML."""
    return str(FIXTURES_DIR / "test_rules.yaml")


@pytest.fixture
def categorized_transactions(sample_transactions, sample_rules_file) -> list[Transaction]:
    """Transactions that have been through categorize_all."""
    return categorize_all(sample_transactions, sample_rules_file)
