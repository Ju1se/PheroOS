from __future__ import annotations

from pathlib import Path

import pytest

from tools.safe_tools import WorkspaceTools


def test_list_and_read_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    tools = WorkspaceTools(tmp_path)

    listed = tools.list_files(pattern="*.md")
    read = tools.read_file(path="README.md")

    assert listed.ok is True
    assert listed.data["files"] == ["README.md"]
    assert read.ok is True
    assert read.data["content"] == "hello"


def test_write_file_is_restricted_to_workspace(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path)

    result = tools.write_file(path="notes/todo.md", content="ship it")

    assert result.ok is True
    assert (tmp_path / "notes" / "todo.md").read_text(encoding="utf-8") == "ship it"

    with pytest.raises(ValueError, match="outside workspace"):
        tools.write_file(path="../outside.md", content="nope")


def test_run_pytest_rejects_unsafe_args(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path)

    result = tools.run_pytest(args=["--override-ini=pythonpath=/tmp"])

    assert result.ok is False
    assert "not allowed" in (result.error or "")
