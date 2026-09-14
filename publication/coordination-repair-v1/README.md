# Experimental coordination repair publication

This additive PR follows PheroOS PR #35 and the companion runtime PR #1. Read the [phase report](../../pheroos-bench/next-cycle/coordination-repair-v1/REPORT.md), [machine status](../../pheroos-bench/next-cycle/coordination-repair-v1/status.json) and [reproduction guide](../../pheroos-bench/next-cycle/coordination-repair-v1/REPRODUCE.md).

All selected new source, data, package and report bytes are directly stored in Git and listed in [manifest.json](manifest.json), using the existing `publication_evidence_v1` verification contract. Generated environments, caches, third-party model weights and audit scratch database copies are excluded. Original evidence, including the pre-dispatch INVALID_ABORT and the corrected reference-policy null finding, is retained. Publication metadata adds no experimental sample.

The prior `publication/evidence-v1/` archives remain byte-identical to the reviewed base. This PR is based on `3604f5ce358ed6051c67e48906d240ac0b581f14`; its companion is based on `c94a2efd13ace1ac424b5ccb1dc0f885b810f82c`. It changes no protocol-core implementation or historical thresholds. Current absolute paths in frozen files describe the collection host and may need explicit relocation.

State: **IMPLEMENTED_COLLECTION_BLOCKED**. Publishing the evidence does not complete the live experiment or promote an experimental mechanism.
