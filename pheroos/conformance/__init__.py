"""Static, thread-safe lazy facade for the Conformance public ABI."""

from importlib import import_module as _import_module
from threading import RLock as _RLock
from typing import TYPE_CHECKING, Any as _Any

from pheroos.conformance._public_api import (
    COMPATIBILITY_MODULES as _COMPATIBILITY_MODULES,
    PUBLIC_API as _PUBLIC_API,
)


if TYPE_CHECKING:
    from pheroos.conformance.commit_tck import COMMIT_TCK_ARTIFACT as COMMIT_TCK_ARTIFACT
    from pheroos.conformance.commit_tck import COMMIT_TCK_SCHEMA_ID as COMMIT_TCK_SCHEMA_ID
    from pheroos.conformance.commit_tck import COMMIT_TCK_VERSION as COMMIT_TCK_VERSION
    from pheroos.conformance.report import CONFORMANCE_REPORT_SCHEMA_ID as CONFORMANCE_REPORT_SCHEMA_ID
    from pheroos.conformance.report import CONFORMANCE_REPORT_VERSION as CONFORMANCE_REPORT_VERSION
    from pheroos.conformance.report import CheckResult as CheckResult
    from pheroos.conformance.commit_tck import CommitTckAdapter as CommitTckAdapter
    from pheroos.conformance.commit_tck import CommitTckReport as CommitTckReport
    from pheroos.conformance.commit_tck import CommitTckResult as CommitTckResult
    from pheroos.conformance.commit_tck import CommitTckVector as CommitTckVector
    from pheroos.conformance.report import ConformanceReport as ConformanceReport
    from pheroos.conformance.profile import ConformanceProfile as ConformanceProfile
    from pheroos.conformance.report import ConformanceSubjectKind as ConformanceSubjectKind
    from pheroos.conformance.checks.authority_ledger_contract import (
        GOVERNANCE_STATE_STORE_FAILURE_STAGES as GOVERNANCE_STATE_STORE_FAILURE_STAGES,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION as GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        GovernanceStateStoreConformanceAdapter as GovernanceStateStoreConformanceAdapter,
    )
    from pheroos.conformance.report import PHEROOS_IMPLEMENTATION_ID as PHEROOS_IMPLEMENTATION_ID
    from pheroos.conformance.commit_tck import ReferenceCommitTckAdapter as ReferenceCommitTckAdapter
    from pheroos.conformance.checks.authority_ledger_contract import (
        ReferenceGovernanceStateStoreConformanceAdapter as ReferenceGovernanceStateStoreConformanceAdapter,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        ReferenceTraceStoreConformanceAdapter as ReferenceTraceStoreConformanceAdapter,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        TRACE_STORE_CONFORMANCE_VERSION as TRACE_STORE_CONFORMANCE_VERSION,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        TraceStoreConformanceAdapter as TraceStoreConformanceAdapter,
    )
    from pheroos.conformance.commit_tck import commit_tck_artifact_root as commit_tck_artifact_root
    from pheroos.conformance.commit_tck import commit_tck_schema as commit_tck_schema
    from pheroos.conformance.report import conformance_report_schema as conformance_report_schema
    from pheroos.conformance.commit_tck import load_commit_tck_vectors as load_commit_tck_vectors
    from pheroos.conformance.profile import profile_for_manifest as profile_for_manifest
    from pheroos.conformance.commit_tck import run_commit_tck as run_commit_tck
    from pheroos.conformance.runner import run_conformance as run_conformance
    from pheroos.conformance.checks.authority_ledger_contract import (
        run_governance_state_store_conformance as run_governance_state_store_conformance,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        run_trace_store_conformance as run_trace_store_conformance,
    )
    from pheroos.conformance.runner import run_source_conformance as run_source_conformance
    from pheroos.conformance.runner import validate_manifest as validate_manifest

del TYPE_CHECKING

__all__ = list(_PUBLIC_API)

_PUBLIC_API_LOCK = _RLock()


def __getattr__(name: str) -> _Any:
    target = _PUBLIC_API.get(name)
    compatibility_module = _COMPATIBILITY_MODULES.get(name)
    if target is None and compatibility_module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _PUBLIC_API_LOCK:
        if name in globals():
            return globals()[name]
        if target is not None:
            module_name, attribute = target
            value = getattr(_import_module(module_name), attribute)
        else:
            value = _import_module(compatibility_module)
        globals()[name] = value
        return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_PUBLIC_API) | set(_COMPATIBILITY_MODULES))
