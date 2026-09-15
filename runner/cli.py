"""Explicit offline commands by default; one separately authorized live cell."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='pheroos-interaction')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('mock', 'api-dry-run', 'live'):
        command = sub.add_parser(name)
        command.add_argument('--output', required=True, type=Path)
        command.add_argument('--world', default='fresh_a/stale')
        command.add_argument('--condition', default='eligibility_current')
        if name == 'live':
            command.add_argument('--ledger', required=True, type=Path)
            command.add_argument('--authorization', required=True, type=Path,
                help='New explicit user authorization JSON for this exact 4-request cell and existing ledger')
    replay = sub.add_parser('replay')
    replay.add_argument('--run', required=True, type=Path)
    replay.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'replay':
        from pheroos_interaction.experiments.current.replay import run_replay
        report = run_replay(args.run, args.output)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    from .host import run_episode, save
    if args.command == 'live':
        # Neither historical budgets nor this cleanup supply this approval.
        # A trusted host controls this local declaration; it is not a certificate.
        approval = json.loads(args.authorization.read_text())
        expected = dict(purpose='new-paid-interaction-cell', model='kimi-k2.6', max_requests=4,
            world=args.world, condition=args.condition, data_scope='synthetic-public-only',
            ledger=str(args.ledger.expanduser().resolve()))
        if approval != expected or not args.ledger.expanduser().is_file():
            parser.error('separate exact-cell authorization and an existing shared ledger are required')
        from .accounting import MoneyLedger
        from .adapters import KimiCNAdapter
        ledger = MoneyLedger(args.ledger, budget_cny='50', max_http_requests=500)
        if ledger.summary()['unresolved_calls']:
            parser.error('unresolved historical liability stops new dispatch')
        result = run_episode(args.output, world_id=args.world, condition=args.condition, model=KimiCNAdapter(ledger))
    else:
        result = run_episode(args.output, world_id=args.world, condition=args.condition)
        if args.command == 'api-dry-run':
            from .adapters import KimiCNAdapter
            adapter = KimiCNAdapter()  # no money database, credentials or network
            requests = [dict(messages_sha256=row['context']['messages_sha256'],
                             payload=json.loads(adapter._payload(row['context']['messages'], 512)))
                        for row in result['calls'] if row['status'] == 'RECEIVED']
            dry = dict(mode='api_dry_run', requests=requests, provider_calls=0, credentials_read=False,
                       ledger_opened=False, basis='Mock paths only; not predictions of Kimi behavior')
            save(args.output / 'api-dry-run.json', dry)
    print(json.dumps({k: result[k] for k in ('mode', 'complete', 'world_id', 'condition',
                     'final_grounded', 'actual_tool_executions', 'inspection_intents', 'cache_hits', 'error_type')},
                     ensure_ascii=False))
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
