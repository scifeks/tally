"""Run the one-time TAL-284 migration: python scripts/migrate_tal_284.py"""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_module("infrastructure.store.tal_284_migration", run_name="__main__")
