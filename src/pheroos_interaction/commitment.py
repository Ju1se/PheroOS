"""Commitment over declared candidate losses: cross-inhibition and optimal stopping with recall.

Two rules choose between published candidates and abstention from certified losses
that the callers DECLARE. Neither rule verifies a certified loss, calibrates it, or
learns from outcomes. ``commit_value`` is an exact finite-horizon dynamic programme
that is optimal only under its declared arrival model (independent arrivals with a
declared discrete loss distribution); ``cross_inhibition`` is the decentralized
approximation from the colony analysis (a cross-inhibition ODE with an admissibility
gate) and carries no optimality claim: it is a deterministic, bounded-work heuristic
whose 'deadlock' means no quorum with margin within the declared integration window.
This module performs no reads, calls, reservations, messages or authority decisions,
uses no clock and no randomness: the symmetry-breaking perturbation is a hash of the
declared seed and candidate key, so results are replayable and order-independent.
"""
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite

NO_ADMISSIBLE = 'no candidate beats abstaining after latency'
DEADLOCK = 'deadlock'
QUORUM = 'quorum_with_margin'
MAX_STEPS = 2000  # the reference implementation's clamp, refused explicitly instead of silently applied
MAX_ITERATIONS = 1000000  # Euler substeps per integration; the rule runs inside commit's ledger transaction


def _number(value, label):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError('finite ' + label + ' required')
    return value


def _nonnegative(value, label):
    if _number(value, label) < 0:
        raise ValueError('nonnegative ' + label + ' required')
    return value


def _positive(value, label):
    if _number(value, label) <= 0:
        raise ValueError('positive ' + label + ' required')
    return value


def _unit(value, label):
    if not 0 <= _number(value, label) <= 1:
        raise ValueError(label + ' must be in [0,1]')
    return value


def _count(value, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum:
        raise ValueError('exact integer ' + label + ' >= ' + str(minimum) + ' required')
    if maximum is not None and value > maximum:
        raise ValueError(label + ' must not exceed ' + str(maximum))
    return value


def _substeps(dt, rates):
    """(dt_eff, substeps): the stability-limited substep <= .1/rates and how many fill one dt."""
    dt_eff = min(dt, .1 / rates) if rates > 0 else dt
    return dt_eff, max(1, int(round(dt / dt_eff)))


def _sequence(values, label, check):
    values = list(values)
    return [check(value, label) for value in values]


def sigma_star(v):
    """Critical cross-inhibition strength 4v^3/(v^2-1)^2 (Theorem 4); inf for v <= 1.

    Above it the symmetric deadlock of two equal-value candidates is unstable. This
    is the continuous-time threshold; the discrete integration below reaches the
    asymmetric equilibrium only within its bounded window.
    """
    _number(v, 'value')
    return float('inf') if v <= 1 else 4 * v ** 3 / (v * v - 1) ** 2


def deadlock_fraction(v, sigma):
    """Symmetric equilibrium share y* of two equal-value candidates from its quadratic."""
    _positive(v, 'value')
    _nonnegative(sigma, 'sigma')
    a, b, c = 2 * v + sigma, v + 1 / v, -v
    return (-b + (b * b - 4 * a * c) ** .5) / (2 * a)


def commitment_flow(y, values, sigma):
    """Cross-inhibition vector field over commitment shares y with 1-sum(y) uncommitted."""
    y = _sequence(y, 'share', _unit)
    values = _sequence(values, 'value', _positive)
    if len(y) != len(values) or not values:
        raise ValueError('one positive value per share required')
    _nonnegative(sigma, 'sigma')
    y_u = 1 - fsum(y)
    return [v * y_u - yi / v + v * yi * y_u - sigma * yi * (fsum(y) - yi) for yi, v in zip(y, values)]


def integrate_commitment(values, sigma, y0, dt, steps):
    """Explicit Euler with a stability-limited substep (<= .1/(2 max v + sigma)) and simplex projection.

    Deterministic: the result depends only on the arguments. Work is steps times the
    substep count round(dt*(2 max v + sigma)/.1), each substep one flow evaluation,
    and steps*substeps above MAX_ITERATIONS is refused (CommitmentConfig additionally
    caps steps at MAX_STEPS because its rule runs inside a ledger transaction). This
    integrates the declared flow; it is not a proof of convergence to any equilibrium.
    """
    values = _sequence(values, 'value', _positive)
    _nonnegative(sigma, 'sigma')
    y = _sequence(y0, 'initial share', _unit)
    if len(y) != len(values) or not values:
        raise ValueError('one positive value per initial share required')
    if fsum(y) > 1:
        raise ValueError('initial shares must lie in the simplex')
    _positive(dt, 'dt')
    _count(steps, 'steps', 1)
    dt_eff, substeps = _substeps(dt, 2 * max(values) + sigma)
    if steps * substeps > MAX_ITERATIONS:
        raise ValueError('steps * substeps must not exceed ' + str(MAX_ITERATIONS))
    for _ in range(steps * substeps):
        flow = commitment_flow(y, values, sigma)
        y = [min(1., max(0., yi + dt_eff * f)) for yi, f in zip(y, flow)]
        total = fsum(y)
        if total > 1:
            y = [yi / total for yi in y]
    return y


@dataclass(frozen=True)
class CommitmentConfig:
    """Declared cross-inhibition parameters with exact types and an explicit work bound.

    Per commit the rule runs steps*substeps flow evaluations INSIDE the ledger's write
    transaction, with steps <= MAX_STEPS and substeps = round(dt*(2 max v + sigma)/.1)
    <= round(30*dt*sigma_cap) since values and sigma are capped by sigma_cap;
    iteration_bound() is that worst case and must not exceed MAX_ITERATIONS (the
    defaults give 600000, of the order of a second in CPython for a handful of
    candidates). The bound is a lock-hold limit, not a convergence guarantee.
    """
    abstain_loss: float
    latency_cost: float
    decision_time: float
    quorum_frac: float = .45
    margin: float = .05
    dt: float = .01
    steps: int = 2000
    perturbation: float = 1e-3
    seed: str = 'colony'
    sigma_cap: float = 1e3

    def __post_init__(self):
        _positive(self.abstain_loss, 'abstain_loss')
        _nonnegative(self.latency_cost, 'latency_cost')
        _nonnegative(self.decision_time, 'decision_time')
        _unit(self.quorum_frac, 'quorum_frac')
        _nonnegative(self.margin, 'margin')
        _positive(self.dt, 'dt')
        _count(self.steps, 'steps', 1, MAX_STEPS)
        _positive(self.perturbation, 'perturbation')
        if type(self.seed) is not str or '\0' in self.seed:
            raise ValueError('seed must be a string without NUL')
        _positive(self.sigma_cap, 'sigma_cap')
        if self.iteration_bound() > MAX_ITERATIONS:
            raise ValueError('steps * worst-case substeps must not exceed ' + str(MAX_ITERATIONS))

    def iteration_bound(self):
        """Worst-case flow evaluations per commit: steps times the substeps at rates 3*sigma_cap."""
        return self.steps * _substeps(self.dt, 3 * self.sigma_cap)[1]


def _perturbation(key, config):
    digest = sha256((config.seed + '\0' + key).encode('utf-8')).hexdigest()
    return config.perturbation * (int(digest, 16) / 2 ** 256)


def cross_inhibition(certified_losses, keys, config):
    """Decentralized commitment: admissibility gate, then the cross-inhibition ODE.

    Candidate i enters iff loss_i + latency_cost*decision_time < abstain_loss, which is
    exactly v_i > v_bar for v_i = abstain_loss/loss_i (a zero loss takes sigma_cap) and
    v_bar = abstain_loss/(abstain_loss - latency); sigma = sigma_star(v_bar) capped, or 0
    when latency >= abstain_loss (v_bar reported as inf). Publishes the top share iff it
    reaches quorum_frac with margin over the second share after config.steps of dt, else
    abstains: 'reason' is NO_ADMISSIBLE when the gate empties the field and DEADLOCK
    otherwise. Never waits. 'index' is the position in the supplied sequences; 'y' is
    aligned with them (0. for inadmissible candidates, listed under 'admissible').
    Deterministic and independent of candidate order: shares start at a hash of the
    seed and key. No claim that the outcome is optimal or that the losses are true.
    """
    if not isinstance(config, CommitmentConfig):
        raise ValueError('validated commitment config required')
    keys = list(keys)
    losses = _sequence(certified_losses, 'certified loss', _nonnegative)
    if not keys or len(keys) != len(losses):
        raise ValueError('one key per certified loss required')
    if any(type(key) is not str or '\0' in key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError('distinct string keys without NUL required')
    abstain, cap = config.abstain_loss, config.sigma_cap
    latency = config.latency_cost * config.decision_time
    if latency >= abstain:
        v_bar, sigma = float('inf'), 0.
    else:
        v_bar = abstain / (abstain - latency)
        sigma = min(sigma_star(v_bar), cap)
    admissible = tuple(i for i, loss in enumerate(losses) if loss + latency < abstain)
    result = {'decision': 'abstain', 'index': None, 'sigma': sigma, 'v_bar': v_bar,
              'y': [0.] * len(losses), 'admissible': admissible, 'reason': NO_ADMISSIBLE}
    if not admissible:
        return result
    values = [min(abstain / losses[i], cap) if losses[i] > 0 else cap for i in admissible]
    y0 = [_perturbation(keys[i], config) for i in admissible]
    if fsum(y0) > 1:
        raise ValueError('perturbation too large for the candidate count')
    y = integrate_commitment(values, sigma, y0, config.dt, config.steps)
    order = sorted(range(len(y)), key=lambda j: (-y[j], keys[admissible[j]]))
    top = order[0]
    second = y[order[1]] if len(order) > 1 else 0.
    for j, share in zip(admissible, y):
        result['y'][j] = share
    if y[top] >= config.quorum_frac and y[top] - second >= config.margin:
        result.update(decision='publish', index=admissible[top], reason=QUORUM)
    else:
        result['reason'] = DEADLOCK
    return result


def _rows(candidates):
    rows = list(candidates)
    for row in rows:
        if type(row.get('call_id')) is not str:
            raise ValueError('candidate rows need string call ids')
        _nonnegative(row.get('certified_loss'), 'certified loss')
    return rows


def cross_inhibition_rule(config):
    """Decision rule for PlatformMixin.commit: the chosen call id or None (terminal abstention).

    Keys are call ids. The ledger's abstain_loss must equal the configured one, since
    the gate and sigma were derived from it. Never returns wait.
    """
    if not isinstance(config, CommitmentConfig):
        raise ValueError('validated commitment config required')

    def rule(candidates, abstain_loss):
        if _nonnegative(abstain_loss, 'abstain_loss') != config.abstain_loss:
            raise ValueError('ledger abstain_loss must equal the configured abstain_loss')
        rows = _rows(candidates)
        keys = [row['call_id'] for row in rows]
        result = cross_inhibition([row['certified_loss'] for row in rows], keys, config)
        return keys[result['index']] if result['decision'] == 'publish' else None
    return rule


def commit_value(abstain_loss, latency_cost, deadline, arrival_prob, loss_support, loss_probs):
    """Optimal stopping with recall, evaluated EXACTLY for arbitrary states.

    State (t, r): r is the best certified loss in hand (None = no candidate), t ticks
    elapsed. Actions: publish (loss r), abstain (loss l0), wait one tick (cost
    latency_cost; with probability arrival_prob a candidate arrives with loss drawn
    from the declared discrete distribution).
        V_T(r) = min(r, l0)                       V_T(None) = l0
        V_t(r) = min(r, l0, c + (1-lam) V_{t+1}(r) + lam sum_k p_k V_{t+1}(min(r, r_k)))
    min(r, r_k) is r or a support value, so the states reachable from any r form a
    finite closure and V_t(r) is tabulated exactly for an off-support r (no grid).
    Returns decide(t, r) -> {'state': 'no_candidate'|'publish'|'abstain'|'wait',
    'value': V_t(r), 'wait_value': the wait branch or None at the deadline}; t at or
    beyond the deadline holds. Optimal only under this declared model; the arrival
    probability and loss distribution are caller assumptions, not calibrated ones.
    """
    l0 = _nonnegative(abstain_loss, 'abstain_loss')
    c_t = _nonnegative(latency_cost, 'latency_cost')
    _count(deadline, 'deadline')
    _unit(arrival_prob, 'arrival_prob')
    support = _sequence(loss_support, 'loss', _nonnegative)
    probs = _sequence(loss_probs, 'probability', _nonnegative)
    if not support or len(support) != len(probs):
        raise ValueError('loss_support and loss_probs must be non-empty and of equal length')
    if abs(fsum(probs) - 1) > 1e-12:
        raise ValueError('loss_probs must sum to 1')
    dist = list(zip(support, probs))
    memo = {}

    def hold(r):
        return l0 if r is None else min(r, l0)

    def fill(r):
        closure = {r} | ({s for s in support} if r is None else {min(r, s) for s in support})
        states = sorted(closure, key=lambda s: (s is not None, s))
        for t in range(deadline - 1, -1, -1):
            for s in states:
                if (t, s) in memo:
                    continue
                expect = fsum(p * value(t + 1, r_new if s is None else min(s, r_new))[0] for r_new, p in dist)
                wait = c_t + (1 - arrival_prob) * value(t + 1, s)[0] + arrival_prob * expect
                memo[(t, s)] = (min(hold(s), wait), wait)

    def value(t, r):
        if t >= deadline:
            return hold(r), None
        if (t, r) not in memo:
            fill(r)
        return memo[(t, r)]

    def decide(t, r):
        _count(t, 'tick')
        if r is not None:
            _nonnegative(r, 'candidate loss')
        current, wait = value(t, r)
        if r is None:
            state = 'no_candidate' if (wait is not None and wait < l0) else 'abstain'
        elif r <= l0 and (wait is None or r <= wait):
            state = 'publish'
        elif wait is not None and wait < l0:
            state = 'wait'
        else:
            state = 'abstain'
        return {'state': state, 'value': current, 'wait_value': wait}

    return decide


def optimal_stopping_rule(abstain_loss, latency_cost, deadline, arrival_prob, loss_support, loss_probs, elapsed):
    """Decision rule for PlatformMixin.commit from commit_value at the declared elapsed tick.

    r is the smallest certified loss; publish returns that call id (ties by call id
    ascending), wait returns {'decision': 'wait'}, abstain or no candidate returns
    None. The ledger's abstain_loss must equal the one the programme was built from.
    """
    decide = commit_value(abstain_loss, latency_cost, deadline, arrival_prob, loss_support, loss_probs)
    _count(elapsed, 'elapsed')

    def rule(candidates, ledger_abstain_loss):
        if _nonnegative(ledger_abstain_loss, 'abstain_loss') != abstain_loss:
            raise ValueError('ledger abstain_loss must equal the programmed abstain_loss')
        rows = _rows(candidates)
        if not rows:
            return None
        best = min(rows, key=lambda row: (row['certified_loss'], row['call_id']))
        state = decide(elapsed, best['certified_loss'])['state']
        if state == 'publish':
            return best['call_id']
        return {'decision': 'wait'} if state == 'wait' else None
    return rule
