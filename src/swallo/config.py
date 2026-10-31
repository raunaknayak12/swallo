"""
Configuration loader and store location helper for swallo.

Per ADR-026 and TRD.md section 11:
- Stdlib location helper: XDG on POSIX, ~/Library/Application Support on macOS,
  %LOCALAPPDATA% on Windows.
- Overrides: SWALLO_HOME environment variable and explicit CLI options.
- Read with tomllib (stdlib) and validated with Pydantic.
- Warns on unknown keys and if store is inside a git work tree.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StoreSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dir: str | None = None


class RedactSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["fail_closed", "warn"] = "fail_closed"
    denylist: list[str] = Field(default_factory=list)
    decode_depth: int = 2
    breaker_threshold: int = 5
    breaker_window_minutes: int = 10


class DeliverySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["two_file", "inline_trusted_only"] = "two_file"


class TrustSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ide_agent_autoapprove: bool = False


class BudgetSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    default_tokens: int = 4000


class RepoSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    warn_ignore: bool = True


class LogSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    verify_on_start: bool = False


class MCPSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rate_burst: int = 10
    rate_refill_per_hour: int = 20
    draft_quota_count: int = 100
    draft_quota_bytes: int = 10485760
    draft_ttl_days: int = 7


class StaleSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    policy_mcp: Literal["block", "warn"] = "block"
    policy_cli: Literal["block", "warn"] = "warn"


class ApproveSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    signing: Literal["off", "passphrase"] = "off"


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store: StoreSettings = Field(default_factory=StoreSettings)
    redact: RedactSettings = Field(default_factory=RedactSettings)
    delivery: DeliverySettings = Field(default_factory=DeliverySettings)
    trust: TrustSettings = Field(default_factory=TrustSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    repo: RepoSettings = Field(default_factory=RepoSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    stale: StaleSettings = Field(default_factory=StaleSettings)
    approve: ApproveSettings = Field(default_factory=ApproveSettings)


def get_store_dir(override: Path | str | None = None) -> Path:
    """
    Determine store directory without any third-party platformdir dependencies.

    Precedence:
    1. Explicit override (e.g. --store)
    2. SWALLO_HOME environment variable
    3. OS specific default:
       - Windows: %LOCALAPPDATA%\\swallo (never roaming profile)
       - macOS: ~/Library/Application Support/swallo
       - Linux/POSIX: $XDG_DATA_HOME/swallo or ~/.local/share/swallo
    """
    if override is not None:
        return Path(override).expanduser().resolve()

    swallo_home = os.environ.get("SWALLO_HOME")
    if swallo_home:
        return Path(swallo_home).expanduser().resolve()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data)
        else:
            base = Path.home() / "AppData" / "Local"
        return (base / "swallo").resolve()

    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "swallo").resolve()

    # Linux / other POSIX
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    return (base / "swallo").resolve()


def is_inside_git_worktree(path: Path) -> bool:
    """Check if the given directory or any parent contains a .git directory or file."""
    curr = path.resolve()
    while True:
        if (curr / ".git").exists():
            return True
        parent = curr.parent
        if parent == curr:
            break
        curr = parent
    return False


def _find_unknown_keys(
    raw: dict[str, object],
    model: type[BaseModel],
    prefix: str = "",
) -> list[str]:
    unknown: list[str] = []
    known_fields = model.model_fields
    for k, v in raw.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if k not in known_fields:
            unknown.append(full_key)
        elif isinstance(v, dict):
            field_info = known_fields[k]
            annotation = field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                unknown.extend(_find_unknown_keys(v, annotation, full_key))
    return unknown


def load_config(store_dir: Path | str | None = None) -> tuple[Config, list[str]]:
    """
    Load and validate config.toml from the store directory.

    Returns (Config, list_of_warning_messages).
    """
    base_dir = get_store_dir(store_dir)
    config_file = base_dir / "config.toml"

    warnings: list[str] = []

    if is_inside_git_worktree(base_dir):
        warnings.append(f"Store directory '{base_dir}' is located inside a git working tree.")

    if not config_file.is_file():
        return Config(), warnings

    content = config_file.read_bytes()
    raw = tomllib.loads(content.decode("utf-8"))

    unknown_keys = _find_unknown_keys(raw, Config)
    for u in unknown_keys:
        warnings.append(f"Unknown configuration key in {config_file}: '{u}'")

    config = Config.model_validate(raw)
    return config, warnings


def get_default_config_template() -> str:
    """Default template for config.toml written during swallo init."""
    return """# swallo configuration file

[store]
# dir = "" # Override store directory (default: system local app data)

[redact]
mode = "fail_closed" # "fail_closed" or "warn"
denylist = []
decode_depth = 2
breaker_threshold = 5
breaker_window_minutes = 10

[delivery]
mode = "two_file" # "two_file" or "inline_trusted_only"

[trust]
ide_agent_autoapprove = false

[budget]
default_tokens = 4000

[repo]
warn_ignore = true

[log]
verify_on_start = false

[mcp]
rate_burst = 10
rate_refill_per_hour = 20
draft_quota_count = 100
draft_quota_bytes = 10485760
draft_ttl_days = 7

[stale]
policy_mcp = "block" # "block" or "warn"
policy_cli = "warn"

[approve]
signing = "off" # "off" or "passphrase"
"""
