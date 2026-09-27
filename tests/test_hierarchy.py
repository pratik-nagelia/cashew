"""The shared category list: loaders and the real rules/category_hierarchy.yaml."""

import yaml

from expense_planner.categorizer import load_rules
from expense_planner.hierarchy import (
    HIERARCHY_FILE,
    build_subcategory_to_parent_map,
    get_fixed_subcategories,
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
