from pathlib import Path

from pheroos.conformance.checks.domain_neutrality import check_public_core


def test_public_core_domain_neutrality_guard_passes() -> None:
    result = check_public_core(Path(__file__).resolve().parents[2])

    assert result.ok is True, result.detail
