"""Finite R3 v2 tool/action pilot with predeclared artifact-withheld probes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from pheroos.kernel import RuntimeScope
from . import r3_tool_tasks as tasks
from .r3_pilot import ARMS, Worker, append, canonical, digest, save

METHOD = "r3_tool_loop_pilot_v2"
PROBE_STEPS = (2, 4)


class ToolWorker(Worker):
    """Never issue another RPC after a transport response loses its framing."""
    transport_failed = False

    def request(self, payload):
        if self.transport_failed:
            raise RuntimeError('backend transport quarantined')
        try:
            return super().request(payload)
        except (TimeoutError, OSError, json.JSONDecodeError):
            self.transport_failed = True
            if self.process.poll() is None:
                self.process.kill()
            raise
        except RuntimeError as exc:
            if str(exc).startswith('local backend exited'):
                self.transport_failed = True
            raise

    def close(self):
        try:
            super().close()
        except (BrokenPipeError, ValueError):
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=10)
            self.stderr.close()


def configuration():
    return dict(method_version=METHOD, arms=list(ARMS), worlds=tasks.world_ids(),
                steps=6, max_new_tokens=256, episode_token_cap=12288,
                probe_steps=list(PROBE_STEPS), probe_token_cap=4096, seed=71)


def withheld(memory, agent, version):
    eligible = [r for r in memory if r['valid'] and r['agent'] != agent
                and r['task_version'] == version]
    removed = {r['id'] for r in eligible}
    return [r for r in memory if r['id'] not in removed], sorted(removed)


def perform(worker, request, world, step, memory):
    # Keep received usage even when verification or publication subsequently fails.
    response, result, publication, publication_request = None, None, None, None
    started = time.monotonic_ns()
    try:
        response = worker.request(request)
        result = tasks.apply(world, step, memory, response['text'])
        if result['valid']:
            publication_request = dict(op='publish', scope=request['scope'],
                task_id=world, version=request['version'], artifact=result['artifact'],
                verification={k: result[k] for k in ('valid', 'feedback', 'artifact')})
            publication = worker.request(publication_request)
        return dict(status='received', response=response, result=result, publication=publication,
                    publication_request=publication_request, elapsed_ns=time.monotonic_ns()-started)
    except Exception as exc:
        return dict(status='INVALID_ABORT', response=response, result=result, publication=publication,
                    publication_request=publication_request,
                    elapsed_ns=time.monotonic_ns()-started, error=f'{type(exc).__name__}: {exc}')


def prepared_run(worker, request, world, step, memory, *, trim):
    """Fit whole receipts with the actual tokenizer; keep every preflight cost."""
    memory = list(memory)
    context, dropped = [], []
    started = time.monotonic_ns()
    try:
        while True:
            messages = tasks.messages_for(world, step, memory)
            preflight = dict(op='tokenize', messages=messages)
            item = dict(request=preflight, response=None)
            context.append(item)
            item['response'] = worker.request(preflight)
            count = item['response'].get('prompt_tokens')
            if type(count) is not int or count < 1:
                raise ValueError('invalid preflight token count')
            if count + request['max_new_tokens'] <= 2048:
                break
            if not trim or not memory:
                raise ValueError('public task or fixed probe exceeds context bound')
            dropped.append(memory.pop(0)['id'])
        request['messages'] = messages
        run = perform(worker, request, world, step, memory)
        if run['response'] is not None and run['response']['prompt_tokens'] != count:
            run['status'] = 'INVALID_ABORT'
            run['error'] = 'generation prompt usage differs from actual preflight'
    except Exception as exc:
        run = dict(status='INVALID_ABORT', response=None, result=None, publication=None,
                   publication_request=None, error=f'{type(exc).__name__}: {exc}')
    run['elapsed_ns'] = time.monotonic_ns()-started
    run['context_preflight'] = context
    run['context_dropped_ids'] = dropped
    return memory, run


def final_ledger(worker, request):
    if getattr(worker, 'transport_failed', False):
        return None
    try:
        ledger = worker.request({k: request[k] for k in ('ledger_path', 'token_cap', 'max_calls')} | {'op':'ledger'})
        expected = {k: request[k] for k in ('token_cap', 'max_calls')}
        if ledger.get('config') != expected or not isinstance(ledger.get('calls'), list):
            return None
        if any(type(ledger.get(k)) is not int or ledger[k] < 0 for k in
               ('actual_tokens','reserved_tokens','unknown_tokens','call_count')):
            return None
        if ledger['call_count'] != len(ledger['calls']):
            return None
        return ledger
    except Exception:
        return None


def episode(worker, config, world, arm, ordinal, output):
    identity = f'{ordinal:03d}-{arm}'
    records, trace, probes, curve = [], [], [], []
    main_request, probe_request = None, None
    error = None
    started = time.monotonic_ns()
    for step in range(config['steps']):
        version = tasks.version(world, step)
        agent = tasks.agent_for(arm, step)
        memory = tasks.memory_for(arm, records, step, version)
        main_request = dict(op='generate', messages=tasks.messages_for(world, step, memory),
            scope=RuntimeScope('r3-tool-pilot-v2', identity, 'episode').to_dict(),
            task_id=world, version=version, call_id=f'{identity}:{step}',
            ledger_path=str(output/f'{identity}.sqlite'), token_cap=config['episode_token_cap'],
            max_calls=config['steps'], max_new_tokens=config['max_new_tokens'],
            seed=config['seed'] + tasks.world_ids().index(world)*100 + step)
        memory, run = prepared_run(worker, main_request, world, step, memory, trim=True)
        row = dict(episode_id=identity, world_id=world, arm=arm, step=step, agent=agent,
                   task_version=version, consumed_ids=[r['id'] for r in memory],
                   request=main_request, **run)
        if run['status'] == 'received':
            result = run['result']
            record = dict(id=f'{identity}:artifact:{step}', agent=agent, step=step,
                task_version=version, **{k:result[k] for k in
                ('valid','feedback','artifact','action','semantic_action')},
                receipt_digest=digest(result['artifact']))
            row['record'] = record
            records.append(record)
        append(output/'trace.jsonl', row)
        trace.append(row)
        if run['status'] != 'received':
            error = run['error']
            break
        # Hidden final checks are recorded for prefix curves, never used as feedback.
        curve.append(dict(calls=step+1, task_version=version,
            success=tasks.score(world, step, records),
            tokens=sum(t['response']['prompt_tokens']+t['response']['completion_tokens'] for t in trace),
            elapsed_ns=sum(t['elapsed_ns'] for t in trace)))
        if step in config['probe_steps']:
            fork_memory, removed = withheld(memory, agent, version)
            probe_request = main_request | dict(
                messages=tasks.messages_for(world, step, fork_memory),
                scope=RuntimeScope('r3-tool-pilot-v2', identity+'-probe', 'episode').to_dict(),
                call_id=f'{identity}:probe:{step}', ledger_path=str(output/f'{identity}-probe.sqlite'),
                token_cap=config['probe_token_cap'], max_calls=len(config['probe_steps']))
            _, probe = prepared_run(worker, probe_request, world, step, fork_memory, trim=False)
            comparable = probe['status']=='received'
            pair = dict(episode_id=identity, world_id=world, arm=arm, step=step,
                removed_ids=removed, eligible=bool(removed), request=probe_request,
                actual_semantic_action=result['semantic_action'],
                semantic_action_changed=(result['semantic_action'] != probe['result']['semantic_action']) if comparable else None,
                actual_valid=result['valid'], **probe)
            append(output/'probes.jsonl', pair)
            probes.append(pair)
            if not comparable:
                error = probe['error']
                break
    main_ledger = final_ledger(worker, main_request) if main_request else None
    probe_ledger = final_ledger(worker, probe_request) if probe_request else None
    for ledger, required in ((main_ledger, True), (probe_ledger, bool(probe_request))):
        if required and (ledger is None or ledger['unknown_tokens'] or ledger['reserved_tokens']):
            error = error or 'unresolved or unavailable final ledger'
    complete = len(trace)==config['steps'] and len(probes)==len(config['probe_steps'])
    if not complete:
        error = error or 'incomplete declared episode/probe grid'
    def usage(rows):
        return dict(input_tokens=sum(r['response']['prompt_tokens'] for r in rows if r['response']),
                    output_tokens=sum(r['response']['completion_tokens'] for r in rows if r['response']))
    return dict(method_version=METHOD, phase='engineering_pilot', counts_toward_verdict=False,
        episode_id=identity, world_id=world, arm=arm, error=error,
        outcome='INVALID_ABORT' if error else ('success' if tasks.score(world,config['steps']-1,records) else 'failed'),
        main_calls=len(trace), probe_calls=len(probes), main_usage=usage(trace), probe_usage=usage(probes),
        main_ledger=main_ledger, probe_ledger=probe_ledger, curve=curve,
        accounting_status='KNOWN' if not error else 'CHECK_ABORT',
        eligible_probes=sum(p['eligible'] for p in probes),
        valid_action_changes=sum(p['eligible'] and p['semantic_action_changed'] is True and
                                 p['actual_valid'] and p['result']['valid'] for p in probes if p['result']),
        elapsed_ns=time.monotonic_ns()-started,
        peak_cuda_bytes=max((r['response']['peak_cuda_bytes'] for r in trace+probes if r['response']), default=0),
        transport_bytes=sum(sum(len(canonical(r[k]).encode()) for k in
            ('request','response','publication_request','publication') if r[k] is not None) +
            sum(len(canonical(p[k]).encode()) for p in r['context_preflight']
                for k in ('request','response') if p[k] is not None) for r in trace+probes),
        tool_receipt_bytes=sum(len(canonical(r['result']).encode()) for r in trace+probes if r['result'] is not None))


def summarize(rows):
    expected={(w,a) for w in tasks.world_ids() for a in ARMS}
    if len(rows)!=len(expected) or {(r['world_id'],r['arm']) for r in rows}!=expected:
        raise ValueError('missing or duplicated paired episodes')
    arms={}
    for arm in ARMS:
        group=[r for r in rows if r['arm']==arm]
        arms[arm]=dict(episodes=len(group), successes=sum(r['outcome']=='success' for r in group),
            invalid=sum(r['outcome']=='INVALID_ABORT' for r in group),
            main_tokens=sum(sum(r['main_usage'].values()) for r in group),
            probe_tokens=sum(sum(r['probe_usage'].values()) for r in group),
            eligible_probes=sum(r['eligible_probes'] for r in group),
            valid_action_changes=sum(r['valid_action_changes'] for r in group),
            curve=[dict(calls=k, observed=sum(len(r['curve'])>=k for r in group),
                successes=sum(r['curve'][k-1]['success'] for r in group if len(r['curve'])>=k),
                tokens=sum(r['curve'][k-1]['tokens'] for r in group if len(r['curve'])>=k),
                elapsed_ns=sum(r['curve'][k-1]['elapsed_ns'] for r in group if len(r['curve'])>=k))
                for k in range(1,7)])
    return dict(method_version=METHOD, counts_toward_verdict=False,
        status='INVALID_ABORT' if any(a['invalid'] for a in arms.values()) else 'PILOT_COMPLETE', arms=arms,
        limitations=['four previously observed worlds; engineering pilot, not held-out efficacy',
            'sequential GPU inference; no hardware or agent-count scaling',
            'prefix quality uses current source version; evidence changes at call 4',
            'paired probe changes access to current verified other-agent receipts; no downstream branch rollout',
            'no-eligible probes are retained controls; action difference is not necessarily improvement',
            'logical JSON bytes exclude physical device/storage IO',
            'runtime development authority and trusted-host verification remain unchanged'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','output','runtime-python','runtime-source','model-path'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    if config!=configuration():
        raise ValueError('unsupported pilot configuration')
    args.output.mkdir(parents=True,exist_ok=False)
    output=args.output.resolve()
    bench=Path(__file__).resolve().parents[2]
    from . import r3_pilot, r3_tasks
    paths=[Path(__file__),Path(tasks.__file__),Path(r3_pilot.__file__),Path(r3_tasks.__file__),
        args.config,bench/'R3-tool-loop-v2-contract.md',
        *sorted((bench/'tests').glob('test_r3_tool*.py')),
        *sorted((args.runtime_source/'src/pheroos_runtime').glob('*.py'))]
    freeze={str(p.resolve()):sha256(p.read_bytes()).hexdigest() for p in paths}
    save(output/'freeze.json',dict(config=config,source_sha256=freeze,
        model=json.loads((args.model_path/'manifest.json').read_text()),frozen_before_calls=True))
    worker=None
    rows=[]
    try:
        worker=ToolWorker(args.runtime_python,args.model_path,output)
        save(output/'environment.json',worker.identity)
        for i,world in enumerate(tasks.world_ids()):
            for arm in ARMS[i:]+ARMS[:i]:
                row=episode(worker,config,world,arm,len(rows),output)
                rows.append(row)
                append(output/'episodes.jsonl',row)
                print(world,arm,row['outcome'],row['main_usage'],row['probe_usage'],flush=True)
                if row['outcome']=='INVALID_ABORT':
                    raise RuntimeError(row['error'])
        save(output/'summary.json',summarize(rows))
        if any(sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in freeze.items()):
            raise RuntimeError('frozen source changed during experiment')
    except Exception as error:
        save(output/'abort.json',dict(status='INVALID_ABORT',error=str(error),completed_episodes=len(rows)))
        raise
    finally:
        if worker:
            worker.close()


if __name__=='__main__':
    main()
