"""Compatibility facade for lifecycle-scoped governance implementations."""

from __future__ import annotations

# The private owner modules deliberately preserve the historical public
# ``__module__`` value for pickle and annotation compatibility.  These imports
# provide that public annotation namespace; wildcard imports are constrained by
# each owner module's explicit ``__all__`` contract.
# ruff: noqa: F401,F403
import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    effective_pheromone_scored_subject_types,
    is_scored_pheromone_subject_type,
)
from pheroos.trace._pheromone_receipts import canonical_pheromone_clip_payload

from pheroos.governance._pheromone.diffusion import *
from pheroos.governance._pheromone.invariants import *
from pheroos.governance._pheromone.lifecycle import *
from pheroos.governance._pheromone.records import *
from pheroos.governance._pheromone.scoring import *
