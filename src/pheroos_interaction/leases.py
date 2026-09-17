"""Evaporation of authority: one lease TTL from a declared stage-duration sample.

One exact argmin over a finite candidate set. This module reads no ledger, holds
no clock and issues, renews or expires no lease; the caller passes the chosen
TTL to claim/renew. The failure rate and both costs are declared inputs, not
estimates: nothing here calibrates them or verifies that the sample describes
the holders that will actually run.
"""
from bisect import bisect_right

from .inspection import _nonnegative, _number


def lease_ttl(stage_durations, p_fail, per_tick_cost, false_expiry_cost, candidates=()):
    """argmin over the empirical support of (1-F(T))*false_expiry_cost + T*p_fail*per_tick_cost.

    Two execution semantics share this objective. The caller supplies the inputs
    that match the semantics in force; the function does not relabel them:
      * today's PheroOS ('uncertain', never retried): stage_durations are
        claim->dispatch lead times. Only a pre-dispatch expiry re-queues work; a
        post-dispatch expiry marks the work uncertain and a late receipt is
        published by publish_received without a new call. false_expiry_cost is
        the re-claim/re-verify overhead and per_tick_cost the value of detecting
        a dead holder one tick earlier. The TTL bounds nothing else: not stall
        time, not the duration of an unknown dispatch, not retry behaviour.
      * a future idempotent re-dispatch semantics: stage_durations are full call
        durations, false_expiry_cost one duplicate query, per_tick_cost the
        latency loss of the stall. No runner implements this today.
    The search is exact over the POSITIVE part of the union of the empirical
    support and `candidates` (pass the incumbent, e.g. 60, so its loss is
    reported under 'candidate_losses'); ties keep the smallest T. A zero TTL is
    not feasible because claim/renew reject it, so 0 is excluded from 'searched'
    and a sample with no positive duration or candidate raises. A zero candidate
    still gets an entry in 'candidate_losses', but that entry is the plain
    objective value: at T=0 the survival term counts only holders whose lead time
    exceeds 0, so it understates the fact that a lease expiring at claim time is
    a false expiry for every holder. It is reported, never searched. p_fail is a declared
    per-tick holder failure rate on [0,1], not a fitted one. A single-sample
    argmin is neither a calibrated failure model nor a guarantee of dominance
    on other samples or under other semantics.
    """
    ordered = list(stage_durations)
    for duration in ordered:
        _nonnegative(duration, 'stage duration')
    if not ordered:
        raise ValueError('need at least one stage duration')
    extra = list(candidates)
    for candidate in extra:
        _nonnegative(candidate, 'candidate ttl')
    if not 0 <= _number(p_fail, 'p_fail') <= 1:
        raise ValueError('p_fail must be in [0,1]')
    _nonnegative(per_tick_cost, 'per-tick cost')
    _nonnegative(false_expiry_cost, 'false-expiry cost')
    ordered.sort()
    n = len(ordered)

    def loss(T):  # survival * false_expiry_cost + T * p_fail * per_tick_cost, in this order
        return (n-bisect_right(ordered, T)) / n * false_expiry_cost + T * p_fail * per_tick_cost

    searched = sorted(T for T in set(ordered) | set(extra) if T > 0)
    if not searched:
        raise ValueError('no positive TTL to search: claim/renew require a positive duration')
    best = None
    for T in searched:
        cost = loss(T)
        if best is None or cost < best[0]:
            best = (cost, T)
    return {'ttl': best[1], 'expected_loss': best[0], 'searched': searched,
            'candidate_losses': {candidate: loss(candidate) for candidate in extra}}
