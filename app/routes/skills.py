from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routes.dependencies import get_skill_loader
from runtime.skill_loader import SkillLoader


router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills(loader: SkillLoader = Depends(get_skill_loader)) -> dict[str, object]:
    skills = loader.list_skills()
    return {
        "object": "list",
        "data": [skill.to_public_dict(include_content=False) for skill in skills],
    }


@router.get("/{name}")
def get_skill(name: str, loader: SkillLoader = Depends(get_skill_loader)) -> dict[str, object]:
    skill = loader.get_skill(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Unknown skill: {name}")
    return skill.to_public_dict(include_content=True)
