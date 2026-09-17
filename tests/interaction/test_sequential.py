"""Finite-horizon trees: horizon 1 is plan_inspection bit for bit; certificates enclose fixed trees."""
import ast
import random
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from itertools import product
from pathlib import Path

import pytest

from pheroos_interaction import inspection as policy
from pheroos_interaction import sequential as seq


def assumptions(**changes):
    values=dict(family=policy.FAMILY,version='declared-v1',source='synthetic conditional channel specification',
        applicability='fixed prior; symmetric binary test or copying a known positive reference',
        prior=.5,q_low=.9,q_high=.95,rho_low=0.,rho_high=0.,reference=True)
    values.update(changes)
    return policy.ModelAssumptions(**values)


def losses(**changes):
    return policy.Losses(**(dict(false_accept=8.,false_reject=4.,abstain=1.)|changes))


def same_as_inspection(model,preferences,cost,epsilon=1e-12):
    plan=policy.plan_inspection(model,preferences,cost,epsilon=epsilon)
    tree=seq.plan_tree(model.prior,seq.corner(model),preferences,cost,1,epsilon=epsilon)
    same=(plan.stop_action==tree.stop_action and plan.stop_risk==tree.stop_risk
        and plan.purchase==tree.query and plan.query_risk==tree.query_risk)
    if plan.purchase:
        expected=dict(plan.query_delta)
        same=same and expected[False]==tree.children[0].stop_action and expected[True]==tree.children[1].stop_action
    sequential=seq.plan_sequential(model,preferences,cost,1,epsilon=epsilon,certify=False)
    same=same and (sequential.stop_action,sequential.stop_risk,sequential.query_risk,sequential.purchase)==(
        plan.stop_action,plan.stop_risk,plan.query_risk,plan.purchase)
    return same


@pytest.mark.parametrize('model,preferences,cost,epsilon',[
    (assumptions(prior=.1),losses(),.2,1e-12),
    (assumptions(prior=.5),losses(),.2,1e-12),
    (assumptions(prior=.9),losses(),.2,1e-12),
    (assumptions(prior=.99),losses(),.2,1e-12),
    (assumptions(rho_low=.1,rho_high=1.),losses(),.2,1e-12),
    (assumptions(prior=.9,rho_low=1.,rho_high=1.),losses(),.1,1e-12),
    (assumptions(prior=0.),losses(),0.,1e-12),
    (assumptions(prior=1.),losses(),0.,1e-12),
    (assumptions(prior=.25-3.75e-13,q_low=.5,q_high=.5),losses(),0.,1e-12),
    (assumptions(q_low=.9,q_high=.9),losses(false_accept=9.999999999988,false_reject=9.999999999988),0.,0.),
    (assumptions(q_low=.9,q_high=.9),losses(false_accept=9.99999999999,false_reject=9.99999999999),.1,1e-12),
    (assumptions(prior=.25-1e-13),losses(),1.,1e-12),
    (assumptions(),losses(),1-1e-6,1e-6),
    (assumptions(q_low=.8,q_high=.8),losses(false_accept=1.,false_reject=1.,abstain=.2+1.5e-12),0.,0.)])
def test_horizon_one_reproduces_every_repository_inspection_case_exactly(model,preferences,cost,epsilon):
    assert same_as_inspection(model,preferences,cost,epsilon)


def test_horizon_one_reproduces_plan_inspection_on_seeded_random_configurations():
    rng=random.Random(7)
    for _ in range(5000):
        q_low=.5+.5*rng.random()
        q_high=q_low+(1-q_low)*rng.random()
        rho_high=rng.random()*(.999 if rng.random()<.8 else .2)
        model=assumptions(prior=rng.random(),q_low=q_low,q_high=q_high,rho_low=rho_high*rng.random(),rho_high=rho_high)
        preferences=losses(false_accept=rng.random()*10,false_reject=rng.random()*10,abstain=rng.random()*3)
        assert same_as_inspection(model,preferences,rng.random()*2)


def test_corner_is_the_least_favourable_declared_point_and_joint_matches_branch_costs():
    model=assumptions(q_low=.81,q_high=.99,rho_low=.1,rho_high=.6)
    channel=seq.corner(model)
    assert channel==seq.Channel(.81,.6)
    negative,positive=policy._branch_costs(model,losses())
    h_neg,n_neg=channel.joint(.5,.5,False)
    h_pos,n_pos=channel.joint(.5,.5,True)
    assert (h_neg*4.,n_neg*8.)==negative[1:] and (h_pos*4.,n_pos*8.)==positive[1:]
    assert channel.a==pytest.approx(.6+.4*.81) and channel.b==pytest.approx(.6+.4*.19)
    with pytest.raises(ValueError):
        seq.corner('assumptions')


def test_garbling_matrix_reproduces_the_degraded_channel_and_rejects_improvements():
    better,worse=seq.Channel(.9,0.),seq.Channel(.8,.3)
    matrix=seq.garbling_matrix(better,worse)
    assert matrix[0]==pytest.approx((.9125,.0875)) and matrix[1]==pytest.approx((.3875,.6125))
    for truth in (True,False):
        row=(better.a,1-better.a) if truth else (better.b,1-better.b)
        garbled=tuple(sum(row[i]*matrix[i][j] for i in range(2)) for j in range(2))
        assert garbled==pytest.approx((worse.a,1-worse.a) if truth else (worse.b,1-worse.b))
    with pytest.raises(ValueError,match='not a garbling'):
        seq.garbling_matrix(worse,better)
    with pytest.raises(ValueError,match='uninformative'):
        seq.garbling_matrix(seq.Channel(.5,0.),seq.Channel(.9,0.))
    flat=seq.garbling_matrix(seq.Channel(.5,0.),seq.Channel(.7,1.))
    assert flat==((1.,0.),(1.,0.))
    with pytest.raises(ValueError):
        seq.garbling_matrix(better,(0.8,.3))


def test_value_table_from_the_design_note_for_two_query_costs():
    channel=seq.Channel(.9,0.)
    values=[seq.plan_tree(.5,channel,losses(),.2,k).risk for k in range(5)]
    assert [round(v,3) for v in values]==[1.,.8,.63,.604,.573]
    cheap=[seq.plan_tree(.5,channel,losses(),.05,k).risk for k in range(4)]
    assert round(cheap[1],3)==.65 and round(cheap[3],3)==.277
    horizon,found=seq.choose_horizon(.5,channel,losses(),.2,4)
    assert horizon==4 and found==values
    horizon,_=seq.choose_horizon(.5,channel,losses(),.2,1)
    assert horizon==1
    assert seq.choose_horizon(.5,channel,losses(),2.,3)==(0,[1.,1.,1.,1.])
    with pytest.raises(ValueError):
        seq.choose_horizon(.5,channel,losses(),.2,True)


def test_choose_horizon_uses_the_plateau_at_the_cap_not_the_first_flat_step():
    # One observation is worth nothing here (V_1 == V_0) yet two and three observations pay off, so the
    # first flat step would wrongly stop at K=0; the rule is the smallest K within epsilon of V at the cap.
    channel,preferences=seq.Channel(.83148,0.),losses(false_accept=7.4496,false_reject=8.8957,abstain=.5943)
    horizon,values=seq.choose_horizon(.52683,channel,preferences,.0720,3)
    assert values[0]==values[1]==.5943 and values[1]>values[2]>values[3]
    assert horizon==3
    assert seq.choose_horizon(.52683,channel,preferences,.0720,2)[0]==2
    assert seq.choose_horizon(.52683,channel,preferences,.0720,1)==(0,values[:2])


def test_tree_nodes_carry_joint_masses_sources_and_leaf_actions():
    tree=seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.2,2)
    assert tree.query and tree.source==0 and tree.depth==0
    negative,positive=tree.children
    assert not negative.query and negative.stop_action=='reject'
    assert positive.query and positive.source==1
    assert positive.children[0].stop_action=='abstain' and positive.children[1].stop_action=='accept'
    assert negative.mass_h+negative.mass_n+positive.mass_h+positive.mass_n==pytest.approx(1.)
    assert tree.risk==tree.query_risk and negative.risk==negative.stop_risk
    encoded=tree.to_json()
    assert set(encoded['children'])=={'false','true'} and 'children' not in encoded['children']['false']
    with pytest.raises(FrozenInstanceError):
        tree.query=False


def test_certificate_encloses_every_fixed_tree_and_is_exact_at_horizon_one():
    rng=random.Random(11)
    informative=deep=0
    for _ in range(40):
        q_low=.7+.3*rng.random()
        box=(q_low,q_low+(1-q_low)*rng.random(),rng.random()*.15,.15+rng.random()*.15)
        preferences=losses(false_accept=2+rng.random()*8,false_reject=2+rng.random()*8,abstain=.5+rng.random()*2.5)
        prior,cost=.2+.6*rng.random(),rng.random()*.05
        horizon=rng.choice((1,2,3))
        tree=seq.plan_tree(prior,seq.Channel(box[0],box[3]),preferences,cost,horizon)
        informative+=tree.query
        deep+=tree.query and any(child.query for child in tree.children)
        certificate=seq.certify_worst_case(tree,prior,box,preferences,cost,subdivisions=2)
        assert certificate['exact_upper']>=certificate['exact_attained']
        assert certificate['upper_bound']>=certificate['attained']
        assert isinstance(certificate['exact_upper'],Fraction)
        for q,rho in ((box[0],box[2]),(box[1],box[3]),(box[0],box[3]),(box[1],box[2])):
            exact=seq.policy_risk_exact(tree,prior,seq.Channel(q,rho),preferences,cost)
            assert exact<=certificate['exact_upper']
            assert seq.policy_risk(tree,prior,seq.Channel(q,rho),preferences,cost)==pytest.approx(float(exact))
        assert seq.policy_risk(tree,prior,seq.Channel(box[0],box[3]),preferences,cost)==pytest.approx(tree.risk)
        if horizon==1:
            assert certificate['exact_upper']==certificate['exact_attained']
    # The draw must exercise real trees: most roots query and most multi-depth trees query below the root.
    assert informative>=30 and deep>=20


def relabel_by_depth(node):
    """A fixed tree that is NOT the Bayes tree (leaf action ACTIONS[depth % 3]); certificates cover any fixed tree."""
    if not node.query:
        action=policy.ACTIONS[node.depth%3]
        return replace(node,stop_action=action,stop_risk=node.terms[policy.ACTIONS.index(action)])
    return replace(node,children=tuple(relabel_by_depth(child) for child in node.children))


def test_deep_tree_certificate_exceeds_the_corner_maximum_and_subdivision_tightens_it():
    box,preferences,prior,cost=(.74,.98,.35,.75),losses(false_accept=1.1,false_reject=9.5,abstain=2.6),.12,.01
    tree=relabel_by_depth(seq.plan_tree(prior,seq.Channel(box[0],box[3]),preferences,cost,4))
    assert sorted({node.depth for node in seq._nodes(tree) if node.query})==[0,1,2,3]
    corners=max(seq.policy_risk_exact(tree,prior,seq.Channel(q,rho),preferences,cost)
        for q,rho in product((box[0],box[1]),(box[2],box[3])))
    q0,q1,r0,r1=(Fraction(x) for x in box)
    grid=max(seq._exact_risk(tree,prior,lambda source:(q0+(q1-q0)*i/12,r0+(r1-r0)*j/12),preferences,cost)
        for i in range(13) for j in range(13))
    raw=seq.bernstein_bounds(seq.risk_polynomial(tree,prior,preferences,cost),box)[1]
    certificate=seq.certify_worst_case(tree,prior,box,preferences,cost,subdivisions=3)
    # Interior points beat every corner, so a corner-only bound would be a wrong certificate for this tree;
    # the Bernstein enclosure still covers the grid and subdivision tightens it strictly below the raw bound.
    assert corners<certificate['exact_attained']<=certificate['exact_upper']
    assert corners<grid<=certificate['exact_upper']<raw
    assert seq.certify_worst_case(tree,prior,box,preferences,cost,subdivisions=0)['exact_upper']==raw
    assert certificate['upper_bound']>=float(certificate['exact_upper']) and certificate['gap']>0
    assert float(corners)==pytest.approx(1.6578,abs=1e-4) and float(grid)==pytest.approx(1.7118,abs=1e-4)
    assert float(certificate['exact_upper'])==pytest.approx(1.7122,abs=1e-4) and float(raw)==pytest.approx(1.7435,abs=1e-4)


def test_design_note_certificate_example_over_the_declared_box():
    model=assumptions(q_low=.9,q_high=.95,rho_low=0.,rho_high=.05)
    plan=seq.plan_sequential(model,losses(),.2,1)
    assert plan.purchase and plan.tree.source==0
    assert plan.certificate['upper_bound']==pytest.approx(.915)
    assert plan.certificate['exact_upper']==plan.certificate['exact_attained']
    assert plan.certificate['gap']==0.
    favourable=seq.Channel(.9,0.)
    assert seq.plan_tree(.5,favourable,losses(),.2,1).risk==pytest.approx(.8)
    # The corner tree stops with (reject, abstain); planning for the worst corner costs .1 at the best one.
    assert seq.policy_risk(plan.tree,.5,favourable,losses(),.2)==pytest.approx(.9)
    assert seq.policy_risk_exact(plan.tree,.5,seq.Channel(.9,.05),losses(),.2)==plan.certificate['exact_attained']
    assert plan.query_risk==pytest.approx(.915) and plan.stop_risk==1.
    assert plan.assumptions is model and plan.horizon==1 and plan.reason=='positive_loss_reduction'
    assert 'verification of actual dependencies' in plan.risk_basis
    assert seq.plan_sequential(model,losses(),.2,1,certify=False).certificate is None
    with pytest.raises(FrozenInstanceError):
        plan.purchase=False
    with pytest.raises(ValueError):
        seq.plan_sequential(model,losses(),.2,1,certify=1)


def test_plan_sequential_reasons_mirror_the_cost_screen_and_horizon():
    assert seq.plan_sequential(assumptions(),losses(),.2,0).reason=='no_horizon'
    assert seq.plan_sequential(assumptions(),losses(),1.,2).reason=='cost_screen_skip'
    assert seq.plan_sequential(assumptions(rho_low=.1,rho_high=1.),losses(),.2,1).reason=='no_gain_above_margin'


def test_unknown_outcome_abstains_at_any_depth_without_replanning(monkeypatch):
    plan=seq.plan_sequential(assumptions(),losses(),.05,3,certify=False)
    def forbidden(*args,**kwargs):
        raise AssertionError('a receipt must not rerun the planner')
    monkeypatch.setattr(seq,'plan_tree',forbidden)
    monkeypatch.setattr(seq,'plan_sequential',forbidden)
    assert seq.apply_sequential(plan,())==('query',0)
    step,node=seq.next_step(plan.tree,(True,))
    assert step=='query' and node.depth==1
    assert seq.apply_sequential(plan,(True,))==('query',1)
    paths=[()]
    depths=set()
    while paths:
        path=paths.pop()
        step,node=seq.next_step(plan.tree,path)
        if step=='query':
            depths.add(node.depth)
            assert seq.apply_sequential(plan,path+(None,))==('stop','abstain')
            paths.extend((path+(False,),path+(True,)))
        else:
            assert node in policy.ACTIONS
    assert depths=={0,1,2}
    assert seq.apply_sequential(plan,(True,True,True))==('stop','accept')
    assert seq.apply_sequential(plan,(False,False))==('stop','reject')
    with pytest.raises(ValueError,match='boolean or None'):
        seq.apply_sequential(plan,(1,))
    with pytest.raises(ValueError):
        seq.apply_sequential(plan.tree,())
    with pytest.raises(ValueError):
        seq.next_step(plan,())


def test_stop_at_root_applies_without_outcomes():
    plan=seq.plan_sequential(assumptions(prior=.99),losses(),.2,2,certify=False)
    assert not plan.purchase
    assert seq.apply_sequential(plan,())==('stop','accept')
    assert seq.apply_sequential(plan,(None,))==('stop','accept')


def test_per_depth_channels_never_buy_a_repeated_source_declared_with_full_copy():
    tree=seq.plan_tree(.5,(seq.Channel(.9,0.),seq.Channel(.9,1.)),losses(),.05,2)
    assert tree.query and tree.source==0
    assert all(not child.query for child in tree.children)
    fresh=seq.plan_tree(.5,(seq.Channel(.9,0.),seq.Channel(.9,0.)),losses(),.05,2)
    assert any(child.query and child.source==1 for child in fresh.children)
    assert fresh.risk==seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.05,2).risk
    with pytest.raises(ValueError,match='one declared channel per depth'):
        seq.plan_tree(.5,(seq.Channel(.9,0.),),losses(),.05,2)
    with pytest.raises(ValueError):
        seq.plan_tree(.5,(seq.Channel(.9,0.),(.9,0.)),losses(),.05,2)


def test_joint_corner_certificate_for_distinct_sources_and_refusal_on_repeats():
    channels=(seq.Channel(.9,.05),seq.Channel(.8,.1))
    tree=seq.plan_tree(.5,channels,losses(),.05,2)
    boxes=((.9,.95,0.,.05),(.8,.9,0.,.1))
    certificate=seq.certify_joint_corners(tree,.5,boxes,losses(),.05)
    assert certificate['exact']==seq.policy_risk_exact(tree,.5,list(channels),losses(),.05)
    assert certificate['worst_case']>=float(certificate['exact'])
    assert certificate['at']==((.9,.05),(.8,.1))
    for first in ((.9,0.),(.95,.05)):
        for second in ((.8,0.),(.9,.1)):
            world=[seq.Channel(*first),seq.Channel(*second)]
            assert seq.policy_risk_exact(tree,.5,world,losses(),.05)<=certificate['exact']
    leaf=seq.Node(2,0.,0.,(0.,0.,0.),'abstain',0.,None,False,None)
    inner=seq.Node(1,0.,0.,(0.,0.,0.),'abstain',0.,0.,True,(leaf,leaf),0)
    repeated=seq.Node(0,0.,0.,(0.,0.,0.),'abstain',0.,0.,True,(inner,inner),0)
    with pytest.raises(ValueError,match='repeats'):
        seq.certify_joint_corners(repeated,.5,boxes,losses(),.05)
    with pytest.raises(ValueError,match='one declared box per source'):
        seq.certify_joint_corners(tree,.5,boxes[:1],losses(),.05)
    with pytest.raises(ValueError):
        seq.certify_joint_corners(tree,.5,((.9,.95,0.),),losses(),.05)


def test_tree_digest_is_stable_and_independent_of_key_order():
    plan=seq.plan_sequential(assumptions(),losses(),.2,2,certify=False)
    digest=seq.tree_digest(plan)
    assert len(digest)==64 and int(digest,16)>=0
    assert digest==seq.tree_digest(plan.tree)==seq.tree_digest(plan.tree.to_json())
    reordered={key:plan.tree.to_json()[key] for key in sorted(plan.tree.to_json(),reverse=True)}
    assert seq.tree_digest(reordered)==digest
    assert seq.tree_digest(seq.plan_sequential(assumptions(),losses(),.2,2,certify=False))==digest
    assert seq.tree_digest(seq.plan_sequential(assumptions(),losses(),.2,1,certify=False))!=digest
    with pytest.raises(ValueError):
        seq.tree_digest('{}')


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-.1,1.1])
def test_prior_and_channel_parameters_require_exact_finite_numbers(value):
    with pytest.raises(ValueError):
        seq.Channel(.9,value)
    with pytest.raises(ValueError):
        seq.Channel(value if value not in (True,False) else value,0.)
    with pytest.raises(ValueError):
        seq.plan_tree(value,seq.Channel(.9,0.),losses(),.2,1)
    with pytest.raises(ValueError):
        seq.policy_risk(seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.2,1),value,seq.Channel(.9,0.),losses(),.2)


@pytest.mark.parametrize('horizon',[True,1.,-1,float('nan'),float('inf'),None,'1'])
def test_horizon_must_be_an_exact_nonnegative_integer(horizon):
    with pytest.raises(ValueError):
        seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.2,horizon)
    with pytest.raises(ValueError):
        seq.plan_sequential(assumptions(),losses(),.2,horizon)


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf'),True])
def test_query_cost_margin_and_boxes_are_validated(value):
    with pytest.raises(ValueError):
        seq.plan_tree(.5,seq.Channel(.9,0.),losses(),value,1)
    with pytest.raises(ValueError):
        seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.2,1,epsilon=value)
    tree=seq.plan_tree(.5,seq.Channel(.9,0.),losses(),.2,1)
    with pytest.raises(ValueError):
        seq.certify_worst_case(tree,.5,(.9,.95,0.,value),losses(),.2)
    with pytest.raises(ValueError):
        seq.certify_worst_case(tree,.5,(.9,.95,0.,.05),losses(),.2,subdivisions=value)
    with pytest.raises(ValueError):
        seq.plan_tree(.5,seq.Channel(.9,0.),(8.,4.,1.),.2,1)


def test_sequential_policy_imports_only_declared_standard_modules_and_inspection():
    source=Path(seq.__file__).read_text()
    tree=ast.parse(source)
    absolute,relative=[],[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            absolute.extend(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):
            (relative if node.level else absolute).append(node.module)
    assert set(absolute)=={'dataclasses','fractions','hashlib','itertools','json','math'}
    assert relative==['inspection']
    assert 'random' not in absolute and 'time' not in absolute and 'runner' not in source
