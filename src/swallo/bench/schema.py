"""
Benchmark results schema and dataclasses.

Per BENCHMARKS.md results.json schema (schema_version 0.1):
- BenchEnvironment: OS, Python version, CPU, memory info.
- BenchFixtureMeta: Manifest SHA-256, count, split.
- BenchResultEntry: Per-test name, sample count, value, 95% CI.
- BenchResults: Top-level container written to results.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class BenchEnvironment:
    """Runtime environment snapshot for reproducibility."""

    os: str
    python: str
    cpu: str
    memory_gb: float


@dataclass
class BenchFixtureMeta:
    """Fixture set metadata for integrity verification."""

    manifest_sha256: str
    count: int
    split: str  # "dev" | "sealed"


@dataclass
class BenchResultEntry:
    """Single benchmark metric result with confidence interval."""

    test: str
    n: int
    value: float
    ci: list[float]  # [lower, upper] 95% CI


@dataclass
class BenchResults:
    """
    Top-level benchmark results container.

    Serialized to results.json with schema_version 0.1.
    """

    tool_version: str
    schema_version: str
    git_commit: str
    seed: int
    environment: BenchEnvironment
    fixtures: BenchFixtureMeta
    results: list[BenchResultEntry] = field(default_factory=list)
    logs: str = "raw/"

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable dictionary."""
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(data: dict[str, object]) -> BenchResults:
        """Deserialize from a dictionary (e.g. parsed from results.json)."""
        env_raw = data.get("environment", {})
        if not isinstance(env_raw, dict):
            env_raw = {}
        env = BenchEnvironment(
            os=str(env_raw.get("os", "")),
            python=str(env_raw.get("python", "")),
            cpu=str(env_raw.get("cpu", "")),
            memory_gb=float(env_raw.get("memory_gb", 0.0)),
        )
        fix_raw = data.get("fixtures", {})
        if not isinstance(fix_raw, dict):
            fix_raw = {}
        fix = BenchFixtureMeta(
            manifest_sha256=str(fix_raw.get("manifest_sha256", "")),
            count=int(fix_raw.get("count", 0)),
            split=str(fix_raw.get("split", "dev")),
        )
        results_raw = data.get("results", [])
        results: list[BenchResultEntry] = []
        if isinstance(results_raw, list):
            for r in results_raw:
                if not isinstance(r, dict):
                    continue
                ci_raw = r.get("ci", [0.0, 0.0])
                if not isinstance(ci_raw, list):
                    ci_raw = [0.0, 0.0]
                results.append(
                    BenchResultEntry(
                        test=str(r.get("test", "")),
                        n=int(r.get("n", 0)),
                        value=float(r.get("value", 0.0)),
                        ci=[float(ci_raw[0]), float(ci_raw[1])] if len(ci_raw) >= 2
                        else [0.0, 0.0],
                    )
                )
        return BenchResults(
            tool_version=str(data.get("tool_version", "")),
            schema_version=str(data.get("schema_version", "0.1")),
            git_commit=str(data.get("git_commit", "")),
            seed=int(data.get("seed", 0)),
            environment=env,
            fixtures=fix,
            results=results,
            logs=str(data.get("logs", "raw/")),
        )
