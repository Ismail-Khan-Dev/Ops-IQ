#!/usr/bin/env python3
"""Triage `except Exception` / bare `except` handlers in the codebase.

Senior-engineer rule of thumb (post-audit): security and financial/decision
paths must not silently swallow errors; observability/instrumentation paths
often should. This script does not judge intent — it lists every broad
exception handler, groups it by module bucket, and flags the ones that both
(a) live in a security/financial module and (b) swallow the exception
(only log `pass`, or return/log without re-raising). Those are your
highest-priority follow-ups.

Usage:
    python scripts/check_bare_except.py [root_dir]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SECURITY_DIRS = {"security", "auth", "tools"}
FINANCIAL_DIRS = {
    "pipeline",
    "checkout",
    "payments",
    "orders",
    "billing",
    "fraud",
    "cart_recovery",
}
AGENT_ACTION_DIRS = {"agents"}
INSTRUMENTATION_DIRS = {"observability", "telemetry", "infra", "memory"}
API_DIRS = {"api", "connectors"}
UTIL_DIRS = {"utils", "models", "graph", "demo", "safety"}

GUILDED_RE = ("logger", "logging", "print")


def bucket_for(path: Path) -> str:
    parts = set(p.lower() for p in path.parts)
    if parts & SECURITY_DIRS:
        return "SECURITY"
    if parts & FINANCIAL_DIRS:
        return "FINANCIAL"
    if parts & AGENT_ACTION_DIRS and "fraud" in parts:
        return "FINANCIAL"
    if parts & AGENT_ACTION_DIRS:
        return "AGENT_ACTION"
    if parts & INSTRUMENTATION_DIRS:
        return "INSTRUMENTATION"
    if parts & API_DIRS:
        return "API"
    return "OTHER"


def _is_silent(body: list[ast.stmt]) -> bool:
    """True if the handler does NOT re-raise and only logs/passes/returns None-ly."""
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            return False
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            name = ast.unparse(func) if hasattr(ast, "unparse") else ""
            if any(n in name for n in GUILDED_RE):
                continue
            return False
        if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
            continue
        if isinstance(stmt, ast.Assign) and not any(
            isinstance(t, ast.Name) and t.id.startswith("_") for t in stmt.targets
        ):
            continue
        if isinstance(stmt, ast.Return):
            continue
        return False
    return True


def _handler_type(node: ast.ExceptHandler) -> str:
    if node.type is None:
        return "bare except"
    try:
        return f"except {ast.unparse(node.type)}" if hasattr(ast, "unparse") else "except <type>"
    except Exception:
        return "except <type>"


def scan(root: Path) -> int:
    risky = 0
    print(f"Scanning {root} for broad exception handlers...\n")
    rows = []
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            label = _handler_type(node)
            is_broad = node.type is None or (
                isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
            )
            if not is_broad:
                continue
            bucket = bucket_for(path)
            silent = _is_silent(node.body)
            first = ""
            if node.body:
                first = ast.get_source_segment(path.read_text(encoding="utf-8", errors="ignore"), node.body[0]) or ""
            first = first.strip().splitlines()[0][:60] if first else ""
            rows.append((bucket, str(path.relative_to(root)), node.lineno, label, silent, first))

    rows.sort(key=lambda r: (0 if r[0] in ("SECURITY", "FINANCIAL") else 1, r[0], r[1], r[2]))
    cur_bucket = None
    for bucket, rel, lineno, label, silent, first in rows:
        if bucket != cur_bucket:
            cur_bucket = bucket
            print(f"\n=== {bucket} ===")
        flag = ""
        if bucket in ("SECURITY", "FINANCIAL") and silent:
            flag = "  [!! silently swallowed — review]"
            risky += 1
        elif silent:
            flag = "  [swallowed]"
        print(f"  {rel}:{lineno}  {label}{flag}\n    -> {first}")

    print(f"\nSummary: {len(rows)} broad handlers; {risky} in security/financial paths swallow without re-raise.")
    return risky


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    return scan(root)


if __name__ == "__main__":
    sys.exit(main())
