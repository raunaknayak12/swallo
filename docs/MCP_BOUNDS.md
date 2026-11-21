# MCP Dependency Lower Bound Empirical Verification

Date: 2026-11-15
Author: Release Engineer

## 1. Problem Statement
The package metadata in v0.1.3 declared:
```toml
mcp = ["mcp>=1.0.0,<2.0.0"]
```
However, `swallo/server/mcp_server.py` relies on `from mcp.server.fastmcp import FastMCP`.
If an installer resolved `mcp` to `1.0.0` or `1.1.x`, `swallo mcp serve` would crash with:
`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`

## 2. Empirical Verification
Inspecting the wheel contents published to PyPI for official `mcp` SDK releases:

| Version | Released | Has `mcp.server.fastmcp` | Status |
|---|---|---|---|
| 1.0.0 | 2024-11 | ❌ False | Incompatible (ModuleNotFoundError) |
| 1.1.0 | 2024-12 | ❌ False | Incompatible (ModuleNotFoundError) |
| 1.1.2 | 2024-12 | ❌ False | Incompatible (ModuleNotFoundError) |
| 1.1.3 | 2024-12 | ❌ False | Incompatible (ModuleNotFoundError) |
| **1.2.0** | 2024-12 | ✅ True (`mcp/server/fastmcp/__init__.py`) | **Lowest Compatible Version** |
| 1.3.0 | 2025-01 | ✅ True | Compatible |
| 1.30.0 | 2025-10 | ✅ True | Highest v1.x Compatible Version |
| 2.0.0 | 2025-11 | ❌ False (`FastMCP` renamed to `MCPServer`) | Incompatible (Breaking v2.x change) |

## 3. Resolution
Updated `pyproject.toml` to:
```toml
[project.optional-dependencies]
mcp = [
    "mcp>=1.2.0,<2.0.0",
]
```
Both `mcp==1.2.0` and `mcp==1.30.0` are continuously verified in `.github/workflows/new-user-validation.yml`.
