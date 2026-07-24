# Hybrid Replay Protocol

This provider-free, network-free reference example exercises the public Hybrid
Replay v2 Governance ABI with an exact Capability Schema v3 / Protocol v2
manifest. It evaluates and commits two complete Hybrid steps, including
deposits, diffusion, feedback reinforcement, layer coordination, and bounded
policy adjustments.

The default run serializes and restores the local in-memory StateStore reference
between the two steps, then rehydrates the first portable request through Store
inclusion and currentness checks before advancing. The in-memory store and its
checkpoint are deterministic test implementations only; neither is a database,
production persistence layer, or source of authority.

```bash
python3 examples/hybrid-replay-protocol/run.py
```

The process-boundary reference flow uses explicit canonical test data:

```bash
python3 examples/hybrid-replay-protocol/run.py prepare --checkpoint /tmp/hybrid.json
python3 examples/hybrid-replay-protocol/run.py resume --checkpoint /tmp/hybrid.json
```

The checkpoint contains the first portable request and a private snapshot of the
reference StateStore. Resume still requires the restored Store to prove the
committed request; the checkpoint itself grants no replay authority.
