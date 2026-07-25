from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from pheroos.conformance.schema_catalog import SCHEMA_ARTIFACT_SPECS


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "tests" / "typing" / "stable_consumer.py"
# This Draft/conformance fixture belongs to the distribution-test harness.  The
# copied consumer imports only promotion-candidate facade roots and receives
# the external implementation through GovernanceStateStoreConformanceAdapterV2.
_INDEPENDENT_WRITE_JOURNEY_HARNESS = (
    "from stable_consumer import exercise_governance_write_journey;"
    "from pheroos.conformance.authority_store_v2_spec_adapter import "
    "IndependentStdlibGovernanceStateStoreV2Adapter;"
    "exercise_governance_write_journey("
    "IndependentStdlibGovernanceStateStoreV2Adapter())"
)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_write_journey_store_fixture_is_independent_and_harness_only() -> None:
    consumer_source = CONSUMER.read_text(encoding="utf-8")

    assert (
        "IndependentStdlibGovernanceStateStoreV2Adapter"
        in _INDEPENDENT_WRITE_JOURNEY_HARNESS
    )
    assert (
        "ReferenceGovernanceStateStoreConformanceAdapterV2"
        not in _INDEPENDENT_WRITE_JOURNEY_HARNESS
    )
    assert "authority_store_v2_spec_adapter" not in consumer_source
    assert "adapter: GovernanceStateStoreConformanceAdapterV2" in consumer_source


@pytest.fixture(scope="module")
def distribution_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    output = tmp_path_factory.mktemp("stable-distributions")
    completed = _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--sdist",
            "--outdir",
            str(output),
        ],
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return {
        "wheel": next(output.glob("*.whl")),
        "sdist": next(output.glob("*.tar.gz")),
    }


@pytest.mark.parametrize("distribution_kind", ("wheel", "sdist"))
def test_distribution_installs_and_runs_same_external_stable_consumer(
    distribution_kind: str,
    distribution_artifacts: dict[str, Path],
    tmp_path: Path,
) -> None:
    site_packages = tmp_path / f"{distribution_kind}-site-packages"
    installed = _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            "--ignore-installed",
            "--target",
            str(site_packages),
            str(distribution_artifacts[distribution_kind]),
        ],
        cwd=tmp_path,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    external_cwd = tmp_path / f"external-{distribution_kind}"
    external_cwd.mkdir()
    external_consumer = external_cwd / "stable_consumer.py"
    shutil.copy2(CONSUMER, external_consumer)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(site_packages)

    location = _run(
        [
            sys.executable,
            "-S",
            "-c",
            "import pathlib, pheroos; print(pathlib.Path(pheroos.__file__).resolve())",
        ],
        cwd=external_cwd,
        env=environment,
    )
    assert location.returncode == 0, location.stdout + location.stderr
    package_dir = Path(location.stdout.strip()).parent
    assert site_packages.resolve() in package_dir.parents
    assert ROOT.resolve() not in package_dir.parents
    assert (package_dir / "py.typed").is_file()
    installed_candidate = (
        package_dir / "conformance" / "abi" / "stable-python-api-v1.json"
    )
    assert (
        installed_candidate.read_bytes()
        == (
            ROOT / "pheroos" / "conformance" / "abi" / "stable-python-api-v1.json"
        ).read_bytes()
    )

    executed = _run(
        [sys.executable, "-S", str(external_consumer)],
        cwd=external_cwd,
        env=environment,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr

    write_journey = _run(
        [
            sys.executable,
            "-S",
            "-c",
            _INDEPENDENT_WRITE_JOURNEY_HARNESS,
        ],
        cwd=external_cwd,
        env=environment,
    )
    assert write_journey.returncode == 0, write_journey.stdout + write_journey.stderr

    shown = _run(
        [
            sys.executable,
            "-S",
            "-m",
            "pheroos.cli.main",
            "abi",
            "show",
            "--stable-only",
        ],
        cwd=external_cwd,
        env=environment,
    )
    assert shown.returncode == 0, shown.stdout + shown.stderr
    payload = json.loads(shown.stdout)
    assert payload["inventory"]["lifecycle"] == {
        "formal_stable": False,
        "stability": "draft",
        "status": "promotion_candidate",
    }

    for spec in SCHEMA_ARTIFACT_SPECS:
        expected = (ROOT / spec.path).read_bytes()
        for surface in spec.cli_surfaces:
            exported = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-m",
                    "pheroos.cli.main",
                    "schema",
                    "export",
                    surface.name,
                ],
                cwd=external_cwd,
                env=environment,
                check=False,
                capture_output=True,
            )
            assert exported.returncode == 0, exported.stderr.decode("utf-8")
            assert exported.stdout == expected
