"""The shared category list: loaders and the real rules/category_hierarchy.yaml."""

from datetime import date
from decimal import Decimal

import pytest
import yaml

from expense_planner.categorizer import categorize, load_rules
from expense_planner.hierarchy import (
    HIERARCHY_FILE,
    build_subcategory_emoji_map,
    build_subcategory_to_parent_map,
    get_expense_parents,
    get_fixed_subcategories,
    get_subcategories_by_type,
    load_hierarchy,
    load_subcategory_emoji,
)
from expense_planner.models import Transaction, TransactionType

RULES_FILE = HIERARCHY_FILE.parent / "rules.yaml"


def test_fixed_subcategories_come_from_each_parent_in_order(tmp_path):
    path = tmp_path / "h.yaml"
    path.write_text(yaml.safe_dump({"hierarchy": {
        "Housing": {"type": "expense", "subcategories": ["Rent", "Home Improvement"], "fixed": ["Rent"]},
        "Food": {"type": "expense", "subcategories": ["Groceries"]},
        "Bills": {"type": "expense", "subcategories": ["Electricity"], "fixed": ["Electricity"]},
    }}, sort_keys=False))
    assert get_fixed_subcategories(load_hierarchy(str(path))) == ["Rent", "Electricity"]


def test_subcategory_emoji_is_empty_when_the_file_has_none(tmp_path):
    path = tmp_path / "h.yaml"
    path.write_text(yaml.safe_dump({"hierarchy": {}}))
    assert load_subcategory_emoji(str(path)) == {}


def test_real_hierarchy_is_consistent():
    hierarchy = load_hierarchy()
    parent_of = build_subcategory_to_parent_map(hierarchy)
    names = [s for info in hierarchy.values() for s in info["subcategories"]]
    assert len(names) == len(set(names)), "a subcategory is listed under two parents"
    for parent, info in hierarchy.items():
        assert info["type"] in {"expense", "income", "investment", "exclude"}, parent
        assert set(info.get("fixed", [])) <= set(info["subcategories"]), parent
    emoji = load_subcategory_emoji()
    assert set(emoji) <= set(parent_of), "emoji for a subcategory that doesn't exist"


def test_every_category_the_rules_assign_is_in_the_hierarchy():
    rules = load_rules(str(RULES_FILE))
    parent_of = build_subcategory_to_parent_map(load_hierarchy())
    assigned = {
        rule["assign_category"]
        for section in ("investment_rules", "remittance_rules", "income_rules", "expense_overrides")
        for rule in rules.get(section) or []
    }
    assert assigned - set(parent_of) == set()


def _write(tmp_path, data):
    path = tmp_path / "h.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return str(path)


def test_expense_parents_keep_yaml_order(tmp_path):
    path = _write(tmp_path, {"hierarchy": {
        "Shopping": {"type": "expense", "subcategories": ["Clothing"]},
        "Income": {"type": "income", "subcategories": ["Paycheck"]},
        "Auto": {"type": "expense", "subcategories": ["Gas"]},
        "Transfers": {"type": "exclude", "subcategories": ["Transfer"]},
    }})
    assert get_expense_parents(load_hierarchy(path)) == ["Shopping", "Auto"]


def test_subcategories_by_type_are_in_yaml_order(tmp_path):
    path = _write(tmp_path, {"hierarchy": {
        "Shopping": {"type": "expense", "subcategories": ["Shopping", "Clothing"]},
        "Stocks": {"type": "investment", "subcategories": ["Stocks"]},
        "Auto": {"type": "expense", "subcategories": ["Gas", "Auto Payment"]},
        "Transfers": {"type": "exclude", "subcategories": ["Transfer"]},
    }})
    hierarchy = load_hierarchy(path)
    assert get_subcategories_by_type("expense", hierarchy) == ["Shopping", "Clothing", "Gas", "Auto Payment"]
    assert get_subcategories_by_type("exclude", hierarchy) == ["Transfer"]
    assert get_subcategories_by_type("income", hierarchy) == []


def test_emoji_map_falls_back_to_parent_emoji(tmp_path):
    path = _write(tmp_path, {
        "hierarchy": {
            "Food": {"emoji": "🍽️", "type": "expense", "subcategories": ["Groceries", "Dining"]},
            "Other": {"type": "expense", "subcategories": ["Miscellaneous"]},
        },
        "subcategory_emoji": {"Groceries": "🛒"},
    })
    emoji = build_subcategory_emoji_map(load_hierarchy(path), load_subcategory_emoji(path))
    assert emoji == {"Groceries": "🛒", "Dining": "🍽️", "Miscellaneous": ""}


def test_every_real_subcategory_has_an_emoji():
    emoji = build_subcategory_emoji_map()
    assert all(emoji.values()), [s for s, e in emoji.items() if not e]


# Every category the owner's Monarch account uses (2026-09-27). A name that
# stopped reaching a hierarchy subcategory would be written to FY-26-Auto under
# a label Reports has no row for, and drop out of its totals without a sound.
OWNER_MONARCH_CATEGORIES = [
    "Auto Payment", "Garbage", "Groceries", "Investment", "Loan Repayment", "Medical", "Paychecks", "Rent",
    "Shopping", "Student Loans", "Transfer", "Travel & Vacation", "Uncategorized", "Charity", "Clothing",
    "Credit Card Payment", "Dentist", "Education", "Financial & Legal Services", "Home Improvement",
    "India Transfer", "Interest", "Miscellaneous", "Public Transit", "Restaurants & Bars", "Water",
    "Balance Adjustments", "Coffee Shops", "Entertainment & Recreation", "Financial Fees", "Fitness",
    "Furniture & Housewares", "Gas", "Gas & Electric", "Other Income", "Stocks", "Auto Maintenance",
    "Cash & ATM", "Electronics", "FDs", "Internet & Cable", "Personal", "Insurance", "Parking & Tolls",
    "Phone", "Travel Food", "Taxes", "Taxi & Ride Shares", "Postage & Shipping", "Vape & Nashe",
    "Business Income",
]
EXCLUDED = {"Transfer", "Credit Card Payment", "Balance Adjustments"}


@pytest.mark.parametrize("monarch_name", OWNER_MONARCH_CATEGORIES)
def test_every_owner_monarch_category_lands_on_a_subcategory_of_the_right_type(monarch_name):
    rules = load_rules(str(RULES_FILE))
    hierarchy = load_hierarchy()
    parent_of = build_subcategory_to_parent_map(hierarchy)
    amount = Decimal("100") if monarch_name in {"Paychecks", "Other Income", "Business Income", "Interest"} else Decimal("-25")
    txn = Transaction(
        id="t", date=date(2026, 9, 1), amount=amount, merchant="Some Merchant", category=monarch_name,
        category_id="", account="Checking", account_id="", month="2026-09",
    )
    categorize(txn, rules)
    if monarch_name in EXCLUDED:
        assert txn.resolved_type == TransactionType.EXCLUDE
        return
    assert txn.resolved_category in parent_of, f"{monarch_name} -> {txn.resolved_category}, not in the hierarchy"
    assert hierarchy[parent_of[txn.resolved_category]]["type"] == txn.resolved_type.value
