from __future__ import annotations

from pathlib import Path


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

PROTOCOL_SCHEMA = SCHEMA_DIR / "pheroos.protocol.v0.1.schema.json"
CAPABILITY_SCHEMA = SCHEMA_DIR / "pheroos.capability.v0.1.schema.json"
SIGNAL_SCHEMA = SCHEMA_DIR / "pheroos.signal.v0.1.schema.json"
EVIDENCE_SCHEMA = SCHEMA_DIR / "pheroos.evidence.v0.1.schema.json"
TRACE_SCHEMA = SCHEMA_DIR / "pheroos.trace.v0.1.schema.json"


def schema_paths() -> dict[str, Path]:
    return {
        "protocol": PROTOCOL_SCHEMA,
        "capability": CAPABILITY_SCHEMA,
        "signal": SIGNAL_SCHEMA,
        "evidence": EVIDENCE_SCHEMA,
        "trace": TRACE_SCHEMA,
    }
