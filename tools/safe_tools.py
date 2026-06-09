from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_EXCLUDES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
MAX_FILE_BYTES = 256_000
MAX_TOOL_OUTPUT_CHARS = 12_000


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"ok": self.ok, "data": self.data}
        if self.error:
            payload["error"] = self.error
        return payload


class WorkspaceTools:
    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def list_files(
        self,
        *,
        path: str = ".",
        pattern: str = "*",
        max_results: int = 200,
    ) -> ToolResult:
        root = self.resolve_workspace_path(path)
        if not root.exists():
            return ToolResult(False, {"path": path}, "path does not exist")
        if not root.is_dir():
            return ToolResult(False, {"path": path}, "path must be a directory")

        max_results = clamp_int(max_results, minimum=1, maximum=1_000)
        files = []
        for candidate in sorted(root.rglob(pattern)):
            if len(files) >= max_results:
                break
            if should_exclude(candidate):
                continue
            if candidate.is_file():
                files.append(str(candidate.relative_to(self.workspace_root)))

        return ToolResult(
            True,
            {
                "path": str(root.relative_to(self.workspace_root)),
                "pattern": pattern,
                "files": files,
                "truncated": len(files) >= max_results,
            },
        )

    def read_file(self, *, path: str, max_bytes: int = MAX_FILE_BYTES) -> ToolResult:
        file_path = self.resolve_workspace_path(path)
        if not file_path.exists():
            return ToolResult(False, {"path": path}, "file does not exist")
        if not file_path.is_file():
            return ToolResult(False, {"path": path}, "path must be a file")

        max_bytes = clamp_int(max_bytes, minimum=1, maximum=MAX_FILE_BYTES)
        raw = file_path.read_bytes()
        truncated = len(raw) > max_bytes
        content = raw[:max_bytes].decode("utf-8", errors="replace")
        return ToolResult(
            True,
            {
                "path": str(file_path.relative_to(self.workspace_root)),
                "content": content,
                "bytes": len(raw),
                "truncated": truncated,
            },
        )

    def write_file(
        self,
        *,
        path: str,
        content: str,
        create_parents: bool = True,
    ) -> ToolResult:
        file_path = self.resolve_workspace_path(path)
        if file_path.exists() and file_path.is_dir():
            return ToolResult(False, {"path": path}, "path is a directory")
        if not isinstance(content, str):
            return ToolResult(False, {"path": path}, "content must be a string")

        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            return ToolResult(
                False,
                {"path": path, "bytes": len(encoded), "max_bytes": MAX_FILE_BYTES},
                "content is too large",
            )

        existed = file_path.exists()
        if create_parents:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return ToolResult(
            True,
            {
                "path": str(file_path.relative_to(self.workspace_root)),
                "bytes": len(encoded),
                "created": not existed,
            },
        )

    def run_pytest(
        self,
        *,
        args: list[str] | None = None,
        timeout_seconds: int = 120,
    ) -> ToolResult:
        try:
            safe_args = validate_pytest_args(args or [])
        except ValueError as exc:
            return ToolResult(False, {"args": args or []}, str(exc))

        timeout_seconds = clamp_int(timeout_seconds, minimum=1, maximum=300)
        command = [sys.executable, "-m", "pytest", *safe_args]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                False,
                {
                    "command": command,
                    "timeout_seconds": timeout_seconds,
                    "stdout": truncate(exc.stdout or ""),
                    "stderr": truncate(exc.stderr or ""),
                },
                "pytest timed out",
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        return ToolResult(
            completed.returncode == 0,
            {
                "command": command,
                "returncode": completed.returncode,
                "duration_ms": duration_ms,
                "stdout": truncate(completed.stdout),
                "stderr": truncate(completed.stderr),
            },
            None if completed.returncode == 0 else "pytest failed",
        )

    def resolve_workspace_path(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string")
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError(f"path is outside workspace: {path}") from exc

        return resolved


def should_exclude(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDES for part in path.parts)


def clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(number, maximum))


def truncate(value: str) -> str:
    if len(value) <= MAX_TOOL_OUTPUT_CHARS:
        return value
    return value[:MAX_TOOL_OUTPUT_CHARS] + "\n...[truncated]"


def validate_pytest_args(args: list[str]) -> list[str]:
    if not isinstance(args, list):
        raise ValueError("pytest args must be a list")

    safe_args = []
    for arg in args:
        if not isinstance(arg, str) or not arg:
            raise ValueError("pytest args must be non-empty strings")
        if "\x00" in arg or "\n" in arg or "\r" in arg:
            raise ValueError("pytest args contain invalid characters")
        if arg in {"-c", "--override-ini"} or arg.startswith("--override-ini"):
            raise ValueError(f"pytest arg is not allowed: {arg}")
        if arg.startswith("/"):
            raise ValueError(f"absolute pytest paths are not allowed: {arg}")
        if arg.startswith("..") or f"{os.sep}.." in arg:
            raise ValueError(f"pytest path traversal is not allowed: {arg}")
        safe_args.append(arg)
    return safe_args
