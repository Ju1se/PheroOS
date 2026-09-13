# Experimental Session v1: exact consumer artifacts

This archive retains byte-identical accepted artifacts. It is not a release,
Stable API or production profile. The wheel and sdist share the historical
`0.1.0.dev1` label with a legacy build; install the exact files here, not another
artifact with the same name/version. The original external `dist` remains
unchanged and contains the legacy build without Session.

Run these commands from this archive directory. Acceptance used Python 3.12.3
on the recorded single-host Linux environment. Choose fresh environment/output
paths if the example paths already exist. This document does not execute them.

```sh
sha256sum --check SHA256SUMS
python3.12 -m venv /tmp/pheroos-session-v1-consumer-env
/tmp/pheroos-session-v1-consumer-env/bin/python -m pip install --no-index --no-deps artifacts/pheroos-0.1.0-py3-none-any.whl artifacts/pheroos_runtime-0.1.0.dev1-py3-none-any.whl
/tmp/pheroos-session-v1-consumer-env/bin/python consumer/run_session_journey_v1.py --output /tmp/pheroos-session-v1-consumer-run
```

Both exact wheels are supplied deliberately. The runtime metadata retains its
historical Git dependency declaration; `--no-index --no-deps` prevents fetching
or substituting another core. The accepted core has no runtime dependencies.
No model/provider dependency is required for the default two-agent journey.
The sdist is archived for the accepted source cohort; this recipe installs the
accepted wheel and does not rebuild it.

Use direct imports `pheroos_runtime.session_v1.Session` and
`pheroos_runtime.session_driver_v1.SessionDriver`. Create a new database with
`Session.create` and reopen only this same cohort's databases. G1 Store and
PilotLedger database migration is unsupported. Model loading is explicit and
optional; a model registry entry, receipt or checkpoint grants no authority.

`archive-receipt.json` records original locations, exact hashes and archive
member comparisons. `receipts/` preserves the original acceptance and adoption
records without rewriting their historical paths or labels. Wheel and sdist
acceptance each reported 131 tests, including historical compatibility tests.
No installation, build, model call or new acceptance test was performed while
archiving. `consumer/` contains byte copies of the accepted journey and its
experimental contract. The adjacent final consumer decision states the finite
backend and authority limits; this archive does not expand them.
