"""Local inspection execution and frozen-record replay."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='pheroos-interaction')
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect', help='one optional local binary-source check')
    inspect.add_argument('--config', required=True, type=Path)
    inspect.add_argument('--source', required=True, type=Path)
    inspect.add_argument('--output', required=True, type=Path)
    replay = sub.add_parser('inspect-replay', help='verify frozen plan and receipt without a source read')
    replay.add_argument('--run', required=True, type=Path)
    replay.add_argument('--historical', action='store_true',
                        help='verify an existing local inspection despite a changed source inventory')
    orchestrate = sub.add_parser('orchestrate', help='run a bounded agent workflow into a new output directory')
    orchestrate.add_argument('--workflow', required=True, type=Path)
    orchestrate.add_argument('--output', required=True, type=Path)
    orchestrate.add_argument('--script', type=Path, help='deterministic model script for the fake provider')
    orchestrate.add_argument('--max-sweeps', type=int, default=None)
    resume = sub.add_parser('orchestrate-resume', help='continue the unfinished work of a recorded run')
    resume.add_argument('--run', required=True, type=Path)
    resume.add_argument('--script', type=Path)
    resume.add_argument('--max-sweeps', type=int, default=None)
    audit = sub.add_parser('orchestrate-replay',
                           help='verify a recorded run offline, without a model, tool or transport')
    audit.add_argument('--run', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command in ('inspect', 'inspect-replay'):
        from .inspection import run_inspection, replay_inspection
        report = (run_inspection(args.config, args.source, args.output)
                  if args.command == 'inspect' else replay_inspection(args.run, require_source_match=not args.historical))
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 2 if report.get('status') in ('UNKNOWN', 'STOPPED', 'CANCELLED') else 0
    if args.command == 'orchestrate-replay':
        from .audit import replay_run
        report = replay_run(args.run / 'session.sqlite')
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 0 if report['status'] == 'PASS' else (1 if report['status'] == 'FAIL' else 2)
    from .runtime import resume_run, start_run
    report = (start_run(args.workflow, args.output, script_path=args.script, max_sweeps=args.max_sweeps)
              if args.command == 'orchestrate'
              else resume_run(args.run, script_path=args.script, max_sweeps=args.max_sweeps))
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report['status'] == 'success' else 2


if __name__ == '__main__':
    raise SystemExit(main())
