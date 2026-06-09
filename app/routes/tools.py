from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routes.dependencies import get_agent_runtime
from runtime.graph import AgentRuntime


router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools(runtime: AgentRuntime = Depends(get_agent_runtime)) -> dict[str, object]:
    return {
        "object": "list",
        "data": runtime.tool_registry.manifest(),
    }
