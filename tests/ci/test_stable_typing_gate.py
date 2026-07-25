from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.check_stable_typing import (
    MYPY_VERSION,
    PUBLIC_PACKAGES,
    candidate_failures,
    check_stable_typing,
    load_candidate,
    mypy_command,
    stable_owner_modules,
    stable_owner_paths,
)


ROOT = Path(__file__).resolve().parents[2]


def test_checked_candidate_declares_exact_resolvable_stable_owner_scope() -> None:
    candidate = load_candidate(ROOT)

    assert candidate_failures(candidate) == []
    assert set(candidate["packages"]) == set(PUBLIC_PACKAGES)
    assert len(stable_owner_modules(candidate)) == 28
    assert len(stable_owner_paths(ROOT, candidate)) == 28


def test_stable_typing_command_is_strict_and_traverses_normal_imports() -> None:
    command = mypy_command((Path("pheroos/protocol/models.py"),))

    assert "--strict" in command
    assert "--no-incremental" in command
    assert "--follow-imports=normal" in command
    assert all("follow-imports=skip" not in item for item in command)
    assert all("follow-imports=silent" not in item for item in command)
    assert MYPY_VERSION == "1.18.2"


def test_candidate_integrity_and_owner_scope_fail_closed() -> None:
    candidate = load_candidate(ROOT)
    tampered_root = deepcopy(candidate)
    tampered_root["artifact_version"] = "unreviewed"
    tampered_owner = deepcopy(candidate)
    first_package = tampered_owner["packages"][PUBLIC_PACKAGES[0]]
    first_package["exports"][0]["shape"]["owner"] = "external.owner"

    assert candidate_failures(tampered_root)
    assert candidate_failures(tampered_owner)


def test_missing_owner_source_is_rejected(tmp_path: Path) -> None:
    candidate = load_candidate(ROOT)

    with pytest.raises(ValueError, match="exactly one source"):
        stable_owner_paths(tmp_path, candidate)


def test_checked_stable_owner_import_closure_has_zero_strict_errors() -> None:
    assert check_stable_typing(ROOT) == 0
