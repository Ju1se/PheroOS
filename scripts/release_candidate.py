#!/usr/bin/env python3
"""Build and verify an offline-only PheroOS release-candidate staging set.

The first distribution build is the release subject.  A second build exists
only to prove reproducibility and is never accepted by the staging API.  This
script does not create commits, tags, GitHub Releases, attestations, or PyPI
uploads.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from email.parser import Parser
from hashlib import sha1, sha256
from importlib import import_module
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from typing import Any, Callable, Literal, TypeAlias, cast
import zipfile


def _release_sbom_module() -> Any:
    try:
        return import_module("scripts.generate_release_sbom")
    except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
        return import_module("generate_release_sbom")


_SBOM_MODULE = _release_sbom_module()
RELEASE_SOURCE_DATE_EPOCH = cast(int, _SBOM_MODULE.RELEASE_SOURCE_DATE_EPOCH)
build_sboms = cast(
    Callable[..., tuple[dict[str, object], dict[str, object]]],
    _SBOM_MODULE.build_sboms,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE_MANIFEST_VERSION = "pheroos-release-candidate-manifest-v1"
RELEASE_MODE = "dry-run"
EXPECTED_SCHEMA_EXPORT_COUNT = 25
RELEASE_ASSET_NAMES = (
    "ABI-DIFF.json",
    "MIGRATION-NOTES.md",
    "SHA256SUMS",
    "pheroos.cdx.json",
    "pheroos.spdx.json",
    "release-manifest.json",
)
MIGRATION_SOURCE_PATHS = (
    Path("CHANGELOG.md"),
    Path("docs/process/schema-v1-v2-migration.md"),
    Path("docs/process/removal-ledger.md"),
    Path("docs/protocol/authority-v2-migration.md"),
    Path("docs/protocol/runtime-integration.md"),
)
CONFORMANCE_EXAMPLES = (
    "toy-protocol",
    "e2e-protocol",
    "swarm-protocol",
    "hybrid-pheromone-protocol",
    "hybrid-commit-protocol",
    "distributed-commit-protocol",
)
V3_PROVIDER_FREE_EXAMPLES = (
    "hybrid-replay-protocol",
    "scoped-output-protocol",
)
HEX_SHA1 = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?")
GIT_CONTEXT_ENVIRONMENT_KEYS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_ATTR_SOURCE",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    }
)

DistributionRole: TypeAlias = Literal["subject", "comparison"]
DistributionKind: TypeAlias = Literal["wheel", "sdist"]


class ReleaseCandidateError(ValueError):
    """A fail-closed release-candidate validation error."""


@dataclass(frozen=True)
class DistributionArtifact:
    path: Path
    name: str
    kind: DistributionKind
    digest: str
    size: int

    def descriptor(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "name": self.name,
            "sha256": self.digest,
            "size": self.size,
        }


@dataclass(frozen=True)
class DistributionSet:
    directory: Path
    role: DistributionRole
    version: str
    artifacts: tuple[DistributionArtifact, DistributionArtifact]

    @property
    def hashes(self) -> dict[str, str]:
        return {artifact.name: artifact.digest for artifact in self.artifacts}


@dataclass(frozen=True)
class CommandOutput:
    stdout: bytes
    stderr: bytes

    @property
    def digest(self) -> str:
        payload = (
            len(self.stdout).to_bytes(8, "big")
            + self.stdout
            + len(self.stderr).to_bytes(8, "big")
            + self.stderr
        )
        return sha256(payload).hexdigest()


@dataclass(frozen=True)
class ExternalVerification:
    environment: str
    outputs: Mapping[str, CommandOutput]
    schema_export_count: int
    transcript_root: str

    @classmethod
    def from_outputs(
        cls,
        environment: str,
        outputs: Mapping[str, CommandOutput],
        *,
        schema_export_count: int,
    ) -> ExternalVerification:
        if not outputs:
            raise ReleaseCandidateError("external verification transcript is empty")
        material = "\n".join(
            f"{label}:{outputs[label].digest}" for label in sorted(outputs)
        ).encode("utf-8")
        return cls(
            environment=environment,
            outputs=dict(outputs),
            schema_export_count=schema_export_count,
            transcript_root=f"sha256:{sha256(material).hexdigest()}",
        )


@dataclass(frozen=True)
class GitTreeEntry:
    mode: str
    object_id: str
    relative: str
    parts: tuple[str, ...]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCandidateError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseCandidateError(f"{label} must be a JSON object")
    return value


def project_version(root: Path = ROOT) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    value = project.get("project", {}).get("version")
    if not isinstance(value, str) or VERSION.fullmatch(value) is None:
        raise ReleaseCandidateError("pyproject.toml has an unsupported project version")
    return value


def package_version(root: Path = ROOT) -> str:
    source = (root / "pheroos" / "_version.py").read_text(encoding="utf-8")
    values: list[str] = []
    for statement in ast.parse(source).body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "__version__"
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            values.append(statement.value.value)
    if len(values) != 1:
        raise ReleaseCandidateError("pheroos._version must assign __version__ once")
    return values[0]


def validate_tag_and_versions(
    tag: str,
    *,
    root: Path = ROOT,
) -> str:
    declared = project_version(root)
    runtime = package_version(root)
    expected_tag = f"v{declared}"
    if runtime != declared:
        raise ReleaseCandidateError(
            f"package version mismatch: pyproject={declared!r}, pheroos={runtime!r}"
        )
    if tag != expected_tag:
        raise ReleaseCandidateError(
            f"candidate tag mismatch: expected {expected_tag!r}, observed {tag!r}"
        )
    return declared


def _metadata_version(metadata: bytes, *, label: str) -> str:
    try:
        message = Parser().parsestr(metadata.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ReleaseCandidateError(f"{label} metadata is not UTF-8") from error
    versions = message.get_all("Version", [])
    if len(versions) != 1 or not versions[0]:
        raise ReleaseCandidateError(f"{label} must contain one Version field")
    return versions[0]


def _wheel_version(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(names) != 1:
                raise ReleaseCandidateError(
                    f"wheel {path.name} must contain one dist-info/METADATA"
                )
            metadata = archive.read(names[0])
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ReleaseCandidateError(
            f"cannot inspect wheel {path.name}: {error}"
        ) from error
    return _metadata_version(metadata, label=f"wheel {path.name}")


def _sdist_version(path: Path) -> str:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.isfile()
                and member.name.count("/") == 1
                and member.name.endswith("/PKG-INFO")
            ]
            if len(members) != 1 or members[0].size > 1_000_000:
                raise ReleaseCandidateError(
                    f"sdist {path.name} must contain one bounded root PKG-INFO"
                )
            extracted = archive.extractfile(members[0])
            if extracted is None:
                raise ReleaseCandidateError(f"cannot read sdist {path.name} PKG-INFO")
            metadata = extracted.read()
    except (OSError, tarfile.TarError) as error:
        raise ReleaseCandidateError(
            f"cannot inspect sdist {path.name}: {error}"
        ) from error
    return _metadata_version(metadata, label=f"sdist {path.name}")


def _distribution_paths(directory: Path) -> tuple[Path, Path]:
    if not directory.is_dir():
        raise ReleaseCandidateError(
            f"distribution directory does not exist: {directory}"
        )
    wheels = sorted(path for path in directory.iterdir() if path.suffix == ".whl")
    sdists = sorted(
        path for path in directory.iterdir() if path.name.endswith(".tar.gz")
    )
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseCandidateError(
            f"expected one wheel and one sdist in {directory}, "
            f"found wheel={len(wheels)}, sdist={len(sdists)}"
        )
    if any(path.is_symlink() or not path.is_file() for path in (*wheels, *sdists)):
        raise ReleaseCandidateError("distribution subjects must be regular files")
    return wheels[0], sdists[0]


def load_distribution_set(
    directory: Path,
    *,
    role: DistributionRole,
    version: str,
) -> DistributionSet:
    wheel, sdist = _distribution_paths(directory)
    expected_prefix = f"pheroos-{version.replace('-', '_')}"
    if not wheel.name.startswith(f"{expected_prefix}-"):
        raise ReleaseCandidateError(
            "wheel filename does not bind the candidate version"
        )
    if sdist.name != f"pheroos-{version}.tar.gz":
        raise ReleaseCandidateError(
            "sdist filename does not bind the candidate version"
        )
    embedded = {"wheel": _wheel_version(wheel), "sdist": _sdist_version(sdist)}
    if set(embedded.values()) != {version}:
        raise ReleaseCandidateError(
            f"distribution metadata version mismatch: expected {version!r}, "
            f"observed {embedded!r}"
        )
    artifacts = (
        DistributionArtifact(
            path=wheel,
            name=wheel.name,
            kind="wheel",
            digest=_digest(wheel),
            size=wheel.stat().st_size,
        ),
        DistributionArtifact(
            path=sdist,
            name=sdist.name,
            kind="sdist",
            digest=_digest(sdist),
            size=sdist.stat().st_size,
        ),
    )
    return DistributionSet(
        directory=directory.resolve(),
        role=role,
        version=version,
        artifacts=artifacts,
    )


def compare_distribution_sets(
    subject: DistributionSet,
    comparison: DistributionSet,
) -> None:
    if subject.role != "subject" or comparison.role != "comparison":
        raise ReleaseCandidateError("reproducibility comparison roles are invalid")
    if subject.version != comparison.version or subject.hashes != comparison.hashes:
        raise ReleaseCandidateError(
            "comparison build is not byte-identical to the release subject"
        )


def _ensure_empty_directory(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ReleaseCandidateError(f"directory must be absent or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def stage_distribution_subjects(
    distributions: DistributionSet,
    staging_directory: Path,
) -> None:
    if distributions.role != "subject":
        raise ReleaseCandidateError(
            "comparison-only distributions cannot enter release staging"
        )
    staging_directory.mkdir(parents=True, exist_ok=True)
    for artifact in distributions.artifacts:
        if _digest(artifact.path) != artifact.digest:
            raise ReleaseCandidateError(
                f"release subject changed after identity capture: {artifact.name}"
            )
        destination = staging_directory / artifact.name
        if destination.exists():
            raise ReleaseCandidateError(
                f"staging destination already exists: {destination}"
            )
        shutil.copyfile(artifact.path, destination)
        if _digest(destination) != artifact.digest:
            raise ReleaseCandidateError(f"staged subject differs: {artifact.name}")


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
    timeout: float,
) -> CommandOutput:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment) if environment is not None else None,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseCandidateError(
            f"command did not complete: {command[0]!r}: {error}"
        ) from error
    if completed.returncode != 0:
        stdout = completed.stdout[-4000:].decode("utf-8", errors="replace")
        stderr = completed.stderr[-4000:].decode("utf-8", errors="replace")
        raise ReleaseCandidateError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return CommandOutput(completed.stdout, completed.stderr)


def _git_object_environment() -> dict[str, str]:
    """Return a Git environment bound to the repository discovered from ``cwd``."""

    environment = os.environ.copy()
    for key in tuple(environment):
        if (
            key in GIT_CONTEXT_ENVIRONMENT_KEYS
            or key.startswith("GIT_CONFIG_KEY_")
            or key.startswith("GIT_CONFIG_VALUE_")
        ):
            environment.pop(key, None)
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _build_distribution(
    root: Path,
    output_directory: Path,
    *,
    role: DistributionRole,
    version: str,
    python: str,
    timeout: float,
) -> DistributionSet:
    _ensure_empty_directory(output_directory)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": str(RELEASE_SOURCE_DATE_EPOCH),
        }
    )
    _run(
        (
            python,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--sdist",
            "--outdir",
            str(output_directory),
        ),
        cwd=root,
        environment=environment,
        timeout=timeout,
    )
    _, sdist = _distribution_paths(output_directory)
    _run(
        (
            python,
            str(root / "scripts" / "normalize_sdist.py"),
            str(sdist),
            "--source-date-epoch",
            str(RELEASE_SOURCE_DATE_EPOCH),
        ),
        cwd=root,
        environment=environment,
        timeout=timeout,
    )
    return load_distribution_set(output_directory, role=role, version=version)


def _external_environment(import_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(import_root),
            "PYTHONSAFEPATH": "1",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _installed_import_root(
    artifact: DistributionArtifact,
    *,
    workspace: Path,
    python: str,
    timeout: float,
) -> Path:
    target = workspace / f"installed-{artifact.kind}"
    external = workspace / f"install-cwd-{artifact.kind}"
    target.mkdir()
    external.mkdir()
    _run(
        (
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-build-isolation",
            "--no-deps",
            "--ignore-installed",
            "--target",
            str(target),
            str(artifact.path),
        ),
        cwd=external,
        timeout=timeout,
    )
    if not (target / "pheroos" / "__init__.py").is_file():
        raise ReleaseCandidateError(f"{artifact.kind} did not install PheroOS")
    return target


def _python_command(python: str, *arguments: str) -> tuple[str, ...]:
    return (python, "-S", *arguments)


def _semantic_commands(
    root: Path,
    *,
    python: str,
    stable_consumer: Path,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    cli = (python, "-S", "-m", "pheroos.cli.main")
    commands: list[tuple[str, tuple[str, ...]]] = [
        ("stable-consumer", _python_command(python, str(stable_consumer))),
        ("version", (*cli, "version")),
        ("abi-show", (*cli, "abi", "show", "--stable-only")),
        ("abi-diff", (*cli, "abi", "diff", "--stable-only")),
        ("schema-list", (*cli, "schema", "list")),
        ("tck-v1", (*cli, "tck", "run", "--version", "v1")),
        ("tck-v2", (*cli, "tck", "run", "--version", "v2")),
        (
            "runtime-integration-independent",
            _python_command(
                python,
                str(root / "examples" / "runtime-integration-protocol" / "run.py"),
            ),
        ),
    ]
    commands.extend(
        (
            f"conformance:{example}",
            (*cli, "conformance", str(root / "examples" / example)),
        )
        for example in CONFORMANCE_EXAMPLES
    )
    for example in V3_PROVIDER_FREE_EXAMPLES:
        commands.extend(
            (
                (
                    f"wire:{example}",
                    (
                        *cli,
                        "wire",
                        "validate",
                        "capability-v3",
                        str(root / "examples" / example / "capability.json"),
                    ),
                ),
                (
                    f"provider-free-example:{example}",
                    _python_command(
                        python,
                        str(root / "examples" / example / "run.py"),
                    ),
                ),
            )
        )
    return tuple(commands)


def _schema_surfaces(output: CommandOutput) -> tuple[str, ...]:
    try:
        payload = json.loads(output.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCandidateError("schema list output is not JSON") from error
    schemas = payload.get("schemas") if isinstance(payload, dict) else None
    if not isinstance(schemas, list):
        raise ReleaseCandidateError("schema list output lacks schemas")
    surfaces = tuple(item.get("surface") for item in schemas if isinstance(item, dict))
    if not surfaces or any(not isinstance(surface, str) for surface in surfaces):
        raise ReleaseCandidateError("schema list contains an invalid surface")
    if len(surfaces) != len(set(surfaces)):
        raise ReleaseCandidateError("schema list contains duplicate surfaces")
    return surfaces  # type: ignore[return-value]


def _assert_import_origin(
    root: Path,
    *,
    environment: Mapping[str, str],
    external_cwd: Path,
    python: str,
    expected_import_root: Path,
    expected_version: str,
    timeout: float,
) -> None:
    statement = (
        "import json,pathlib,pheroos;"
        "print(json.dumps({'path':str(pathlib.Path(pheroos.__file__).resolve()),"
        "'version':pheroos.__version__},sort_keys=True))"
    )
    output = _run(
        _python_command(python, "-c", statement),
        cwd=external_cwd,
        environment=environment,
        timeout=timeout,
    )
    try:
        payload = json.loads(output.stdout.decode("utf-8"))
        observed_path = Path(payload["path"]).resolve()
        observed_version = payload["version"]
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCandidateError("package-origin probe is malformed") from error
    expected_root = expected_import_root.resolve()
    if not observed_path.is_relative_to(expected_root):
        raise ReleaseCandidateError(
            f"external verification imported outside {expected_root}: {observed_path}"
        )
    if observed_version != expected_version:
        raise ReleaseCandidateError("installed pheroos.__version__ is inconsistent")
    if external_cwd.resolve().is_relative_to(root.resolve()):
        raise ReleaseCandidateError("verification cwd is inside the source checkout")


def run_external_verification(
    root: Path,
    *,
    environment_name: str,
    import_root: Path,
    workspace: Path,
    python: str,
    version: str,
    timeout: float,
) -> ExternalVerification:
    external_cwd = workspace / f"external-{environment_name}"
    external_cwd.mkdir()
    stable_consumer = external_cwd / "stable_consumer.py"
    shutil.copyfile(root / "tests" / "typing" / "stable_consumer.py", stable_consumer)
    environment = _external_environment(import_root)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(import_root),
            str(root / "examples" / "runtime-integration-protocol"),
        )
    )
    _assert_import_origin(
        root,
        environment=environment,
        external_cwd=external_cwd,
        python=python,
        expected_import_root=import_root,
        expected_version=version,
        timeout=timeout,
    )
    outputs: dict[str, CommandOutput] = {}
    for label, command in _semantic_commands(
        root,
        python=python,
        stable_consumer=stable_consumer,
    ):
        outputs[label] = _run(
            command,
            cwd=external_cwd,
            environment=environment,
            timeout=timeout,
        )
    surfaces = _schema_surfaces(outputs["schema-list"])
    for surface in surfaces:
        label = f"schema-export:{surface}"
        outputs[label] = _run(
            _python_command(
                python,
                "-m",
                "pheroos.cli.main",
                "schema",
                "export",
                surface,
            ),
            cwd=external_cwd,
            environment=environment,
            timeout=timeout,
        )
    return ExternalVerification.from_outputs(
        environment_name,
        outputs,
        schema_export_count=len(surfaces),
    )


def validate_external_verifications(
    verifications: Mapping[str, ExternalVerification],
) -> ExternalVerification:
    expected = {"source", "wheel", "sdist"}
    if set(verifications) != expected:
        raise ReleaseCandidateError(
            f"external verification environments differ: {sorted(verifications)}"
        )
    source = verifications["source"]
    for name in ("wheel", "sdist"):
        observed = verifications[name]
        if observed.environment != name:
            raise ReleaseCandidateError(
                f"external verification environment label differs for {name}"
            )
        if observed.outputs != source.outputs:
            raise ReleaseCandidateError(
                f"{name} semantic transcript differs from the source transcript"
            )
        if observed.schema_export_count != source.schema_export_count:
            raise ReleaseCandidateError(f"{name} schema export count differs")
    if source.environment != "source":
        raise ReleaseCandidateError("source verification environment label differs")
    required = (
        {
            "stable-consumer",
            "version",
            "abi-show",
            "abi-diff",
            "schema-list",
            "tck-v1",
            "tck-v2",
            "runtime-integration-independent",
        }
        | {f"conformance:{example}" for example in CONFORMANCE_EXAMPLES}
        | {f"wire:{example}" for example in V3_PROVIDER_FREE_EXAMPLES}
        | {f"provider-free-example:{example}" for example in V3_PROVIDER_FREE_EXAMPLES}
    )
    missing = required - set(source.outputs)
    schema_labels = {
        label for label in source.outputs if label.startswith("schema-export:")
    }
    if (
        missing
        or source.schema_export_count != EXPECTED_SCHEMA_EXPORT_COUNT
        or len(schema_labels) != EXPECTED_SCHEMA_EXPORT_COUNT
    ):
        raise ReleaseCandidateError(
            f"external verification transcript is incomplete: {sorted(missing)}"
        )
    return source


def _abi_report(verification: ExternalVerification) -> dict[str, Any]:
    try:
        report = json.loads(verification.outputs["abi-diff"].stdout.decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCandidateError("Stable ABI diff output is malformed") from error
    if not isinstance(report, dict):
        raise ReleaseCandidateError("Stable ABI diff must be a JSON object")
    expected = {
        "ok": True,
        "stable_only": True,
        "candidate_status": "promotion_candidate",
        "formal_stable": False,
        "stable_breaking": False,
        "differences": [],
        "breaking_differences": [],
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise ReleaseCandidateError(
                f"Stable ABI candidate gate failed at {key}: {report.get(key)!r}"
            )
    return report


def _unreleased_changelog(root: Path) -> str:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## Unreleased\s*$", changelog, re.MULTILINE)
    if match is None:
        raise ReleaseCandidateError("CHANGELOG.md lacks an Unreleased section")
    following = changelog[match.end() :]
    next_section = re.search(r"^## (?!#)", following, re.MULTILINE)
    body = following[: next_section.start() if next_section else None].strip()
    if not body:
        raise ReleaseCandidateError("CHANGELOG.md Unreleased section is empty")
    return body


def _migration_source_descriptors(root: Path) -> list[dict[str, object]]:
    descriptors: list[dict[str, object]] = []
    for relative in MIGRATION_SOURCE_PATHS:
        path = root / relative
        if not path.is_file():
            raise ReleaseCandidateError(f"migration source is missing: {relative}")
        descriptors.append(
            {
                "path": relative.as_posix(),
                "sha256": _digest(path),
                "size": path.stat().st_size,
            }
        )
    return descriptors


def render_migration_notes(
    root: Path,
    *,
    version: str,
    tag: str,
    commit: str,
    abi_report: Mapping[str, Any],
) -> tuple[bytes, list[dict[str, object]]]:
    descriptors = _migration_source_descriptors(root)
    sources = "\n".join(
        f"- `{item['path']}` — `sha256:{item['sha256']}`" for item in descriptors
    )
    body = (
        f"# PheroOS {version} Draft Promotion Candidate Migration Notes\n\n"
        f"Candidate tag: `{tag}`  \n"
        f"Candidate commit: `{commit}`  \n"
        "Lifecycle: `draft / promotion_candidate / formal_stable=false`\n\n"
        "This is a dry-run promotion candidate, not a Stable lifecycle claim. "
        "It does not authorize publication, replace an existing tag or asset, "
        "or permit a runtime to fall back to a weaker ABI.\n\n"
        "## Candidate ABI result\n\n"
        f"- Candidate drift: `{len(abi_report.get('differences', []))}`\n"
        f"- Breaking differences: `{len(abi_report.get('breaking_differences', []))}`\n"
        "- Closure missing: `0` (the strict candidate diff completed successfully)\n\n"
        "## Versioned migration sources\n\n"
        f"{sources}\n\n"
        "## Unreleased changes\n\n"
        f"{_unreleased_changelog(root)}\n"
    )
    return body.encode("utf-8"), descriptors


def _asset_descriptor(path: Path, *, role: str) -> dict[str, object]:
    return {
        "name": path.name,
        "role": role,
        "sha256": _digest(path),
        "size": path.stat().st_size,
    }


def _write_sboms(staging: Path) -> tuple[Path, Path]:
    cyclonedx, spdx = build_sboms(
        staging,
        source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
    )
    cdx_path = staging / "pheroos.cdx.json"
    spdx_path = staging / "pheroos.spdx.json"
    cdx_path.write_bytes(_canonical_json(cyclonedx))
    spdx_path.write_bytes(_canonical_json(spdx))
    return cdx_path, spdx_path


def _write_sha256sums(staging: Path) -> None:
    path = staging / "SHA256SUMS"
    names = sorted(item.name for item in staging.iterdir() if item.name != path.name)
    lines = [f"{_digest(staging / name)}  {name}" for name in names]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def assemble_release_staging(
    root: Path,
    staging: Path,
    *,
    subject: DistributionSet,
    comparison: DistributionSet,
    version: str,
    tag: str,
    commit: str,
    tree: str,
    verifications: Mapping[str, ExternalVerification],
) -> dict[str, Any]:
    if RELEASE_SOURCE_DATE_EPOCH != 315532800:
        raise ReleaseCandidateError("release epoch must remain the ZIP-safe 1980 floor")
    compare_distribution_sets(subject, comparison)
    source_verification = validate_external_verifications(verifications)
    abi_report = _abi_report(source_verification)
    _ensure_empty_directory(staging)
    stage_distribution_subjects(subject, staging)
    cdx_path, spdx_path = _write_sboms(staging)
    abi_path = staging / "ABI-DIFF.json"
    abi_path.write_bytes(_canonical_json(abi_report))
    notes, migration_sources = render_migration_notes(
        root,
        version=version,
        tag=tag,
        commit=commit,
        abi_report=abi_report,
    )
    notes_path = staging / "MIGRATION-NOTES.md"
    notes_path.write_bytes(notes)
    auxiliary_assets = [
        _asset_descriptor(cdx_path, role="cyclonedx-1.6-sbom"),
        _asset_descriptor(spdx_path, role="spdx-2.3-sbom"),
        _asset_descriptor(abi_path, role="stable-candidate-abi-diff"),
        _asset_descriptor(notes_path, role="migration-notes"),
    ]
    transcript_roots = {
        name: verification.transcript_root
        for name, verification in sorted(verifications.items())
    }
    manifest: dict[str, Any] = {
        "candidate_tag": tag,
        "external_verification": {
            "environments": ["source", "wheel", "sdist"],
            "external_cwd": True,
            "includes_independent_runtime_adapter": True,
            "schema_export_count": source_verification.schema_export_count,
            "semantic_outputs_identical": True,
            "transcript_roots": transcript_roots,
        },
        "lifecycle": {
            "formal_stable": False,
            "stability": "draft",
            "status": "promotion_candidate",
        },
        "mode": RELEASE_MODE,
        "non_subject_assets": auxiliary_assets,
        "publication_allowed": False,
        "reproducibility": {
            "comparison_hashes": comparison.hashes,
            "comparison_publishable": False,
            "comparison_role": "comparison_only",
            "identical": True,
            "subject_hashes": subject.hashes,
        },
        "schema": RELEASE_MANIFEST_VERSION,
        "source": {
            "commit": commit,
            "source_date_epoch": RELEASE_SOURCE_DATE_EPOCH,
            "tree": tree,
            "worktree_clean": True,
        },
        "subject_artifacts": [artifact.descriptor() for artifact in subject.artifacts],
        "supply_chain": {
            "abi_diff": abi_path.name,
            "cyclonedx": cdx_path.name,
            "migration_notes": notes_path.name,
            "migration_sources": migration_sources,
            "sha256_manifest": "SHA256SUMS",
            "spdx": spdx_path.name,
        },
        "version": version,
    }
    manifest_path = staging / "release-manifest.json"
    manifest_path.write_bytes(_canonical_json(manifest))
    _write_sha256sums(staging)
    validate_release_staging(
        staging,
        root=root,
        expected_commit=commit,
        expected_tree=tree,
    )
    return manifest


def _staging_files(staging: Path) -> dict[str, Path]:
    if not staging.is_dir():
        raise ReleaseCandidateError("release staging directory does not exist")
    files: dict[str, Path] = {}
    for path in staging.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ReleaseCandidateError("release staging permits regular files only")
        files[path.name] = path
    return files


def _manifest_subjects(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    subjects = manifest.get("subject_artifacts")
    if not isinstance(subjects, list) or len(subjects) != 2:
        raise ReleaseCandidateError("release manifest must contain two subjects")
    required = {"kind", "name", "sha256", "size"}
    if not all(isinstance(item, dict) and set(item) == required for item in subjects):
        raise ReleaseCandidateError("release subject descriptors are malformed")
    kinds = {item["kind"] for item in subjects}
    if kinds != {"wheel", "sdist"}:
        raise ReleaseCandidateError("release subjects must be one wheel and one sdist")
    return subjects


def _validate_staging_allowlist(
    files: Mapping[str, Path],
    subjects: Sequence[Mapping[str, Any]],
) -> None:
    subject_names = {str(item["name"]) for item in subjects}
    expected = subject_names | set(RELEASE_ASSET_NAMES)
    observed = set(files)
    if observed != expected:
        raise ReleaseCandidateError(
            "release staging allowlist differs: "
            f"missing={sorted(expected - observed)}, "
            f"unknown={sorted(observed - expected)}"
        )


def _validate_sha256sums(files: Mapping[str, Path]) -> None:
    path = files["SHA256SUMS"]
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseCandidateError(f"cannot read SHA256SUMS: {error}") from error
    expected_names = sorted(set(files) - {"SHA256SUMS"})
    expected_lines = [f"{_digest(files[name])}  {name}" for name in expected_names]
    if lines != expected_lines:
        raise ReleaseCandidateError(
            "SHA256SUMS is not canonical or does not bind staging"
        )


def _validate_subject_descriptors(
    staging: Path,
    manifest: Mapping[str, Any],
    subjects: Sequence[Mapping[str, Any]],
) -> DistributionSet:
    version = manifest.get("version")
    if not isinstance(version, str):
        raise ReleaseCandidateError("release manifest version is invalid")
    observed = load_distribution_set(staging, role="subject", version=version)
    expected = {str(item["name"]): item for item in subjects}
    for artifact in observed.artifacts:
        descriptor = expected.get(artifact.name)
        if descriptor != artifact.descriptor():
            raise ReleaseCandidateError(
                f"release subject descriptor differs: {artifact.name}"
            )
    return observed


def _validate_manifest_contract(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    expected_commit: str | None,
    expected_tree: str | None,
) -> None:
    required = {
        "candidate_tag",
        "external_verification",
        "lifecycle",
        "mode",
        "non_subject_assets",
        "publication_allowed",
        "reproducibility",
        "schema",
        "source",
        "subject_artifacts",
        "supply_chain",
        "version",
    }
    if set(manifest) != required:
        raise ReleaseCandidateError("release manifest keys differ from v1")
    if manifest.get("schema") != RELEASE_MANIFEST_VERSION:
        raise ReleaseCandidateError("release manifest schema is unsupported")
    if manifest.get("mode") != RELEASE_MODE:
        raise ReleaseCandidateError("release candidate must remain dry-run only")
    if manifest.get("publication_allowed") is not False:
        raise ReleaseCandidateError("release candidate must remain dry-run only")
    _validate_manifest_identity(manifest, root=root)
    _validate_source_manifest(
        manifest.get("source"),
        expected_commit=expected_commit,
        expected_tree=expected_tree,
    )
    _validate_external_manifest(manifest.get("external_verification"))
    _validate_supply_chain_manifest(manifest.get("supply_chain"), root=root)


def _validate_manifest_identity(manifest: Mapping[str, Any], *, root: Path) -> None:
    version = manifest.get("version")
    tag = manifest.get("candidate_tag")
    if not isinstance(version, str) or tag != f"v{version}":
        raise ReleaseCandidateError("release manifest tag/version binding is invalid")
    if version != project_version(root) or version != package_version(root):
        raise ReleaseCandidateError("release manifest differs from source versions")
    lifecycle = manifest.get("lifecycle")
    if lifecycle != {
        "formal_stable": False,
        "stability": "draft",
        "status": "promotion_candidate",
    }:
        raise ReleaseCandidateError("release manifest makes an invalid lifecycle claim")


def _validate_source_manifest(
    source: object,
    *,
    expected_commit: str | None,
    expected_tree: str | None,
) -> None:
    if not isinstance(source, dict) or set(source) != {
        "commit",
        "source_date_epoch",
        "tree",
        "worktree_clean",
    }:
        raise ReleaseCandidateError("release candidate source binding is malformed")
    if source.get("worktree_clean") is not True:
        raise ReleaseCandidateError("release candidate does not bind a clean worktree")
    if source.get("source_date_epoch") != RELEASE_SOURCE_DATE_EPOCH:
        raise ReleaseCandidateError("release candidate uses the wrong build epoch")
    commit = source.get("commit")
    if not isinstance(commit, str) or HEX_SHA1.fullmatch(commit) is None:
        raise ReleaseCandidateError("release candidate commit is not a full SHA-1")
    tree = source.get("tree")
    if not isinstance(tree, str) or HEX_SHA1.fullmatch(tree) is None:
        raise ReleaseCandidateError("release candidate tree is not a full SHA-1")
    if (expected_commit is None) != (expected_tree is None):
        raise ReleaseCandidateError("release source expectations are incomplete")
    if expected_commit is not None and (
        commit != expected_commit or tree != expected_tree
    ):
        raise ReleaseCandidateError(
            "release candidate source differs from the expected commit tree"
        )


def _validate_external_manifest(value: object) -> None:
    expected_keys = {
        "environments",
        "external_cwd",
        "includes_independent_runtime_adapter",
        "schema_export_count",
        "semantic_outputs_identical",
        "transcript_roots",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ReleaseCandidateError("external verification manifest is malformed")
    if value["environments"] != ["source", "wheel", "sdist"]:
        raise ReleaseCandidateError("external verification environments differ")
    boolean_fields = (
        "external_cwd",
        "includes_independent_runtime_adapter",
        "semantic_outputs_identical",
    )
    if any(value[field] is not True for field in boolean_fields):
        raise ReleaseCandidateError("external verification evidence is incomplete")
    if (
        type(value["schema_export_count"]) is not int
        or value["schema_export_count"] != EXPECTED_SCHEMA_EXPORT_COUNT
    ):
        raise ReleaseCandidateError("external schema export evidence is invalid")
    roots = value["transcript_roots"]
    if not isinstance(roots, dict) or set(roots) != {"source", "wheel", "sdist"}:
        raise ReleaseCandidateError("external transcript roots are malformed")
    root_values = tuple(roots.values())
    if any(
        not isinstance(root, str)
        or not root.startswith("sha256:")
        or re.fullmatch(r"[0-9a-f]{64}", root.removeprefix("sha256:")) is None
        for root in root_values
    ):
        raise ReleaseCandidateError("external transcript roots are inconsistent")
    if len(set(root_values)) != 1:
        raise ReleaseCandidateError("external transcript roots differ")


def _validate_supply_chain_manifest(value: object, *, root: Path) -> None:
    expected = {
        "abi_diff": "ABI-DIFF.json",
        "cyclonedx": "pheroos.cdx.json",
        "migration_notes": "MIGRATION-NOTES.md",
        "migration_sources": _migration_source_descriptors(root),
        "sha256_manifest": "SHA256SUMS",
        "spdx": "pheroos.spdx.json",
    }
    if value != expected:
        raise ReleaseCandidateError("release supply-chain manifest differs")


def _validate_reproducibility(
    manifest: Mapping[str, Any],
    subject: DistributionSet,
) -> None:
    value = manifest.get("reproducibility")
    expected = {
        "comparison_hashes": subject.hashes,
        "comparison_publishable": False,
        "comparison_role": "comparison_only",
        "identical": True,
        "subject_hashes": subject.hashes,
    }
    if value != expected:
        raise ReleaseCandidateError("release reproducibility evidence is invalid")


def _validate_sboms(staging: Path) -> None:
    expected_cdx, expected_spdx = build_sboms(
        staging,
        source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
    )
    observed_cdx = _load_json_object(
        staging / "pheroos.cdx.json",
        label="CycloneDX SBOM",
    )
    observed_spdx = _load_json_object(
        staging / "pheroos.spdx.json",
        label="SPDX SBOM",
    )
    if observed_cdx != expected_cdx or observed_spdx != expected_spdx:
        raise ReleaseCandidateError("SBOMs do not bind the exact release subjects")
    if (staging / "pheroos.cdx.json").read_bytes() != _canonical_json(expected_cdx):
        raise ReleaseCandidateError("CycloneDX SBOM is not canonical")
    if (staging / "pheroos.spdx.json").read_bytes() != _canonical_json(expected_spdx):
        raise ReleaseCandidateError("SPDX SBOM is not canonical")


def _validate_auxiliary_assets(
    staging: Path,
    manifest: Mapping[str, Any],
    *,
    root: Path,
) -> None:
    assets = manifest.get("non_subject_assets")
    if not isinstance(assets, list):
        raise ReleaseCandidateError("release non-subject asset list is invalid")
    expected = [
        _asset_descriptor(staging / "pheroos.cdx.json", role="cyclonedx-1.6-sbom"),
        _asset_descriptor(staging / "pheroos.spdx.json", role="spdx-2.3-sbom"),
        _asset_descriptor(staging / "ABI-DIFF.json", role="stable-candidate-abi-diff"),
        _asset_descriptor(staging / "MIGRATION-NOTES.md", role="migration-notes"),
    ]
    if assets != expected:
        raise ReleaseCandidateError("release auxiliary asset descriptors differ")
    abi_report = _abi_report(
        ExternalVerification.from_outputs(
            "staging",
            {
                "abi-diff": CommandOutput(
                    (staging / "ABI-DIFF.json").read_bytes(),
                    b"",
                )
            },
            schema_export_count=1,
        )
    )
    if (staging / "ABI-DIFF.json").read_bytes() != _canonical_json(abi_report):
        raise ReleaseCandidateError("Stable ABI diff JSON is not canonical")
    source = manifest["source"]
    expected_notes, _ = render_migration_notes(
        root,
        version=manifest["version"],
        tag=manifest["candidate_tag"],
        commit=source["commit"],
        abi_report=abi_report,
    )
    if (staging / "MIGRATION-NOTES.md").read_bytes() != expected_notes:
        raise ReleaseCandidateError("migration notes differ from the candidate sources")


def validate_release_staging(
    staging: Path,
    *,
    root: Path = ROOT,
    expected_commit: str | None = None,
    expected_tree: str | None = None,
) -> dict[str, Any]:
    files = _staging_files(staging)
    manifest_path = files.get("release-manifest.json")
    if manifest_path is None:
        raise ReleaseCandidateError("release manifest is missing")
    manifest = _load_json_object(manifest_path, label="release manifest")
    if manifest_path.read_bytes() != _canonical_json(manifest):
        raise ReleaseCandidateError("release manifest JSON is not canonical")
    _validate_manifest_contract(
        manifest,
        root=root,
        expected_commit=expected_commit,
        expected_tree=expected_tree,
    )
    subjects = _manifest_subjects(manifest)
    _validate_staging_allowlist(files, subjects)
    _validate_sha256sums(files)
    distribution_set = _validate_subject_descriptors(staging, manifest, subjects)
    _validate_reproducibility(manifest, distribution_set)
    _validate_sboms(staging)
    _validate_auxiliary_assets(staging, manifest, root=root)
    return manifest


def _git_commit_and_clean(root: Path, *, timeout: float) -> str:
    environment = _git_object_environment()
    status = _run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=root,
        environment=environment,
        timeout=timeout,
    )
    if status.stdout:
        raise ReleaseCandidateError(
            "release-candidate dry-run requires a clean tracked/untracked worktree"
        )
    commit = _run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        environment=environment,
        timeout=timeout,
    )
    value = commit.stdout.decode("ascii", errors="strict").strip()
    if HEX_SHA1.fullmatch(value) is None:
        raise ReleaseCandidateError("git did not return a full candidate commit")
    return value


def _git_tree(root: Path, commit: str, *, timeout: float) -> str:
    tree = _run(
        ("git", "rev-parse", f"{commit}^{{tree}}"),
        cwd=root,
        environment=_git_object_environment(),
        timeout=timeout,
    )
    value = tree.stdout.decode("ascii", errors="strict").strip()
    if HEX_SHA1.fullmatch(value) is None:
        raise ReleaseCandidateError("git did not return a full candidate tree")
    return value


def _decode_git_tree_record(record: bytes) -> tuple[str, str, str, str]:
    header, separator, raw_path = record.partition(b"\t")
    fields = header.split()
    if separator != b"\t" or len(fields) != 3:
        raise ReleaseCandidateError("candidate tree contains a malformed entry")
    try:
        mode, object_type, object_id = (
            field.decode("ascii", errors="strict") for field in fields
        )
        relative = raw_path.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ReleaseCandidateError(
            "candidate tree paths and metadata must be UTF-8/ASCII"
        ) from error
    return mode, object_type, object_id, relative


def _parse_git_tree_entry(
    record: bytes,
    *,
    observed_paths: set[str],
) -> GitTreeEntry:
    mode, object_type, object_id, relative = _decode_git_tree_record(record)
    parts = tuple(relative.split("/"))
    if (
        not relative
        or relative in observed_paths
        or any(part in {"", ".", ".."} for part in parts)
        or any(part.casefold() == ".git" for part in parts)
    ):
        raise ReleaseCandidateError(
            f"candidate tree contains an unsafe path: {relative!r}"
        )
    if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
        raise ReleaseCandidateError(
            f"candidate tree entry is not a supported blob: {relative!r} "
            f"({mode} {object_type})"
        )
    if HEX_SHA1.fullmatch(object_id) is None:
        raise ReleaseCandidateError(
            f"candidate tree blob lacks a full SHA-1: {relative!r}"
        )
    observed_paths.add(relative)
    return GitTreeEntry(
        mode=mode,
        object_id=object_id,
        relative=relative,
        parts=parts,
    )


def _parse_git_tree_listing(listing: bytes) -> tuple[GitTreeEntry, ...]:
    if not listing:
        return ()
    if not listing.endswith(b"\0"):
        raise ReleaseCandidateError("candidate tree listing is not NUL terminated")
    observed_paths: set[str] = set()
    return tuple(
        _parse_git_tree_entry(record, observed_paths=observed_paths)
        for record in listing[:-1].split(b"\0")
    )


def _read_verified_git_blob(
    root: Path,
    entry: GitTreeEntry,
    *,
    environment: Mapping[str, str],
    timeout: float,
) -> bytes:
    blob = _run(
        ("git", "cat-file", "blob", entry.object_id),
        cwd=root,
        environment=environment,
        timeout=timeout,
    ).stdout
    observed_object_id = sha1(
        b"blob " + str(len(blob)).encode("ascii") + b"\0" + blob,
        usedforsecurity=False,
    ).hexdigest()
    if observed_object_id != entry.object_id:
        raise ReleaseCandidateError(
            f"candidate blob failed object identity verification: {entry.relative!r}"
        )
    return blob


def _unsafe_symlink_target(target: str) -> bool:
    return (
        not target
        or "\0" in target
        or Path(target).is_absolute()
        or any(part == "" for part in target.split("/"))
    )


def _write_candidate_symlink(
    destination: Path,
    entry: GitTreeEntry,
    blob: bytes,
) -> None:
    try:
        target = blob.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ReleaseCandidateError(
            f"candidate symlink target must be UTF-8: {entry.relative!r}"
        ) from error
    if _unsafe_symlink_target(target):
        raise ReleaseCandidateError(
            f"candidate symlink target is unsafe: {entry.relative!r}"
        )
    destination.symlink_to(target)


def _materialize_git_tree_entry(
    root: Path,
    snapshot: Path,
    entry: GitTreeEntry,
    *,
    environment: Mapping[str, str],
    timeout: float,
) -> Path | None:
    blob = _read_verified_git_blob(
        root,
        entry,
        environment=environment,
        timeout=timeout,
    )
    destination = snapshot.joinpath(*entry.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ReleaseCandidateError(
            f"candidate tree path collides during materialization: {entry.relative!r}"
        )
    if entry.mode == "120000":
        _write_candidate_symlink(destination, entry, blob)
        return destination
    destination.write_bytes(blob)
    destination.chmod(0o755 if entry.mode == "100755" else 0o644)
    return None


def _validate_materialized_symlinks(snapshot: Path, symlinks: Sequence[Path]) -> None:
    snapshot_root = snapshot.resolve()
    for link in symlinks:
        relative = link.relative_to(snapshot)
        try:
            resolved_target = link.resolve(strict=False)
        except RuntimeError as error:
            raise ReleaseCandidateError(
                f"candidate symlink cycle is not permitted: {relative}"
            ) from error
        if not resolved_target.is_relative_to(snapshot_root):
            raise ReleaseCandidateError(
                f"candidate symlink escapes the captured tree: {relative}"
            )


def _materialize_candidate_snapshot(
    root: Path,
    workspace: Path,
    *,
    commit: str,
    tree: str,
    timeout: float,
) -> Path:
    """Materialize exact Git blobs without archive attributes or checkout filters."""

    snapshot = workspace / "candidate-source"
    snapshot.mkdir()
    observed_tree = _git_tree(root, commit, timeout=timeout)
    if observed_tree != tree:
        raise ReleaseCandidateError(
            "candidate commit no longer resolves to the captured tree"
        )
    environment = _git_object_environment()
    listing = _run(
        (
            "git",
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            tree,
        ),
        cwd=root,
        environment=environment,
        timeout=timeout,
    )
    symlinks: list[Path] = []
    for entry in _parse_git_tree_listing(listing.stdout):
        link = _materialize_git_tree_entry(
            root,
            snapshot,
            entry,
            environment=environment,
            timeout=timeout,
        )
        if link is not None:
            symlinks.append(link)
    _validate_materialized_symlinks(snapshot, symlinks)
    return snapshot


def _assert_candidate_unchanged(
    root: Path,
    *,
    expected_commit: str,
    timeout: float,
) -> None:
    observed = _git_commit_and_clean(root, timeout=timeout)
    if observed != expected_commit:
        raise ReleaseCandidateError(
            "candidate commit changed while the release dry-run was executing"
        )


def run_release_candidate(
    *,
    root: Path,
    staging: Path,
    tag: str,
    python: str,
    timeout: float,
) -> dict[str, Any]:
    version = validate_tag_and_versions(tag, root=root)
    commit = _git_commit_and_clean(root, timeout=timeout)
    tree = _git_tree(root, commit, timeout=timeout)
    resolved_staging = staging.resolve()
    if resolved_staging.is_relative_to(root.resolve()):
        raise ReleaseCandidateError(
            "release staging must be outside the source checkout"
        )
    _ensure_empty_directory(resolved_staging)
    with tempfile.TemporaryDirectory(prefix="pheroos-release-candidate-") as temporary:
        workspace = Path(temporary)
        snapshot = _materialize_candidate_snapshot(
            root,
            workspace,
            commit=commit,
            tree=tree,
            timeout=timeout,
        )
        if validate_tag_and_versions(tag, root=snapshot) != version:
            raise ReleaseCandidateError("candidate snapshot version differs")
        subject = _build_distribution(
            snapshot,
            workspace / "subject",
            role="subject",
            version=version,
            python=python,
            timeout=timeout,
        )
        comparison = _build_distribution(
            snapshot,
            workspace / "comparison",
            role="comparison",
            version=version,
            python=python,
            timeout=timeout,
        )
        compare_distribution_sets(subject, comparison)
        wheel = next(item for item in subject.artifacts if item.kind == "wheel")
        sdist = next(item for item in subject.artifacts if item.kind == "sdist")
        wheel_root = _installed_import_root(
            wheel,
            workspace=workspace,
            python=python,
            timeout=timeout,
        )
        sdist_root = _installed_import_root(
            sdist,
            workspace=workspace,
            python=python,
            timeout=timeout,
        )
        verification_workspace = workspace / "verification"
        verification_workspace.mkdir()
        verifications = {
            "source": run_external_verification(
                snapshot,
                environment_name="source",
                import_root=snapshot,
                workspace=verification_workspace,
                python=python,
                version=version,
                timeout=timeout,
            ),
            "wheel": run_external_verification(
                snapshot,
                environment_name="wheel",
                import_root=wheel_root,
                workspace=verification_workspace,
                python=python,
                version=version,
                timeout=timeout,
            ),
            "sdist": run_external_verification(
                snapshot,
                environment_name="sdist",
                import_root=sdist_root,
                workspace=verification_workspace,
                python=python,
                version=version,
                timeout=timeout,
            ),
        }
        _assert_candidate_unchanged(
            root,
            expected_commit=commit,
            timeout=timeout,
        )
        manifest = assemble_release_staging(
            snapshot,
            resolved_staging,
            subject=subject,
            comparison=comparison,
            version=version,
            tag=tag,
            commit=commit,
            tree=tree,
            verifications=verifications,
        )
        _assert_candidate_unchanged(
            root,
            expected_commit=commit,
            timeout=timeout,
        )
        return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify an offline-only release-candidate dry-run",
    )
    parser.add_argument(
        "--tag",
        help="candidate tag; defaults to v<pyproject version>",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        help="empty output directory outside the source checkout",
    )
    parser.add_argument(
        "--verify-staging",
        type=Path,
        help="verify an existing staging directory without rebuilding",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--command-timeout", type=float, default=600.0)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.verify_staging is not None:
            if args.staging_dir is not None or args.tag is not None:
                parser.error("--verify-staging cannot be combined with build options")
            commit = _git_commit_and_clean(ROOT, timeout=args.command_timeout)
            tree = _git_tree(ROOT, commit, timeout=args.command_timeout)
            manifest = validate_release_staging(
                args.verify_staging,
                expected_commit=commit,
                expected_tree=tree,
            )
        else:
            if args.staging_dir is None:
                parser.error("--staging-dir is required for a dry-run build")
            version = project_version()
            manifest = run_release_candidate(
                root=ROOT,
                staging=args.staging_dir,
                tag=args.tag or f"v{version}",
                python=args.python,
                timeout=args.command_timeout,
            )
    except (OSError, ReleaseCandidateError, UnicodeDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        json.dumps(
            {
                "candidate_tag": manifest["candidate_tag"],
                "mode": manifest["mode"],
                "ok": True,
                "publication_allowed": manifest["publication_allowed"],
                "schema": manifest["schema"],
                "version": manifest["version"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
