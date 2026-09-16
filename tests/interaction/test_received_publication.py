"""Publish committed receipts without repeating their tool or weakening fences."""
from hashlib import sha256
import json

import pytest

from pheroos_interaction.records import LeaseLost, StateError
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.session import _wire


BODY = {'source_id': 'x', 'source_version': 1, 'value': True,
        'nested': {'checks': ['original']}}
ARGS = {'source_id': 'x'}
FINGERPRINT = sha256(_wire(BODY).encode()).hexdigest()


def make_session(tmp_path, *, clock=None, max_calls=4, token_cap=0,
                 inspection_readers=None):
    readers = ['a', 'b', 'observer']
    return CoordinationSession.create(
        tmp_path / 'session.sqlite', 'received-publication', agents=readers,
        work=[{'id': 'work', 'version': 1, 'dependencies': [],
               'agents': ['a', 'b'], 'actions': ['tool.evaluate']}],
        sources=[{'id': 'x', 'version': 1, 'readers': readers,
                  'state_fingerprint': FINGERPRINT}],
        inspections=[{'work_id': 'work', 'source_id': 'x', 'source_version': 1,
                      'tool_ref': 'inspect', 'tool_version': 'v1', 'arguments': ARGS,
                      'state_fingerprint': FINGERPRINT,
                      'readers': readers if inspection_readers is None else inspection_readers}],
        token_cap=token_cap, max_calls=max_calls, clock=clock)


def settle(session, lease, calls, call_id='received'):
    driver = SessionDriver(session, tools={
        'inspect': lambda args: calls.append(args) or BODY,
    })
    return driver.evaluate(lease, call_id, 'inspect', ARGS)


def reserve(session, lease, call_id, *, tokens=0):
    session.reserve(lease, call_id, 'tool.evaluate',
                    {'tool_ref': 'inspect', 'arguments': ARGS},
                    prompt_tokens=0, max_new_tokens=tokens)


def verify(work, value):
    return work == 'work' and value == BODY


@pytest.mark.parametrize('recover_first,publisher', [(False, 'b'), (True, 'a')])
def test_expired_received_call_is_reclaimed_and_published_without_execution(
        tmp_path, recover_first, publisher):
    now, calls = [100.], []
    session = make_session(tmp_path, clock=lambda: now[0], max_calls=1)
    lease = session.claim('a', 'work', lease_seconds=1)
    response = settle(session, lease, calls)
    now[0] = 102.
    reopened = CoordinationSession(session.path, clock=lambda: now[0])
    if recover_first:
        reopened.recover()
    ref = reopened.publish_received(publisher, 'received', verify=verify)
    snapshot = reopened.snapshot()
    assert calls == [ARGS]
    assert snapshot['run']['status'] == 'completed'
    assert snapshot['work'][0]['epoch'] == 2
    assert snapshot['call_count'] == 1
    assert snapshot['calls'][0]['epoch'] == 1
    assert snapshot['calls'][0]['state'] == 'received'
    assert json.loads(snapshot['calls'][0]['response']) == response
    assert snapshot['actual_tokens'] == snapshot['reserved_tokens'] == snapshot['unknown_tokens'] == 0
    assert snapshot['artifacts'][0]['ref'] == ref
    assert snapshot['artifacts'][0]['publisher'] == publisher
    assert snapshot['artifacts'][0]['call_id'] == 'received'


def test_live_owner_is_reused_without_another_claim(tmp_path):
    calls = []
    session = make_session(tmp_path)
    lease = session.claim('a', 'work')
    settle(session, lease, calls)
    before = session.snapshot()
    session.publish_received('a', 'received', verify=verify)
    after = session.snapshot()
    assert after['work'][0]['epoch'] == lease.epoch
    assert after['calls'] == before['calls']
    assert [event['event_type'] for event in after['events'][len(before['events']):]] == [
        'interaction.session.published']
    assert calls == [ARGS]


def test_reclaim_publication_preserves_settled_nonzero_usage_at_call_cap(tmp_path):
    now = [100.]
    session = make_session(tmp_path, clock=lambda: now[0], max_calls=1, token_cap=10)
    lease = session.claim('a', 'work', lease_seconds=1)
    session.reserve(lease, 'received', 'tool.evaluate',
                    {'tool_ref': 'inspect', 'arguments': ARGS},
                    prompt_tokens=3, max_new_tokens=7)
    session.dispatch(lease, 'received')
    session.receive('received', {'artifact': BODY, 'prompt_tokens': 3, 'completion_tokens': 1})
    now[0] = 102.
    before = session.snapshot()
    assert before['call_count'] == 1 and before['actual_tokens'] == 4
    session.publish_received('b', 'received', verify=verify)
    after = session.snapshot()
    assert after['calls'] == before['calls']
    assert after['call_count'] == 1 and after['actual_tokens'] == 4
    assert after['reserved_tokens'] == after['unknown_tokens'] == 0
    assert after['work'][0]['epoch'] == 2
    assert len(after['artifacts']) == 1


def test_other_live_owner_is_not_displaced(tmp_path):
    session = make_session(tmp_path)
    lease = session.claim('a', 'work')
    settle(session, lease, [])
    before = session.snapshot()
    with pytest.raises(StateError):
        session.publish_received('b', 'received', verify=verify)
    assert session.snapshot() == before


@pytest.mark.parametrize('state', ['missing', 'reserved', 'dispatched', 'abandoned',
                                  'response_rejected', 'receipt_without_artifact'])
def test_non_publishable_call_is_not_settled_retried_or_claimed(tmp_path, state):
    now = [100.]
    session = make_session(tmp_path, clock=lambda: now[0])
    lease = session.claim('a', 'work', lease_seconds=1)
    if state != 'missing':
        reserve(session, lease, 'target')
    if state in ('dispatched', 'response_rejected', 'receipt_without_artifact'):
        session.dispatch(lease, 'target')
    if state == 'abandoned':
        now[0] = 102.
        session.recover()
    if state == 'response_rejected':
        with pytest.raises(StateError, match='response rejected'):
            session.receive('target', {'prompt_tokens': 0, 'completion_tokens': 0,
                                       'artifact': {'large': 'x' * 9000}})
    if state == 'receipt_without_artifact':
        session.receive('target', {'prompt_tokens': 0, 'completion_tokens': 0})
    before = session.snapshot()
    verified = []
    with pytest.raises(StateError):
        session.publish_received('a', 'target', verify=lambda *args: verified.append(args) or True)
    assert session.snapshot() == before
    assert verified == []


@pytest.mark.parametrize('lease_state', ['active', 'expired', 'recovered_uncertain'])
def test_another_unknown_call_on_the_work_blocks_received_publication(tmp_path, lease_state):
    now, calls = [100.], []
    session = make_session(tmp_path, clock=lambda: now[0])
    lease = session.claim('a', 'work', lease_seconds=1)
    response = settle(session, lease, calls)
    reserve(session, lease, 'unknown')
    session.dispatch(lease, 'unknown')
    if lease_state != 'active':
        now[0] = 102.
    if lease_state == 'recovered_uncertain':
        session.recover()
    before = session.snapshot()
    with pytest.raises(StateError):
        session.publish_received('a', 'received', verify=verify)
    assert session.snapshot() == before
    assert session.call('unknown')['state'] == 'dispatched'
    assert session.call('unknown')['actual'] is None
    assert calls == [ARGS]
    if lease_state == 'active':
        # The new helper's restriction must not silently change legacy publish.
        ref = session.publish(lease, 'received', response['artifact'], verify=verify)
        assert session.snapshot()['work'][0]['status'] == 'done'
        assert session.call('unknown')['state'] == 'dispatched'
        published = session.snapshot()

        def must_not_verify(*args):
            raise AssertionError('idempotent retrieval must not verify or touch unknown calls')

        assert session.publish_received('a', 'received', verify=must_not_verify) == ref
        assert session.snapshot() == published


@pytest.mark.parametrize('failure', ['false', 'exception'])
def test_verification_failure_rolls_back_recovery_claim_and_abandonment(tmp_path, failure):
    now = [100.]
    session = make_session(tmp_path, clock=lambda: now[0], token_cap=10)
    lease = session.claim('a', 'work', lease_seconds=1)
    settle(session, lease, [])
    reserve(session, lease, 'unused', tokens=10)
    now[0] = 102.
    before = session.snapshot()
    verified = []

    def fail(work, value):
        verified.append((work, value))
        if failure == 'exception':
            raise ValueError('local verification failed')
        return False

    with pytest.raises(ValueError if failure == 'exception' else StateError):
        session.publish_received('b', 'received', verify=fail)
    assert len(verified) == 1
    assert session.snapshot() == before
    assert session.call('unused')['state'] == 'reserved'
    assert session.snapshot()['reserved_tokens'] == 10


def test_verifier_mutation_cannot_change_the_settled_artifact(tmp_path):
    session = make_session(tmp_path)
    lease = session.claim('a', 'work')
    response = settle(session, lease, [])

    def modifying_verifier(work, value):
        assert work == 'work' and value == BODY
        value['value'] = False
        value['nested']['checks'].append('verifier mutation')
        return True

    session.publish_received('a', 'received', verify=modifying_verifier)
    snapshot = session.snapshot()
    assert json.loads(snapshot['artifacts'][0]['value']) == BODY
    assert json.loads(snapshot['calls'][0]['response']) == response


def test_verification_elapsed_time_is_fenced_before_publication_commit(tmp_path):
    now = [100.]
    session = make_session(tmp_path, clock=lambda: now[0], token_cap=10)
    lease = session.claim('a', 'work', lease_seconds=1)
    settle(session, lease, [])
    reserve(session, lease, 'unused', tokens=10)
    now[0] = 102.
    before = session.snapshot()
    verified = []

    def slow_verification(work, value):
        verified.append((work, value))
        now[0] = 104.  # The replacement lease expires at 103 during verification.
        return True

    with pytest.raises(LeaseLost):
        session.publish_received('b', 'received', verify=slow_verification, lease_seconds=1)
    assert len(verified) == 1
    assert session.snapshot() == before
    assert session.snapshot()['work'][0]['epoch'] == 1
    assert session.call('unused')['state'] == 'reserved'


def test_same_published_call_is_idempotent_after_completion(tmp_path):
    session = make_session(tmp_path, max_calls=1)
    lease = session.claim('a', 'work')
    settle(session, lease, [])
    ref = session.publish_received('a', 'received', verify=verify)
    before = session.snapshot()
    assert before['run']['status'] == 'completed'

    def must_not_verify(*args):
        raise AssertionError('already published receipt must not be verified again')

    reopened = CoordinationSession(session.path)
    assert reopened.publish_received('a', 'received', verify=must_not_verify) == ref
    assert reopened.snapshot() == before


@pytest.mark.parametrize('published', [False, True])
@pytest.mark.parametrize('boundary', ['cancelled', 'source_reader', 'source_version',
                                    'inspection_reader', 'role', 'undeclared'])
def test_current_authorization_is_checked_before_new_or_idempotent_publication(
        tmp_path, published, boundary):
    session = make_session(tmp_path, inspection_readers=['a'] if boundary == 'inspection_reader' else None)
    lease = session.claim('a', 'work')
    settle(session, lease, [])
    if published:
        session.publish_received('a', 'received', verify=verify)
    agent = 'a'
    if boundary == 'cancelled':
        session.cancel()
    elif boundary == 'source_reader':
        session.source_update('x', 1, ['b'], FINGERPRINT)
    elif boundary == 'source_version':
        session.source_update('x', 2, ['a', 'b'], 'new-state')
    elif boundary == 'inspection_reader':
        agent = 'b'
    elif boundary == 'role':
        agent = 'observer'
    else:
        agent = 'undeclared'
    before = session.snapshot()
    verified = []
    with pytest.raises((StateError, PermissionError)):
        session.publish_received(agent, 'received', verify=lambda *args: verified.append(args) or True)
    assert verified == []
    assert session.snapshot() == before


def test_another_received_call_cannot_reuse_an_existing_artifact(tmp_path):
    session = make_session(tmp_path, max_calls=2)
    lease = session.claim('a', 'work')
    settle(session, lease, [], 'one')
    settle(session, lease, [], 'two')
    session.publish_received('a', 'one', verify=verify)
    before = session.snapshot()
    with pytest.raises(StateError):
        session.publish_received('a', 'two', verify=verify)
    assert session.snapshot() == before


def test_cancellation_still_allows_receipt_settlement_but_not_publication(tmp_path):
    session = make_session(tmp_path, max_calls=1)
    lease = session.claim('a', 'work')
    reserve(session, lease, 'late')
    session.dispatch(lease, 'late')
    session.cancel()
    session.receive('late', {'artifact': BODY, 'prompt_tokens': 0, 'completion_tokens': 0})
    before = session.snapshot()
    assert session.call('late')['state'] == 'received'
    assert before['unknown_calls'] == 0
    with pytest.raises((StateError, PermissionError)):
        session.publish_received('a', 'late', verify=verify)
    assert session.snapshot() == before
