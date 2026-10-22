"""Bounded static review of untrusted Python drafts. Never imports or runs a draft.

Passing this deliberately narrow check is not containment, a security verdict, or
permission to execute. K4 and independent promotion gates remain mandatory.
"""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from typing import Any

POLICY = "python-draft-static-v1"
MAX_BYTES = 16384
MAX_TOKENS = 2000
MAX_NODES = 2000
MAX_DEPTH = 32
ALLOWED_IMPORTS = frozenset({"math", "statistics", "decimal", "fractions"})
BLOCKED_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "breakpoint",
        "help",
        "exit",
        "quit",
    }
)


def validate_draft(source: str) -> dict[str, Any]:
    """A fixed-cost, conservative lint gate, not a Python sandbox or safety proof."""
    encoded = source.encode("utf-8")
    codes: set[str] = set()
    if not source.strip():
        codes.add("empty_source")
    if len(encoded) > MAX_BYTES:
        codes.add("source_size_limit")
    # Tokenize first: nesting/token budgets precede the recursive Python parser.
    if not codes:
        depth = 0
        try:
            for index, token in enumerate(tokenize.generate_tokens(io.StringIO(source).readline)):
                if index >= MAX_TOKENS:
                    codes.add("token_limit")
                    break
                if token.type == tokenize.OP:
                    if token.string in ("(", "[", "{"):
                        depth += 1
                    elif token.string in (")", "]", "}"):
                        depth -= 1
                    if depth > MAX_DEPTH:
                        codes.add("nesting_limit")
                        break
        except (tokenize.TokenError, SyntaxError, ValueError):
            codes.add("invalid_python")
    if not codes:
        try:
            tree = ast.parse(source, mode="exec")
            for index, node in enumerate(ast.walk(tree)):
                if index >= MAX_NODES:
                    codes.add("node_limit")
                    break
                if isinstance(node, ast.Import) and any(
                    alias.name not in ALLOWED_IMPORTS for alias in node.names
                ):
                    codes.add("undeclared_import")
                if isinstance(node, ast.ImportFrom) and (
                    node.level or node.module not in ALLOWED_IMPORTS
                ):
                    codes.add("undeclared_import")
                if isinstance(node, ast.Name) and (
                    node.id in BLOCKED_NAMES or node.id.startswith("__")
                ):
                    codes.add("restricted_name")
                if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                    codes.add("restricted_attribute")
        except (SyntaxError, ValueError, RecursionError):
            codes.add("invalid_python")
    return {
        "policy": POLICY,
        "source_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_bytes": len(encoded),
        "static_status": "rejected" if codes else "passed_static_only",
        "findings": sorted(codes),
        "sandbox_tested": False,
        "execution_authorized": False,
        "required_gates": [
            "reviewed_k4_runtime",
            "isolated_tests",
            "independent_review",
            "owner_approval",
        ],
    }
