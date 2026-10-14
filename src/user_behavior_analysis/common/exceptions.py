"""Define explicit project errors for configuration and resource failures."""


class ProjectError(Exception):
    """Represent an expected project operation failure."""


class ConfigurationError(ProjectError, ValueError):
    """Represent an invalid or incomplete project configuration."""


class ResourceError(ProjectError, RuntimeError):
    """Represent an unavailable or inconsistent worker resource budget."""
