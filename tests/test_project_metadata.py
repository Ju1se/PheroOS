from pathlib import Path
import tomllib

import pheroos


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert pheroos.__version__ == pyproject["project"]["version"]


def test_open_protocol_materials_exist() -> None:
    for path in [
        "SPEC.md",
        "CHANGELOG.md",
        "docs/process/api-lifecycle.md",
        "docs/process/release-checklist.md",
        "docs/protocol/extension-points.md",
    ]:
        assert Path(path).is_file()
