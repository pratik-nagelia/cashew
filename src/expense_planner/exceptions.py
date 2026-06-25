"""Custom exceptions for clear error messages."""


class ConfigError(Exception):
    """Missing .env, bad rules YAML, or invalid configuration."""


class MonarchAuthError(Exception):
    """Login or session failures with Monarch Money."""


class DataError(Exception):
    """No cached data, empty month, or data format issues."""
