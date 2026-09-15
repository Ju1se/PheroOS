"""A replaceable one-inspection policy for one explicitly declared channel family.

Recognizing a fixed-prior symmetric positive-copy model is not verification of
its real dependency structure. The supplied assumptions are preserved in each
plan. This module performs no reads, calls, reservations or authority decisions.
"""
from dataclasses import dataclass
from math import fsum, isclose, isfinite

FAMILY = 'fixed-prior-symmetric-positive-copy-v1'
ACTIONS = ('abstain', 'reject', 'accept')
TIE_TOLERANCE = 1e-12
MAX_TEXT_LENGTH = 2048


def _number(value, label):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError('finite ' + label + ' required')
    return value


def _nonnegative(value, label):
    if _number(value, label) < 0:
        raise ValueError('nonnegative ' + label + ' required')


def _text(value, label):
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise ValueError('bounded nonempty ' + label + ' required')


@dataclass(frozen=True)
class ModelAssumptions:
    family: str
    version: str
    source: str
    applicability: str
    prior: float
    q_low: float
    q_high: float
    rho_low: float
    rho_high: float
    reference: bool = True

    def __post_init__(self):
        for field in ('family', 'version', 'source', 'applicability'):
            _text(getattr(self, field), field)
        if self.family != FAMILY:
            raise ValueError('unsupported conditional channel family')
        for field in ('prior', 'q_low', 'q_high', 'rho_low', 'rho_high'):
            _number(getattr(self, field), field)
        if not 0 <= self.prior <= 1:
            raise ValueError('prior must be in [0,1]')
        if not .5 <= self.q_low <= self.q_high <= 1:
            raise ValueError('symmetric reliability range must satisfy .5 <= q_low <= q_high <= 1')
        if not 0 <= self.rho_low <= self.rho_high <= 1:
            raise ValueError('copy range must satisfy 0 <= rho_low <= rho_high <= 1')
        if type(self.reference) is not bool or not self.reference:
            raise ValueError('this family requires the declared positive reference')


@dataclass(frozen=True)
class Losses:
    false_accept: float
    false_reject: float
    abstain: float

    def __post_init__(self):
        for field in ('false_accept', 'false_reject', 'abstain'):
            _nonnegative(getattr(self, field), field + ' loss')


@dataclass(frozen=True)
class InspectionPlan:
    assumptions: ModelAssumptions
    losses: Losses
    query_cost: float
    epsilon: float
    stop_action: str
    stop_risk: float
    query_risk: float | None
    query_delta: tuple[tuple[bool | None, str], ...] | None
    purchase: bool
    reason: str
    risk_term_count: int
    tie_tolerance: float = TIE_TOLERANCE
    risk_basis: str = 'expected loss within the declared family; neither posterior probability nor verification of actual dependencies'


def _feasible(candidate, minimum):
    # Adding the tolerance to minimum can round up and admit a point more than
    # tolerance away. Compare the actual difference, including inspection cost.
    return candidate <= minimum or isclose(candidate, minimum, rel_tol=0., abs_tol=TIE_TOLERANCE)


def _risk(query_cost, *contributions):
    try:
        return query_cost + fsum(contributions)
    except OverflowError:
        return float('inf')  # An overflowing alternative cannot beat a finite plan.


def _branch_costs(assumptions, losses):
    """Exactly six joint-loss contributions at q_low, rho_high; no posteriors."""
    p, q, rho = assumptions.prior, assumptions.q_low, assumptions.rho_high
    not_h_negative = (1-p) * (1-rho) * q
    h_negative = p * (1-rho) * (1-q)
    not_h_positive = (1-p) * (rho + (1-rho) * (1-q))
    h_positive = p * (rho + (1-rho) * q)
    return tuple((fsum((not_h*losses.abstain, h*losses.abstain)),
                  h*losses.false_reject, not_h*losses.false_accept)
                 for not_h, h in ((not_h_negative, h_negative), (not_h_positive, h_positive)))


def _shared_map(branches, query_cost):
    """Use one global tie budget; prefer fewer decisions, then U/R/A by outcome.

    The two branches have additive loss. Count layers K=0,1,2 establish the
    smallest feasible number of non-abstaining actions. Greedy feasibility then
    selects each action without enumerating the nine possible complete maps.
    """
    negative, positive = branches
    # For each outcome: cheapest action with zero or one non-abstaining action.
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
                return selected, ((False, first_action), (True, second_action), (None, 'abstain'))
    raise ArithmeticError('no feasible inspection map within the global tie tolerance')


def plan_inspection(assumptions, losses, query_cost, epsilon=1e-12):
    """Plan once: three stop risks, an early cost screen, then at most six terms.

    Query risk/map remain None when the cost screen exits. Scope, call caps,
    cancellation, result verification and budget reservations belong to the caller.
    """
    if not isinstance(assumptions, ModelAssumptions) or not isinstance(losses, Losses):
        raise ValueError('validated assumptions and explicit losses required')
    _nonnegative(query_cost, 'inspection cost')
    _nonnegative(epsilon, 'minimum improvement')
    stop_costs = (losses.abstain, assumptions.prior*losses.false_reject,
                  (1-assumptions.prior)*losses.false_accept)
    minimum = min(stop_costs)
    stop_index = next(index for index in range(3) if _feasible(stop_costs[index], minimum))
    stop_action, stop_risk = ACTIONS[stop_index], stop_costs[stop_index]
    if query_cost >= stop_risk-epsilon:
        return InspectionPlan(assumptions, losses, query_cost, epsilon, stop_action, stop_risk,
            None, None, False, 'cost_screen_skip', 3)
    query_risk, delta = _shared_map(_branch_costs(assumptions, losses), query_cost)
    purchase = stop_risk-query_risk > epsilon
    return InspectionPlan(assumptions, losses, query_cost, epsilon, stop_action, stop_risk,
        query_risk, delta, purchase, 'positive_loss_reduction' if purchase else 'no_gain_above_margin', 9)


def apply_plan(plan, outcome=None):
    """Apply the precommitted plan; an unknown observation never starts replanning."""
    if not isinstance(plan, InspectionPlan):
        raise ValueError('validated inspection plan required')
    if outcome is not None and type(outcome) is not bool:
        raise ValueError('inspection outcome must be boolean or None for unknown')
    if not plan.purchase:
        return plan.stop_action
    if outcome is None:
        return 'abstain'
    return dict(plan.query_delta)[outcome]
