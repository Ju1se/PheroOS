# Historical evidence boundary

The active package is `pheroos-interaction`, not a compatible distribution of
`pheroos==0.1.0`. History was preserved and restored before removing active code.

## Verified archive

[Archive and restore instructions](/Users/scottxie/Desktop/pheroos-interaction-history-20260914/README.md)

- Source/data payload: `history-payload.tar.gz`, SHA-256
  `4afe2a7804869b628b0b2250dcf7fea57d3078d0cd11a5f9d17b184f0fd04ec9`.
- 6,725 payload files verified after extraction. Git bundles plus dirty patches
  and untracked/ignored snapshots reproduced all three original Git states.
- Research baseline: `28c798cf6f858d7cd478f27fa5c144d0c1a6e450`, including its
  separately archived dirty dev9 source and data.
- Runtime baseline: `2222d59bb05785528e4301dc14d164d538408ac6`, including dirty dev5 changes.
- Main baseline: `053a0d33d72a259d631ba5299e1452c0838aafe9`.
- Clean offline restore: accepted core 0.1.0, runtime dev5, bench dev9, NumPy2.5.3;
  678 package files and 11 frozen execution source files match their artifacts;
  117 selected v1/v2 offline tests pass. This is not the full retired test suite.
- Platform boundary: existing CPython3.14/macOS arm64; no system installation or
  model download. A labeled installed-source setuptools84 fallback is preserved
  because its original wheel was absent. Credentials are excluded and unread.

Full before inventory, import measurements, category definitions and classification:
[Inventory directory](/Users/scottxie/Desktop/pheroos-interaction-inventory-20260914).
The report separates required installed source from representative loaded modules.

## Retained cohorts for exact-input replay

Archives contain these paths under `payload/research/pheroos-bench/results/`:

- `visibility-prototype-v1/run`: 16 cells, 96 historical responses, 36 tool calls.
- `visibility-factorial-v2/run`: 24 cells, 96 historical responses, 100 tool calls.
- Previous Kimi worker, shared-dependency and other historical cohorts and builds
  remain in the archive, with their original configurations, raw data and meaning.

The new package reads these records only as external replay inputs. No historical
raw dataset, old wheel, old runtime, core API or conformance catalog is bundled
in the default lean wheel. Old receipts are observations, not a promise that
remote generations can be recreated offline or proof of old authority guarantees.
