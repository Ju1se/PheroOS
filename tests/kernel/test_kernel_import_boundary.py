import ast
import subprocess
import sys
from pathlib import Path

from pheroos.conformance.checks.kernel_import_boundary import check


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {"app", "runtime", "tools", "capabilities", "fastapi", "langgraph", "litellm"}


def test_core_import_does_not_load_removed_runtime_modules() -> None:
    code = (
        "import sys; "
        "import pheroos, pheroos.protocol, pheroos.kernel, pheroos.governance; "
        "forbidden={'app','runtime','tools','capabilities','fastapi','langgraph','litellm'}; "
        "loaded=sorted(name for name in sys.modules if name.split('.')[0] in forbidden); "
        "assert not loaded, loaded"
    )

    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_core_package_has_no_forbidden_import_roots() -> None:
    offenders = []
    for path in (ROOT / "pheroos").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if module.split(".", 1)[0] in FORBIDDEN:
                        offenders.append(f"{path}:{module}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".", 1)[0] in FORBIDDEN:
                    offenders.append(f"{path}:{module}")

    assert offenders == []


def test_core_package_respects_package_import_dag() -> None:
    result = check(ROOT)

    assert result.ok is True, result.detail


def test_package_import_dag_resolves_relative_cross_package_imports(tmp_path: Path) -> None:
    protocol = tmp_path / "pheroos" / "protocol"
    protocol.mkdir(parents=True)
    (tmp_path / "pheroos" / "__init__.py").write_text("", encoding="utf-8")
    (protocol / "__init__.py").write_text("", encoding="utf-8")
    (protocol / "bad.py").write_text("from ..governance import Candidate\n", encoding="utf-8")

    result = check(tmp_path)

    assert result.ok is False
    assert result.name == "package_import_boundary"
    assert "pheroos.governance" in result.detail


def test_package_import_dag_resolves_absolute_root_alias_imports(tmp_path: Path) -> None:
    protocol = tmp_path / "pheroos" / "protocol"
    protocol.mkdir(parents=True)
    (tmp_path / "pheroos" / "__init__.py").write_text("", encoding="utf-8")
    (protocol / "__init__.py").write_text("", encoding="utf-8")
    (protocol / "bad.py").write_text(
        "from pheroos import governance as forbidden_governance\n",
        encoding="utf-8",
    )

    result = check(tmp_path)

    assert result.ok is False
    assert "pheroos.governance" in result.detail
