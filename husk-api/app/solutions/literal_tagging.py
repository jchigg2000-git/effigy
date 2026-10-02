"""I3 — String-Literal & PII Tagging with Type-Class Placeholders.

Replaces every string literal in the input with a typed placeholder
(<URL:n>, <PATH:n>, <MSG:n>, ...). Same literal content → same placeholder
across the whole input (deduplication / coupling preserved).
"""

import re
from urllib.parse import urlparse

from app.registry import register


# Order matters: triple-quoted before single, to avoid mismatching.
# _iter_literals tries these in order at each opener.
_BRANCHES = (
    ('"""', re.compile(r'"""(?:\\.|[^\\])*?"""', re.DOTALL)),  # triple double-quoted
    ("'''", re.compile(r"'''(?:\\.|[^\\])*?'''", re.DOTALL)),  # triple single-quoted
    ('"', re.compile(r'"(?:\\.|[^"\\])*"', re.DOTALL)),         # double-quoted
    # Single-quoted literals may not cross a raw newline (Go, JS/TS, Python and
    # C-family all forbid it). Without the ban an apostrophe in a comment
    # ("Don't") pairs with a quote lines later and swallows the code between.
    # Cost: a multi-line single-quoted Ruby/PHP/shell string is left untagged.
    # Double quotes still cross lines: Rust, Ruby, PHP and shell allow it.
    ("'", re.compile(r"'(?:\\.|[^'\\\n])*'", re.DOTALL)),      # single-quoted
    ("`", re.compile(r"`(?:\\.|[^`\\])*`", re.DOTALL)),         # backtick (template literal)
)
_OPENER_RE = re.compile(r"[\"'`]")
# How far an unterminated single-quoted literal reads before it stops.
_SQ_RUN_RE = re.compile(r"'(?:\\.|[^'\\\n])*", re.DOTALL)

# Languages whose backticks are template literals with ${...} interpolation.
_JS_LANGUAGES = frozenset({"js", "jsx", "ts", "tsx", "javascript", "typescript"})
_RUST_LANGUAGES = frozenset({"rs", "rust"})

# Rust: a single quote opens only a char literal ('x', '\n', '\u{1F600}'); in
# <'a>, &'a str and 'outer: it is a lifetime or a label, and a char literal is
# left as it is, like any rune. A raw string r"..." / br#"..."# has no escapes
# and ends at a quote followed by as many # as opened it.
_RUST_CHAR_RE = re.compile(r"'(?:[^'\\\n]|\\(?:u\{[0-9A-Fa-f_]{1,8}\}|x[0-9A-Fa-f]{2}|.))'")
_RUST_RAW_HEAD_RE = re.compile(r"(?<![\w#])b?r(#*)$")


def _template_end(s: str, i: int) -> int:
    """Index just past the JS template literal opened by the backtick at s[i],
    or -1 if it never closes. Tracks ${...} so a template nested inside an
    interpolation stays part of the outer literal. Iterative, so deep nesting
    cannot hit the recursion limit."""
    n = len(s)
    # -1 marks template text; k >= 0 marks a ${...} at brace depth k.
    stack = [-1]
    j = i + 1
    while j < n:
        c = s[j]
        if stack[-1] < 0:
            if c == "\\":
                j += 2
                continue
            if c == "`":
                stack.pop()
                j += 1
                if not stack:
                    return j
                continue
            if c == "$" and s.startswith("{", j + 1):
                stack.append(0)
                j += 2
                continue
        elif c in "\"'":
            # Skip a quoted string inside ${...} so its braces and backticks
            # do not count. A quote that does not close on its own line was not
            # a string opener (a regex like /'/g, or a comment's apostrophe), and
            # scanning on would swallow the code after the template, so give up
            # and let the caller use the plain first-backtick rule.
            j += 1
            while j < n and s[j] != c and s[j] != "\n":
                j += 2 if s[j] == "\\" else 1
            if j >= n or s[j] != c:
                return -1
        elif c == "`":
            stack.append(-1)
        elif c == "{":
            stack[-1] += 1
        elif c == "}":
            if stack[-1] == 0:
                stack.pop()
            else:
                stack[-1] -= 1
        j += 1
    return -1


def _rust_raw_end(s: str, i: int, dead: set[str]) -> int:
    """If the double quote at s[i] opens a Rust raw string, the index just past
    its closing quote (its closing #s stay outside the literal), else -1. A
    closer that is missing from one point on is missing from every later one,
    so `dead` makes each failed search count once."""
    head = _RUST_RAW_HEAD_RE.search(s, max(0, i - 258), i)
    if head is None:
        return -1
    closer = '"' + head.group(1)
    close = -1 if closer in dead else s.find(closer, i + 1)
    if close < 0:
        dead.add(closer)
        return -1
    return close + 1


def _iter_literals(s: str, js_templates: bool = False, rust: bool = False):
    """Yield (start, end) for each literal, left to right.

    Gives the same spans as one alternation of _BRANCHES under re.sub, which is
    quadratic on an unterminated quote: the engine retries at every later
    escaped quote and rescans to the end each time, so a 200 KB request took
    minutes. Each branch reads `\\.` pairs and single characters, so a branch
    that cannot close from one opener cannot close from a later opener before
    the point where it stopped. Remembering that point keeps the scan linear.
    """
    n = len(s)
    dead_until = [0] * len(_BRANCHES)
    dead_raw: set[str] = set()
    pos = 0
    while True:
        m = _OPENER_RE.search(s, pos)
        if m is None:
            return
        i = m.start()
        end = -1
        if rust and s[i] == "'":
            char = _RUST_CHAR_RE.match(s, i)
            pos = char.end() if char else i + 1
            continue
        if rust and s[i] == '"' and (end := _rust_raw_end(s, i, dead_raw)) >= 0:
            yield i, end
            pos = end
            continue
        for b, (opener, rx) in enumerate(_BRANCHES):
            if i < dead_until[b] or not s.startswith(opener, i):
                continue
            if opener == "`" and js_templates:
                end = _template_end(s, i)
                if end >= 0:
                    break
                # Unterminated: use the plain backtick rule from here on, so
                # a failed scan to the end of input is paid only once.
                js_templates = False
            hit = rx.match(s, i)
            if hit:
                end = hit.end()
                break
            # Only the single-quoted branch can stop before the end of input.
            dead_until[b] = _SQ_RUN_RE.match(s, i).end() if opener == "'" else n
        if end < 0:
            pos = i + 1
        else:
            yield i, end
            pos = end


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
# MIME types ("application/json") match _PATH_RE but are not paths. Dots are
# allowed only in the vnd./prs./x. subtype trees, so "image/logo.png" stays a
# PATH. They go to MSG, an existing class (handoff 03: no silent new classes).
_MIME_RE = re.compile(
    r"^(?:application|audio|font|image|message|model|multipart|text|video)/"
    r"(?:(?:vnd|prs|x)\.[A-Za-z0-9.+\-]+|[A-Za-z0-9+\-]+)(?:\s*;.*)?$",
    re.IGNORECASE,
)
# Slash-joined shorthand that is not a path: dates and fractions ("09/26/2026",
# "1/2") and a short list of everyday pairs ("and/or", "N/A", "km/h", "yes/no").
# Dots stay out of both arms, so "v1/2.json" and "src/lib" are still PATH. They
# go to MSG, an existing class (handoff 03: no silent new classes).
_SLASH_SHORTHAND_RE = re.compile(
    r"^(?:\d+(?:/\d+)+|and/or|n/a|km/h|mi/h|yes/no|on/off|true/false|w/o|he/she)$",
    re.IGNORECASE,
)
# One character or one escape in single quotes: a Go/C/Java rune or char. A
# placeholder there makes a multi-character rune, which does not compile, and
# a single character says next to nothing about the source.
_RUNE_RE = re.compile(
    r"[^\\'\n]|\\(?:[abfnrtv\\'\"0]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|[0-7]{3})"
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
    if _MIME_RE.match(s):
        return "MSG"
    if _SLASH_SHORTHAND_RE.match(s):
        return "MSG"
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
    input_str: str, crumb_level: int, emit_map: bool = False, js_templates: bool = False,
    rust: bool = False,
) -> tuple[str, dict[str, int], dict[str, str]]:
    indices: dict[tuple[str, str], int] = {}
    counters: dict[str, int] = {}
    by_class: dict[str, int] = {}
    # placeholder -> original literal content (built only when emit_map is set).
    reidentify_map: dict[str, str] = {}

    def replace(lit: str) -> str:
        content, quote = _strip_quotes(lit)
        if quote == "'" and _RUNE_RE.fullmatch(content):
            return lit
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

    parts, last = [], 0
    for start, end in _iter_literals(input_str, js_templates, rust):
        parts.append(input_str[last:start])
        parts.append(replace(input_str[start:end]))
        last = end
    parts.append(input_str[last:])
    return "".join(parts), by_class, reidentify_map


@register(
    slug="literal-tagging",
    name="String-Literal Type-Class Tagging (I3)",
    description="Replaces every string literal with a typed placeholder. Repeated literals → repeated tags.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    # Only the JSON boolean true opts in (see fpe.husk).
    emit_map = options.get("emit_map") is True
    # Nested template literals are tracked only when the caller says the input
    # is JS/TS. Go raw strings are backticked too, and a stray "${" in one
    # would send the scanner on through the code after it.
    language = str(options.get("language") or "").lower().lstrip(".")
    output, by_class, reidentify_map = _replace_literals(
        input, crumb_level, emit_map, language in _JS_LANGUAGES, language in _RUST_LANGUAGES
    )
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
