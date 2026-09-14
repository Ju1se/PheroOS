"""Counterexamples for independent post-run helper arithmetic and null handling."""
import json
from pathlib import Path
import tempfile
import unittest

import audit
import export

CORE = Path('/tmp/pheroos-interface-core/pheroos-bench')


class AuditHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = audit.task_inputs((CORE / 'src/pheroos_bench/coordination_repair_v1_tasks.py').read_text())
        cls.config = json.loads((CORE / 'next-cycle/model-interface-v1/pilot-config-proposal.json').read_text())

    def evidence(self, world):
        return [dict(source_id=k, source_version=2 if world.startswith('version_correction/') else 1)
                for k in audit.documents(world, self.inputs)]

    def test_exact_config_and_grid(self):
        self.assertEqual(audit.digest(self.config), audit.CONFIG_SHA)
        grid = audit.grid(self.config)
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({(r['world'], r['arm'], r['seed']) for r in grid}), 64)
        self.assertEqual(grid[4]['arm'], 'compact_action_256')

    def test_public_rule_arithmetic_not_hidden_table(self):
        expected = {'interval_intersection/dev_a': {'selection': 5}, 'interval_intersection/dev_b': {'selection': 3},
            'dependency_readiness/dev_a': {'ready': ['cobalt']}, 'dependency_readiness/dev_b': {'ready': ['flint']},
            'inventory_reconciliation/dev_a': {'totals': {'copper': 5, 'zinc': 7}},
            'inventory_reconciliation/dev_b': {'totals': {'nickel': 13, 'tin': 7}},
            'version_correction/dev_a': {'value': 11}, 'version_correction/dev_b': {'value': 2}}
        self.assertEqual({w: audit.final_answer(w, self.inputs) for w in self.config['worlds']}, expected)

    def test_direct_does_not_correct_wrong_answer(self):
        world = 'interval_intersection/dev_a'
        valid, stage, action, framing = audit.independent_validation(world, 'direct_json_256', '{"selection":4}', self.evidence(world), self.inputs)
        self.assertTrue(valid)
        self.assertEqual(action['answer'], {'selection': 4})
        self.assertNotEqual(action['answer'], audit.final_answer(world, self.inputs))

    def test_boolean_duplicate_and_envelope_fail(self):
        world = 'interval_intersection/dev_a'
        for raw, expected in [('{"selection":true}', 'action_schema'), ('{"selection":4,"selection":5}', 'transport_format'),
                              ('{"agent":"agent0","task":{}}', 'action_schema')]:
            with self.subTest(raw=raw):
                self.assertEqual(audit.independent_validation(world, 'direct_json_256', raw, self.evidence(world), self.inputs)[:2], (False, expected))

    def test_complete_fence_allowed_incomplete_rejected(self):
        world = 'version_correction/dev_b'
        value = audit.independent_validation(world, 'direct_json_256', '```json\n{"value":2}\n```', self.evidence(world), self.inputs)
        self.assertTrue(value[0])
        self.assertEqual(value[3], 'plain_json')  # Compiled action is parsed again.
        self.assertEqual(audit.independent_validation(world, 'direct_json_256', '```json\n{"value":2}', self.evidence(world), self.inputs)[:2],
                         (False, 'transport_format'))

    def test_stale_citation_and_inspect_not_accepted(self):
        world = 'version_correction/dev_b'
        raw = audit.wire(dict(action='submit', answer={'value': 2}, citations=[dict(source_id='current_values', source_version=1)]))
        self.assertEqual(audit.independent_validation(world, 'compact_action_256', raw, self.evidence(world), self.inputs)[:2],
                         (False, 'missing_or_stale_evidence'))
        for target, stage in [('current_values', 'action_schema'), ('absent', 'undeclared_target')]:
            self.assertEqual(audit.independent_validation(world, 'envelope_256', audit.wire(dict(action='inspect', target=target)), self.evidence(world), self.inputs)[:2],
                             (False, stage))

    def test_unstarted_full_csv_retains_null_not_zero(self):
        rows = export.build_rows(audit.grid(self.config), [], [])
        self.assertEqual(len(rows), 64)
        self.assertTrue(all(r['known_tokens'] is None and r['objective_success'] is None and r['status'] == 'UNSTARTED' for r in rows))
        described = export.describe(rows)
        self.assertEqual(described['status'], 'INVALID')
        self.assertIsNone(described['effects'])
        self.assertIsNone(described['world_seed_means'])

    def test_duplicates_fail_export(self):
        record = dict(world_id=self.config['worlds'][0], arm='direct_json_256', seed=1729)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            export.build_rows(audit.grid(self.config), [record, record], [])

    def test_seed_average_then_equal_world_mean_and_invalid_no_subset(self):
        rows = export.build_rows(audit.grid(self.config), [], [])
        for row in rows:
            row.update(status='VALID_KNOWN', complete=True, public_accepted=True,
                       objective_success=row['world_id'] == self.config['worlds'][0],
                       output_at_cap=row['seed'] % 2 == 0, validation_stage='accepted')
            row.update({k: 2 for k in export.RESOURCE_FIELDS})
        summary = export.describe(rows)
        self.assertEqual(len(summary['world_seed_means']), 32)
        self.assertEqual(summary['arm_summaries']['direct_json_256']['world_mean_rates']['objective_success'], 1 / 8)
        self.assertEqual(summary['contrasts'][0]['paired_world_mean_difference']['known_tokens'], 0)
        rows[-1].update(status='INVALID_ABORT', objective_success=None, unknown_tokens=2048)
        invalid = export.describe(rows)
        self.assertEqual(invalid['status'], 'INVALID')
        self.assertIsNone(invalid['arm_summaries'])

    def test_relocated_source_requires_original_hash_and_present_package_file(self):
        original = '/vanished/tmp/site/pheroos_runtime/recorded_local_v3.py'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            relocated = root / 'pheroos_runtime/recorded_local_v3.py'
            relocated.parent.mkdir()
            audited = audit.Audit(root)
            with self.assertRaises(FileNotFoundError):
                audited.source(original, '0' * 64, root)
            relocated.write_bytes(b'fixed source\n')
            expected = audit.sha256(relocated.read_bytes()).hexdigest()
            self.assertEqual(audited.source(original, expected, root), b'fixed source\n')
            self.assertEqual(audited.source_snapshots[original]['resolved_path'], str(relocated))
            self.assertFalse(audited.findings)
            mismatch = audit.Audit(root)
            mismatch.source(original, '0' * 64, root)
            self.assertEqual(mismatch.findings[0]['check'], 'frozen_source_unchanged')
            with self.assertRaises(ValueError):
                audit.source_path('/old/unknown_package/source.py', root)


if __name__ == '__main__':
    unittest.main()
