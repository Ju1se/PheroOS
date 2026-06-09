from __future__ import annotations

from pheroos.protocol.models import ProtocolManifest


def compose_protocols(protocols: list[ProtocolManifest]) -> dict[str, list[str]]:
    return {
        "protocols": [protocol.id for protocol in protocols],
        "targets": sorted({target.id for protocol in protocols for target in protocol.targets}),
        "candidates": sorted({candidate.id for protocol in protocols for candidate in protocol.candidates}),
    }
