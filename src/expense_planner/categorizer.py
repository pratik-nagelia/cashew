"""Rules-based transaction categorizer."""

from pathlib import Path
from typing import Optional

import yaml

from .exceptions import ConfigError
from .hierarchy import load_hierarchy
from .models import Transaction, TransactionType

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


def load_rules(rules_file: Optional[str] = None) -> dict:
    """Load categorization rules from YAML.

    Args:
        rules_file: Path to rules YAML. Defaults to rules/rules.yaml.

    Returns:
        Parsed rules dict with sections: exclude_rules, remittance_rules,
        income_rules, expense_overrides, defaults.
    """
    if rules_file is None:
        rules_file = str(RULES_DIR / "rules.yaml")

    path = Path(rules_file)
    if not path.exists():
        raise ConfigError(f"Rules file not found: {rules_file}")

    try:
        with open(path) as f:
            rules = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {rules_file}: {e}") from e

    if not isinstance(rules, dict):
        raise ConfigError(f"Rules file must be a YAML mapping, got {type(rules).__name__}")

    return rules


def _get_field_value(txn: Transaction, field_name: str) -> str:
    """Get the value of a match field from a transaction."""
    field_map = {
        "merchant": txn.merchant,
        "category": txn.category,
        "account": txn.account,
        "plaid_name": txn.plaid_name or "",
    }
    return field_map.get(field_name, "")


def _match(txn: Transaction, rule: dict) -> bool:
    """Check if a transaction matches a single rule."""
    field_name = rule.get("match_field", "")
    value = _get_field_value(txn, field_name)
    pattern = rule.get("pattern", "")
    mode = rule.get("match_mode", "contains")

    if mode == "exact":
        return value.lower() == pattern.lower()
    elif mode == "startswith":
        return value.lower().startswith(pattern.lower())
    elif mode == "contains":
        return pattern.lower() in value.lower()
    return False


def _check_rules(txn: Transaction, rules_list: list[dict]) -> Optional[dict]:
    """Check a transaction against a list of rules. Returns first matching rule or None."""
    for rule in rules_list:
        if _match(txn, rule):
            return rule
    return None


def categorize(txn: Transaction, rules: dict) -> Transaction:
    """Apply rules to a single transaction, setting resolved_type and resolved_category.

    Evaluation order: hidden → investment → exclude → remittance → income → expense override → default.
    First match wins within each section. Mutates and returns the transaction.
    """
    # Step 1: Skip transactions hidden from reports
    if txn.hide_from_reports:
        txn.resolved_type = TransactionType.EXCLUDE
        txn.resolved_category = "Hidden"
        return txn

    # Step 2: Check investment rules (before excludes — investment transfers
    # like Robinhood are categorized as "Transfer" in Monarch but are real
    # outflows we want to track, not internal moves to exclude)
    rule = _check_rules(txn, rules.get("investment_rules", []))
    if rule:
        txn.resolved_type = TransactionType.INVESTMENT
        txn.resolved_category = rule.get("assign_category", txn.category)
        return txn

    # Step 3: Check exclude rules
    rule = _check_rules(txn, rules.get("exclude_rules", []))
    if rule:
        txn.resolved_type = TransactionType.EXCLUDE
        # assign_category files the row under a category (card payments ->
        # Transfer) for tools that list excluded rows; else the rule's note.
        txn.resolved_category = rule.get("assign_category") or rule.get("note", "Excluded")
        return txn

    # Step 4: Check remittance rules
    rule = _check_rules(txn, rules.get("remittance_rules", []))
    if rule:
        txn.resolved_type = TransactionType.REMITTANCE
        txn.resolved_category = rule.get("assign_category", txn.category)
        return txn

    # Step 5: Check income rules
    rule = _check_rules(txn, rules.get("income_rules", []))
    if rule:
        txn.resolved_type = TransactionType.INCOME
        txn.resolved_category = rule.get("assign_category", txn.category)
        return txn

    # Step 6: Check expense overrides
    rule = _check_rules(txn, rules.get("expense_overrides", []))
    if rule:
        txn.resolved_type = TransactionType.EXPENSE
        txn.resolved_category = rule.get("assign_category", txn.category)
        return txn

    # Step 7: Default — expense with original category
    txn.resolved_type = TransactionType.EXPENSE
    defaults = rules.get("defaults", {})
    behavior = defaults.get("unmatched_category_behavior", "keep_original")
    if behavior == "keep_original":
        txn.resolved_category = txn.category
    else:
        txn.resolved_category = "Uncategorized"
    return txn


def categorize_all(
    transactions: list[Transaction], rules_file: Optional[str] = None
) -> list[Transaction]:
    """Categorize all transactions using rules from YAML.

    Args:
        transactions: List of Transaction objects to categorize.
        rules_file: Optional path to rules YAML.

    Returns:
        The same list with resolved_type and resolved_category set on each.
    """
    rules = load_rules(rules_file)
    for txn in transactions:
        categorize(txn, rules)
    return transactions


def get_known_categories(rules_file: Optional[str] = None) -> set[str]:
    """Categories that need no new rule: every subcategory in the hierarchy
    (a Monarch name equal to one is kept as is) plus every rule target.

    The hierarchy is the category_hierarchy.yaml next to the rules file, or
    the default one. Used to detect 'unknown' categories.
    """
    rules = load_rules(rules_file)
    known = set()
    for section in ["expense_overrides", "income_rules", "investment_rules", "remittance_rules", "exclude_rules"]:
        for rule in rules.get(section) or []:
            cat = rule.get("assign_category")
            if cat:
                known.add(cat)

    sibling = Path(rules_file).parent / "category_hierarchy.yaml" if rules_file else None
    hierarchy = load_hierarchy(str(sibling) if sibling and sibling.exists() else None)
    for info in hierarchy.values():
        known.update(info.get("subcategories", []))
    return known
