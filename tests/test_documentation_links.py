from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _documentation_files() -> tuple[Path, ...]:
    roots = (
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "SPEC.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "CHANGELOG.md",
    )
    return tuple(path for path in roots if path.is_file()) + tuple(
        sorted((ROOT / "docs").rglob("*.md"))
    )


def test_relative_documentation_links_resolve_inside_the_repository() -> None:
    missing: list[str] = []
    for source in _documentation_files():
        text = source.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if (
                not target
                or target.startswith(("#", "http://", "https://", "mailto:"))
            ):
                continue
            path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path_text:
                continue
            resolved = (
                ROOT / path_text.lstrip("/")
                if path_text.startswith("/")
                else source.parent / path_text
            ).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                missing.append(
                    f"{source.relative_to(ROOT).as_posix()} -> outside:{target}"
                )
                continue
            if not resolved.exists():
                missing.append(
                    f"{source.relative_to(ROOT).as_posix()} -> {target}"
                )

    assert missing == []


def test_english_and_chinese_readmes_link_the_same_maintained_materials() -> None:
    english = set(LINK.findall((ROOT / "README.md").read_text(encoding="utf-8")))
    chinese = set(
        LINK.findall((ROOT / "README.zh-CN.md").read_text(encoding="utf-8"))
    )
    english.discard("README.zh-CN.md")
    chinese.discard("README.md")

    assert english == chinese
