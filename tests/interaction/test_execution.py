"""Required durable boundaries for local tool execution."""
from dataclasses import replace
from hashlib import sha256
import sqlite3

import pytest

from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.session import _wire
from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError


BODY = dict(source_id='x', source_version=1, value=7)
ARGS = {'source_id': 'x'}
FINGERPRINT = sha256(_wire(BODY).encode()).hexdigest()


def make_session(tmp_path, name='one', *, readers=None, token_cap=0, max_calls=8, clock=None):
    readers = ['a', 'b'] if readers is None else readers
    work = [dict(id='tool-'+agent, version=1, dependencies=[], agents=[agent],
                 actions=['tool.evaluate']) for agent in ['a', 'b']]
    source = dict(id='x', version=1, readers=readers, state_fingerprint=FINGERPRINT)
    inspections = [dict(work_id='tool-'+agent, source_id='x', source_version=1,
        tool_ref='inspect', tool_version='v1', arguments=ARGS,
        state_fingerprint=FINGERPRINT, readers=readers) for agent in ['a', 'b']]
    return CoordinationSession.create(tmp_path/(name+'.sqlite'), name, agents=['a', 'b'],
        sources=[source], work=work, inspections=inspections, token_cap=token_cap,
        max_calls=max_calls, clock=clock)


def driver(session, calls):
    return SessionDriver(session, tools={'inspect': lambda args: calls.append(args) or dict(BODY)})


def test_declared_tool_and_arguments_gate_dispatch_and_publication_binds_receipt(tmp_path):
    session, calls = make_session(tmp_path), []
    dispatch = driver(session, calls)
    lease = session.claim('a', 'tool-a')
    with pytest.raises(KeyError):
        dispatch.evaluate(lease, 'bad-tool', 'shell', {})
    with pytest.raises(StateError):
        dispatch.evaluate(lease, 'bad-target', 'inspect', {'source_id': 'foreign'})
    assert calls == []
    reply = dispatch.evaluate(lease, 'good', 'inspect', ARGS)
    with pytest.raises(StateError):
        session.publish(lease, 'good', BODY | {'value': 999}, verify=lambda _, value: True)
    with pytest.raises(StateError):
        session.publish(lease, 'good', reply['artifact'], verify=lambda _, value: False)
    session.publish(lease, 'good', reply['artifact'], verify=lambda _, value: value == BODY)
    assert len(session.snapshot()['artifacts']) == 1
    assert dispatch.replay('good') == reply and calls == [ARGS]


@pytest.mark.parametrize('cap', [1, 2])
def test_configured_call_cap_is_not_hardcoded_to_one(tmp_path, cap):
    session, calls = make_session(tmp_path, max_calls=cap), []
    dispatch = driver(session, calls)
    one, two = session.claim('a', 'tool-a'), session.claim('b', 'tool-b')
    dispatch.evaluate(one, 'first', 'inspect', ARGS)
    with pytest.raises(StateError):
        dispatch.evaluate(one, 'first', 'inspect', ARGS)
    if cap == 1:
        with pytest.raises(BudgetExceeded):
            dispatch.evaluate(two, 'second', 'inspect', ARGS)
    else:
        dispatch.evaluate(two, 'second', 'inspect', ARGS)
    assert len(calls) == session.snapshot()['call_count'] == cap


def test_source_reader_and_cross_session_lease_checks_happen_before_tool(tmp_path):
    one, calls = make_session(tmp_path, readers=['a']), []
    a, b = one.claim('a', 'tool-a'), one.claim('b', 'tool-b')
    with pytest.raises(PermissionError):
        driver(one, calls).evaluate(b, 'denied', 'inspect', ARGS)
    two = make_session(tmp_path, 'two')
    two.claim('a', 'tool-a')
    with pytest.raises(LeaseLost):
        driver(two, calls).evaluate(a, 'foreign', 'inspect', ARGS)
    with pytest.raises(LeaseLost):
        driver(one, calls).evaluate(replace(a, version=2), 'stale', 'inspect', ARGS)
    assert calls == [] and one.snapshot()['call_count'] == two.snapshot()['call_count'] == 0


def test_cancellation_abandons_reserved_call_before_dispatch(tmp_path):
    session, calls = make_session(tmp_path), []
    lease = session.claim('a', 'tool-a')
    payload = {'task_id': lease.task_id, 'version': lease.version, 'tool_ref': 'inspect', 'arguments': ARGS}
    session.reserve(lease, 'reserved', 'tool.evaluate', payload, prompt_tokens=0, max_new_tokens=0)
    # A second connection sees the durable reservation before any tool side effect.
    with sqlite3.connect(session.path) as db:
        assert db.execute('SELECT state FROM calls').fetchone()[0] == 'reserved'
    session.cancel()
    with pytest.raises(LeaseLost):
        session.dispatch(lease, 'reserved')
    with pytest.raises(LeaseLost):
        driver(session, calls).evaluate(lease, 'another', 'inspect', ARGS)
    snapshot = session.snapshot()
    assert calls == [] and snapshot['calls'][0]['state'] == 'abandoned'
    assert snapshot['unknown_calls'] == 0 and session.claim('b', 'tool-b') is None


def test_unknown_dispatch_survives_reopen_expiry_and_cannot_be_retried(tmp_path):
    now, calls = [100.], []
    session = make_session(tmp_path, clock=lambda: now[0])
    lease = session.claim('a', 'tool-a', lease_seconds=1)

    def fail(arguments):
        calls.append(arguments)
        with sqlite3.connect(session.path) as db:
            assert db.execute('SELECT state FROM calls').fetchone()[0] == 'dispatched'
        raise TimeoutError('unknown local outcome')

    dispatch = SessionDriver(session, tools={'inspect': fail})
    with pytest.raises(TimeoutError):
        dispatch.evaluate(lease, 'unknown', 'inspect', ARGS)
    with pytest.raises(StateError):
        dispatch.evaluate(lease, 'unknown', 'inspect', ARGS)
    with pytest.raises(ValueError):
        dispatch.replay('unknown')
    now[0] = 102.
    reopened = CoordinationSession(session.path, clock=lambda: now[0])
    reopened.recover()
    assert reopened.claim('a', 'tool-a') is None
    assert reopened.snapshot()['unknown_calls'] == 1
    assert reopened.snapshot()['work'][0]['status'] == 'uncertain'
    reopened.cancel()
    assert reopened.snapshot()['unknown_calls'] == 1 and calls == [ARGS]


def test_current_source_update_fences_old_work_and_releases_unused_reservation(tmp_path):
    session, calls = make_session(tmp_path), []
    lease = session.claim('a', 'tool-a')
    session.reserve(lease, 'reserved', 'tool.evaluate',
        {'tool_ref': 'inspect', 'arguments': ARGS}, prompt_tokens=0, max_new_tokens=0)
    session.source_update('x', 2, ['a', 'b'], 'new-version-fingerprint')
    with pytest.raises(LeaseLost):
        driver(session, calls).evaluate(lease, 'stale', 'inspect', ARGS)
    assert session.snapshot()['calls'][0]['state'] == 'abandoned'
    assert session.claim('a', 'tool-a') is None and calls == []
    with pytest.raises(StateError):
        session.source_update('x', 1, ['a', 'b'], FINGERPRINT)
    with pytest.raises(StateError):
        session.source_update('x', 2, ['a', 'b'], 'unversioned-change')


@pytest.mark.parametrize('boundary', ['reader_revoked', 'cancelled'])
def test_revocation_or_cancellation_after_receipt_blocks_publication(tmp_path, boundary):
    session, calls = make_session(tmp_path), []
    lease = session.claim('a', 'tool-a')
    dispatch = driver(session, calls)
    reply = dispatch.evaluate(lease, 'read', 'inspect', ARGS)
    if boundary == 'reader_revoked':
        session.source_update('x', 1, ['b'], FINGERPRINT)
    else:
        session.cancel()
    with pytest.raises((PermissionError, LeaseLost)):
        session.publish(lease, 'read', reply['artifact'], verify=lambda _, value: True)
    assert session.snapshot()['artifacts'] == []
    assert dispatch.replay('read') == reply and calls == [ARGS]


def test_request_and_receipt_byte_bounds_are_enforced(tmp_path):
    session, calls = make_session(tmp_path), []
    lease = session.claim('a', 'tool-a')
    with pytest.raises(StateError):
        driver(session, calls).evaluate(lease, 'huge-request', 'inspect', {'payload': 'x'*5000})
    assert session.snapshot()['call_count'] == 0 and calls == []
    dispatch = SessionDriver(session, tools={'inspect': lambda args: {'payload': 'x'*9000}})
    with pytest.raises(StateError, match='response rejected'):
        dispatch.evaluate(lease, 'huge-receipt', 'inspect', ARGS)
    snapshot = session.snapshot()
    assert snapshot['calls'][0]['state'] == 'response_rejected'
    assert snapshot['calls'][0]['actual'] == 0 and snapshot['unknown_calls'] == 0
    with pytest.raises(ValueError):
        dispatch.replay('huge-receipt')


def test_explicit_token_cap_rejects_reservation_before_dispatch(tmp_path):
    session = make_session(tmp_path, token_cap=3)
    lease = session.claim('a', 'tool-a')
    with pytest.raises(BudgetExceeded):
        session.reserve(lease, 'over-cap', 'tool.evaluate',
            {'tool_ref': 'inspect', 'arguments': ARGS}, prompt_tokens=2, max_new_tokens=2)
    assert session.snapshot()['call_count'] == 0
