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
    args = parser.parse_args(argv)
    from .inspection import run_inspection, replay_inspection
    report = (run_inspection(args.config, args.source, args.output)
              if args.command == 'inspect' else replay_inspection(args.run, require_source_match=not args.historical))
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 2 if report.get('status') in ('UNKNOWN', 'STOPPED', 'CANCELLED') else 0


if __name__ == '__main__':
    raise SystemExit(main())
