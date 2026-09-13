"""One separately identified full-grid replication of the unchanged R4 method.

No model or runtime imports occur until execution is explicitly requested. The
campaign adds bounded clock observations, not lease/deadline or policy changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import threading
import time

METHOD = "r4_full_grid_replication_v1"
INNER_METHOD = "r4_session_scaling_pilot_v1"
AUDIT_METHOD = "r4_session_scaling_abort_audit_v1"
AUDIT_STATUS = "ACCOUNTING_AND_ABORT_INTEGRITY_PASS"
BENCH = Path(__file__).resolve().parents[1]
CONFIG = BENCH / "scaling-full-grid-replication-v1.json"
COUNTERS = ("actual_tokens", "model_calls", "tool_calls", "control_operations",
            "reserved_tokens", "unknown_tokens", "unknown_calls")


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def parse(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read(path):
    return parse(Path(path).read_text())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hash_file(path):
    value = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")


def configuration(path=CONFIG):
    config = read(path)
    require(wire(config) == wire(read(CONFIG)), "config differs from this campaign declaration")
    require(config["method_version"] == METHOD and config["inner_method_version"] == INNER_METHOD
            and config["counts_toward_verdict"] is False and type(config["attempts"]) is int
            and config["attempts"] == 1, "exactly one nonconfirmatory campaign attempt required")
    return config


def clocks():
    realtime = time.time_ns()
    boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else None
    return dict(utc=datetime.fromtimestamp(realtime / 1_000_000_000, timezone.utc).isoformat(),
                realtime_ns=realtime, monotonic_ns=time.monotonic_ns(), boottime_ns=boot)


class ClockObserver:
    """Finite diagnostic thread; never controls the runner or its clocks."""

    def __init__(self, path, *, period_seconds, max_samples):
        require(type(period_seconds) is int and period_seconds > 0, "positive exact period required")
        require(type(max_samples) is int and 2 <= max_samples <= 20_000, "bounded sample count required")
        self.path, self.period, self.maximum = Path(path), period_seconds, max_samples
        self.stop_event, self.thread = threading.Event(), None
        self.count, self.bytes, self.errors, self.first, self.last = 0, 0, [], None, None
        self.maximum_clock_delta_ns = 0

    def sample(self, kind):
        require(self.count < self.maximum, "clock sample cap exhausted")
        value = clocks()
        for key in ("realtime_ns", "monotonic_ns"):
            require(type(value[key]) is int and value[key] >= 0, "invalid clock reading")
        require(value["boottime_ns"] is None or type(value["boottime_ns"]) is int
                and value["boottime_ns"] >= 0, "invalid boottime reading")
        if self.last is not None:
            delta = (value["realtime_ns"] - self.last["realtime_ns"]
                     - (value["monotonic_ns"] - self.last["monotonic_ns"]))
            self.maximum_clock_delta_ns = max(self.maximum_clock_delta_ns, abs(delta))
            value["realtime_minus_monotonic_interval_ns"] = delta
        encoded = wire(dict(sequence=self.count, kind=kind, **value)) + "\n"
        with self.path.open("a") as stream:
            stream.write(encoded)
            stream.flush()
        self.bytes += len(encoded.encode())
        if self.first is None:
            self.first = value
        self.last, self.count = value, self.count + 1

    def _watch(self):
        try:
            while not self.stop_event.wait(self.period):
                if self.count >= self.maximum - 1:  # Reserve one slot for finish.
                    raise ValueError("clock observation sample cap reached")
                self.sample("periodic")
        except Exception as error:
            self.errors.append(f"{type(error).__name__}: {error}")

    def start(self):
        try:
            with self.path.open("x"):
                pass
            self.sample("startup")
            self.thread = threading.Thread(target=self._watch, name="r4-clock-observer", daemon=True)
            self.thread.start()
        except Exception as error:
            self.errors.append(f"startup: {type(error).__name__}: {error}")
            raise

    def finish(self):
        self.stop_event.set()
        if self.thread is not None and self.thread.ident is not None:
            self.thread.join(timeout=2)
        alive = self.thread is not None and self.thread.is_alive()
        if alive:
            self.errors.append("clock observer did not join within two seconds")
        else:
            try:
                self.sample("finish")
            except Exception as error:
                self.errors.append(f"finish sample: {type(error).__name__}: {error}")
        return dict(status="INVALID_ABORT" if self.errors else "OBSERVED", samples=self.count,
                    serialized_bytes=self.bytes,
                    max_samples=self.maximum, period_seconds=self.period, joined=not alive,
                    maximum_absolute_realtime_minus_monotonic_interval_ns=self.maximum_clock_delta_ns,
                    errors=list(self.errors), first=self.first, last=self.last,
                    interpretation="Separate campaign control overhead; not included in unchanged per-episode call_units. No GPU-time or monetary inference.")


def load_runner():
    from pheroos_bench import r4_session_scaling
    return r4_session_scaling


def original_inputs(config):
    root = (BENCH / config["original_result_directory"]).resolve()
    config_path = (BENCH / config["original_config"]).resolve()
    files = {str(root / name): expected for name, expected in config["original_sha256"].items()}
    files[str(config_path)] = config["original_config_sha256"]
    for name, expected in files.items():
        require(hash_file(name) == expected, f"original artifact differs: {name}")
    frozen, summary = read(root / "freeze.json"), read(root / "summary.json")
    failed = read(root / config["failed_episode"])
    require(frozen["method_version"] == INNER_METHOD and frozen["counts_toward_verdict"] is False,
            "original inner method must remain a pilot")
    require(summary["status"] == "INVALID_ABORT" and summary["reason"] == "source_abort"
            and summary["aborted_row_indices"] == list(range(204, 264)), "original abort disposition differs")
    require(failed["status"] == "INVALID_ABORT" and failed["condition_id"] == config["failed_condition"]
            and failed["world_id"] == config["failed_world"], "failed episode identity differs")
    require(len(frozen["config"]["conditions"]) == 66 and len(frozen["config"]["worlds"]) == 4
            and frozen["config"]["steps"] == 32, "the entire original grid is required")
    return root, config_path, frozen, summary, files


def accounting(summary):
    """Keep missing spend distinct from a partial sum of actually reported values."""
    source = summary.get("source_accounting") if type(summary) is dict else None
    result = dict(source_status=summary.get("status") if type(summary) is dict else None,
                  source_accounting=source, reported_subtotals={})
    if type(source) is not list:
        return result
    for key in COUNTERS:
        known, missing = [], []
        for index, row in enumerate(source):
            reported = row.get("reported_accounting")
            value = reported.get(key) if type(reported) is dict else None
            if value is None:
                missing.append(index)
            else:
                require(type(value) is int and value >= 0, f"invalid reported accounting: {key} row {index}")
                known.append(value)
        result["reported_subtotals"][key] = dict(known_subtotal=sum(known), known_rows=len(known), missing_row_indices=missing)
    return result


def audit_gate(config, frozen, original):
    audit = config["original_audit"]
    require(type(audit.get("path")) is str and type(audit.get("sha256")) is str
            and len(audit["sha256"]) == 64 and audit.get("status") == AUDIT_STATUS,
            "original independent abort audit must be pinned before execution")
    path = (BENCH / audit["path"]).resolve()
    require(hash_file(path) == audit["sha256"], "original independent abort audit hash differs")
    report = read(path)
    require(report.get("audit_method") == AUDIT_METHOD and report.get("audit_status") == AUDIT_STATUS
            and report.get("source_status") == "INVALID_ABORT" and report.get("counts_toward_verdict") is False
            and report.get("original_evidence_unchanged") is True
            and report.get("inference_status") == "FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT",
            "original abort audit has not passed the exact declared integrity gate")
    require(wire(report.get("source_config")) == wire(frozen["config"])
            and wire(report.get("retained_source_accounting")) == wire(original["source_accounting"]),
            "original abort audit config/accounting identity differs")
    root = (BENCH / config["original_result_directory"]).resolve()
    require(all(report.get("evidence_sha256", {}).get(str(root / name)) == expected
                for name, expected in config["original_sha256"].items()),
            "original abort audit evidence identity differs")
    return {str(path): audit["sha256"]}


def combined_accounting(original, replication):
    parts = dict(original=accounting(original), replication=accounting(replication))
    totals = {}
    for key in COUNTERS:
        present = {name: part["reported_subtotals"].get(key) for name, part in parts.items()}
        totals[key] = dict(known_subtotal=sum(item["known_subtotal"] for item in present.values() if item is not None),
                          unavailable_campaigns=[name for name, item in present.items() if item is None],
                          missing_rows={name: item["missing_row_indices"] for name, item in present.items() if item is not None})
    return dict(**parts, across_attempt_reported_subtotals=totals, monetary_cost=None,
                interpretation="Known subtotals are not complete totals when rows are missing. No original abort or cost is removed; campaigns are not pooled as independent worlds.")


def partial_accounting(collection, expected=264):
    """Diagnostic recovery when the inner runner could not save its summary."""
    path = collection / "episodes.jsonl"
    if not path.is_file():
        return None
    rows, errors = [], []
    with path.open() as stream:
        for index, line in enumerate(stream):
            if index >= expected:
                errors.append("extra raw rows beyond declared grid")
                break
            try:
                row = parse(line)
                reported = row.get("accounting")
                if reported is not None:
                    require(type(reported) is dict, "raw accounting must be an object or null")
                    for key in COUNTERS:
                        value = reported.get(key)
                        require(value is None or type(value) is int and value >= 0, f"invalid raw counter {key}")
                rows.append(dict(row_index=index, status=row.get("status"), world_id=row.get("world_id"),
                                 condition_id=row.get("condition_id"), reported_accounting=reported))
            except (ValueError, TypeError, AttributeError) as error:
                errors.append(f"raw row {index}: {type(error).__name__}: {error}")
                rows.append(dict(row_index=index, reported_accounting=None))
    observed = len(rows)
    rows.extend(dict(row_index=index, reported_accounting=None) for index in range(observed, expected))
    return dict(status="INVALID_ABORT", source_accounting=rows, raw_rows_observed=observed,
                accounting_recovery_errors=errors, recovered_from=str(path),
                interpretation="Reported raw values only; missing and unexported rows remain unknown. This is not a valid grid or a replacement summary.")


def run(config_path, output):
    config = configuration(config_path)
    destination = Path(output).resolve()
    original_path = (BENCH / config["original_result_directory"]).resolve()
    require(not destination.is_relative_to(original_path), "replication cannot write inside original evidence")
    require(destination.name == config["campaign_id"], "output must use the declared campaign identity")
    destination.mkdir(parents=True, exist_ok=False)
    started = clocks()
    result = dict(method_version=METHOD, campaign_id=config["campaign_id"], inner_method_version=INNER_METHOD,
                  counts_toward_verdict=False, status="INVALID_ABORT", attempted=False, attempts=0,
                  original_status="INVALID_ABORT", collection_status=None, errors=[])
    errors, original, summary, observer, live_before = result["errors"], None, None, None, None
    identities, original_hashes, model_paths = {}, {}, {}
    try:
        _, original_config, frozen, original, original_hashes = original_inputs(config)
        result["original_accounting"] = accounting(original)
        save(destination / "original-accounting.json", result["original_accounting"])
        original_hashes.update(audit_gate(config, frozen, original))
        runner = load_runner()
        require(Path(sys.executable).resolve() == Path(frozen["interpreter"]).resolve()
                and sys.version == frozen["python"], "use the original frozen interpreter/Python build")
        model_paths = {key: Path(path) for key, path in config["model_paths"].items()}
        live_before = runner.freeze(original_config, model_paths)
        require(wire(live_before) == wire(frozen), "live method/runtime/models differ from original freeze")
        require(wire(runner.configuration()) == wire(frozen["config"]), "original runner declaration differs")
        identities = {str(path.resolve()): hash_file(path) for path in
                      (Path(__file__), Path(config_path), CONFIG, BENCH / "SCALING-replication-v1-contract.md",
                       BENCH / "tests/test_scaling_replication.py")}
        save(destination / "campaign-freeze.json", dict(method_version=METHOD, config=config,
             wrapper_source_sha256=identities, original_artifact_sha256=original_hashes,
             original_freeze=frozen, created_clocks=clocks(), counts_toward_verdict=False,
             rule="One fresh complete grid attempt. Original rows are never borrowed, replaced, pooled or reclassified."))
        observer = ClockObserver(destination / "clock-observations.jsonl", **config["clock_observer"])
        observer.start()
        result.update(attempted=True, attempts=1)
        summary = runner.run(original_config, destination / "collection", model_paths)
        result["collection_status"] = summary.get("status")
        require(summary.get("status") == "PILOT_COMPLETE", "new full-grid collection is INVALID_ABORT")
        require(wire(read(destination / "collection/freeze.json")) == wire(frozen), "new collection freeze differs")
        require(read(destination / "collection/order.json") == read(original_path / "order.json"), "new full-grid order differs")
        require(summary.get("n_episodes") == 264 and summary.get("n_worlds") == 4, "new collection grid differs")
    except (Exception, KeyboardInterrupt) as error:
        errors.append(dict(stage="campaign", type=type(error).__name__, message=str(error)))
    finally:
        if observer is not None:
            try:
                observed = observer.finish()
                result["clock_observer"] = observed
                if observed["status"] != "OBSERVED":
                    errors.append(dict(stage="clock_observer", type="ObservationFailed", message=wire(observed)))
            except Exception as error:
                observer.stop_event.set()
                joined = None
                try:
                    if observer.thread is not None and observer.thread.ident is not None:
                        observer.thread.join(timeout=2)
                    joined = observer.thread is None or not observer.thread.is_alive()
                except Exception as cleanup:
                    errors.append(dict(stage="clock_join_recovery", type=type(cleanup).__name__, message=str(cleanup)))
                result["clock_observer"] = dict(status="INVALID_ABORT", samples=observer.count,
                    serialized_bytes=observer.bytes, joined=joined, errors=[str(error)])
                errors.append(dict(stage="clock_cleanup", type=type(error).__name__, message=str(error)))
        if summary is None and (destination / "collection/summary.json").is_file():
            try:
                summary = read(destination / "collection/summary.json")
                result["collection_status"] = summary.get("status")
            except Exception as error:
                errors.append(dict(stage="recover_summary", type=type(error).__name__, message=str(error)))
        if summary is None:
            try:
                summary = partial_accounting(destination / "collection")
                if summary is not None:
                    result["collection_status"] = "INVALID_ABORT"
                    result["raw_accounting_recovery"] = {key: value for key, value in summary.items() if key != "source_accounting"}
            except Exception as error:
                errors.append(dict(stage="recover_raw_accounting", type=type(error).__name__, message=str(error)))
        if live_before is not None:
            try:
                require(wire(runner.freeze(original_config, model_paths)) == wire(live_before), "post-campaign method/runtime/model drift")
            except Exception as error:
                errors.append(dict(stage="post_freeze", type=type(error).__name__, message=str(error)))
        for name, expected in {**original_hashes, **identities}.items():
            try:
                require(hash_file(name) == expected, f"input changed during campaign: {name}")
            except Exception as error:
                errors.append(dict(stage="post_input", type=type(error).__name__, message=str(error)))
    try:
        result["accounting"] = combined_accounting(original, summary)
    except Exception as error:
        result["accounting"] = dict(original_source=original, replication_source=summary, known_subtotal=None)
        errors.append(dict(stage="accounting", type=type(error).__name__, message=str(error)))
    result["status"] = "REPLICATION_COLLECTED_PENDING_INDEPENDENT_AUDIT" if not errors else "INVALID_ABORT"
    try:
        finished = clocks()
        result["campaign_timing"] = dict(started=started, finished=finished,
            monotonic_elapsed_ns=finished["monotonic_ns"] - started["monotonic_ns"],
            realtime_elapsed_ns=finished["realtime_ns"] - started["realtime_ns"],
            boottime_elapsed_ns=(finished["boottime_ns"] - started["boottime_ns"])
                if finished["boottime_ns"] is not None and started["boottime_ns"] is not None else None,
            interpretation="Outer campaign time includes identity checks and observation overhead, separately from unchanged episode clocks/call_units; not GPU time or monetary cost.")
    except Exception as error:
        errors.append(dict(stage="campaign_timing", type=type(error).__name__, message=str(error)))
        result["status"] = "INVALID_ABORT"
    result["required_next_gate"] = "Independent full-grid raw/SQLite/authority/identity/accounting audit; no automatic acceptance or usable paired export from this wrapper."
    result["collection_directory"] = str(destination / "collection")
    try:
        save(destination / "campaign-summary.json", result)
        files = {str(path.relative_to(destination)): hash_file(path) for path in destination.iterdir() if path.is_file()}
        save(destination / "campaign-artifact-hashes.json", files)
    except Exception as error:
        errors.append(dict(stage="finalization", type=type(error).__name__, message=str(error)))
        result["status"] = "INVALID_ABORT"
        try:
            (destination / "campaign-summary.json").write_text(wire(result) + "\n")
        except Exception as recovery:
            errors.append(dict(stage="finalization_recovery", type=type(recovery).__name__, message=str(recovery)))
            try:
                (destination / "campaign-summary.json").unlink(missing_ok=True)
            except OSError as removal:
                errors.append(dict(stage="summary_removal", type=type(removal).__name__, message=str(removal)))
        try:
            (destination / "campaign-artifact-hashes.json").unlink(missing_ok=True)
        except OSError as removal:
            errors.append(dict(stage="hash_removal", type=type(removal).__name__, message=str(removal)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.config, args.output)
    print(wire(result), flush=True)
    return 2 if result["status"] == "INVALID_ABORT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
