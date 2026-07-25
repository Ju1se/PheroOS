from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

import pytest

from scripts.release_candidate import (
    CONFORMANCE_EXAMPLES,
    EXPECTED_SCHEMA_EXPORT_COUNT,
    RELEASE_ASSET_NAMES,
    CommandOutput,
    DistributionSet,
    ExternalVerification,
    ReleaseCandidateError,
    V3_PROVIDER_FREE_EXAMPLES,
    _git_tree,
    _materialize_candidate_snapshot,
    assemble_release_staging,
    load_distribution_set,
    project_version,
    stage_distribution_subjects,
    validate_release_staging,
    validate_tag_and_versions,
)


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-candidate.yml"


def _wheel(path: Path, version: str) -> None:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: pheroos\n"
        f"Version: {version}\n"
        "License-Expression: MIT\n\n"
    )
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"pheroos-{version}.dist-info/METADATA", metadata)
        archive.writestr("pheroos/__init__.py", "")


def _sdist(path: Path, version: str) -> None:
    metadata = (f"Metadata-Version: 2.4\nName: pheroos\nVersion: {version}\n\n").encode(
        "utf-8"
    )
    with tarfile.open(path, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pheroos-{version}/PKG-INFO")
        info.size = len(metadata)
        info.mtime = 0
        archive.addfile(info, BytesIO(metadata))


def _distributions(tmp_path: Path) -> tuple[DistributionSet, DistributionSet]:
    version = project_version()
    subject_dir = tmp_path / "subject"
    comparison_dir = tmp_path / "comparison"
    subject_dir.mkdir()
    comparison_dir.mkdir()
    wheel = subject_dir / f"pheroos-{version}-py3-none-any.whl"
    sdist = subject_dir / f"pheroos-{version}.tar.gz"
    _wheel(wheel, version)
    _sdist(sdist, version)
    shutil.copyfile(wheel, comparison_dir / wheel.name)
    shutil.copyfile(sdist, comparison_dir / sdist.name)
    return (
        load_distribution_set(subject_dir, role="subject", version=version),
        load_distribution_set(comparison_dir, role="comparison", version=version),
    )


def _abi_report() -> dict[str, object]:
    return {
        "breaking_differences": [],
        "candidate_status": "promotion_candidate",
        "differences": [],
        "expected_version": "pheroos-stable-python-api-v1",
        "formal_stable": False,
        "observed_version": "pheroos-stable-python-api-v1",
        "ok": True,
        "report_version": "pheroos-abi-command-report-v1",
        "stable_breaking": False,
        "stable_only": True,
    }


def _verifications() -> dict[str, ExternalVerification]:
    outputs = {
        "stable-consumer": CommandOutput(b"", b""),
        "version": CommandOutput(b'{"ok":true}\n', b""),
        "abi-show": CommandOutput(b'{"ok":true}\n', b""),
        "abi-diff": CommandOutput(
            (json.dumps(_abi_report(), sort_keys=True) + "\n").encode("utf-8"),
            b"",
        ),
        "schema-list": CommandOutput(b'{"ok":true,"schemas":[]}\n', b""),
        "tck-v1": CommandOutput(b'{"ok":true}\n', b""),
        "tck-v2": CommandOutput(b'{"ok":true}\n', b""),
        "runtime-integration-independent": CommandOutput(b'{"ok":true}\n', b""),
    }
    outputs.update(
        {
            f"schema-export:fixture-{index:02d}": CommandOutput(
                b'{"type":"object"}\n', b""
            )
            for index in range(EXPECTED_SCHEMA_EXPORT_COUNT)
        }
    )
    outputs.update(
        {
            f"conformance:{example}": CommandOutput(b'{"ok":true}\n', b"")
            for example in CONFORMANCE_EXAMPLES
        }
    )
    outputs.update(
        {
            label: CommandOutput(b'{"ok":true}\n', b"")
            for example in V3_PROVIDER_FREE_EXAMPLES
            for label in (
                f"wire:{example}",
                f"provider-free-example:{example}",
            )
        }
    )
    return {
        name: ExternalVerification.from_outputs(
            name,
            outputs,
            schema_export_count=EXPECTED_SCHEMA_EXPORT_COUNT,
        )
        for name in ("source", "wheel", "sdist")
    }


def _assemble(tmp_path: Path) -> Path:
    subject, comparison = _distributions(tmp_path)
    staging = tmp_path / "staging"
    version = project_version()
    assemble_release_staging(
        ROOT,
        staging,
        subject=subject,
        comparison=comparison,
        version=version,
        tag=f"v{version}",
        commit="a" * 40,
        tree="c" * 40,
        verifications=_verifications(),
    )
    return staging


def test_release_staging_binds_exact_subjects_and_all_required_assets(
    tmp_path: Path,
) -> None:
    staging = _assemble(tmp_path)

    manifest = validate_release_staging(staging)
    subject_names = {item["name"] for item in manifest["subject_artifacts"]}
    assert {path.name for path in staging.iterdir()} == subject_names | set(
        RELEASE_ASSET_NAMES
    )
    assert manifest["mode"] == "dry-run"
    assert manifest["publication_allowed"] is False
    assert manifest["source"]["worktree_clean"] is True
    assert manifest["source"]["tree"] == "c" * 40
    assert manifest["reproducibility"] == {
        "comparison_hashes": manifest["reproducibility"]["subject_hashes"],
        "comparison_publishable": False,
        "comparison_role": "comparison_only",
        "identical": True,
        "subject_hashes": manifest["reproducibility"]["subject_hashes"],
    }
    assert len(manifest["external_verification"]["transcript_roots"]) == 3
    assert manifest["external_verification"]["semantic_outputs_identical"] is True

    sums = (staging / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    assert [line.split("  ", maxsplit=1)[1] for line in sums] == sorted(
        path.name for path in staging.iterdir() if path.name != "SHA256SUMS"
    )


def test_release_staging_rejects_subject_tampering(tmp_path: Path) -> None:
    staging = _assemble(tmp_path)
    wheel = next(staging.glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")

    with pytest.raises(ReleaseCandidateError):
        validate_release_staging(staging)


def test_release_staging_rejects_any_extra_asset(tmp_path: Path) -> None:
    staging = _assemble(tmp_path)
    (staging / "comparison-build.whl").write_bytes(b"forbidden")

    with pytest.raises(ReleaseCandidateError, match="allowlist"):
        validate_release_staging(staging)


def test_release_staging_binds_the_expected_commit_tree(tmp_path: Path) -> None:
    staging = _assemble(tmp_path)

    validate_release_staging(
        staging,
        expected_commit="a" * 40,
        expected_tree="c" * 40,
    )
    with pytest.raises(ReleaseCandidateError, match="expected commit tree"):
        validate_release_staging(
            staging,
            expected_commit="a" * 40,
            expected_tree="d" * 40,
        )


def test_candidate_snapshot_is_exported_from_the_captured_git_tree(
    tmp_path: Path,
) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = _git_tree(ROOT, commit, timeout=30.0)

    snapshot = _materialize_candidate_snapshot(
        ROOT,
        tmp_path,
        commit=commit,
        tree=tree,
        timeout=30.0,
    )

    assert not (snapshot / ".git").exists()
    assert (
        tree
        == subprocess.run(
            ["git", "rev-parse", f"{commit}^{{tree}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    assert (snapshot / "pyproject.toml").read_bytes() == subprocess.run(
        ["git", "show", f"{commit}:pyproject.toml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def test_candidate_snapshot_ignores_archive_attributes_and_checkout_filters(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "snapshot@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Snapshot Test"],
        cwd=repository,
        check=True,
    )
    tracked = {
        ".gitattributes": (
            "tracked-ignored.txt export-ignore\n"
            "substituted.txt export-subst\n"
            "filtered.txt filter=hostile\n"
        ),
        "filtered.txt": "FILTER-MUST-NOT-RUN\n",
        "global-ignored.txt": "GLOBAL-ATTRIBUTE-MUST-NOT-RUN\n",
        "info-ignored.txt": "INFO-ATTRIBUTE-MUST-NOT-RUN\n",
        "substituted.txt": "$Format:%H$\n",
        "tracked-ignored.txt": "TRACKED-ATTRIBUTE-MUST-NOT-RUN\n",
    }
    for relative, content in tracked.items():
        (repository / relative).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "snapshot fixture"],
        cwd=repository,
        check=True,
    )

    external_attributes = tmp_path / "external-attributes"
    external_attributes.write_text(
        "global-ignored.txt export-ignore\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "config", "core.attributesFile", str(external_attributes)],
        cwd=repository,
        check=True,
    )
    info_attributes = repository / ".git" / "info" / "attributes"
    info_attributes.write_text(
        "info-ignored.txt export-ignore\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "git",
            "config",
            "filter.hostile.smudge",
            "this-command-must-never-run",
        ],
        cwd=repository,
        check=True,
    )
    assert (
        subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        == b""
    )

    archive_path = tmp_path / "attribute-affected.tar"
    subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            "HEAD",
        ],
        cwd=repository,
        check=True,
    )
    with tarfile.open(archive_path, mode="r:") as archive:
        archive_names = set(archive.getnames())
        substituted = archive.extractfile("substituted.txt")
        assert substituted is not None
        substituted_bytes = substituted.read()
    assert "tracked-ignored.txt" not in archive_names
    assert "global-ignored.txt" not in archive_names
    assert "info-ignored.txt" not in archive_names
    assert substituted_bytes != tracked["substituted.txt"].encode("utf-8")

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = _git_tree(repository, commit, timeout=30.0)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = _materialize_candidate_snapshot(
        repository,
        workspace,
        commit=commit,
        tree=tree,
        timeout=30.0,
    )

    for relative, content in tracked.items():
        assert (snapshot / relative).read_text(encoding="utf-8") == content


def test_tag_and_source_versions_must_match_exactly(tmp_path: Path) -> None:
    version = project_version()
    with pytest.raises(ReleaseCandidateError, match="candidate tag mismatch"):
        validate_tag_and_versions("v999.0.0")

    root = tmp_path / "mismatch"
    (root / "pheroos").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "pheroos"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "pheroos" / "_version.py").write_text(
        '__version__ = "0.1.1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ReleaseCandidateError, match="package version mismatch"):
        validate_tag_and_versions(f"v{version}", root=root)


def test_comparison_build_can_never_be_staged_as_the_subject(tmp_path: Path) -> None:
    _, comparison = _distributions(tmp_path)

    with pytest.raises(ReleaseCandidateError, match="comparison-only"):
        stage_distribution_subjects(comparison, tmp_path / "forbidden-staging")


def test_reproducibility_mismatch_fails_before_staging(tmp_path: Path) -> None:
    subject, comparison = _distributions(tmp_path)
    comparison_wheel = next(comparison.directory.glob("*.whl"))
    comparison_wheel.write_bytes(comparison_wheel.read_bytes() + b"comparison-drift")
    changed_comparison = load_distribution_set(
        comparison.directory,
        role="comparison",
        version=project_version(),
    )

    with pytest.raises(ReleaseCandidateError, match="byte-identical"):
        assemble_release_staging(
            ROOT,
            tmp_path / "staging",
            subject=subject,
            comparison=changed_comparison,
            version=project_version(),
            tag=f"v{project_version()}",
            commit="b" * 40,
            tree="c" * 40,
            verifications=_verifications(),
        )


def test_release_candidate_workflow_is_read_only_and_dry_run_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read\n" in workflow
    assert "python scripts/release_candidate.py" in workflow
    assert "--verify-staging" in workflow
    assert "name: pheroos-release-candidate-dry-run" in workflow
    assert "path: ${{ runner.temp }}/pheroos-release-candidate/*" in workflow
    assert "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd" in workflow
    assert "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405" in workflow
    assert (
        "actions/upload-artifact@330a01c490aca151604b8cf639adc76d48f6c5d4" in workflow
    )
    for forbidden in (
        "contents: write",
        "id-token: write",
        "attestations: write",
        "actions/attest@",
        "gh release",
        "git tag",
        "pypi",
        "twine",
        "comparison/*",
    ):
        assert forbidden not in workflow.lower()
