from pheroos.conformance.checks import runtime_scope_contract


def test_runtime_scope_contract_binds_kernel_driver_governance_and_trace() -> None:
    result = runtime_scope_contract.check()

    assert result.ok is True, result.detail
