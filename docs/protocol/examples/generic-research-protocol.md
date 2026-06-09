# Generic Research Protocol

Generic research is an evidence-gathering capability. It should declare source
retrieval, citation audit, contradiction handling, and output constraints
without embedding a specific domain.

```json
{
  "id": "generic-research",
  "name": "Generic Research",
  "version": "0.1.0",
  "description": "Source-grounded research with citation governance.",
  "capability_types": ["research", "evidence"],
  "permissions": ["network:approved-provider", "data:read"],
  "risk_level": "low",
  "tools": ["provider_web_search", "approved_source_fetch"],
  "protocol": {
    "intents": ["generic_research"],
    "targets": [
      {"target": "research:source_retrieval", "aliases": ["source candidates"]},
      {"target": "gate:research_evidence_gate", "aliases": ["claim support"]},
      {"target": "gate:research_citation_audit", "aliases": ["citation audit"]}
    ],
    "candidates": [
      {"candidate": "candidate:research:supported_summary"},
      {"candidate": "candidate:research:insufficient_sources", "safe_fallback": true}
    ],
    "evidence_policy": {
      "raw_data_allowed_in_final": false,
      "min_independent_sources": 2,
      "contradiction_policy": "surface_and_degrade"
    },
    "recovery_protocols": [
      {
        "recovery_id": "source_gap_recovery",
        "trigger_targets": ["gate:research_evidence_gate"],
        "allowed_agent_roles": ["source_retriever", "citation_auditor"],
        "required_tools": ["provider_web_search"],
        "recovery_failure_candidate": "candidate:research:insufficient_sources"
      }
    ],
    "output_policy": {
      "required_evidence_display": ["source_urls", "evidence_gaps"],
      "writer_can_create_facts": false
    }
  }
}
```
