"""Finite-horizon inspection trees in joint coordinates for one declared channel family.

A tree fixes every read and every stop action before the first receipt. Horizon 1
reproduces plan_inspection bit for bit, including its global tie budget across the
two branches. Each depth binds a DISTINCT declared source: re-reading the same
fingerprint returns the same evidence, not a fresh conditionally independent draw,
so a repeated source must be declared with rho=1 and the tree will not buy it.

Certificates bound the expected loss of the FIXED tree over the declared box using
exact rational arithmetic on the represented float inputs. They are not posterior
probabilities, not a verification of actual dependencies, not a calibration of q or
rho, and not a proof that the tree is minimax over the box. A tree minimizes the
declared expected loss only at the corner it was planned at, within the tie tolerance
and epsilon margin and with ties broken towards fewer decisions; no optimality is
claimed beyond that declaration. This module performs no reads, calls, reservations
or authority decisions, and an unknown observation never replans.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from itertools import product
from json import dumps
from math import comb, fsum, nextafter

from .inspection import (ACTIONS, TIE_TOLERANCE, Losses, ModelAssumptions, _feasible,
                         _nonnegative, _number, _risk)

RISK_BASIS = ('expected loss of the frozen tree within the declared family, planned at its '
              'least-favourable corner and certified over the declared box; neither posterior '
              'probability, verification of actual dependencies nor a minimax optimality claim')


def _exact_int(value, label):
    if type(value) is not int:
        raise ValueError('exact integer ' + label + ' required')
    return value


def _unit(value, label):
    if not 0 <= _number(value, label) <= 1:
        raise ValueError(label + ' must be in [0,1]')
    return value


@dataclass(frozen=True)
class Channel:
    """One declared symmetric positive-copy channel: reliability q and copy weight rho."""
    q: float
    rho: float

    def __post_init__(self):
        if not .5 <= _number(self.q, 'q') <= 1:
            raise ValueError('symmetric reliability q must satisfy .5 <= q <= 1')
        _unit(self.rho, 'rho')

    @property
    def a(self):
        return self.rho + (1-self.rho) * self.q  # P(+ | H)

    @property
    def b(self):
        return self.rho + (1-self.rho) * (1-self.q)  # P(+ | not H)

    def joint(self, mass_h, mass_n, outcome):
        """Joint masses after one outcome, in exactly the arithmetic order of inspection._branch_costs."""
        q, rho = self.q, self.rho
        if outcome:
            return mass_h * (rho + (1-rho) * q), mass_n * (rho + (1-rho) * (1-q))
        return mass_h * (1-rho) * (1-q), mass_n * (1-rho) * q


def corner(assumptions):
    """The least-favourable corner (q_low, rho_high) of the declared box; no calibration."""
    if not isinstance(assumptions, ModelAssumptions):
        raise ValueError('validated assumptions required')
    return Channel(assumptions.q_low, assumptions.rho_high)


def garbling_matrix(better, worse):
    """Row-stochastic M (rows and columns ordered +,-) with W(worse) = W(better) @ M.

    Defined when worse is a degradation of better (worse.q <= better.q and
    worse.rho >= better.rho); raises otherwise. Two uninformative channels are
    related by the matrix whose rows both equal the worse channel's outcome law.
    Blackwell ordering says nothing about which channel a real source is.
    """
    if not isinstance(better, Channel) or not isinstance(worse, Channel):
        raise ValueError('two validated channels required')
    info_better = (1-better.rho) * (2*better.q-1)
    info_worse = (1-worse.rho) * (2*worse.q-1)
    if info_better == 0:
        if info_worse != 0:
            raise ValueError('an uninformative channel cannot be garbled into an informative one')
        return ((worse.a, 1-worse.a), (worse.a, 1-worse.a))
    degradation = info_worse / info_better
    m_minus = worse.b - better.b * degradation
    m_plus = m_minus + degradation
    for entry in (m_minus, m_plus):
        if not -TIE_TOLERANCE <= entry <= 1+TIE_TOLERANCE:
            raise ValueError('not a garbling: needs worse.q <= better.q and worse.rho >= better.rho')
    m_plus, m_minus = min(1., max(0., m_plus)), min(1., max(0., m_minus))
    return ((m_plus, 1-m_plus), (m_minus, 1-m_minus))


def stop_terms(mass_h, mass_n, losses, root):
    """(abstain, reject, accept) joint losses in plan_inspection's arithmetic order.

    At the root plan_inspection uses (abstain, prior*false_reject, (1-prior)*false_accept);
    in a branch it uses fsum((not_h*abstain, h*abstain)), h*false_reject, not_h*false_accept.
    """
    if root:
        return (losses.abstain, mass_h*losses.false_reject, mass_n*losses.false_accept)
    return (fsum((mass_n*losses.abstain, mass_h*losses.abstain)),
            mass_h*losses.false_reject, mass_n*losses.false_accept)


def _argmin_tie(terms):
    minimum = min(terms)
    return next(index for index in range(len(terms)) if _feasible(terms[index], minimum))


def shared_map(negative, positive, query_cost):
    """inspection._shared_map over two leaf term triples: one global tie budget.

    Prefers fewer non-abstaining decisions, then abstain/reject/accept by outcome.
    Returns (query_risk, (action_on_negative, action_on_positive)).
    """
    by_count = ((negative[0], min(negative[1:])), (positive[0], min(positive[1:])))
    minimum = _risk(query_cost, min(negative), min(positive))
    count_minima = (_risk(query_cost, by_count[0][0], by_count[1][0]),
        min(_risk(query_cost, by_count[0][0], by_count[1][1]),
            _risk(query_cost, by_count[0][1], by_count[1][0])),
        _risk(query_cost, by_count[0][1], by_count[1][1]))
    count = next(k for k in (0, 1, 2) if _feasible(count_minima[k], minimum))
    for first_index, first_action in enumerate(ACTIONS):
        remaining = count - int(first_action != 'abstain')
        if remaining not in (0, 1) or not _feasible(
                _risk(query_cost, negative[first_index], by_count[1][remaining]), minimum):
            continue
        for second_index, second_action in enumerate(ACTIONS):
            if int(second_action != 'abstain') != remaining:
                continue
            selected = _risk(query_cost, negative[first_index], positive[second_index])
            if _feasible(selected, minimum):
                return selected, (first_action, second_action)
    raise ArithmeticError('no feasible inspection map within the global tie tolerance')


@dataclass(frozen=True)
class Node:
    """One tree node in joint coordinates; source is the declared source index read here."""
    depth: int
    mass_h: float
    mass_n: float
    terms: tuple
    stop_action: str
    stop_risk: float
    query_risk: float | None
    query: bool
    children: tuple | None
    source: int | None = None

    @property
    def risk(self):
        return self.query_risk if self.query else self.stop_risk

    def to_json(self):
        """Plain dict; children keyed 'false'/'true'. Infinite risks cannot be frozen (allow_nan=False)."""
        out = {'depth': self.depth, 'mass_h': self.mass_h, 'mass_n': self.mass_n,
               'stop_action': self.stop_action, 'stop_risk': self.stop_risk,
               'query_risk': self.query_risk, 'query': self.query, 'source': self.source}
        if self.query:
            out['children'] = {'false': self.children[0].to_json(), 'true': self.children[1].to_json()}
        return out


def _channels(channels, horizon):
    if isinstance(channels, Channel):
        return channels
    channels = tuple(channels)
    if not all(isinstance(channel, Channel) for channel in channels):
        raise ValueError('validated channels required')
    if len(channels) < horizon:
        raise ValueError('one declared channel per depth required')
    return channels


def _channel_at(channels, index):
    return channels if isinstance(channels, Channel) else channels[index]


def _source(node):
    return node.source if node.source is not None else node.depth


def _plan_inputs(prior, losses, query_cost, epsilon):
    _unit(prior, 'prior')
    if not isinstance(losses, Losses):
        raise ValueError('explicit losses required')
    _nonnegative(query_cost, 'inspection cost')
    _nonnegative(epsilon, 'minimum improvement')


def plan_tree(prior, channels, losses, query_cost, horizon, epsilon=1e-12):
    """Backward induction in joint coordinates; no posteriors, no divisions.

    channels: one Channel (the same declared family at every depth) or a sequence with
    one Channel per depth, each a DISTINCT declared source (Node.source = depth). The
    plan minimizes the declared expected loss only at the supplied channels, within the
    tie tolerance and epsilon margin; the value at other points of a declared box is
    what the certificates bound. horizon=1 equals plan_inspection.
    """
    _plan_inputs(prior, losses, query_cost, epsilon)
    if _exact_int(horizon, 'horizon') < 0:
        raise ValueError('horizon must be a nonnegative integer')
    channels = _channels(channels, horizon)

    def build(mass_h, mass_n, depth, root):
        terms = stop_terms(mass_h, mass_n, losses, root)
        index = _argmin_tie(terms)
        stop_action, stop_risk = ACTIONS[index], terms[index]
        mass = 1. if root else mass_h+mass_n
        cost = query_cost if root else query_cost*mass
        if depth == horizon or cost >= stop_risk-epsilon*mass:
            return Node(depth, mass_h, mass_n, terms, stop_action, stop_risk, None, False, None)
        channel = _channel_at(channels, depth)
        kids = []
        for outcome in (False, True):
            h, n = channel.joint(mass_h, mass_n, outcome)
            kids.append(build(h, n, depth+1, False))
        if not kids[0].query and not kids[1].query:
            query_risk, (act_neg, act_pos) = shared_map(kids[0].terms, kids[1].terms, cost)
            kids = [replace(kids[0], stop_action=act_neg, stop_risk=kids[0].terms[ACTIONS.index(act_neg)]),
                    replace(kids[1], stop_action=act_pos, stop_risk=kids[1].terms[ACTIONS.index(act_pos)])]
        else:
            query_risk = _risk(cost, kids[0].risk, kids[1].risk)
        query = stop_risk-query_risk > epsilon*mass
        return Node(depth, mass_h, mass_n, terms, stop_action, stop_risk, query_risk, query,
                    tuple(kids) if query else None, depth if query else None)

    return build(prior, 1-prior, 0, True)


def choose_horizon(prior, channels, losses, query_cost, max_calls, epsilon=1e-12):
    """Smallest K whose value is within epsilon of the value at the call cap.

    V_K is non-increasing in K but can plateau before dropping (value only after
    several observations), so the first flat step is not used. Returns (K, values).
    """
    if _exact_int(max_calls, 'call cap') < 0:
        raise ValueError('call cap must be a nonnegative integer')
    values = [plan_tree(prior, channels, losses, query_cost, k, epsilon).risk for k in range(max_calls+1)]
    target = values[-1]
    return next(k for k, value in enumerate(values) if value <= target+epsilon), values


def next_step(node, outcomes):
    """Walk the frozen tree; an unknown observation stops with abstain and never replans."""
    if not isinstance(node, Node):
        raise ValueError('validated tree node required')
    for outcome in outcomes:
        if outcome is not None and type(outcome) is not bool:
            raise ValueError('inspection outcome must be boolean or None for unknown')
        if not node.query:
            break
        if outcome is None:
            return 'stop', 'abstain'
        node = node.children[int(outcome)]
    return ('query', node) if node.query else ('stop', node.stop_action)


def policy_risk(node, prior, channels, losses, query_cost):
    """Float risk of the FIXED tree when the world is channels (one Channel or a list by source)."""
    _plan_inputs(prior, losses, query_cost, 0.)
    if not isinstance(node, Node):
        raise ValueError('validated tree node required')

    def walk(node, mass_h, mass_n):
        if not node.query:
            return dict(zip(ACTIONS, stop_terms(mass_h, mass_n, losses, False)))[node.stop_action]
        channel = _channel_at(channels, _source(node))
        total = query_cost*(mass_h+mass_n)
        for outcome, child in zip((False, True), node.children):
            h, n = channel.joint(mass_h, mass_n, outcome)
            total += walk(child, h, n)
        return total
    return walk(node, prior, 1-prior)


def _F(value):
    return value if isinstance(value, Fraction) else Fraction(value)


def _float_up(value):
    """Smallest float >= the exact rational (outward rounding for an upper bound)."""
    approximation = float(value)
    return approximation if Fraction(approximation) >= value else nextafter(approximation, float('inf'))


def _float_down(value):
    approximation = float(value)
    return approximation if Fraction(approximation) <= value else nextafter(approximation, float('-inf'))


def _exact_likelihood(q, rho, outcome, h):
    if outcome:
        return rho + (1-rho)*q if h else rho + (1-rho)*(1-q)
    return (1-rho)*(1-q) if h else (1-rho)*q


def _exact_risk(node, prior, parameters, losses, query_cost):
    """Exact rational risk; parameters(source) -> exact (q, rho) of the source read there."""
    fa, fr, ab, c = (_F(losses.false_accept), _F(losses.false_reject), _F(losses.abstain), _F(query_cost))

    def walk(node, weight_h, weight_n):
        if not node.query:
            return {'abstain': (weight_h+weight_n)*ab, 'reject': weight_h*fr, 'accept': weight_n*fa}[node.stop_action]
        q, rho = parameters(_source(node))
        total = c*(weight_h+weight_n)
        for outcome, child in zip((False, True), node.children):
            total += walk(child, weight_h*_exact_likelihood(q, rho, outcome, True),
                          weight_n*_exact_likelihood(q, rho, outcome, False))
        return total
    return walk(node, _F(prior), 1-_F(prior))


def policy_risk_exact(node, prior, channels, losses, query_cost):
    """Exact rational risk of the fixed tree at the represented channel parameters."""
    _plan_inputs(prior, losses, query_cost, 0.)
    if not isinstance(node, Node):
        raise ValueError('validated tree node required')

    def parameters(source):
        channel = _channel_at(channels, source)
        return _F(channel.q), _F(channel.rho)
    return _exact_risk(node, prior, parameters, losses, query_cost)


# Exponents (i, j) mean q^i * rho^j; coefficients are exact integers.
_LIKELIHOOD_POLY = {
    (True, True): {(1, 0): 1, (0, 1): 1, (1, 1): -1},               # P(+|H)    = q + rho - q rho
    (True, False): {(0, 0): 1, (1, 0): -1, (1, 1): 1},              # P(+|notH) = 1 - q + q rho
    (False, True): {(0, 0): 1, (1, 0): -1, (0, 1): -1, (1, 1): 1},  # P(-|H)    = 1 - q - rho + q rho
    (False, False): {(1, 0): 1, (1, 1): -1},                        # P(-|notH) = q - q rho
}


def _pmul(a, b):
    out = {}
    for (i, j), x in a.items():
        for (k, l), y in b.items():
            out[(i+k, j+l)] = out.get((i+k, j+l), 0) + x*y
    return out


def _padd(*polys):
    out = {}
    for poly in polys:
        for key, value in poly.items():
            out[key] = out.get(key, 0) + value
    return out


def _pscale(a, s):
    return {key: value*s for key, value in a.items()}


def risk_polynomial(node, prior, losses, query_cost):
    """Exact coefficients of the fixed tree's risk as a polynomial in (q, rho).

    Shared-parameter case: the SAME channel box at every depth. For per-source boxes
    use certify_joint_corners.
    """
    fa, fr, ab, c = (_F(losses.false_accept), _F(losses.false_reject), _F(losses.abstain), _F(query_cost))

    def walk(node, poly_h, poly_n):
        if not node.query:
            if node.stop_action == 'abstain':
                return _pscale(_padd(poly_h, poly_n), ab)
            if node.stop_action == 'reject':
                return _pscale(poly_h, fr)
            return _pscale(poly_n, fa)
        total = _pscale(_padd(poly_h, poly_n), c)
        for outcome, child in zip((False, True), node.children):
            total = _padd(total, walk(child, _pmul(poly_h, _LIKELIHOOD_POLY[(outcome, True)]),
                                      _pmul(poly_n, _LIKELIHOOD_POLY[(outcome, False)])))
        return total
    return walk(node, {(0, 0): _F(prior)}, {(0, 0): 1-_F(prior)})


def _to_unit_square(poly, box):
    q0, q1, r0, r1 = (_F(x) for x in box)
    dq, dr = q1-q0, r1-r0
    out = {}
    for (i, j), coefficient in poly.items():
        for k in range(i+1):
            for l in range(j+1):
                out[(k, l)] = out.get((k, l), 0) + (coefficient * comb(i, k) * q0**(i-k) * dq**k
                                                    * comb(j, l) * r0**(j-l) * dr**l)
    return out


def bernstein_bounds(poly, box):
    """Exact (lower, upper) Fractions enclosing the polynomial over the box.

    Bernstein coefficient bounds (Cargo-Shisha 1966; Garloff 1985): exact at the
    corners, an enclosure everywhere else.
    """
    unit = _to_unit_square(poly, box)
    n = max((i for i, _ in unit), default=0)
    m = max((j for _, j in unit), default=0)
    coefficients = []
    for k in range(n+1):
        for l in range(m+1):
            b = Fraction(0)
            for (i, j), a in unit.items():
                if i <= k and j <= l:
                    b += a * Fraction(comb(k, i)*comb(l, j), comb(n, i)*comb(m, j))
            coefficients.append(b)
    return min(coefficients), max(coefficients)


def _check_box(box):
    """Boxes are represented-float inputs (q_low, q_high, rho_low, rho_high)."""
    box = tuple(box)
    if len(box) != 4:
        raise ValueError('box must be four values (q_low, q_high, rho_low, rho_high)')
    for value in box:
        _number(value, 'box bound')
    q0, q1, r0, r1 = box
    if not (.5 <= q0 <= q1 <= 1 and 0 <= r0 <= r1 <= 1):
        raise ValueError('box out of range or inverted')
    return box


def certify_worst_case(node, prior, box, losses, query_cost, subdivisions=3):
    """Rigorous enclosure of max risk of the FIXED tree over a shared-parameter box.

    exact_upper is the Bernstein upper bound tightened by subdivision; exact_attained
    is the exact maximum at the evaluated sub-box corners (a lower bound on the true
    maximum), so exact_upper >= exact_attained holds strictly and at horizon 1 the
    bilinear risk makes them equal at a corner. Floats are rounded outward. Sub-box
    corners are evaluated as exact rationals (the reference kernel rounds them to
    floats), so after a subdivision exact_attained can differ from the kernel's in
    its last bits while every bound stays valid. This bounds expected loss of one
    fixed tree only; it is not a minimax value and says nothing about a realized
    trajectory.
    """
    _plan_inputs(prior, losses, query_cost, 0.)
    if not isinstance(node, Node):
        raise ValueError('validated tree node required')
    if _exact_int(subdivisions, 'subdivision count') < 0:
        raise ValueError('subdivision count must be a nonnegative integer')
    box = _check_box(box)
    poly = risk_polynomial(node, prior, losses, query_cost)

    def recurse(sub, level):
        _, upper = bernstein_bounds(poly, sub)
        attained = max(_exact_risk(node, prior, lambda source: (q, r), losses, query_cost)
                       for q, r in product((sub[0], sub[1]), (sub[2], sub[3])))
        if level == 0 or upper <= attained:
            return upper, attained
        q0, q1, r0, r1 = sub
        qm, rm = (q0+q1)/2, (r0+r1)/2
        parts = [recurse(part, level-1) for part in
                 ((q0, qm, r0, rm), (qm, q1, r0, rm), (q0, qm, rm, r1), (qm, q1, rm, r1))]
        return max(u for u, _ in parts), max(a for _, a in parts)

    upper, attained = recurse(tuple(_F(x) for x in box), subdivisions)
    return {'upper_bound': _float_up(upper), 'attained': _float_down(attained),
            'gap': _float_up(upper-attained), 'exact_upper': upper, 'exact_attained': attained}


def _nodes(node):
    yield node
    if node.query:
        for child in node.children:
            yield from _nodes(child)


def _repeats(node, seen=frozenset()):
    """Yield True for any path on which a source is read twice."""
    if not node.query:
        yield False
        return
    if _source(node) in seen:
        yield True
        return
    for child in node.children:
        yield from _repeats(child, seen | {_source(node)})


def certify_joint_corners(node, prior, boxes, losses, query_cost):
    """Exact worst case of the FIXED tree for PER-SOURCE boxes, each source read at most once per path.

    The fixed-policy risk is then multilinear in the source parameters, so its maximum
    over the product of boxes is at a joint corner: 4^K exact evaluations. boxes are
    indexed by source. Raises when a source repeats on some path (use certify_worst_case).
    """
    _plan_inputs(prior, losses, query_cost, 0.)
    if not isinstance(node, Node):
        raise ValueError('validated tree node required')
    boxes = [_check_box(box) for box in boxes]
    sources = {_source(inner) for inner in _nodes(node) if inner.query}
    if any(_repeats(node)):
        raise ValueError('a source repeats on some path: multilinearity fails, use certify_worst_case')
    if any(source >= len(boxes) for source in sources):
        raise ValueError('one declared box per source required')
    best, arg = None, None
    for joint in product(*[list(product((box[0], box[1]), (box[2], box[3]))) for box in boxes]):
        value = _exact_risk(node, prior, lambda source: (_F(joint[source][0]), _F(joint[source][1])),
                            losses, query_cost)
        if best is None or value > best:
            best, arg = value, joint
    return {'worst_case': _float_up(best), 'exact': best, 'at': arg}


@dataclass(frozen=True)
class SequentialPlan:
    assumptions: ModelAssumptions
    losses: Losses
    query_cost: float
    epsilon: float
    horizon: int
    tree: Node
    stop_action: str
    stop_risk: float
    query_risk: float | None
    purchase: bool
    reason: str
    certificate: dict | None
    tie_tolerance: float = TIE_TOLERANCE
    risk_basis: str = RISK_BASIS


def plan_sequential(assumptions, losses, query_cost, horizon, epsilon=1e-12, certify=True):
    """Plan at the least-favourable corner and certify the frozen tree over the declared box.

    The same declared family is read at every depth. Scope, call caps, cancellation,
    result verification and budget reservations belong to the caller.
    """
    if not isinstance(assumptions, ModelAssumptions) or not isinstance(losses, Losses):
        raise ValueError('validated assumptions and explicit losses required')
    if type(certify) is not bool:
        raise ValueError('certify must be boolean')
    tree = plan_tree(assumptions.prior, corner(assumptions), losses, query_cost, horizon, epsilon)
    if horizon == 0:
        reason = 'no_horizon'
    elif tree.query_risk is None:
        reason = 'cost_screen_skip'
    else:
        reason = 'positive_loss_reduction' if tree.query else 'no_gain_above_margin'
    certificate = None
    if certify:
        box = (assumptions.q_low, assumptions.q_high, assumptions.rho_low, assumptions.rho_high)
        certificate = certify_worst_case(tree, assumptions.prior, box, losses, query_cost)
    return SequentialPlan(assumptions, losses, query_cost, epsilon, horizon, tree, tree.stop_action,
        tree.stop_risk, tree.query_risk, tree.query, reason, certificate)


def apply_sequential(plan, outcomes):
    """Apply the precommitted tree: ('query', depth) or ('stop', action); unknown abstains."""
    if not isinstance(plan, SequentialPlan):
        raise ValueError('validated sequential plan required')
    step, value = next_step(plan.tree, outcomes)
    return (step, value.depth) if step == 'query' else (step, value)


def tree_digest(tree):
    """sha256 of the canonical JSON of a plan's tree, a Node or its to_json dict."""
    if isinstance(tree, SequentialPlan):
        tree = tree.tree
    if isinstance(tree, Node):
        tree = tree.to_json()
    if type(tree) is not dict:
        raise ValueError('sequential plan, tree node or its JSON dict required')
    return sha256(dumps(tree, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
