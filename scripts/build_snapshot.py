"""Portable entry point without installation or environment variables."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ctw_adviser.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
