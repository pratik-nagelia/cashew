"""The shared category list: loaders and the real rules/category_hierarchy.yaml."""

import yaml

from expense_planner.categorizer import load_rules
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
