"""I3 — String-Literal & PII Tagging with Type-Class Placeholders.

Replaces every string literal in the input with a typed placeholder
(<URL:n>, <PATH:n>, <MSG:n>, ...). Same literal content → same placeholder
across the whole input (deduplication / coupling preserved).
"""

import re
from urllib.parse import urlparse

from app.registry import register


# Order matters: triple-quoted before single, to avoid mismatching.
_LITERAL_RE = re.compile(
    r"""
    (?P<triple_d>\"\"\"(?:\\.|[^\\])*?\"\"\")    |   # triple double-quoted
    (?P<triple_s>'''(?:\\.|[^\\])*?''')          |   # triple single-quoted
    (?P<dq>"(?:\\.|[^"\\])*")                    |   # double-quoted
    (?P<sq>'(?:\\.|[^'\\])*')                    |   # single-quoted
    (?P<bt>`(?:\\.|[^`\\])*`)                        # backtick (template literal)
    """,
    re.VERBOSE | re.DOTALL,
)


def _strip_quotes(lit: str) -> tuple[str, str]:
    """Return (content, quote_style)."""
    for q in ('"""', "'''"):
        if lit.startswith(q) and lit.endswith(q):
            return lit[3:-3], q
    for q in ('"', "'", "`"):
        if lit.startswith(q) and lit.endswith(q):
            return lit[1:-1], q
    return lit, '"'


_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s]+$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PATH_RE = re.compile(
    r"^(?:/|\./|\.\./|~/|[A-Za-z]:[\\/]|[A-Za-z0-9_.\-]+/)[\w./\\\-]*$"
)
_SECRET_PREFIX_RE = re.compile(
    r"^(?:sk_|pk_|ghp_|ghs_|AKIA|ASIA|xox[abp]-|AIza)[A-Za-z0-9_\-]{8,}$"
)
_SECRET_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")
_SQL_KEYWORDS_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|CREATE\s+TABLE)\b",
    re.IGNORECASE,
)


def _classify(content: str) -> str:
    s = content.strip()
    if not s:
        return "EMPTY"
    if _URL_RE.match(s):
        return "URL"
    if _EMAIL_RE.match(s):
        return "EMAIL"
    if _UUID_RE.match(s):
        return "UUID"
    if _SECRET_PREFIX_RE.match(s):
        return "KEY"
    if _SQL_KEYWORDS_RE.search(s):
        return "SQL"
    if _PATH_RE.match(s):
        return "PATH"
    if _SECRET_HIGH_ENTROPY_RE.match(s) and not s.isalpha():
        return "KEY"
    return "MSG"


def _subclass(klass: str, content: str) -> str | None:
    """Returns the L2 sub-tag, or None if no further refinement."""
    s = content.strip()
    if klass == "URL":
        try:
            return urlparse(s).scheme.upper() or None
        except Exception:
            return None
    if klass == "PATH":
        if s.startswith(("./", "../")):
            return "RELATIVE"
        if s.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", s):
            return "ABSOLUTE"
        return "RELATIVE"
    if klass == "SQL":
        m = _SQL_KEYWORDS_RE.search(s)
        return m.group(1).upper().replace(" ", "_") if m else None
    if klass == "MSG":
        if " " in s and any(s.rstrip().endswith(p) for p in (".", "!", "?")):
            return "USER-FACING"
        return "INTERNAL"
    return None


def _skeleton(klass: str, content: str) -> str | None:
    s = content.strip()
    if klass == "URL":
        try:
            u = urlparse(s)
            scheme = (u.scheme or "?").upper()
            host = "HOST" if u.hostname else "?"
            path_segments = [p for p in u.path.split("/") if p]
            path_repr = (
                "/" + "/".join("<seg>" for _ in path_segments)
                if path_segments
                else "/"
            )
            return f"{scheme}:{host}:{path_repr}"
        except Exception:
            return None
    if klass == "PATH":
        segs = [p for p in re.split(r"[\\/]", s) if p]
        return "/" + "/".join("<seg>" for _ in segs) if segs else "/"
    return None


def _format_placeholder(klass: str, idx: int, crumb_level: int, content: str) -> str:
    if crumb_level == 0:
        return f"<LIT:{idx}>"
    if crumb_level == 1:
        return f"<{klass}:{idx}>"
    if crumb_level == 2:
        sub = _subclass(klass, content)
        return f"<{klass}:{sub}:{idx}>" if sub else f"<{klass}:{idx}>"
    sub = _subclass(klass, content)
    skel = _skeleton(klass, content)
    pieces = [klass]
    if sub:
        pieces.append(sub)
    if skel:
        pieces.append(skel)
    pieces.append(str(idx))
    return "<" + ":".join(pieces) + ">"


def _replace_literals(
    input_str: str, crumb_level: int, emit_map: bool = False
) -> tuple[str, dict[str, int], dict[str, str]]:
    indices: dict[tuple[str, str], int] = {}
    counters: dict[str, int] = {}
    by_class: dict[str, int] = {}
    # placeholder -> original literal content (built only when emit_map is set).
    reidentify_map: dict[str, str] = {}

    def replace(m: re.Match) -> str:
        lit = m.group(0)
        content, quote = _strip_quotes(lit)
        klass = _classify(content)
        by_class[klass] = by_class.get(klass, 0) + 1
        key = ("LIT" if crumb_level == 0 else klass, content)
        if key not in indices:
            cls_for_counter = "LIT" if crumb_level == 0 else klass
            indices[key] = counters.get(cls_for_counter, 0)
            counters[cls_for_counter] = indices[key] + 1
        idx = indices[key]
        placeholder = _format_placeholder(klass, idx, crumb_level, content)
        if emit_map:
            # Same content -> same placeholder, so this assignment is stable.
            reidentify_map[placeholder] = content
        return f"{quote}{placeholder}{quote}"

    output = _LITERAL_RE.sub(replace, input_str)
    return output, by_class, reidentify_map


@register(
    slug="literal-tagging",
    name="String-Literal Type-Class Tagging (I3)",
    description="Replaces every string literal with a typed placeholder. Repeated literals → repeated tags.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    emit_map = bool(options.get("emit_map"))
    output, by_class, reidentify_map = _replace_literals(input, crumb_level, emit_map)
    meta = {
        "literals_by_class": by_class,
        "total_literals_replaced": sum(by_class.values()),
    }
    # Opt-in re-identification map (placeholder -> original literal). Sensitive:
    # main.py lifts it into a dedicated response field and it is never logged or
    # persisted. See app/dehusk.py for the reverse-substitution that consumes it.
    if emit_map:
        meta["reidentify_map"] = reidentify_map
    return output, meta
