from __future__ import annotations

from pathlib import Path

import pytest

from runtime.skill_loader import SkillLoader, needs_value_investing_research


def write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: {description}
---

# {name}
""",
        encoding="utf-8",
    )


def test_list_skills_reads_frontmatter(tmp_path: Path) -> None:
    write_skill(tmp_path, "fastapi-api", "Build FastAPI APIs and tests.")

    skills = SkillLoader(tmp_path).list_skills()

    assert len(skills) == 1
    assert skills[0].name == "fastapi-api"
    assert "FastAPI" in skills[0].description


def test_match_skills_by_keyword(tmp_path: Path) -> None:
    write_skill(tmp_path, "fastapi-api", "Build FastAPI REST APIs.")
    write_skill(tmp_path, "python-testing", "Write pytest coverage.")

    matches = SkillLoader(tmp_path).match("Add a FastAPI upload endpoint")

    assert [skill.name for skill in matches] == ["fastapi-api"]


def test_match_ignores_common_stopwords(tmp_path: Path) -> None:
    write_skill(tmp_path, "fastapi-api", "Use this skill for FastAPI REST APIs.")

    matches = SkillLoader(tmp_path).match("List markdown files in this workspace. Do not write files.")

    assert matches == []


def test_match_infers_web_research_for_company_analysis(tmp_path: Path) -> None:
    write_skill(tmp_path, "web-research", "Research public web sources.")

    matches = SkillLoader(tmp_path).match("分析药明康德")

    assert [skill.name for skill in matches] == ["web-research"]


def test_match_infers_web_research_for_known_company_name(tmp_path: Path) -> None:
    write_skill(tmp_path, "web-research", "Research public web sources.")

    matches = SkillLoader(tmp_path).match("药明康德")

    assert [skill.name for skill in matches] == ["web-research"]


def test_match_infers_value_research_for_known_company_name(tmp_path: Path) -> None:
    write_skill(tmp_path, "web-research", "Research public web sources.")
    write_skill(tmp_path, "value-investing-research", "Value investing research.")

    matches = SkillLoader(tmp_path).match("五粮液")

    assert {skill.name for skill in matches} == {"web-research", "value-investing-research"}


def test_match_infers_value_research_for_hudian_gufen(tmp_path: Path) -> None:
    write_skill(tmp_path, "web-research", "Research public web sources.")
    write_skill(tmp_path, "value-investing-research", "Value investing research.")

    matches = SkillLoader(tmp_path).match("沪电股份")

    assert {skill.name for skill in matches} == {"web-research", "value-investing-research"}


def test_swarm_system_research_does_not_need_value_investing() -> None:
    assert needs_value_investing_research("研究蚁群以及蜂群的群体决策机制可以对multi-agent系统的借鉴") is False


def test_match_infers_document_writing(tmp_path: Path) -> None:
    write_skill(tmp_path, "document-writing", "Document writing.")

    matches = SkillLoader(tmp_path).match("帮我撰写一份项目 proposal")

    assert [skill.name for skill in matches] == ["document-writing"]


def test_match_infers_data_analysis(tmp_path: Path) -> None:
    write_skill(tmp_path, "data-analysis", "Data analysis.")

    matches = SkillLoader(tmp_path).match("Analyze this CSV dataset and compute summary statistics")

    assert [skill.name for skill in matches] == ["data-analysis"]


def test_explicit_unknown_skill_raises(tmp_path: Path) -> None:
    write_skill(tmp_path, "fastapi-api", "Build FastAPI REST APIs.")

    with pytest.raises(ValueError, match="Unknown skills"):
        SkillLoader(tmp_path).match("task", explicit_names=["missing"])
