from pheroos.conformance.checks import authority_ledger_contract


def test_authority_ledger_contract_proves_provider_neutral_atomic_authority() -> None:
    result = authority_ledger_contract.check()

    assert result.ok is True, result.detail
    assert result.name == "authority_ledger_contract"
    assert result.detail == ""
