#!/usr/bin/env python3
"""Main entry point for tally pentesting REPL."""
import argparse
import sys

from core.repl import REPL
from core.tools import tool_registry
from core.startup.checker import DependencyChecker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tally pentesting REPL')
    parser.add_argument(
        '--skip-checks', action='store_true',
        help='Skip dependency checks on startup (for development)'
    )
    parser.add_argument(
        '--check', action='store_true',
        help='Run dependency checks and exit without starting the REPL'
    )
    args = parser.parse_args()

    checker = DependencyChecker(tool_registry)

    if args.check:
        result = checker.run()
        sys.exit(0 if result.all_required_present else 1)

    if not args.skip_checks:
        result = checker.run()
        if not result.all_required_present:
            sys.exit(1)

    try:
        REPL(base_path='.').run()
    except KeyboardInterrupt:
        pass
