from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.kernel import capability_resolution as resolution
from pheroos.kernel.run_scope import RUNTIME_SCOPE_VERSION, RuntimeScope


def test_connection_diagnostics_distinguish_ambiguity_and_detail() -> None:
    assert resolution._connection_problem(
        "connection:one",
        connections={},
        ambiguous_connections={"connection:one"},
    ) == (
        "connection_readiness_ambiguous",
        "Connection connection:one has conflicting readiness snapshots.",
        "error",
    )
    unavailable = resolution._connection_problem(
        "connection:one",
        connections={
            "connection:one": cast(
                Any,
                SimpleNamespace(available=False, detail="offline"),
            )
        },
        ambiguous_connections=set(),
    )
    assert unavailable == (
        "connection_unavailable",
        "Connection connection:one is unavailable: offline",
        "warning",
    )


def test_driver_diagnostics_cover_missing_identity_ambiguity_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = SimpleNamespace(id="capability:test")
    driver = SimpleNamespace(version="1", capabilities=())
    monkeypatch.setattr(resolution, "driver_spec_id", lambda _driver: "")
    exposure, problem = resolution._driver_exposure_or_problem(
        cast(Any, capability),
        cast(Any, driver),
        probes={},
        ambiguous_probes=set(),
    )
    assert exposure is None
    assert problem is not None and problem[0] == "driver_identity_missing"

    ambiguous = resolution._driver_probe_problem(
        cast(Any, driver),
        driver_id="driver:one",
        permissions=("invoke",),
        probes={},
        ambiguous_probes={"driver:one"},
    )
    assert ambiguous is not None and ambiguous[0] == "driver_probe_ambiguous"

    unavailable = resolution._driver_probe_problem(
        cast(Any, driver),
        driver_id="driver:one",
        permissions=("invoke",),
        probes={
            "driver:one": cast(
                Any,
                SimpleNamespace(
                    available=False,
                    detail="probe failed",
                    version="1",
                    capabilities=(),
                ),
            )
        },
        ambiguous_probes=set(),
    )
    assert unavailable == (
        "driver_probe_unavailable",
        "Driver driver:one is unavailable: probe failed",
        "warning",
    )


def test_manifest_warning_is_not_promoted_to_a_failure() -> None:
    diagnostics: list[object] = []
    capability_id, failures = resolution._record_manifest_diagnostics(
        SimpleNamespace(id="capability:test"),
        (
            cast(
                Any,
                SimpleNamespace(level="warning", code="warning", message="warning"),
            ),
        ),
        cast(Any, diagnostics),
    )
    assert capability_id == "<unsupported>"
    assert failures == []
    assert diagnostics == []


def test_runtime_scope_portable_guards_are_total() -> None:
    scope = RuntimeScope("tenant", "run", "request")
    object.__setattr__(scope, "scope_ref", "scope:substituted")
    with pytest.raises(ValueError, match="does not match"):
        scope.to_dict()

    with pytest.raises(ValueError, match="must be a mapping"):
        RuntimeScope.from_dict([])  # type: ignore[arg-type]

    payload: dict[str, object] = {
        "scope_version": RUNTIME_SCOPE_VERSION,
        "tenant_id": "tenant",
        "run_id": "run",
        "request_id": "request",
        "scope_ref": 1,
    }
    with pytest.raises(ValueError, match="must be a string"):
        RuntimeScope.from_dict(payload)
