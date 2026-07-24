from __future__ import annotations

import ast
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from pheroos.governance._scoped_authority_primitives_v2 import (
    _canonical_bytes,
    _compute_root,
    _require_root,
    _require_text,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)


ROOT = Path(__file__).resolve().parents[2]
LEAF_MODULE = "pheroos.governance._scoped_authority_primitives_v2"
LEAF_PATH = ROOT / "pheroos/governance/_scoped_authority_primitives_v2.py"
FOUNDATION_PATH = (
    ROOT / "pheroos/governance/_authority_store_v2_contracts/foundation.py"
)
DOMAIN_PATH = ROOT / "pheroos/governance/_authority_store_v2_contracts/domain.py"
SESSION_PATH = ROOT / "pheroos/governance/_authority_session_v2/contracts.py"
ROOT_PREFIX = "pheroos-governance-authority-v2:"
SHARED_FUNCTIONS = frozenset(
    {
        "_canonical_bytes",
        "_compute_root",
        "_install_root",
        "_require_root",
        "_require_text",
    }
)


def _domain() -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:primitive-golden",
    )


def _grant(domain: AuthorityDomainV2) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:golden",
        grant_ref="grant:golden",
        grant_binding_ref="sha256:" + "1" * 64,
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        ),
        target_refs=("target:alpha", "target:omega"),
        action_refs=("action:publish",),
        issued_epoch=7,
        not_before_epoch=8,
        expires_at_epoch=99,
        revocation_generation=2,
    )


def _independent_canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _independent_root(kind: str, body: object) -> str:
    material = (
        (ROOT_PREFIX + kind).encode("utf-8")
        + b"\x00"
        + _independent_canonical_bytes(body)
    )
    return "sha256:" + sha256(material).hexdigest()


def _root_body(record: object, root_field: str) -> dict[str, object]:
    body = record.to_dict()  # type: ignore[attr-defined]
    del body[root_field]
    return body


def test_shared_canonical_bytes_and_domain_separator_are_frozen() -> None:
    payload = {"z": "蜂", "a": [True, None, 7], "nested": {"é": "NFC"}}

    assert _canonical_bytes(payload) == (
        b'{"a":[true,null,7],"nested":{"\xc3\xa9":"NFC"},"z":"\xe8\x9c\x82"}'
    )
    assert _compute_root("golden-kind", payload) == (
        "sha256:d6fa191bd9166a03b45904dc80f3b26fd068599ef9cf354a6d11e1f24106a01f"
    )
    assert _compute_root("golden-kind", payload) == _independent_root(
        "golden-kind",
        payload,
    )
    assert _compute_root("golden-kind\x00", payload) != _compute_root(
        "golden-kind",
        payload,
    )


def test_store_and_session_wire_records_match_independent_golden_oracle() -> None:
    domain = _domain()
    grant = _grant(domain)

    assert domain.domain_root == (
        "sha256:2618274fed6974d76d7f013866c778b7ec2e8e0de41a74350b2462eade7e33f4"
    )
    assert grant.grant_root == (
        "sha256:5fb8d3c9fa363d2289c03a92a136adb48cda245e86babdfeb57ec1263be1a5d9"
    )
    assert domain.domain_root == _independent_root(
        "domain",
        _root_body(domain, "domain_root"),
    )
    assert grant.grant_root == _independent_root(
        "issuer-grant",
        _root_body(grant, "grant_root"),
    )
    assert sha256(domain.canonical_bytes()).hexdigest() == (
        "9086da206802ea2d99f20c06fdb182010f2bb1217890b83b449add37011cabb1"
    )
    assert sha256(grant.canonical_bytes()).hexdigest() == (
        "c10b6e9a94f7c09230960062b75ef05107ca9337ec417ac97df45dc67638e4f5"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, "field must be canonical non-blank text"),
        ("", "field must be canonical non-blank text"),
        (" padded", "field must be canonical non-blank text"),
        ("e\u0301", "field must already use Unicode NFC"),
        ("has\x00nul", "field must not contain U+0000"),
        ("\ud800", "field must encode as UTF-8"),
    ),
)
def test_shared_text_failure_semantics_are_frozen(
    value: object,
    expected: str,
) -> None:
    with pytest.raises(ValueError) as caught:
        _require_text(value, "field")
    assert str(caught.value) == expected


@pytest.mark.parametrize(
    "value",
    (
        None,
        True,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha512:" + "a" * 64,
    ),
)
def test_shared_root_failure_semantics_are_frozen(value: object) -> None:
    with pytest.raises(ValueError) as caught:
        _require_root(value, "root")
    assert str(caught.value) == "root must be a lowercase sha256 root"


def test_store_and_session_root_installation_failures_remain_differentially_equal() -> (
    None
):
    domain = _domain()
    grant = _grant(domain)
    malformed = "sha256:" + "A" * 64
    mismatched = "sha256:" + "f" * 64

    for record, field in ((domain, "domain_root"), (grant, "grant_root")):
        assert replace(record, **{field: getattr(record, field)}) == record
        with pytest.raises(
            ValueError,
            match=f"^{field} must be a lowercase sha256 root$",
        ):
            replace(record, **{field: malformed})
        with pytest.raises(ValueError, match=f"^{field} is mismatched$"):
            replace(record, **{field: mismatched})


def _imports_from(path: Path, module: str) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return frozenset(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    )


def _top_level_definitions(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            names.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )
    return frozenset(names)


def test_shared_primitive_module_is_a_private_dependency_leaf() -> None:
    tree = ast.parse(LEAF_PATH.read_text(encoding="utf-8"), filename=str(LEAF_PATH))
    project_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("pheroos")
    }
    project_imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("pheroos")
    )

    assert project_imports == set()
    assert "__all__" not in _top_level_definitions(LEAF_PATH)


def test_shared_primitive_ownership_and_import_direction_are_exact() -> None:
    assert _imports_from(FOUNDATION_PATH, LEAF_MODULE) == SHARED_FUNCTIONS
    assert _imports_from(SESSION_PATH, LEAF_MODULE) == SHARED_FUNCTIONS
    assert _imports_from(DOMAIN_PATH, LEAF_MODULE) == frozenset({"_ROOT_PREFIX"})

    removed_definitions = SHARED_FUNCTIONS | {"_ROOT_PREFIX", "_SHA256_PATTERN"}
    assert _top_level_definitions(FOUNDATION_PATH).isdisjoint(removed_definitions)
    assert _top_level_definitions(SESSION_PATH).isdisjoint(removed_definitions)

    importers = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "pheroos/governance").rglob("*.py")
        if path != LEAF_PATH and _imports_from(path, LEAF_MODULE)
    }
    assert importers == {
        "pheroos/governance/_authority_session_v2/contracts.py",
        "pheroos/governance/_authority_store_v2_contracts/domain.py",
        "pheroos/governance/_authority_store_v2_contracts/foundation.py",
    }
