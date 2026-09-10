"""Console-script / `python -m reactifact` entry point — see `reactifact.cli`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
