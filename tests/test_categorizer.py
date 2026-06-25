"""Tests for expense_planner.categorizer — rules engine."""

from copy import deepcopy
from decimal import Decimal

import pytest

from expense_planner.categorizer import (
    _match,
    categorize,
    categorize_all,
    get_known_categories,
    load_rules,
)
from expense_planner.exceptions import ConfigError
from expense_planner.models import Transaction, TransactionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_txn(**overrides) -> Transaction:
    """Create a minimal Transaction with sensible defaults."""
    from datetime import date as dt_date

    defaults = dict(
        id="test",
        date=dt_date(2026, 6, 15),
        amount=Decimal("-100"),
        merchant="TestMerchant",
        category="TestCategory",
        category_id="c_test",
        account="TestAccount",
        account_id="a_test",
        month="2026-06",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


# ---------------------------------------------------------------------------
# load_rules
# ---------------------------------------------------------------------------


class TestLoadRules:
    def test_loads_valid_yaml(self, sample_rules_file):
        rules = load_rules(sample_rules_file)
        assert isinstance(rules, dict)
        assert "exclude_rules" in rules
        assert "income_rules" in rules
        assert "remittance_rules" in rules
        assert "expense_overrides" in rules
        assert "defaults" in rules

    def test_missing_file_raises_config_error(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_rules(str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(":\n  - :\n    - [invalid")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_rules(str(bad))

    def test_non_dict_yaml_raises_config_error(self, tmp_path):
        scalar = tmp_path / "scalar.yaml"
        scalar.write_text("just a string")
        with pytest.raises(ConfigError, match="must be a YAML mapping"):
            load_rules(str(scalar))


# ---------------------------------------------------------------------------
# _match (internal, but critical to test)
# ---------------------------------------------------------------------------


class TestMatch:
    def test_exact_match(self):
        txn = _make_txn(category="Transfer")
        rule = {"match_field": "category", "pattern": "Transfer", "match_mode": "exact"}
        assert _match(txn, rule) is True

    def test_exact_match_case_insensitive(self):
        txn = _make_txn(category="transfer")
        rule = {"match_field": "category", "pattern": "Transfer", "match_mode": "exact"}
        assert _match(txn, rule) is True

    def test_exact_no_match(self):
        txn = _make_txn(category="Transfers")
        rule = {"match_field": "category", "pattern": "Transfer", "match_mode": "exact"}
        assert _match(txn, rule) is False

    def test_contains_match(self):
        txn = _make_txn(category="Credit Card Payment")
        rule = {"match_field": "category", "pattern": "Credit Card", "match_mode": "contains"}
        assert _match(txn, rule) is True

    def test_contains_no_match(self):
        txn = _make_txn(category="Shopping")
        rule = {"match_field": "category", "pattern": "Credit Card", "match_mode": "contains"}
        assert _match(txn, rule) is False

    def test_startswith_match(self):
        txn = _make_txn(merchant="Whole Foods Market")
        rule = {"match_field": "merchant", "pattern": "Whole Foods", "match_mode": "startswith"}
        assert _match(txn, rule) is True

    def test_startswith_no_match(self):
        txn = _make_txn(merchant="Amazon Whole Foods")
        rule = {"match_field": "merchant", "pattern": "Whole Foods", "match_mode": "startswith"}
        assert _match(txn, rule) is False

    def test_default_mode_is_contains(self):
        txn = _make_txn(category="Credit Card Payment")
        rule = {"match_field": "category", "pattern": "Credit Card"}
        # No match_mode specified — defaults to "contains"
        assert _match(txn, rule) is True

    def test_match_on_merchant_field(self):
        txn = _make_txn(merchant="Robinhood")
        rule = {"match_field": "merchant", "pattern": "Robinhood", "match_mode": "exact"}
        assert _match(txn, rule) is True

    def test_match_on_account_field(self):
        txn = _make_txn(account="Chase Checking")
        rule = {"match_field": "account", "pattern": "Chase", "match_mode": "contains"}
        assert _match(txn, rule) is True

    def test_match_on_plaid_name_field(self):
        txn = _make_txn(plaid_name="META PLATFORMS INC")
        rule = {"match_field": "plaid_name", "pattern": "META", "match_mode": "startswith"}
        assert _match(txn, rule) is True

    def test_none_plaid_name_does_not_crash(self):
        txn = _make_txn(plaid_name=None)
        rule = {"match_field": "plaid_name", "pattern": "SOMETHING", "match_mode": "contains"}
        assert _match(txn, rule) is False

    def test_unknown_match_mode_returns_false(self):
        txn = _make_txn(category="Transfer")
        rule = {"match_field": "category", "pattern": "Transfer", "match_mode": "regex"}
        assert _match(txn, rule) is False


# ---------------------------------------------------------------------------
# categorize (single transaction)
# ---------------------------------------------------------------------------


class TestCategorize:
    @pytest.fixture
    def rules(self, sample_rules_file):
        return load_rules(sample_rules_file)

    # Exclude rules
    def test_transfer_excluded(self, rules):
        txn = _make_txn(category="Transfer")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXCLUDE
        assert "transfer" in result.resolved_category.lower()

    def test_credit_card_payment_excluded(self, rules):
        txn = _make_txn(category="Credit Card Payment")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXCLUDE

    def test_credit_card_payment_contains_match(self, rules):
        """The CC rule uses 'contains' mode — partial match should work."""
        txn = _make_txn(category="Auto Credit Card Payment")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXCLUDE

    # hide_from_reports
    def test_hidden_transaction_excluded(self, rules):
        txn = _make_txn(hide_from_reports=True)
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXCLUDE
        assert result.resolved_category == "Hidden"

    # Remittance rules
    def test_india_transfer_remittance(self, rules):
        txn = _make_txn(category="India Transfer", amount=Decimal("-3000"))
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.REMITTANCE
        assert result.resolved_category == "India Transfer"

    # Income rules
    def test_paychecks_income(self, rules):
        txn = _make_txn(category="Paychecks", merchant="Meta", amount=Decimal("5957.92"))
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.INCOME
        # Income uses merchant as resolved_category
        assert result.resolved_category == "Meta"

    def test_interest_income(self, rules):
        txn = _make_txn(category="Interest", merchant="Marcus", amount=Decimal("0.06"))
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.INCOME
        assert result.resolved_category == "Marcus"

    def test_other_income(self, rules):
        txn = _make_txn(category="Other Income", merchant="Side Gig")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.INCOME

    def test_business_income(self, rules):
        txn = _make_txn(category="Business Income", merchant="Consulting LLC")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.INCOME

    # Expense overrides
    def test_rent_mapped_to_housing(self, rules):
        txn = _make_txn(category="Rent", amount=Decimal("-3460"))
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Housing"

    def test_restaurants_mapped_to_dining(self, rules):
        txn = _make_txn(category="Restaurants & Bars")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Dining"

    def test_groceries_keeps_name(self, rules):
        txn = _make_txn(category="Groceries")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Groceries"

    def test_shopping_keeps_name(self, rules):
        txn = _make_txn(category="Shopping")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Shopping"

    def test_insurance_contains_match(self, rules):
        """Insurance rule uses 'contains' — should match 'Auto Insurance'."""
        txn = _make_txn(category="Auto Insurance")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Insurance"

    def test_fitness_mapped_to_health(self, rules):
        txn = _make_txn(category="Fitness")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Health"

    def test_gas_mapped_to_auto(self, rules):
        txn = _make_txn(category="Gas")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Auto"

    def test_eva_college_mapped_to_education(self, rules):
        txn = _make_txn(category="Eva College")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Education"

    # Default behavior — unmatched category
    def test_unknown_category_keeps_original(self, rules):
        txn = _make_txn(category="Pet Care")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Pet Care"

    def test_another_unknown_keeps_original(self, rules):
        txn = _make_txn(category="Subscription Boxes")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Subscription Boxes"

    # Rule priority: exclude wins over income
    def test_exclude_takes_priority(self, rules):
        """If both exclude and income could match, exclude wins (checked first)."""
        txn = _make_txn(category="Transfer", merchant="Meta")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXCLUDE

    # Mutates in place
    def test_categorize_returns_same_object(self, rules):
        txn = _make_txn(category="Groceries")
        result = categorize(txn, rules)
        assert result is txn


# ---------------------------------------------------------------------------
# categorize_all
# ---------------------------------------------------------------------------


class TestCategorizeAll:
    def test_processes_entire_list(self, sample_transactions, sample_rules_file):
        result = categorize_all(sample_transactions, sample_rules_file)
        assert len(result) == len(sample_transactions)
        for txn in result:
            assert txn.resolved_type is not None
            assert txn.resolved_category is not None

    def test_returns_same_list(self, sample_transactions, sample_rules_file):
        result = categorize_all(sample_transactions, sample_rules_file)
        assert result is sample_transactions

    def test_fixture_exclude_count(self, categorized_transactions):
        """Fixture has 2 Transfer + 1 CC Payment + 1 hidden = 4 excluded."""
        excluded = [t for t in categorized_transactions if t.resolved_type == TransactionType.EXCLUDE]
        assert len(excluded) == 4

    def test_fixture_income_count(self, categorized_transactions):
        """Fixture has 2 Paychecks + 1 Interest = 3 income."""
        income = [t for t in categorized_transactions if t.resolved_type == TransactionType.INCOME]
        assert len(income) == 3

    def test_fixture_remittance_count(self, categorized_transactions):
        """Fixture has 2 India Transfer = 2 remittances."""
        remit = [t for t in categorized_transactions if t.resolved_type == TransactionType.REMITTANCE]
        assert len(remit) == 2

    def test_fixture_expense_count(self, categorized_transactions):
        """After splits filtered: Rent, Groceries, Shopping, Pet Care, Dining = 5 expenses."""
        expenses = [t for t in categorized_transactions if t.resolved_type == TransactionType.EXPENSE]
        assert len(expenses) == 5


# ---------------------------------------------------------------------------
# get_known_categories
# ---------------------------------------------------------------------------


class TestGetKnownCategories:
    def test_returns_set(self, sample_rules_file):
        known = get_known_categories(sample_rules_file)
        assert isinstance(known, set)

    def test_contains_expense_override_categories(self, sample_rules_file):
        known = get_known_categories(sample_rules_file)
        assert "Housing" in known
        assert "Groceries" in known
        assert "Dining" in known
        assert "Shopping" in known
        assert "Insurance" in known
        assert "Health" in known
        assert "Auto" in known
        assert "Education" in known

    def test_contains_remittance_category(self, sample_rules_file):
        known = get_known_categories(sample_rules_file)
        assert "India Transfer" in known

    def test_pet_care_not_known(self, sample_rules_file):
        """Pet Care is not in the rules — should be detected as unknown."""
        known = get_known_categories(sample_rules_file)
        assert "Pet Care" not in known


# ---------------------------------------------------------------------------
# Extensibility — adding a new rule works
# ---------------------------------------------------------------------------


class TestExtensibility:
    def test_adding_new_expense_rule(self, sample_rules_file):
        """Adding a new rule to expense_overrides works without code changes."""
        rules = load_rules(sample_rules_file)
        rules["expense_overrides"].append(
            {
                "match_field": "category",
                "pattern": "Pet Care",
                "match_mode": "exact",
                "assign_category": "Pets",
            }
        )
        txn = _make_txn(category="Pet Care")
        result = categorize(txn, rules)
        assert result.resolved_type == TransactionType.EXPENSE
        assert result.resolved_category == "Pets"

    def test_adding_new_exclude_rule(self, sample_rules_file):
        rules = load_rules(sample_rules_file)
        rules["exclude_rules"].append(
            {
                "match_field": "merchant",
                "pattern": "Venmo",
                "match_mode": "exact",
                "note": "Venmo P2P excluded",
            }
        )
        txn = _make_txn(merchant="Venmo", category="Transfer")
        result = categorize(txn, rules)
        # "Transfer" exact match is first in exclude_rules, should still match
        assert result.resolved_type == TransactionType.EXCLUDE
