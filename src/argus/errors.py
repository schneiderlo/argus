"""Argus-specific exception types."""


class ArgusError(Exception):
    """Base exception for command-line and orchestration failures."""


class ArgusUserError(ArgusError):
    """Raised when the user input or requested artifact path is invalid."""


class ArgusNotImplementedError(ArgusError):
    """Raised when the scaffolded CLI reaches a feature not yet implemented."""
