from __future__ import annotations

from typing import Any


def build_trust_badges(member_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [trust_badge_for_agent(spec) for spec in member_specs]


def trust_badge_for_agent(spec: dict[str, Any]) -> dict[str, Any]:
    key = str(spec.get("key") or spec.get("agent") or "agent")
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    identity = spec.get("identity") if isinstance(spec.get("identity"), dict) else {}
    provider = str(identity.get("provider") or spec.get("provider") or "first_party")
    if str(swarm.get("trust_level") or identity.get("trust_level") or "").strip() == "core_system":
        provider = "core_system"
    trust_level = str(identity.get("trust_level") or "")
    if not trust_level and swarm.get("trust_level"):
        trust_level = str(swarm.get("trust_level"))
    if not trust_level:
        trust_level = "trusted_first_party" if provider == "first_party" else "user_installed"
    if provider == "core_system":
        trust_level = "core_system"
    if spec.get("third_party") or provider == "third_party":
        trust_level = "third_party_untrusted"
    if provider == "external_content":
        trust_level = "external_content"
    can_block = bool(swarm.get("can_block")) and trust_level != "third_party_untrusted"
    if trust_level in {"third_party_untrusted", "external_content"}:
        can_block = False
    allowed_lanes = list(identity.get("allowed_lanes") or swarm.get("allowed_lanes") or inferred_allowed_lanes(spec, trust_level=trust_level))
    if trust_level in {"third_party_untrusted", "external_content"}:
        allowed_lanes = ["inspection"]
    return {
        "agent": key,
        "trust_level": trust_level,
        "provider": provider,
        "allowed_lanes": allowed_lanes,
        "can_emit_verified": trust_level == "core_system",
        "can_emit_blocking": can_block,
        "can_emit_evidence": trust_level not in {"external_content"},
        "requires_sanitization": trust_level in {"user_installed", "third_party_untrusted", "external_content"},
        "trust_penalty": 0.35 if trust_level == "external_content" else 0.25 if trust_level == "third_party_untrusted" else 0.08 if trust_level == "user_installed" else 0.0,
    }


def trust_badge_map(badges: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("agent")): item for item in badges if isinstance(item, dict)}


def inferred_allowed_lanes(spec: dict[str, Any], *, trust_level: str) -> list[str]:
    terms = manifest_terms(spec)
    key = str(spec.get("key") or spec.get("agent") or "").strip()
    if key == "writer":
        return ["synthesis"]
    if key == "final_judge":
        return ["verification", "control"]
    if trust_level == "core_system" or any(term in terms for term in {"control", "governance", "scheduler", "police", "marshal"}):
        return ["control"]
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    if swarm.get("can_block"):
        return ["inspection", "verification", "control"]
    if any(term in terms for term in {"verification", "verifier", "evidence", "audit", "quant", "risk"}):
        return ["inspection", "verification"]
    return ["inspection"]


def manifest_terms(spec: dict[str, Any]) -> set[str]:
    values = [
        spec.get("key"),
        spec.get("agent"),
        spec.get("name"),
        spec.get("agent_type"),
        spec.get("committee_role"),
        spec.get("description"),
        spec.get("focus"),
    ]
    for key in ("tags", "focus_items", "required_capabilities", "required_tools"):
        values.extend(spec.get(key) if isinstance(spec.get(key), list) else [])
    output: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in text.replace("-", "_").replace("/", "_").split("_") if part)
    return output
