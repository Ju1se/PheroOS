"""Standalone inspection decisions, explicit assumptions and bounded tie logic."""
import ast
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest

from pheroos_interaction import inspection as policy


def assumptions(**changes):
    values=dict(family=policy.FAMILY,version='declared-v1',source='synthetic conditional channel specification',
        applicability='fixed prior; symmetric binary test or copying a known positive reference',
        prior=.5,q_low=.9,q_high=.95,rho_low=0.,rho_high=0.,reference=True)
    values.update(changes)
    return policy.ModelAssumptions(**values)


def losses(**changes):
    return policy.Losses(**(dict(false_accept=8.,false_reject=4.,abstain=1.)|changes))


def test_explicit_assumptions_ranges_and_preferences_are_preserved_without_defaults():
    model=assumptions(q_low=.81,q_high=.99,rho_low=.1,rho_high=.6)
    preferences=losses(false_accept=12,false_reject=3,abstain=2)
    plan=policy.plan_inspection(model,preferences,.15)
    assert plan.assumptions is model and plan.losses is preferences
    assert asdict(plan)['assumptions']==asdict(model)
    assert 'verification of actual dependencies' in plan.risk_basis
    assert not hasattr(plan,'posterior')
    assert not hasattr(plan,'execution_authorized')
    with pytest.raises(TypeError):
        policy.Losses()
    with pytest.raises(FrozenInstanceError):
        plan.purchase=False


def test_cost_screen_exits_before_branch_work_and_returns_unplanned_query(monkeypatch):
    def forbidden(*args):
        raise AssertionError('cost screen must not compute query branches')
    monkeypatch.setattr(policy,'_branch_costs',forbidden)
    for cost in (1.,1.2):
        plan=policy.plan_inspection(assumptions(),losses(),cost)
        assert not plan.purchase and plan.reason=='cost_screen_skip'
        assert plan.stop_action=='abstain' and plan.stop_risk==1.
        assert plan.query_delta is plan.query_risk is None
        assert plan.risk_term_count==3
        assert policy.apply_plan(plan,True)=='abstain'
    # Exact boundary includes the fixed minimum gain, not only query_cost >= risk.
    plan=policy.plan_inspection(assumptions(),losses(),1-1e-6,epsilon=1e-6)
    assert plan.reason=='cost_screen_skip'


@pytest.mark.parametrize('prior,stop,stop_risk,query_risk,delta,purchase',[
    (.1,'reject',.4,.42,('reject','abstain'),False),
    (.5,'abstain',1.,.8,('reject','accept'),True),
    (.9,'accept',.8,.46,('abstain','accept'),True),
    (.99,'accept',.08,None,None,False)])
def test_known_four_prior_hand_calculations_with_early_cost_saving(prior,stop,stop_risk,query_risk,delta,purchase):
    plan=policy.plan_inspection(assumptions(prior=prior),losses(),.2)
    assert plan.stop_action==stop and plan.stop_risk==pytest.approx(stop_risk)
    assert plan.purchase is purchase
    if query_risk is None:
        assert plan.query_risk is plan.query_delta is None and plan.risk_term_count==3
    else:
        assert plan.query_risk==pytest.approx(query_risk)
        assert (dict(plan.query_delta)[False],dict(plan.query_delta)[True])==delta
        assert plan.risk_term_count==9


def test_copy_corner_keeps_model_scope_and_does_not_buy_duplicate_information():
    model=assumptions(rho_low=.1,rho_high=1.)
    plan=policy.plan_inspection(model,losses(),.2)
    assert plan.stop_risk==1. and plan.query_risk==pytest.approx(1.2)
    assert not plan.purchase and plan.reason=='no_gain_above_margin'
    assert plan.assumptions.rho_low==.1 and plan.assumptions.rho_high==1.
    assert all(action=='abstain' for _,action in plan.query_delta)


def test_zero_probability_branch_and_endpoint_priors_need_no_conditional_division():
    plan=policy.plan_inspection(assumptions(prior=.9,rho_low=1.,rho_high=1.),losses(),.1)
    assert dict(plan.query_delta)[False]=='abstain'  # impossible observation
    assert plan.query_risk==pytest.approx(.9)
    for prior,action in ((0.,'reject'),(1.,'accept')):
        known=policy.plan_inspection(assumptions(prior=prior),losses(),0.)
        assert known.stop_action==action and known.stop_risk==0
        assert known.query_delta is None and not known.purchase


def test_global_tie_budget_does_not_give_each_branch_a_full_tolerance():
    model=assumptions(prior=.25-3.75e-13,q_low=.5,q_high=.5)
    plan=policy.plan_inspection(model,losses(),0.)
    assert dict(plan.query_delta)=={False:'abstain',True:'reject',None:'abstain'}
    assert plan.query_risk==pytest.approx(.99999999999925,abs=2e-16)
    assert plan.query_risk<1.  # independently choosing U on both branches is wrong
    assert plan.stop_action=='reject'
    assert not plan.purchase


def test_global_tie_selection_can_change_purchase_with_explicit_zero_margin():
    plan=policy.plan_inspection(assumptions(q_low=.9,q_high=.9),
        losses(false_accept=9.999999999988,false_reject=9.999999999988),0.,epsilon=0.)
    assert dict(plan.query_delta)=={False:'abstain',True:'accept',None:'abstain'}
    assert 0 < plan.stop_risk-plan.query_risk < 1e-12
    assert plan.purchase


def test_tie_comparison_uses_actual_difference_including_query_cost():
    plan=policy.plan_inspection(assumptions(q_low=.9,q_high=.9),
        losses(false_accept=9.99999999999,false_reject=9.99999999999),.1)
    # Adding 1e-12 to the rounded minimum would mistakenly admit U/U here.
    assert dict(plan.query_delta)=={False:'abstain',True:'accept',None:'abstain'}
    assert plan.query_risk<1.1


def test_stop_tie_uses_selected_actions_actual_risk_for_screen(monkeypatch):
    p=.25-1e-13
    model=assumptions(prior=p)
    chosen=policy.plan_inspection(model,losses(),1.)
    assert chosen.stop_action=='abstain' and chosen.stop_risk==1.
    assert 4*p<chosen.stop_risk
    assert chosen.query_risk is None


def test_apply_uses_precommitted_map_and_unknown_abstains_without_replanning(monkeypatch):
    plan=policy.plan_inspection(assumptions(),losses(),.2)
    def forbidden(*args):
        raise AssertionError('a receipt must not rerun the planner')
    monkeypatch.setattr(policy,'plan_inspection',forbidden)
    monkeypatch.setattr(policy,'_branch_costs',forbidden)
    assert policy.apply_plan(plan,True)=='accept'
    assert policy.apply_plan(plan,False)=='reject'
    assert policy.apply_plan(plan,None)=='abstain'
    with pytest.raises(ValueError,match='boolean or None'):
        policy.apply_plan(plan,'true')


@pytest.mark.parametrize('field,value',[
    ('family','other-family'),('version',''),('source',' '),('applicability','x'*2049),
    ('prior',-.1),('prior',float('nan')),('q_low',.49),('q_high',.8),
    ('q_high',float('inf')),('rho_low',-.1),('rho_low',.2),('rho_high',1.1),
    ('reference',False),('reference',1)])
def test_invalid_or_out_of_family_assumptions_are_rejected(field,value):
    with pytest.raises(ValueError):
        assumptions(**{field:value})


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf'),True])
def test_explicit_loss_cost_and_margin_must_be_finite_nonnegative(value):
    with pytest.raises(ValueError):
        losses(abstain=value)
    with pytest.raises(ValueError):
        policy.plan_inspection(assumptions(),losses(),value)
    with pytest.raises(ValueError):
        policy.plan_inspection(assumptions(),losses(),0.,epsilon=value)


def test_active_policy_has_only_standalone_stdlib_dependencies_and_no_enumeration():
    source=Path(policy.__file__).read_text()
    tree=ast.parse(source)
    modules=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):
            modules.append(node.module)
    assert set(modules)=={'dataclasses','math'}
    assert 'JointModel' not in source and 'itertools' not in source
    # Separate fixed count layers and branch scans are permitted; no complete
    # action-map enumeration is used in the active implementation.
    assert 'for actions in' not in source and 'product(' not in source
