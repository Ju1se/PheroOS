"""Commitment rules: Theorem 4 numerics, deterministic cross-inhibition, exact stopping, platform use."""
import ast
from hashlib import sha256
import math
from pathlib import Path

import pytest

from pheroos_interaction import commitment
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.platform import PlatformSession


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def work(key, agents=('a', 'b')):
    return {'id': key, 'version': 1, 'dependencies': [], 'agents': list(agents), 'actions': ['tool.evaluate']}


def make(tmp_path, clock, items):
    return PlatformSession.create(tmp_path / 's.sqlite', 'run-1', agents=['a', 'b', 'host'], work=items,
                                  token_cap=10_000, max_calls=50, clock=clock, platform={'budgets': {}})


def verify_ok(task_id, artifact):
    return True


def read_ok(session, lease, call_id, value='x'):
    driver = SessionDriver(session, tools={'mock': lambda args: {'value': value, 'arg': args}})
    return driver.evaluate(lease, call_id, 'mock', {'k': 1})


def propose(session, agent, call_id, loss):
    lease = session.claim(agent, 'w')
    read_ok(session, lease, call_id, agent)
    session.propose(lease, call_id, loss)
    session.release(lease)


def events(session, kind):
    return [e for e in session.snapshot()['events'] if e['event_type'] == 'interaction.session.platform.' + kind]


def hashed(keys, perturbation=1e-3, seed='colony'):
    return [perturbation * int(sha256((seed + '\0' + key).encode()).hexdigest(), 16) / 2 ** 256 for key in keys]


def config(**changes):
    return commitment.CommitmentConfig(**(dict(abstain_loss=1., latency_cost=.25, decision_time=1.) | changes))


# (1) Theorem 4 numerics from the design document

def test_theorem_4_critical_sigma_and_equilibria():
    assert commitment.sigma_star(2) == pytest.approx(3.556, abs=5e-4)
    assert commitment.sigma_star(1) == math.inf and commitment.sigma_star(.5) == math.inf
    y0 = hashed('ab')
    assert [round(y, 3) for y in commitment.integrate_commitment([2, 2], 2.5, y0, .01, 2000)] == [.395, .395]
    assert round(commitment.deadlock_fraction(2, 2.5), 3) == .395
    assert sorted(round(y, 3) for y in commitment.integrate_commitment([2, 2], 4, y0, .01, 40000)) == [.25, .5]
    assert sorted(round(y, 3) for y in commitment.integrate_commitment([2, 2], 6, y0, .01, 10000)) == [.136, .614]
    assert [round(y, 3) for y in commitment.integrate_commitment([1.2, 1.2], 6, y0, .01, 2000)] == [.276, .276]
    assert round(commitment.deadlock_fraction(1.2, 6), 3) == .276
    # Below sigma* the symmetric point is the attractor; above it the doc's asymmetric pair is
    # reached only after leaving the saddle, which takes longer than the default 2000-step window.
    early = commitment.integrate_commitment([2, 2], 4, y0, .01, 2000)
    assert early == pytest.approx([commitment.deadlock_fraction(2, 4)] * 2, abs=1e-3)
    assert round(commitment.deadlock_fraction(2, 4), 3) == .368


def test_asymmetric_equilibria_are_fixed_points_of_the_flow():
    assert commitment.commitment_flow([.5, .25], [2, 2], 4) == pytest.approx([0., 0.], abs=1e-12)
    assert commitment.commitment_flow([.614, .136], [2, 2], 6) == pytest.approx([0., 0.], abs=2e-3)
    y = commitment.deadlock_fraction(2, 2.5)
    assert commitment.commitment_flow([y, y], [2, 2], 2.5) == pytest.approx([0., 0.], abs=1e-12)


def test_integration_is_deterministic_and_stays_in_the_simplex():
    first = commitment.integrate_commitment([5, 5, 5], 20, hashed('abc'), .01, 300)
    assert first == commitment.integrate_commitment([5, 5, 5], 20, hashed('abc'), .01, 300)
    assert all(0 <= y <= 1 for y in first) and math.fsum(first) <= 1
    assert commitment.integrate_commitment([1000], 1000, [.9], .01, 1)[0] <= 1


def test_projection_renormalises_an_overshoot_onto_the_simplex():
    # 30 candidates at v = 5 from zero shares: one Euler step gives .05 each (sum 1.5), projected to 1/30 each.
    y = commitment.integrate_commitment([5.] * 30, 0., [0.] * 30, .01, 1)
    assert math.fsum(y) == 1. and all(share == 1 / 30 for share in y)
    keys = ['k%d' % i for i in range(30)]
    result = commitment.cross_inhibition([.2] * 30, keys, config(latency_cost=.5, steps=1))
    assert math.fsum(result['y']) == 1. and all(0 <= share <= 1 for share in result['y'])
    assert result['decision'] == 'abstain' and result['reason'] == commitment.DEADLOCK


def test_work_per_commit_is_bounded_explicitly():
    assert commitment.MAX_STEPS == 2000 and commitment.MAX_ITERATIONS == 1000000
    assert config().iteration_bound() == 2000 * 300  # substeps at rates 3*sigma_cap = 3000 with dt .01
    assert config(dt=1., sigma_cap=10.).iteration_bound() == 2000 * 300
    assert config(steps=1).iteration_bound() == 300
    for changes in ({'steps': 2001}, {'steps': 10 ** 9}, {'dt': 1.}, {'sigma_cap': 1e6}):
        with pytest.raises(ValueError):
            config(**changes)
    with pytest.raises(ValueError, match='substeps'):
        commitment.integrate_commitment([1000.], 1000., [0.], .01, 10 ** 6)
    with pytest.raises(ValueError, match='substeps'):
        commitment.integrate_commitment([1.], 0., [0.], .01, commitment.MAX_ITERATIONS + 1)
    for phrase in ('MAX_STEPS', 'MAX_ITERATIONS', 'transaction'):
        assert phrase in commitment.CommitmentConfig.__doc__


# (2) cross_inhibition

def test_equal_good_candidates_publish_the_same_one_independently_of_order():
    forward = commitment.cross_inhibition([.2, .2], ['a', 'b'], config())
    again = commitment.cross_inhibition([.2, .2], ['a', 'b'], config())
    backward = commitment.cross_inhibition([.2, .2], ['b', 'a'], config())
    assert forward == again and forward['decision'] == 'publish' and forward['reason'] == commitment.QUORUM
    assert ['a', 'b'][forward['index']] == ['b', 'a'][backward['index']] == 'b'
    assert forward['y'][1] == backward['y'][0] and forward['admissible'] == (0, 1)
    assert forward['v_bar'] == pytest.approx(4 / 3) and forward['sigma'] == commitment.sigma_star(4 / 3)
    assert 'a' == ['a', 'b'][commitment.cross_inhibition([.2, .2], ['a', 'b'], config(seed='other'))['index']]


def test_unequal_candidates_choose_the_better_one():
    assert commitment.cross_inhibition([.4, .2], ['a', 'b'], config())['index'] == 1
    assert commitment.cross_inhibition([.2, .4], ['a', 'b'], config())['index'] == 0
    assert commitment.cross_inhibition([0, .2], ['a', 'b'], config())['index'] == 0


def test_equal_poor_candidates_below_v_bar_are_gated_out_before_the_dynamics():
    # v = 1.25 < v_bar = 4/3: loss + latency = 1.05 >= abstain, so no share ever enters.
    result = commitment.cross_inhibition([.8, .8], ['a', 'b'], config())
    assert result == {'decision': 'abstain', 'index': None, 'sigma': commitment.sigma_star(4 / 3), 'v_bar': 4 / 3,
                      'y': [0., 0.], 'admissible': (), 'reason': commitment.NO_ADMISSIBLE}
    assert commitment.cross_inhibition([.75, .2], ['a', 'b'], config())['admissible'] == (1,)


def test_equal_admissible_candidates_below_the_capped_sigma_deadlock():
    # v = 1/.7 > v_bar, but sigma* (v) = 10.77 exceeds the cap 10, so the symmetric point is stable.
    result = commitment.cross_inhibition([.7, .7], ['a', 'b'], config(sigma_cap=10.))
    assert result['decision'] == 'abstain' and result['index'] is None and result['reason'] == commitment.DEADLOCK
    assert result['sigma'] == 10. and result['admissible'] == (0, 1)
    assert [round(y, 3) for y in result['y']] == [round(commitment.deadlock_fraction(1 / .7, 10.), 3)] * 2


def test_single_candidate_passes_iff_it_beats_v_bar():
    # A lone candidate settles at (-1 + sqrt(1 + 4v^4)) / (2v^2), which is .618 at v = 1 and above quorum for all v.
    passing = commitment.cross_inhibition([.74], ['only'], config())
    v = 1 / .74
    assert passing['decision'] == 'publish' and passing['index'] == 0
    assert passing['y'][0] == pytest.approx((-1 + (1 + 4 * v ** 4) ** .5) / (2 * v * v), abs=1e-9)
    assert (-1 + 5 ** .5) / 2 == pytest.approx(.618, abs=5e-4)
    assert commitment.cross_inhibition([.76], ['only'], config())['reason'] == commitment.NO_ADMISSIBLE
    # At loss + latency == abstain the strict gate excludes the candidate.
    assert commitment.cross_inhibition([.75], ['only'], config())['reason'] == commitment.NO_ADMISSIBLE


def test_latency_at_or_above_abstention_gives_sigma_zero_and_abstains():
    result = commitment.cross_inhibition([.2, .2], ['a', 'b'], config(latency_cost=1.))
    assert result['decision'] == 'abstain' and result['sigma'] == 0. and result['v_bar'] == math.inf
    assert commitment.cross_inhibition([0], ['a'], config(latency_cost=2., decision_time=1.))['sigma'] == 0.
    # Zero latency gives v_bar = 1, whose critical sigma is infinite and so takes the cap.
    free = commitment.cross_inhibition([.2], ['a'], config(latency_cost=0.))
    assert free['v_bar'] == 1 and free['sigma'] == 1e3 and free['decision'] == 'publish'


def test_cross_inhibition_never_waits_and_rejects_malformed_candidates():
    for losses, keys in (([.2, .2], ['a', 'b']), ([.8, .8], ['a', 'b']), ([.7, .7], ['a', 'b'])):
        assert commitment.cross_inhibition(losses, keys, config(sigma_cap=10.))['decision'] in ('publish', 'abstain')
    for losses, keys in (([], []), ([.2], ['a', 'b']), ([.2, .2], ['a', 'a']), ([.2], [1]), ([.2], ['a\0'])):
        with pytest.raises(ValueError):
            commitment.cross_inhibition(losses, keys, config())
    with pytest.raises(ValueError):
        commitment.cross_inhibition([.2, .2], ['a', 'b'], config(perturbation=.9))
    with pytest.raises(ValueError):
        commitment.cross_inhibition([.2], ['a'], {'abstain_loss': 1.})


# (3) cross_inhibition_rule on a real PlatformSession

def test_rule_publishes_the_better_candidate_once_and_records_the_decision(tmp_path):
    session = make(tmp_path, Clock(), [work('w')])
    propose(session, 'a', 'w:a', .4)
    propose(session, 'b', 'w:b', .2)
    result = session.commit('w', verify=verify_ok, abstain_loss=1., rule=commitment.cross_inhibition_rule(config()))
    assert result['decision'] == 'publish' and result['call_id'] == 'w:b' and result['publisher'] == 'b'
    snapshot = session.snapshot()
    assert [row['call_id'] for row in snapshot['artifacts']] == ['w:b']
    assert snapshot['platform']['decisions'][0]['work_id'] == 'w'
    replay = session.commit('w', verify=lambda *args: pytest.fail('replayed verification'), abstain_loss=1.,
                            rule=lambda rows, loss: pytest.fail('replayed rule'))
    assert replay == result and session.snapshot() == snapshot


def test_rule_abstains_terminally_on_equal_poor_candidates_without_an_artifact(tmp_path):
    session = make(tmp_path, Clock(), [work('w')])
    propose(session, 'a', 'w:a', .8)
    propose(session, 'b', 'w:b', .8)
    result = session.commit('w', verify=verify_ok, abstain_loss=1., rule=commitment.cross_inhibition_rule(config()))
    assert result['decision'] == 'abstain'
    assert session.ready_work('a') == [] and session.claim('b', 'w') is None
    snapshot = session.snapshot()
    assert not snapshot['artifacts'] and not events(session, 'waited')
    assert session.commit('w', verify=verify_ok, abstain_loss=1., rule=commitment.cross_inhibition_rule(config())) == result
    assert session.snapshot() == snapshot


def test_rule_refuses_a_ledger_abstention_loss_that_disagrees_with_the_config(tmp_path):
    session = make(tmp_path, Clock(), [work('w')])
    propose(session, 'a', 'w:a', .2)
    before = session.snapshot()
    with pytest.raises(ValueError):
        session.commit('w', verify=verify_ok, abstain_loss=2., rule=commitment.cross_inhibition_rule(config()))
    assert session.snapshot() == before
    rule = commitment.cross_inhibition_rule(config())
    with pytest.raises(ValueError):
        rule([{'call_id': 'w:a', 'certified_loss': .2}], True)
    assert rule([{'call_id': 'w:a', 'certified_loss': .2}], 1) == 'w:a'
    with pytest.raises(ValueError):
        commitment.cross_inhibition_rule(None)


# (4) commit_value

def test_commit_value_states_on_a_small_declared_distribution():
    decide = commitment.commit_value(1, .05, 3, .5, [.2, .8], [.5, .5])
    assert decide(0, None) == {'state': 'no_candidate', 'value': .59375, 'wait_value': .59375}
    assert decide(3, None) == {'state': 'abstain', 'value': 1, 'wait_value': None}
    assert decide(0, .2)['state'] == 'publish' and decide(0, .2)['value'] == .2
    assert decide(0, .5) == {'state': 'wait', 'value': .4421875, 'wait_value': .4421875}
    assert decide(3, .5) == {'state': 'publish', 'value': .5, 'wait_value': None}
    assert decide(3, 1.5) == {'state': 'abstain', 'value': 1, 'wait_value': None}
    assert decide(0, 1.5)['state'] == 'wait'      # recall: a poor candidate in hand still waits for a better one
    assert decide(7, .5) == decide(3, .5)          # beyond the deadline holds


def test_commit_value_at_deadline_zero_is_min_of_candidate_and_abstention():
    decide = commitment.commit_value(1, .05, 0, .5, [.2, .8], [.5, .5])
    assert decide(0, .6) == {'state': 'publish', 'value': .6, 'wait_value': None}
    assert decide(0, 1.5) == {'state': 'abstain', 'value': 1, 'wait_value': None}
    assert decide(0, None) == {'state': 'abstain', 'value': 1, 'wait_value': None}
    assert decide(0, 1) == {'state': 'publish', 'value': 1, 'wait_value': None}


def test_commit_value_wait_value_is_exact_for_an_off_support_candidate():
    decide = commitment.commit_value(1, .05, 1, .5, [.2, .8], [.5, .5])
    expected = .05 + .5 * .6 + .5 * math.fsum((.5 * .2, .5 * .6))
    assert decide(0, .6) == {'state': 'wait', 'value': expected, 'wait_value': expected}
    assert expected == pytest.approx(.55, abs=1e-15)
    assert decide(0, .8)['wait_value'] == pytest.approx(.05 + .5 * .8 + .5 * (.5 * .2 + .5 * .8), abs=1e-15)
    # A long horizon is tabulated iteratively, not by recursion over ticks.
    assert commitment.commit_value(1, .05, 5000, .5, [.2, .8], [.5, .5])(0, .6)['state'] == 'wait'


def test_commit_value_rejects_malformed_models():
    for args in ((1, .05, 1, .5, [], []), (1, .05, 1, .5, [.2], [.5, .5]), (1, .05, 1, .5, [.2, .8], [.6, .6]),
                 (1, .05, 1.0, .5, [.2], [1]), (1, .05, -1, .5, [.2], [1]), (1, .05, 1, 1.5, [.2], [1]),
                 (1, math.inf, 1, .5, [.2], [1]), (1, .05, 1, .5, [-.2], [1]), (1, .05, 1, .5, [.2], [True]),
                 (True, .05, 1, .5, [.2], [1]), (math.nan, .05, 1, .5, [.2], [1])):
        with pytest.raises(ValueError):
            commitment.commit_value(*args)
    decide = commitment.commit_value(1, .05, 1, .5, [.2], [1])
    for tick, loss in ((1.0, .2), (-1, .2), (0, -.1), (0, math.nan), (0, True)):
        with pytest.raises(ValueError):
            decide(tick, loss)


# (5) optimal_stopping_rule on a real PlatformSession

def test_optimal_stopping_rule_waits_then_publishes_the_cheapest_by_call_id(tmp_path):
    session = make(tmp_path, Clock(), [work('w')])
    propose(session, 'a', 'w:z', .5)
    propose(session, 'b', 'w:a', .5)
    model = (1., .05, 3, .5, [.2, .8], [.5, .5])
    waiting = commitment.optimal_stopping_rule(*model, 0)
    assert waiting([{'call_id': 'w:z', 'certified_loss': .5}], 1.) == {'decision': 'wait'}
    result = session.commit('w', verify=verify_ok, abstain_loss=1., rule=waiting)
    assert result == {'decision': 'wait', 'candidates': 2}
    assert [e['details'] for e in events(session, 'waited')] == [{'candidates': 2, 'abstain_loss': 1.}]
    assert [row['id'] for row in session.ready_work('a')] == ['w'] and not session.snapshot()['artifacts']
    result = session.commit('w', verify=verify_ok, abstain_loss=1., rule=commitment.optimal_stopping_rule(*model, 3))
    assert result['decision'] == 'publish' and result['call_id'] == 'w:a'


def test_optimal_stopping_rule_abstains_and_checks_the_ledger_loss(tmp_path):
    session = make(tmp_path, Clock(), [work('w')])
    propose(session, 'a', 'w:a', 1.5)
    rule = commitment.optimal_stopping_rule(1., .05, 0, .5, [.2, .8], [.5, .5], 0)
    assert rule([], 1.) is None
    with pytest.raises(ValueError):
        rule([{'call_id': 'w:a', 'certified_loss': 1.5}], 2.)
    assert session.commit('w', verify=verify_ok, abstain_loss=1., rule=rule)['decision'] == 'abstain'
    assert session.claim('b', 'w') is None
    with pytest.raises(ValueError):
        commitment.optimal_stopping_rule(1., .05, 0, .5, [.2, .8], [.5, .5], 0.)


# (6) exact-type validation

@pytest.mark.parametrize('field,value', [
    ('abstain_loss', 0), ('abstain_loss', True), ('abstain_loss', math.inf), ('latency_cost', -1),
    ('decision_time', math.nan), ('quorum_frac', 1.5), ('margin', False), ('dt', 0), ('steps', 0),
    ('steps', 2000.0), ('steps', True), ('steps', 2001), ('perturbation', 0), ('seed', b'colony'),
    ('seed', 'a\0b'), ('sigma_cap', 0), ('sigma_cap', 1e6), ('dt', 1.)])
def test_config_rejects_inexact_or_out_of_range_fields(field, value):
    with pytest.raises(ValueError):
        config(**{field: value})


def test_scalar_functions_reject_bool_nan_inf_and_shape_errors():
    for bad in (True, math.nan, math.inf, '2'):
        with pytest.raises(ValueError):
            commitment.sigma_star(bad)
        with pytest.raises(ValueError):
            commitment.deadlock_fraction(bad, 1)
    with pytest.raises(ValueError):
        commitment.deadlock_fraction(2, -1)
    with pytest.raises(ValueError):
        commitment.deadlock_fraction(0, 1)
    for y, values, sigma in (([.5], [2, 2], 1), ([.5, 1.5], [2, 2], 1), ([.5, .1], [2, 0], 1), ([.5, .1], [2, 2], -1),
                             ([True, .1], [2, 2], 1), ([], [], 1)):
        with pytest.raises(ValueError):
            commitment.commitment_flow(y, values, sigma)
    for values, sigma, y0, dt, steps in (([2, 2], 1, [.6, .6], .01, 1), ([2, 2], 1, [.5], .01, 1), ([2], 1, [.5], 0, 1),
                                         ([2], 1, [.5], .01, 0), ([2], 1, [.5], .01, 1.0), ([2], math.nan, [.5], .01, 1)):
        with pytest.raises(ValueError):
            commitment.integrate_commitment(values, sigma, y0, dt, steps)
    assert commitment.integrate_commitment([2, 2], 1, [.5, .5], .01, 1) is not None


# (7) dependency boundary

def test_commitment_imports_only_dataclasses_hashlib_and_math():
    source = Path(commitment.__file__).read_text()
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module)
    assert set(modules) == {'dataclasses', 'hashlib', 'math'}
    assert 'random.' not in source and 'time' not in modules and 'runner' not in source
    for claim in ('no optimality claim', 'deterministic', 'DECLARE'):
        assert claim in commitment.__doc__
