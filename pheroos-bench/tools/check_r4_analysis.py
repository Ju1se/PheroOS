"""Tiny synthetic checks for the additive analyzer; never opens pilot results.

The existing frozen measurement tests supply deterministic in-memory receipts.
No study, model, GPU, Session execution, or frozen-file modification occurs.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import analyze_r4_session_scaling as analysis

BENCH = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("frozen_r4_measurement_fixtures", BENCH / "tests/test_r4_measurement.py")
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


class AnalysisChecks(unittest.TestCase):
    def metric(self, row, config):
        condition = next(c for c in config["conditions"] if c["id"] == row["condition_id"])
        return analysis.episode_metrics(row, condition, config)

    def test_declared_pairs_are_all_56_and_matched(self):
        config = analysis.runner.configuration()
        conditions = {c["id"]: c for c in config["conditions"]}
        pairs = analysis.matched_pairs(config)
        self.assertEqual(len(pairs), 56)
        self.assertEqual(len(set(pairs)), 56)
        for candidate, control in pairs:
            self.assertEqual([conditions[candidate][k] for k in ("agents", "cohort", "regime")],
                             [conditions[control][k] for k in ("agents", "cohort", "regime")])
        self.assertIn(("fixed_calls-small-versioned-n32", "fixed_calls-small-dedup_ttl-n32"), pairs)
        self.assertIn(("fixed_calls-small-versioned-n32", "fixed_calls-small-blackboard-n32"), pairs)

    def test_exact_public_export_mapping_and_unchanged_inputs(self):
        rows, config = fixtures.fixture()
        original = analysis.wire([rows, config])
        validated = analysis.measurement.summarize(rows, config)
        local = analysis.mapped_export(rows, config, "versioned", "private", validated)
        oracle = analysis.measurement.export_pair(rows, config, "versioned", "private")
        self.assertEqual(analysis.wire(local), analysis.wire(oracle))
        self.assertEqual(local["report"]["n_worlds"], 4)
        self.assertEqual(len(local["records"]), 8)
        self.assertTrue(all(r["cost"] == 5 and r["outcome"] == "failed" for r in local["records"]))
        self.assertEqual(analysis.wire([rows, config]), original)

    def test_invalid_whole_grid_blocks_mapping_and_retains_cost(self):
        rows, config = fixtures.fixture()
        rows.pop()  # Missing condition outside the requested pair still invalidates it.
        validated = analysis.measurement.summarize(rows, config)
        exported = analysis.mapped_export(rows, config, "versioned", "private", validated)
        self.assertEqual(exported["records"], [])
        self.assertEqual(exported["report"]["status"], "INVALID_ABORT")
        self.assertEqual(exported["report"]["source_accounting"][0]["reported_accounting"]["actual_tokens"], 35)

    def test_failed_work_allocation_and_nonadditive_counters(self):
        rows, config = fixtures.fixture()
        row = rows[0]
        original = analysis.wire(row)
        result = self.metric(row, config)
        self.assertEqual(result["logical_operations"], 5)
        self.assertEqual(result["per_model"]["small"]["actual_tokens"], 35)
        self.assertEqual(result["per_model"]["medium"]["actual_tokens"], 0)
        self.assertEqual([r["dispatched_calls"] for r in result["per_agent"]], [1, 0])
        self.assertEqual(result["failed_work"]["publicly_rejected_actions"], 1)
        self.assertEqual(result["failed_work"]["model_tokens_for_publicly_rejected_actions"], 35)
        self.assertEqual(result["failed_work"]["terminal_failed_episode_actual_tokens"], 35)
        self.assertEqual(result["coordination"]["selected_receipt_occurrences"], 0)
        self.assertEqual(result["control_stages"]["fixture.processing"], dict(operations=3, bytes=12, entries=1))
        self.assertEqual(result["timing"]["model_generation_ns"]["p95"], 7)
        self.assertTrue(result["convergence"]["censored"])
        self.assertIsNone(result["source_coverage"]["final_version_required_sources"])
        self.assertEqual(result["steps"][0]["raw_response_text_sha256"], sha256(row["records"][0]["response"]["text"].encode()).hexdigest())
        self.assertEqual(analysis.wire(row), original)

    def test_receipt_reuse_and_origin_duplicate_counts_are_distinct(self):
        rows, config = fixtures.fixture()
        row = rows[4]
        row.update(records=[], ledger_calls=[], controls=[])
        config["conditions"][1]["policy"] = "blackboard"
        for step in range(3):
            fixtures.add_step(row, config, selected=tuple(range(step)),
                              text='{"action":"inspect","target":"cross_ceiling"}')
        validated = analysis.measurement.summarize(rows, config)
        self.assertEqual(validated["status"], "PILOT_COMPLETE")
        result = self.metric(row, config)
        counts = result["coordination"]
        self.assertEqual(counts["published_valid_inspections"], 3)
        self.assertEqual(counts["repeated_inspections_by_origin"], 2)
        self.assertEqual(counts["model_tokens_for_repeated_inspections"], 70)
        self.assertEqual(counts["selected_receipt_occurrences"], 3)
        self.assertEqual(counts["reused_record_occurrences"], 1)
        self.assertEqual(counts["reused_provenance_occurrences"], 2)
        self.assertEqual(counts["within_prompt_duplicate_provenance_occurrences"], 1)
        self.assertEqual(counts["inspection_target_attempt_repeats"], 2)

    def test_failed_inspection_targets_are_counted_as_attempts(self):
        rows, config = fixtures.fixture()
        fixtures.add_step(rows[0], config)
        result = self.metric(rows[0], config)
        self.assertEqual(result["failed_work"]["publicly_rejected_actions"], 2)
        self.assertEqual(result["coordination"]["inspection_target_attempt_repeats"], 1)
        self.assertEqual(result["coordination"]["repeated_inspections_by_origin"], 0)

    def test_evidence_coverage_separates_visible_and_future_version_sources(self):
        rows, config = fixtures.fixture()
        row = rows[6]
        row.update(records=[], ledger_calls=[], controls=[])
        for step, target in enumerate(("route_policy", "route_capacity", "route_ceiling")):
            fixtures.add_step(row, config, selected=tuple(range(step)),
                              text=analysis.wire(dict(action="inspect", target=target)))
        citations = [dict(source_id=target, version=1) for target in ("route_policy", "route_capacity", "route_ceiling")]
        fixtures.add_step(row, config, selected=(0, 1, 2), text=analysis.wire(dict(action="submit",
            candidate=dict(answer=dict(lane="amber", max_units=6), citations=citations))))
        result = self.metric(row, config)
        self.assertTrue(result["current_snapshot_success"])
        self.assertFalse(result["success"])
        self.assertEqual(result["source_coverage"]["full_coverage_prompts"], 1)
        self.assertEqual(result["source_coverage"]["final_version_distinct_sources"], 0)
        self.assertEqual(result["source_coverage"]["final_version_required_sources"], 3)
        self.assertEqual(len(result["source_coverage"]["globally_inspected_by_version"]["1"]), 3)
        self.assertTrue(result["convergence"]["censored"])

    def test_observed_success_is_attributed_to_slot_without_counterfactual_claim(self):
        rows, config = fixtures.fixture()
        row = rows[4]
        row.update(records=[], ledger_calls=[], controls=[])
        config["conditions"][1]["cohort"] = "medium"
        fixtures.add_step(row, config, text=analysis.wire(dict(action="submit", candidate=dict(code_lines=[
            "def bounded_increment(value, increment, ceiling):", "    return min(value + increment, ceiling)"]))))
        result = self.metric(row, config)
        self.assertTrue(result["success"])
        self.assertEqual(result["per_model"]["medium"]["actual_tokens"], 35)
        self.assertEqual(result["per_model"]["small"]["actual_tokens"], 0)
        self.assertEqual(result["convergence"]["first_final_version_success"]["global_turn"], 1)
        self.assertEqual(result["model_slot_attribution"]["medium"]["first_final_version_success_prefix"], 1)

    def test_expected_null_keeps_length_difference_and_first_divergence(self):
        rows, config = fixtures.fixture()
        reference = self.metric(rows[0], config)
        candidate = deepcopy(reference)
        candidate["condition_id"] = "another-N"
        candidate["steps"] = []
        compared = analysis.compare_null(reference, candidate, "fixture")
        self.assertEqual(compared["reference_only_steps"], [0])
        self.assertIsNone(compared["all_common_inputs_equal"])
        candidate["steps"] = deepcopy(reference["steps"])
        candidate["steps"][0]["raw_response_text_sha256"] = "different"
        compared = analysis.compare_null(reference, candidate, "fixture")
        self.assertTrue(compared["all_common_inputs_equal"])
        self.assertEqual(compared["first_response_divergence_on_equal_input"], 0)
        candidate["steps"][0]["prompt_sha256"] = "different"
        compared = analysis.compare_null(reference, candidate, "fixture")
        self.assertEqual(compared["first_input_divergence_step"], 0)
        self.assertIsNone(compared["first_response_divergence_on_equal_input"])

    def test_unknown_zero_token_call_and_empty_quantile(self):
        counted = analysis.usage([dict(state="dispatched", reserved=0)])
        self.assertEqual(counted["unknown_calls"], 1)
        self.assertEqual(counted["unknown_tokens"], 0)
        self.assertIsNone(analysis.distribution([])["p50"])
        self.assertEqual(analysis.percentile([10, 20, 30, 40], 0.5), 25)
        self.assertEqual(analysis.percentile([10, 20, 30, 40], 0.95), 38.5)

    def test_global_model_loads_require_actual_shape_counts_and_identity(self):
        manifests = dict(small=dict(repository="fixture-small", revision="123"))
        entry = dict(model_ref="small", elapsed_ns=0, status="loaded", model_class="Qwen2ForCausalLM",
                     identity=dict(model_manifest=manifests["small"], fixture=True))
        analysis.validate_model_loads([entry], {"small": {}}, manifests)
        corruptions = [dict(entry, elapsed_ns=value) for value in (-1, True, None, 0.5, "2")]
        corruptions.extend((dict(entry, model_ref="foreign"), dict(entry, model_ref=[]),
            dict(entry, status="INVALID_ABORT"), dict(entry, model_class="wrong"),
            dict(entry, identity={}), dict(entry, extra="undeclared")))
        missing = deepcopy(entry)
        del missing["elapsed_ns"]
        corruptions.append(missing)
        for corrupted in corruptions:
            with self.subTest(corrupted=corrupted), self.assertRaises(ValueError):
                analysis.validate_model_loads([corrupted], {"small": {}}, manifests)
        with self.assertRaises(ValueError):
            analysis.validate_model_loads({}, {"small": {}}, manifests)
        with self.assertRaisesRegex(ValueError, "drifted"):
            analysis.validate_model_loads([entry, dict(entry, identity=dict(entry["identity"], fixture=False))],
                                          {"small": {}}, manifests)

    def finalization_fixture(self):
        config = analysis.runner.configuration()
        selected = analysis.matched_pairs(config)
        pending = [(f"pairs/{number:02d}-fixture.json", dict(config={}, records=[dict(cost=35, outcome="failed")],
                    report=dict(status="VALID_MEASUREMENT"), source_grid_sha256="synthetic-grid"))
                   for number, _ in enumerate(selected)]
        index = [dict(candidate=candidate, control=control, file=name, status="VALID_MEASUREMENT", n_worlds=4)
                 for (candidate, control), (name, _) in zip(selected, pending, strict=True)]
        result = dict(status="DESCRIPTIVE_PILOT_COMPLETE", counts_toward_verdict=False,
                      source_grid_sha256="synthetic-grid", total_successful_episodes=0,
                      source_validation=dict(status="PILOT_COMPLETE", source_accounting=[dict(actual_tokens=35)]))
        return result, pending, index

    def assert_failed_finalization(self, destination, result, pending):
        self.assertEqual(result["status"], "INVALID_ABORT")
        self.assertNotIn("total_successful_episodes", result)
        self.assertEqual(result["source_validation"]["source_accounting"], [dict(actual_tokens=35)])
        self.assertEqual(result["paired_export_statuses"], dict(INVALID_ABORT=56))
        self.assertIn("analysis finalization failed", result["errors"][0])
        for name, exported in pending:
            path = destination / name
            if path.exists():
                stored = analysis.parse(path.read_text())
                self.assertEqual(stored["records"], [])
                self.assertEqual(stored["report"]["status"], "INVALID_ABORT")
                self.assertEqual(stored["source_grid_sha256"], "synthetic-grid")
                self.assertEqual(stored["report"]["source_accounting"], [dict(actual_tokens=35)])
        index = analysis.parse((destination / "paired-index.json").read_text())
        self.assertEqual(len(index), 56)
        self.assertTrue(all(item["status"] == "INVALID_ABORT" for item in index))
        self.assertEqual(analysis.parse((destination / "analysis.json").read_text())["status"], "INVALID_ABORT")
        self.assertFalse((destination / "episode-metrics.jsonl").exists())
        self.assertFalse((destination / "expected-null-controls.json").exists())
        self.assertFalse((destination / "artifact-hashes.json").exists())

    def test_each_output_write_failure_invalidates_all_56_selected_pairs(self):
        for failure in ("01-fixture.json", "paired-index.json", "episode-metrics.jsonl",
                        "expected-null-controls.json", "input-manifest.json", "analysis.json", "artifact-hashes.json"):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                destination = Path(directory)
                result, pending, index = self.finalization_fixture()
                original_open = Path.open

                def fail_exclusive_open(path, mode="r", *args, **kwargs):
                    if path.name == failure and mode == "x":
                        raise OSError("synthetic output failure")
                    return original_open(path, mode, *args, **kwargs)

                with patch.object(Path, "open", fail_exclusive_open):
                    returned = analysis.finalize(destination, result, pending, index, [dict(fixture=True)], [],
                                                 dict(files={"raw-source": "unchanged-hash"}), [])
                self.assert_failed_finalization(destination, returned, pending)
                self.assertEqual(returned["finalization_recovery_failures"], [])

    def test_failed_pair_invalidation_is_removed_and_failure_is_retained(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            result, pending, index = self.finalization_fixture()
            original_save, original_overwrite = analysis.save, analysis.overwrite_owned

            def fail_final_save(path, value):
                if path.name == "artifact-hashes.json":
                    raise OSError("synthetic final save failure")
                return original_save(path, value)

            def fail_one_replacement(path, value):
                if path.name == "00-fixture.json":
                    raise OSError("synthetic persistent write failure")
                return original_overwrite(path, value)

            with patch.object(analysis, "save", fail_final_save), patch.object(analysis, "overwrite_owned", fail_one_replacement):
                returned = analysis.finalize(destination, result, pending, index, [], [], {}, [])
            self.assert_failed_finalization(destination, returned, pending)
            self.assertFalse((destination / pending[0][0]).exists())
            self.assertEqual(len(returned["finalization_recovery_failures"]), 1)

    def test_successful_finalization_keeps_failed_work_and_hashes(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            result, pending, index = self.finalization_fixture()
            returned = analysis.finalize(destination, result, pending, index, [], [], {}, [])
            self.assertEqual(returned["status"], "DESCRIPTIVE_PILOT_COMPLETE")
            stored = analysis.parse((destination / pending[0][0]).read_text())
            self.assertEqual(stored["records"], [dict(cost=35, outcome="failed")])
            hashes = analysis.parse((destination / "artifact-hashes.json").read_text())
            for name, expected in hashes.items():
                self.assertEqual(sha256((destination / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
