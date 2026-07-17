from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_ci_supply_chain import ACTION_PINS, REQUIRED_JOBS, audit
from scripts.generate_release_sbom import RELEASE_SOURCE_DATE_EPOCH, build_sboms


ROOT = Path(__file__).resolve().parents[2]


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
            if '-e ".[dev]"' in line
        ]
        self.assertGreater(len(editable_lines), 0)
        lines = workflow.splitlines()
        for index in editable_lines:
            self.assertIn("--no-build-isolation", lines[index])
            self.assertIn(
                "setuptools==80.9.0 wheel==0.45.1",
                "\n".join(lines[max(0, index - 3) : index]),
            )
        provenance = workflow.split("\n  provenance:\n", maxsplit=1)[1]
        self.assertIn("actions/download-artifact@", provenance)
        self.assertIn("name: pheroos-release-artifacts", provenance)
        self.assertNotIn("python -m build", provenance)

    def test_sboms_are_deterministic_and_bind_every_distribution_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            wheel = dist / "pheroos-0.1.0-py3-none-any.whl"
            sdist = dist / "pheroos-0.1.0.tar.gz"
            wheel.write_bytes(b"deterministic-wheel-fixture")
            sdist.write_bytes(b"deterministic-sdist-fixture")

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
                Path(record["fileName"]).name: record["checksums"][0][
                    "checksumValue"
                ]
                for record in spdx["files"]
            }
            self.assertEqual(observed_cdx, expected)
            self.assertEqual(observed_spdx, expected)
            json.dumps(cyclonedx, allow_nan=False)
            json.dumps(spdx, allow_nan=False)

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
