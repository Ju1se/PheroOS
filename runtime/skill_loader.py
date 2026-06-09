from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from runtime.legacy_skill_matching import (
    infer_task_skill_names,
    needs_data_analysis,
    needs_document_writing,
    needs_value_investing_research,
    needs_web_research,
    needs_wrds_data,
)


FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z", re.DOTALL)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+-]+|[\u4e00-\u9fff]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "do",
    "for",
    "in",
    "is",
    "it",
    "not",
    "of",
    "or",
    "the",
    "this",
    "to",
    "use",
    "when",
    "with",
}


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    content: str

    def to_public_dict(self, *, include_content: bool) -> dict[str, str]:
        payload = {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
        }
        if include_content:
            payload["content"] = self.content
        return payload


class SkillLoader:
    def __init__(self, skills_dir: str | Path = "skills") -> None:
        self.skills_dir = Path(skills_dir)

    def list_skills(self) -> list[Skill]:
        if not self.skills_dir.exists():
            return []
        skills = []
        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
            skills.append(self.load_skill(skill_file))
        return skills

    def get_skill(self, name: str) -> Skill | None:
        for skill in self.list_skills():
            if skill.name == name:
                return skill
        return None

    def match(self, task: str, *, explicit_names: list[str] | None = None, limit: int = 3) -> list[Skill]:
        skills = self.list_skills()
        if explicit_names:
            by_name = {skill.name: skill for skill in skills}
            missing = [name for name in explicit_names if name not in by_name]
            if missing:
                raise ValueError(f"Unknown skills: {', '.join(missing)}")
            return [by_name[name] for name in explicit_names]

        task_tokens = set(tokenize(task))
        by_name = {skill.name: skill for skill in skills}
        score_by_name: dict[str, tuple[int, Skill]] = {}
        for skill in skills:
            haystack = f"{skill.name} {skill.description}".lower()
            skill_tokens = set(tokenize(haystack))
            score = len(task_tokens & skill_tokens)
            if skill.name.lower() in task.lower():
                score += 3
            if score > 0:
                score_by_name[skill.name] = (score, skill)

        for inferred_name in infer_task_skill_names(task):
            skill = by_name.get(inferred_name)
            if skill:
                current_score = score_by_name.get(skill.name, (0, skill))[0]
                score_by_name[skill.name] = (max(current_score, 10), skill)

        scored = [(score, skill.name, skill) for score, skill in score_by_name.values()]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [skill for _, _, skill in scored[:limit]]

    def load_skill(self, path: str | Path) -> Skill:
        skill_path = Path(path)
        content = skill_path.read_text(encoding="utf-8")
        frontmatter, _ = split_frontmatter(content)
        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not name or not description:
            raise ValueError(f"{skill_path} must define frontmatter name and description")
        return Skill(
            name=name,
            description=description,
            path=skill_path,
            content=content,
        )


def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    return parse_frontmatter(match.group("meta")), match.group("body")


def parse_frontmatter(raw: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"Invalid frontmatter line: {line}")
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text) if token.lower() not in STOPWORDS]
