"""
Module execution entry point: python -m swallo
"""

from __future__ import annotations

import sys

from swallo.cli import main

if __name__ == "__main__":
    sys.exit(main())
