"""Category hierarchy — maps subcategories to parent categories for reporting."""

from pathlib import Path
from typing import Optional

import yaml

HIERARCHY_FILE = Path(__file__).parent.parent.parent / "rules" / "category_hierarchy.yaml"


def load_hierarchy(hierarchy_file: Optional[str] = None) -> dict:
    """Load the category hierarchy YAML.

    Returns dict: {parent_name: {emoji, type, subcategories: [...]}}
    """
    path = Path(hierarchy_file) if hierarchy_file else HIERARCHY_FILE
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("hierarchy", {})


def get_parent_category(subcategory: str, hierarchy: Optional[dict] = None) -> str:
    """Look up the parent category for a given subcategory.

    Returns the parent category name, or the subcategory itself if not found.
    """
    if hierarchy is None:
        hierarchy = load_hierarchy()

    for parent, info in hierarchy.items():
        if subcategory in info.get("subcategories", []):
            return parent
    return subcategory  # fallback: use subcategory as its own parent


def get_parent_emoji(parent_category: str, hierarchy: Optional[dict] = None) -> str:
    """Get the emoji for a parent category."""
    if hierarchy is None:
        hierarchy = load_hierarchy()

    info = hierarchy.get(parent_category, {})
    return info.get("emoji", "")


def build_subcategory_to_parent_map(hierarchy: Optional[dict] = None) -> dict[str, str]:
    """Build a flat lookup: subcategory_name → parent_category_name."""
    if hierarchy is None:
        hierarchy = load_hierarchy()

    mapping = {}
    for parent, info in hierarchy.items():
        for sub in info.get("subcategories", []):
            mapping[sub] = parent
    return mapping


def get_expense_parents(hierarchy: Optional[dict] = None) -> list[str]:
    """Return parent category names where type=expense, sorted."""
    if hierarchy is None:
        hierarchy = load_hierarchy()

    return sorted(
        name for name, info in hierarchy.items()
        if info.get("type") == "expense"
    )


def load_subcategory_emoji(hierarchy_file: Optional[str] = None) -> dict[str, str]:
    """Per-subcategory emoji from the hierarchy YAML ({} when it has none)."""
    path = Path(hierarchy_file) if hierarchy_file else HIERARCHY_FILE
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("subcategory_emoji") or {}


def get_fixed_subcategories(hierarchy: Optional[dict] = None) -> list[str]:
    """Subcategories marked fixed (recur every month regardless of choices), in YAML order."""
    if hierarchy is None:
        hierarchy = load_hierarchy()

    return [sub for info in hierarchy.values() for sub in info.get("fixed", [])]
