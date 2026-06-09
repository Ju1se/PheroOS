from __future__ import annotations

from pheroos.kernel.input_envelope import InputEnvelope
from pheroos.kernel.os_plan import CapabilityResolution, KernelDiagnostic, OSPlan
from pheroos.protocol.models import CapabilityManifest


class OSKernel:
    """Plan available resources without making domain conclusions."""

    def plan(self, envelope: InputEnvelope, capabilities: list[CapabilityManifest]) -> OSPlan:
        resolutions = [
            CapabilityResolution(capability_id=capability.id, available=True)
            for capability in capabilities
        ]
        diagnostics: list[KernelDiagnostic] = []
        if not capabilities:
            diagnostics.append(
                KernelDiagnostic(
                    code="missing_capability",
                    message="No compatible capability was available.",
                    severity="warning",
                )
            )
        return OSPlan(
            tenant_id=envelope.tenant_id,
            request_id=str(envelope.metadata.get("request_id") or "request"),
            capability_resolutions=resolutions,
            diagnostics=diagnostics,
            runtime_ready=bool(capabilities),
            degraded=not capabilities,
        )
