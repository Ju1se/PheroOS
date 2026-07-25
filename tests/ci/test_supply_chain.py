from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from scripts.check_ci_supply_chain import (
    ACTION_PINS,
    CONSTRAINTS,
    RELEASE_CANDIDATE_ACTION_PINS,
    RELEASE_CANDIDATE_WORKFLOW,
    REQUIRED_JOBS,
    audit,
    audit_release_candidate_workflow,
    parse_hashed_requirements,
)
from scripts.generate_release_sbom import RELEASE_SOURCE_DATE_EPOCH, build_sboms


ROOT = Path(__file__).resolve().parents[2]


def _write_distribution_pair(directory: Path, *, version: str = "0.1.0") -> None:
    metadata = (f"Metadata-Version: 2.4\nName: pheroos\nVersion: {version}\n\n").encode(
        "utf-8"
    )
    wheel = directory / f"pheroos-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"pheroos-{version}.dist-info/METADATA", metadata)
    sdist = directory / f"pheroos-{version}.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pheroos-{version}/PKG-INFO")
        info.size = len(metadata)
        info.mtime = 0
        archive.addfile(info, BytesIO(metadata))


class SupplyChainPolicyTests(unittest.TestCase):
    def test_workflow_constraints_actions_and_permissions_are_closed(self) -> None:
        self.assertEqual(audit(), [])

        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )
        for action, revision in ACTION_PINS.items():
            self.assertIn(f"uses: {action}@{revision}", workflow)
        for job in REQUIRED_JOBS:
            self.assertIn(f"  {job}:\n", workflow)
        editable_lines = [
            index
            for index, line in enumerate(workflow.splitlines())
            if "pip install --no-deps --no-build-isolation -e ." in line
        ]
        self.assertGreater(len(editable_lines), 0)
        lines = workflow.splitlines()
        for index in editable_lines:
            self.assertIn("--no-deps", lines[index])
            self.assertIn("--no-build-isolation", lines[index])
            self.assertIn(
                "--require-hashes --only-binary=:all: "
                "-r requirements/ci-constraints.txt",
                "\n".join(lines[max(0, index - 3) : index]),
            )
        provenance = workflow.split("\n  provenance:\n", maxsplit=1)[1]
        self.assertIn("actions/download-artifact@", provenance)
        self.assertIn("name: pheroos-release-artifacts", provenance)
        self.assertNotIn("python -m build", provenance)

    def test_sboms_are_deterministic_and_bind_every_distribution_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            _write_distribution_pair(dist)
            wheel = dist / "pheroos-0.1.0-py3-none-any.whl"
            sdist = dist / "pheroos-0.1.0.tar.gz"

            first = build_sboms(
                dist,
                source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
            )
            second = build_sboms(
                dist,
                source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
            )
            self.assertEqual(first, second)
            cyclonedx, spdx = first

            self.assertEqual(cyclonedx["bomFormat"], "CycloneDX")
            self.assertEqual(cyclonedx["specVersion"], "1.6")
            self.assertEqual(spdx["spdxVersion"], "SPDX-2.3")
            expected = {
                wheel.name: sha256(wheel.read_bytes()).hexdigest(),
                sdist.name: sha256(sdist.read_bytes()).hexdigest(),
            }
            observed_cdx = {
                component["name"]: component["hashes"][0]["content"]
                for component in cyclonedx["components"]
            }
            observed_spdx = {
                Path(record["fileName"]).name: record["checksums"][0]["checksumValue"]
                for record in spdx["files"]
            }
            self.assertEqual(observed_cdx, expected)
            self.assertEqual(observed_spdx, expected)
            json.dumps(cyclonedx, allow_nan=False)
            json.dumps(spdx, allow_nan=False)

    def test_sbom_version_comes_from_matching_distribution_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            _write_distribution_pair(dist, version="9.8.7")

            cyclonedx, spdx = build_sboms(
                dist,
                source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
            )

            self.assertEqual(
                cyclonedx["metadata"]["component"]["version"],  # type: ignore[index]
                "9.8.7",
            )
            self.assertEqual(spdx["packages"][0]["versionInfo"], "9.8.7")  # type: ignore[index]

    def test_sbom_rejects_duplicate_identity_metadata(self) -> None:
        scenarios = (
            (
                "duplicate Name",
                "Metadata-Version: 2.4\nName: pheroos\nName: other\nVersion: 0.1.0\n\n",
                "identify pheroos exactly once",
            ),
            (
                "duplicate Version",
                "Metadata-Version: 2.4\n"
                "Name: pheroos\n"
                "Version: 0.1.0\n"
                "Version: 9.9.9\n\n",
                "exactly one Version",
            ),
        )
        for scenario, source, message in scenarios:
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as temporary,
            ):
                metadata = source.encode("utf-8")
                dist = Path(temporary)
                wheel = dist / "pheroos-0.1.0-py3-none-any.whl"
                with zipfile.ZipFile(
                    wheel,
                    mode="w",
                    compression=zipfile.ZIP_STORED,
                ) as archive:
                    archive.writestr("pheroos-0.1.0.dist-info/METADATA", metadata)
                sdist = dist / "pheroos-0.1.0.tar.gz"
                with tarfile.open(sdist, mode="w:gz") as archive:
                    info = tarfile.TarInfo("pheroos-0.1.0/PKG-INFO")
                    info.size = len(metadata)
                    info.mtime = 0
                    archive.addfile(info, BytesIO(metadata))

                with self.assertRaisesRegex(ValueError, message):
                    build_sboms(
                        dist,
                        source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
                    )

    def test_sbom_rejects_distribution_filename_or_archive_root_mismatch(self) -> None:
        metadata = ("Metadata-Version: 2.4\nName: pheroos\nVersion: 0.1.0\n\n").encode(
            "utf-8"
        )
        scenarios = (
            (
                "unrelated-0.1.0-py3-none-any.whl",
                "pheroos-0.1.0.dist-info/METADATA",
                "pheroos-0.1.0.tar.gz",
                "pheroos-0.1.0/PKG-INFO",
                "wheel filename",
            ),
            (
                "pheroos-0.1.0-py3-none-any.whl",
                "unrelated-0.1.0.dist-info/METADATA",
                "pheroos-0.1.0.tar.gz",
                "pheroos-0.1.0/PKG-INFO",
                "wheel dist-info",
            ),
            (
                "pheroos-0.1.0-py3-none-any.whl",
                "pheroos-0.1.0.dist-info/METADATA",
                "unrelated-0.1.0.tar.gz",
                "pheroos-0.1.0/PKG-INFO",
                "sdist filename",
            ),
            (
                "pheroos-0.1.0-py3-none-any.whl",
                "pheroos-0.1.0.dist-info/METADATA",
                "pheroos-0.1.0.tar.gz",
                "unrelated-0.1.0/PKG-INFO",
                "sdist root",
            ),
        )
        for wheel_name, wheel_metadata, sdist_name, pkg_info, message in scenarios:
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as temporary,
            ):
                dist = Path(temporary)
                with zipfile.ZipFile(
                    dist / wheel_name,
                    mode="w",
                    compression=zipfile.ZIP_STORED,
                ) as archive:
                    archive.writestr(wheel_metadata, metadata)
                with tarfile.open(dist / sdist_name, mode="w:gz") as archive:
                    info = tarfile.TarInfo(pkg_info)
                    info.size = len(metadata)
                    info.mtime = 0
                    archive.addfile(info, BytesIO(metadata))

                with self.assertRaisesRegex(ValueError, message):
                    build_sboms(
                        dist,
                        source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
                    )

    def test_release_candidate_workflow_uses_only_reviewed_full_sha_actions(
        self,
    ) -> None:
        workflow = RELEASE_CANDIDATE_WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(audit_release_candidate_workflow(workflow), [])
        for action, revision in RELEASE_CANDIDATE_ACTION_PINS.items():
            self.assertIn(f"uses: {action}@{revision}", workflow)

        unpinned = workflow.replace(
            next(iter(RELEASE_CANDIDATE_ACTION_PINS.values())),
            "v0",
            1,
        )
        failures = audit_release_candidate_workflow(unpinned)
        self.assertTrue(any("full commit SHA" in item for item in failures))

        escalated = workflow.replace(
            "  release-candidate-dry-run:\n",
            "  release-candidate-dry-run:\n    permissions: write-all\n",
            1,
        )
        self.assertTrue(
            any(
                "permissions" in item
                for item in audit_release_candidate_workflow(escalated)
            )
        )

        masked = workflow.replace(
            "        run: python scripts/release_candidate.py --staging-dir "
            '"$RUNNER_TEMP/pheroos-release-candidate"\n',
            "        run: |\n"
            "          if false; then\n"
            "            python scripts/release_candidate.py --staging-dir "
            '"$RUNNER_TEMP/pheroos-release-candidate"\n'
            "          fi\n",
            1,
        )
        self.assertTrue(
            any(
                "masked" in item or "orchestrator" in item
                for item in audit_release_candidate_workflow(masked)
            )
        )

        execution_context_mutations = (
            (
                '  SOURCE_DATE_EPOCH: "315532800"\n',
                '  SOURCE_DATE_EPOCH: "315532800"\n  PATH: /tmp/forged\n',
            ),
            (
                "        with:\n          persist-credentials: false\n",
                "        with:\n"
                "          persist-credentials: false\n"
                "          ref: main\n",
            ),
            (
                "      - name: Build the offline release-candidate staging set\n",
                "      - name: Build the offline release-candidate staging set\n"
                "        if: ${{ false }}\n",
            ),
            (
                "    runs-on: ubuntu-latest\n",
                "    runs-on: self-hosted\n",
            ),
            (
                "\njobs:\n  release-candidate-dry-run:\n",
                "\njobs:\n"
                '  "shadow":\n'
                "    permissions: write-all\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: true\n"
                "  release-candidate-dry-run:\n",
            ),
        )
        for current, mutated_value in execution_context_mutations:
            with self.subTest(mutated_value=mutated_value):
                context_mutation = workflow.replace(current, mutated_value, 1)
                self.assertNotEqual(context_mutation, workflow)
                self.assertTrue(
                    any(
                        "contract" in item
                        for item in audit_release_candidate_workflow(context_mutation)
                    )
                )

        unhashed = workflow.replace(
            "pip install --require-hashes --only-binary=:all: "
            "-r requirements/ci-constraints.txt",
            "pip install build==1.3.0",
            1,
        )
        self.assertTrue(
            any(
                "hashed lock" in item
                for item in audit_release_candidate_workflow(unhashed)
            )
        )

    def test_ci_lock_is_hash_closed_and_rejects_any_unhashed_entry(self) -> None:
        pins = parse_hashed_requirements(CONSTRAINTS.read_bytes())

        self.assertIn("pip", pins)
        self.assertIn("coverage", pins)
        self.assertIn("mypy", pins)
        self.assertIn("ruff", pins)

        malformed = CONSTRAINTS.read_bytes().replace(
            b"attrs==25.3.0 \\\n",
            b"attrs==25.3.0\n",
            1,
        )
        with self.assertRaisesRegex(ValueError, "hashed pin"):
            parse_hashed_requirements(malformed)

    def test_generated_release_sboms_match_current_dist_when_present(self) -> None:
        dist = ROOT / "dist"
        cdx_path = ROOT / "sbom" / "pheroos.cdx.json"
        spdx_path = ROOT / "sbom" / "pheroos.spdx.json"
        if not (dist.is_dir() and cdx_path.is_file() and spdx_path.is_file()):
            self.skipTest("release artifacts are generated only in supply-chain CI")

        cyclonedx, spdx = build_sboms(
            dist,
            source_date_epoch=RELEASE_SOURCE_DATE_EPOCH,
        )
        self.assertEqual(json.loads(cdx_path.read_text(encoding="utf-8")), cyclonedx)
        self.assertEqual(json.loads(spdx_path.read_text(encoding="utf-8")), spdx)


if __name__ == "__main__":
    unittest.main()
