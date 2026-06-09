from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.output_policy
    ok = (
        not policy.writer_may_create_facts
        and policy.requires_committed_candidate
        and policy.requires_evidence_contract
        and policy.requires_stop_resolution
        and policy.requires_publication_permission
    )
    return CheckResult("output_contract", ok, "" if ok else "output policy grants too much writer authority")
