"""Regex structural counters for Go / TypeScript / TSX.

Deliberately regex-based, no AST and no new dependencies, matching the posture
of the solutions themselves. These are not a parser and do not claim to be: they
are reproducible proxies for "did the shape survive," replacing prose findings
like "1 struct, 7 funcs -> 1 struct, 7 methods, same arity" with numbers a
re-run can reproduce.

Known imprecision, stated rather than hidden: counts inside strings and comments
are not excluded, so a literal containing the word "func" inflates the count.
This is acceptable because the same bias applies to input and output, and the
quantity of interest is the DELTA.
"""

from __future__ import annotations

import re

_GO_FUNC = re.compile(r"^\s*func\s", re.M)
_GO_STRUCT = re.compile(r"\btype\s+\w+\s+struct\b")
_GO_IFACE = re.compile(r"\btype\s+\w+\s+interface\b")
_TS_FUNC = re.compile(r"\b(?:function\s+\w+|=>\s*\{|\w+\s*\([^)]*\)\s*\{)")
_TS_IFACE = re.compile(r"\b(?:interface|type)\s+\w+\s*[={]")
_TS_CLASS = re.compile(r"\bclass\s+\w+")
_IMPORT = re.compile(r"^\s*(?:import\b|from\s+['\"]|\w+\s+\"[^\"]+\"\s*$)", re.M)
_EXPORT = re.compile(r"^\s*export\s+", re.M)
_STRLIT = re.compile(r"`(?:[^`\\]|\\.)*`|\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")


def _max_brace_depth(text: str) -> int:
    depth = best = 0
    for ch in text:
        if ch == "{":
            depth += 1
            best = max(best, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return best


def count(text: str, language: str) -> dict[str, int]:
    """Structural counters for one artifact. `language` is go | ts | tsx."""
    lang = language.lower()
    if lang == "go":
        funcs = len(_GO_FUNC.findall(text))
        structs = len(_GO_STRUCT.findall(text))
        ifaces = len(_GO_IFACE.findall(text))
    else:
        funcs = len(_TS_FUNC.findall(text))
        structs = len(_TS_CLASS.findall(text))
        ifaces = len(_TS_IFACE.findall(text))
    return {
        "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        "bytes": len(text.encode("utf-8")),
        "funcs": funcs,
        "structs": structs,
        "interfaces": ifaces,
        "imports": len(_IMPORT.findall(text)),
        "exports": len(_EXPORT.findall(text)),
        "string_literals": len(_STRLIT.findall(text)),
        "max_brace_depth": _max_brace_depth(text),
    }


def delta(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    """b - a, per key. Positive means the output has more of it."""
    return {k: b.get(k, 0) - v for k, v in a.items()}
