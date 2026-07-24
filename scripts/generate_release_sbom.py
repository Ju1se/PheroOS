#!/usr/bin/env python3
"""Generate deterministic CycloneDX 1.6 and SPDX 2.3 release SBOMs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import Parser
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
import tarfile
import uuid
import zipfile


RELEASE_SOURCE_DATE_EPOCH = 315532800


def _metadata_version(payload: bytes, *, label: str) -> str:
    try:
        metadata = Parser().parsestr(payload.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} metadata is not UTF-8") from error
    names = metadata.get_all("Name", [])
    versions = metadata.get_all("Version", [])
    if names != ["pheroos"]:
        raise ValueError(f"{label} metadata must identify pheroos exactly once")
    if len(versions) != 1 or not versions[0]:
        raise ValueError(f"{label} metadata must contain exactly one Version")
    return versions[0]


def _wheel_version_component(version: str) -> str:
    return version.replace("-", "_")


def _wheel_filename_matches(path: Path, *, version: str) -> bool:
    if path.suffix != ".whl":
        return False
    components = path.name.removesuffix(".whl").split("-")
    if len(components) not in {5, 6}:
        return False
    if components[:2] != ["pheroos", _wheel_version_component(version)]:
        return False
    if (
        len(components) == 6
        and re.fullmatch(r"[0-9][A-Za-z0-9_]*", components[2]) is None
    ):
        return False
    return all(
        re.fullmatch(r"[A-Za-z0-9_.]+", component) is not None
        for component in components[-3:]
    )


def _wheel_version(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_names = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA") and name.count("/") == 1
            ]
            if len(metadata_names) != 1:
                raise ValueError("wheel must contain one top-level METADATA")
            version = _metadata_version(
                archive.read(metadata_names[0]),
                label="wheel",
            )
            expected_directory = (
                f"pheroos-{_wheel_version_component(version)}.dist-info"
            )
            if metadata_names[0] != f"{expected_directory}/METADATA":
                raise ValueError("wheel dist-info directory does not match metadata")
            if not _wheel_filename_matches(path, version=version):
                raise ValueError("wheel filename does not match metadata")
            return version
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"wheel metadata cannot be read: {error}") from error


def _sdist_version(path: Path) -> str:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            metadata_members = [
                member
                for member in archive.getmembers()
                if member.isfile()
                and member.name.endswith("/PKG-INFO")
                and member.name.count("/") == 1
            ]
            if len(metadata_members) != 1:
                raise ValueError("sdist must contain one top-level PKG-INFO")
            extracted = archive.extractfile(metadata_members[0])
            if extracted is None:
                raise ValueError("sdist PKG-INFO cannot be read")
            version = _metadata_version(extracted.read(), label="sdist")
            expected_root = f"pheroos-{version}"
            if metadata_members[0].name != f"{expected_root}/PKG-INFO":
                raise ValueError("sdist root directory does not match metadata")
            if path.name != f"{expected_root}.tar.gz":
                raise ValueError("sdist filename does not match metadata")
            return version
    except (OSError, tarfile.TarError) as error:
        raise ValueError(f"sdist metadata cannot be read: {error}") from error


def _artifacts(directory: Path) -> list[tuple[Path, str, str]]:
    artifacts = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz")):
            content = path.read_bytes()
            artifacts.append(
                (
                    path,
                    sha256(content).hexdigest(),
                    sha1(content, usedforsecurity=False).hexdigest(),
                )
            )
    wheels = [path for path, _, _ in artifacts if path.suffix == ".whl"]
    sdists = [path for path, _, _ in artifacts if path.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("release SBOM requires exactly one wheel and one sdist")
    return artifacts


def build_sboms(
    directory: Path,
    *,
    source_date_epoch: int,
) -> tuple[dict[str, object], dict[str, object]]:
    artifacts = _artifacts(directory)
    versions = {
        _wheel_version(path) if path.suffix == ".whl" else _sdist_version(path)
        for path, _, _ in artifacts
    }
    if len(versions) != 1:
        raise ValueError("wheel and sdist metadata versions differ")
    version = versions.pop()
    digest_material = "\n".join(
        f"{path.name}:{digest}" for path, digest, _ in artifacts
    )
    namespace_digest = sha256(digest_material.encode("utf-8")).hexdigest()
    timestamp = (
        datetime.fromtimestamp(
            source_date_epoch,
            tz=timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z")
    )
    package_ref = f"pkg:pypi/pheroos@{version}"

    cyclonedx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, namespace_digest)}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "pheroos-release-sbom",
                        "version": "1",
                    }
                ]
            },
            "component": {
                "type": "library",
                "bom-ref": package_ref,
                "name": "pheroos",
                "version": version,
                "purl": package_ref,
                "licenses": [{"license": {"id": "MIT"}}],
            },
        },
        "components": [
            {
                "type": "file",
                "bom-ref": f"urn:sha256:{digest}",
                "name": path.name,
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "properties": [
                    {"name": "pheroos:distribution-path", "value": f"dist/{path.name}"}
                ],
            }
            for path, digest, _ in artifacts
        ],
        "dependencies": [
            {
                "ref": package_ref,
                "dependsOn": [f"urn:sha256:{digest}" for _, digest, _ in artifacts],
            }
        ],
    }

    file_records = [
        {
            "fileName": f"dist/{path.name}",
            "SPDXID": f"SPDXRef-File-{digest}",
            "checksums": [
                {"algorithm": "SHA256", "checksumValue": digest},
                {"algorithm": "SHA1", "checksumValue": sha1_digest},
            ],
        }
        for path, digest, sha1_digest in artifacts
    ]
    package_verification_code = sha1(
        "".join(sorted(item[2] for item in artifacts)).encode("ascii"),
        usedforsecurity=False,
    ).hexdigest()
    spdx: dict[str, object] = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"pheroos-{version}-release",
        "documentNamespace": f"https://pheroos.dev/spdx/{namespace_digest}",
        "creationInfo": {
            "created": timestamp,
            "creators": ["Tool: pheroos-release-sbom-1"],
            "licenseListVersion": "3.25",
        },
        "packages": [
            {
                "name": "pheroos",
                "SPDXID": "SPDXRef-Package-pheroos",
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "packageVerificationCode": {
                    "packageVerificationCodeValue": package_verification_code
                },
                "licenseConcluded": "MIT",
                "licenseDeclared": "MIT",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": package_ref,
                    }
                ],
            }
        ],
        "files": file_records,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package-pheroos",
            },
            *[
                {
                    "spdxElementId": "SPDXRef-Package-pheroos",
                    "relationshipType": "CONTAINS",
                    "relatedSpdxElement": record["SPDXID"],
                }
                for record in file_records
            ],
        ],
    }
    return cyclonedx, spdx


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cyclonedx", type=Path, required=True)
    parser.add_argument("--spdx", type=Path, required=True)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=RELEASE_SOURCE_DATE_EPOCH,
    )
    args = parser.parse_args()
    cyclonedx, spdx = build_sboms(
        args.directory,
        source_date_epoch=args.source_date_epoch,
    )
    _write(args.cyclonedx, cyclonedx)
    _write(args.spdx, spdx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
