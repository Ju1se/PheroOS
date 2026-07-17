#!/usr/bin/env python3
from __future__ import annotations

"""Generate deterministic CycloneDX 1.6 and SPDX 2.3 release SBOMs."""

import argparse
from datetime import datetime, timezone
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
import uuid


ROOT = Path(__file__).resolve().parents[1]
RELEASE_SOURCE_DATE_EPOCH = 315532800


def _project_version() -> str:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"\s*$',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise ValueError("pyproject.toml does not declare a project version")
    return match.group(1)


def _artifacts(directory: Path) -> list[tuple[Path, str, str]]:
    artifacts = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and (
            path.suffix == ".whl" or path.name.endswith(".tar.gz")
        ):
            content = path.read_bytes()
            artifacts.append(
                (
                    path,
                    sha256(content).hexdigest(),
                    sha1(content, usedforsecurity=False).hexdigest(),
                )
            )
    if not artifacts:
        raise ValueError("release SBOM requires at least one wheel or sdist")
    if not any(path.suffix == ".whl" for path, _, _ in artifacts):
        raise ValueError("release SBOM requires a wheel")
    if not any(path.name.endswith(".tar.gz") for path, _, _ in artifacts):
        raise ValueError("release SBOM requires an sdist")
    return artifacts


def build_sboms(
    directory: Path,
    *,
    source_date_epoch: int,
) -> tuple[dict[str, object], dict[str, object]]:
    version = _project_version()
    artifacts = _artifacts(directory)
    digest_material = "\n".join(
        f"{path.name}:{digest}" for path, digest, _ in artifacts
    )
    namespace_digest = sha256(digest_material.encode("utf-8")).hexdigest()
    timestamp = datetime.fromtimestamp(
        source_date_epoch,
        tz=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
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
                "dependsOn": [
                    f"urn:sha256:{digest}" for _, digest, _ in artifacts
                ],
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
    spdx = {
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
