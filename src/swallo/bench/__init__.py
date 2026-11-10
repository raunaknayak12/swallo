"""
Benchmark harness package for swallo.

Per BENCHMARKS.md and IMPLEMENTATION_PLAN.md Step 8:
- Provides deterministic Phase 1 benchmark metrics (no LLM calls required).
- Implements 'swallo bench run' and 'swallo bench verify' CLI subcommands.
- Results JSON schema version 0.1 as specified in BENCHMARKS.md.
"""

from __future__ import annotations

