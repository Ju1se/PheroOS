"""Frozen v1 compatibility state isolated from the durable authority path.

New integrations must use :class:`GovernanceStateStore`.  This package exists
only so pre-0.2 v1 issuers retain their exact replay/fork behavior during the
declared migration window without scattering process globals across domain
modules.
"""

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
    LegacyAuthorityRegistry,
)


__all__ = ["LEGACY_AUTHORITY_REGISTRY", "LegacyAuthorityRegistry"]
