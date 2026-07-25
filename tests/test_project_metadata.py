import json
from pathlib import Path
import tomllib

import pheroos
from pheroos.conformance.schema_catalog import SCHEMA_ARTIFACT_SPECS


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert pheroos.__version__ == pyproject["project"]["version"]


def test_open_protocol_materials_exist() -> None:
    for path in [
        "SPEC.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "docs/process/index.md",
        "docs/process/api-lifecycle.md",
        "docs/process/release-checklist.md",
        "docs/protocol/extension-points.md",
        "docs/protocol/runtime-adapter-guide.md",
        "docs/protocol/runtime-integration.md",
        "docs/protocol/stable-core-consumer.md",
        "docs/conformance/conformance-suite.md",
    ]:
        assert Path(path).is_file()


def test_spec_tracks_the_closed_schema_and_candidate_artifact_catalogs() -> None:
    specification = Path("SPEC.md").read_text(encoding="utf-8")

    for artifact in SCHEMA_ARTIFACT_SPECS:
        assert f"`{artifact.path}`" in specification

    for path in (
        "pheroos/conformance/abi/public-python-api-v1.json",
        "pheroos/conformance/abi/public-python-api-lifecycle-v1.json",
        "pheroos/conformance/abi/runtime-compatibility-v1.json",
        "pheroos/conformance/abi/stable-python-api-v1.json",
    ):
        assert f"`{path}`" in specification

    assert "protocol_version=pheroos.protocol.v2" in specification
    assert "draft / promotion_candidate / formal_stable=false" in specification
    assert "no public lifecycle entry is formally Stable" in specification


def test_stable_consumer_guide_tracks_every_candidate_root() -> None:
    artifact = json.loads(
        Path("pheroos/conformance/abi/stable-python-api-v1.json").read_text(
            encoding="utf-8"
        )
    )
    guide = Path("docs/protocol/stable-core-consumer.md").read_text(encoding="utf-8")

    for package, package_contract in artifact["packages"].items():
        for root in package_contract["roots"]:
            assert f"`{root}`" in guide, f"{package}.{root}"

    assert "tests/typing/stable_consumer.py" in guide
    assert "draft / promotion_candidate / formal_stable=false" in guide
