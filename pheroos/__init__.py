"""PheroOS public package boundary.

The current reference runtime still lives under `runtime/`. This package
exposes stable protocol, driver, and CLI surfaces without forcing an import-path
migration.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
