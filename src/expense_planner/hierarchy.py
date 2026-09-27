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
    """Return parent category names where type=expense, in YAML order.

    The YAML order is the intended display order (it mirrors Monarch's groups).
    """
    if hierarchy is None:
        hierarchy = load_hierarchy()

    return [
        name for name, info in hierarchy.items()
        if info.get("type") == "expense"
    ]


def get_subcategories_by_type(parent_type: str, hierarchy: Optional[dict] = None) -> list[str]:
    """Subcategories of every parent with this type (expense | income | investment | exclude).

    YAML order: parents in file order, each parent's subcategories in its listed order.
    """
    if hierarchy is None:
        hierarchy = load_hierarchy()

    return [
        sub
        for info in hierarchy.values()
        if info.get("type") == parent_type
        for sub in info.get("subcategories", [])
    ]


def load_subcategory_emoji(hierarchy_file: Optional[str] = None) -> dict[str, str]:
    """Per-subcategory emoji from the hierarchy YAML ({} when it has none)."""
    path = Path(hierarchy_file) if hierarchy_file else HIERARCHY_FILE
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("subcategory_emoji") or {}


CONTROL_LEVELS = ("fixed", "essential", "controllable")


def load_control(hierarchy_file: Optional[str] = None) -> dict[str, str]:
    """How much say the owner has over each expense subcategory:
    {subcategory: fixed | essential | controllable} ({} when the file has none)."""
    path = Path(hierarchy_file) if hierarchy_file else HIERARCHY_FILE
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("control") or {}


def build_subcategory_emoji_map(
    hierarchy: Optional[dict] = None, subcategory_emoji: Optional[dict[str, str]] = None
) -> dict[str, str]:
    """{subcategory: emoji} for every subcategory in the hierarchy.

    Uses the subcategory's own emoji from `subcategory_emoji:` when it has one,
    otherwise its parent's emoji ("" when neither has one). Arguments default to
    the real rules/category_hierarchy.yaml.
    """
    if hierarchy is None:
        hierarchy = load_hierarchy()
    if subcategory_emoji is None:
        subcategory_emoji = load_subcategory_emoji()

    emoji_map = {}
    for info in hierarchy.values():
        for sub in info.get("subcategories", []):
            emoji_map[sub] = subcategory_emoji.get(sub) or info.get("emoji", "")
    return emoji_map
