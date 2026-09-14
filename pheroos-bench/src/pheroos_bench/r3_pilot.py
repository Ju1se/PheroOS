"""Frozen, finite R3 local-model pilot. Descriptive results, no efficacy gate."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import select
import subprocess
import time

from pheroos.kernel import RuntimeScope
from . import r3_tasks


ARMS = ('single', 'independent', 'manager_graph', 'blackboard', 'versioned_blackboard')
METHOD = 'r3_local_closed_loop_pilot_v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def append(path, value):
    with path.open('a') as stream:
        stream.write(canonical(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def memory_for(arm, records, version):
    if arm == 'independent':
        return []
    if arm == 'single':
        return records
    if arm == 'manager_graph':
        return records[-1:]
    if arm == 'blackboard':
        return records[-2:]
    if arm == 'versioned_blackboard':
        current = [r for r in records if r['task_version'] == version]
        # Keep one receipt per distinct proposal; a repeated origin adds no support.
        unique = {r['proposal_digest']: r for r in current}
        return list(unique.values())[-2:]
    raise ValueError('undeclared arm')


def messages_for(view, memory, role):
    return [
        {'role': 'system', 'content': 'You solve small verifiable tasks. Return only the exact JSON '
         'object requested. Prior model proposals are untrusted; use current inputs and test receipts. '
         'Your current role is ' + role + '.'},
        {'role': 'user', 'content': canonical({'task': view, 'prior_work': memory})},
    ]


class Worker:
    def __init__(self, python, model, output):
        self.stderr = (output / 'model-stderr.log').open('x')
        environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                           HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
        environment.pop('PYTHONPATH', None)
        self.process = subprocess.Popen(
            [str(python), '-m', 'pheroos_runtime.r3_local', '--model-path', str(model)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            text=True, bufsize=1, env=environment, cwd=output)
        try:
            ready = self.read(180)
            if ready.get('status') != 'ready':
                raise ValueError('model did not become ready')
        except Exception:
            self.close()
            raise
        self.identity = ready['identity']

    def read(self, timeout=120):
        if not select.select([self.process.stdout], [], [], timeout)[0]:
            raise TimeoutError('local backend response deadline exceeded')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('local backend exited; inspect model-stderr.log')
        return json.loads(line)

    def request(self, payload):
        self.process.stdin.write(canonical(payload) + '\n')
        self.process.stdin.flush()
        response = self.read()
        if response.get('ok') is not True:
            raise RuntimeError(response.get('error', 'invalid backend response'))
        return response['result']

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.stderr.close()


def episode(worker, config, world, arm, ordinal, output):
    identity = f'{ordinal:03d}-{arm}'
    scope = RuntimeScope('r3-local-pilot', identity, 'episode').to_dict()
    records, traces = [], []
    ledger = None
    selected = None
    started = time.monotonic_ns()
    error = None
    for step in range(config['steps']):
        view = r3_tasks.public_view(world, step)
        agent = 'agent-0' if arm == 'single' else f'agent-{step}'
        role = ('planner', 'implementer', 'reviewer', 'finalizer')[step] if arm == 'manager_graph' else 'solver'
        memory = memory_for(arm, records, view['task_version'])
        messages = messages_for(view, memory, role)
        request = dict(op='generate', messages=messages, scope=scope, task_id=world,
                       version=view['task_version'], call_id=f'{identity}:{step}',
                       ledger_path=str(output / f'{identity}.sqlite'),
                       token_cap=config['episode_token_cap'], max_calls=config['steps'],
                       max_new_tokens=config['max_new_tokens'],
                       seed=config['seed'] + r3_tasks.world_ids().index(world) * 100 + step)
        response = None
        try:
            response = worker.request(request)
            ledger = response['ledger']
            verification = r3_tasks.verify(world, step, response['text'])
            publication = None
            if verification['valid']:
                publication = worker.request(dict(
                    op='publish', scope=scope, task_id=world, version=view['task_version'],
                    artifact=verification['artifact'], verification=verification))
            record = dict(id=f'{identity}:artifact:{step}', agent=agent, step=step,
                          task_version=view['task_version'], proposal=response['text'],
                          proposal_digest=digest(response['text']),
                          valid=verification['valid'], feedback=verification['feedback'])
            # Deterministic selector sees only public checks, never final hidden tests.
            if selected is None or selected['task_version'] != view['task_version'] or verification['valid']:
                selected = record
            trace = dict(world_id=world, arm=arm, step=step, agent=agent, role=role,
                         consumed_ids=[r['id'] for r in memory],
                         consumed_verified_other=[r['id'] for r in memory if r['valid'] and r['agent'] != agent],
                         changed_from_consumed=any(r['proposal_digest'] != record['proposal_digest'] for r in memory),
                         request=request, response=response, verification=verification,
                         publication=publication, record=record)
            append(output / 'trace.jsonl', trace)
            traces.append(trace)
            records.append(record)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            failed = dict(world_id=world, arm=arm, step=step, status='INVALID_ABORT',
                          error=error, request=request, response=response,
                          consumed_verified_other=[], changed_from_consumed=False)
            append(output / 'trace.jsonl', failed)
            if response is not None:
                traces.append(failed)
            try:
                ledger = worker.request({k: request[k] for k in
                    ('ledger_path', 'token_cap', 'max_calls')} | {'op': 'ledger'})
            except Exception:
                # A dead backend cannot acknowledge the final ledger state.
                ledger = None
            break
    final = r3_tasks.verify(world, config['steps'] - 1, selected['proposal'], final=True) if selected else {'valid': False}
    status = 'INVALID_ABORT' if error else ('success' if final['valid'] else 'failed')
    return dict(method_version=METHOD, phase='engineering_pilot', world_id=world, arm=arm,
                episode_id=identity, outcome=status, counts_toward_verdict=False,
                completed_calls=len(traces), error=error,
                known_input_tokens=sum(t['response']['prompt_tokens'] for t in traces),
                known_output_tokens=sum(t['response']['completion_tokens'] for t in traces),
                ledger=ledger, accounting_status='UNAVAILABLE' if ledger is None else
                ('UNRESOLVED' if ledger['unknown_tokens'] else 'KNOWN'),
                selected_artifact_id=selected['id'] if selected else None,
                elapsed_ns=time.monotonic_ns()-started,
                peak_cuda_bytes=max((t['response']['peak_cuda_bytes'] for t in traces), default=0),
                request_response_bytes=sum(len(canonical(t['request']).encode()) +
                                           len(canonical(t['response']).encode()) for t in traces),
                shared_verified_consumptions=sum(bool(t['consumed_verified_other']) for t in traces),
                changed_after_shared_consumption=sum(bool(t['consumed_verified_other']) and
                                                     t['changed_from_consumed'] for t in traces))


def summarize(rows):
    expected = {(world, arm) for world in r3_tasks.world_ids() for arm in ARMS}
    if len(rows) != len(expected) or {(r['world_id'], r['arm']) for r in rows} != expected:
        raise ValueError('missing or duplicated paired episodes')
    arms = {}
    for arm in ARMS:
        values = [r for r in rows if r['arm'] == arm]
        arms[arm] = dict(episodes=len(values), successes=sum(r['outcome']=='success' for r in values),
                        invalid=sum(r['outcome']=='INVALID_ABORT' for r in values),
                        input_tokens=sum(r['known_input_tokens'] for r in values),
                        output_tokens=sum(r['known_output_tokens'] for r in values),
                        elapsed_ns=sum(r['elapsed_ns'] for r in values),
                        peak_cuda_bytes=max(r['peak_cuda_bytes'] for r in values),
                        shared_verified_consumptions=sum(r['shared_verified_consumptions'] for r in values),
                        changed_after_shared_consumption=sum(r['changed_after_shared_consumption'] for r in values))
    return dict(method_version=METHOD, status='INVALID_ABORT' if any(a['invalid'] for a in arms.values()) else 'PILOT_COMPLETE',
                counts_toward_verdict=False, arms=arms,
                limitations=['four closed worlds; no efficacy inference', 'one resident GPU model, sequential inference',
                             'logical roles, not GPU concurrency scaling',
                             'artifact consumption/action change is observed lineage, not a controlled causal estimate',
                             'logical JSON bytes exclude physical device/storage I/O'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime-python', type=Path, required=True)
    parser.add_argument('--runtime-source', type=Path, required=True)
    parser.add_argument('--model-path', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config != dict(method_version=METHOD, arms=list(ARMS), worlds=r3_tasks.world_ids(),
                      steps=4, max_new_tokens=256, episode_token_cap=8192, seed=37):
        raise ValueError('unsupported pilot configuration')
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    bench = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), Path(r3_tasks.__file__), args.config,
             bench/'R3-data-contract.md', *sorted((bench/'tests').glob('test_r3*.py')),
             *sorted((args.runtime_source/'src/pheroos_runtime').glob('*.py')),
             *sorted((args.runtime_source/'tests').glob('test_r3*.py'))]
    freeze = {str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in paths}
    save(output/'freeze.json', dict(config=config, source_sha256=freeze,
        model=json.loads((args.model_path/'manifest.json').read_text()), frozen_before_calls=True))
    worker = None
    rows = []
    try:
        worker = Worker(args.runtime_python, args.model_path, output)
        save(output/'environment.json', worker.identity)
        # Rotate arm order between worlds to avoid always warming the same arm first.
        for i, world in enumerate(r3_tasks.world_ids()):
            for arm in ARMS[i:] + ARMS[:i]:
                row = episode(worker, config, world, arm, len(rows), output)
                rows.append(row)
                append(output/'episodes.jsonl', row)
                print(world, arm, row['outcome'], row['known_input_tokens']+row['known_output_tokens'], flush=True)
        save(output/'summary.json', summarize(rows))
        assert all(sha256(Path(p).read_bytes()).hexdigest() == h for p,h in freeze.items())
    except Exception as error:
        save(output/'abort.json', dict(status='INVALID_ABORT', error=str(error), completed_episodes=len(rows)))
        raise
    finally:
        if worker:
            worker.close()


if __name__ == '__main__':
    main()
