#!/usr/bin/env python3
"""Main entry point for tally pentesting REPL."""
from core.repl import REPL

if __name__ == '__main__':
    try:
        REPL(base_path='.').run()
    except KeyboardInterrupt:
        pass
