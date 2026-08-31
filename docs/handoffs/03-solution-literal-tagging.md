# Handoff 03 — Solution: String-Literal & PII Type-Class Tagging

## Goal

Add a single endpoint to an existing FastAPI service that takes source code as input and returns a copy of that code with every string literal replaced by a typed placeholder (`<URL:0>`, `<PATH:1>`, `<MSG:0>`, etc.). The same literal content always maps to the same placeholder (deduplication preserved). This implements the **I3** transformation from the Husk algorithm catalog.

The point of this transformation: the *role* of each literal (URL vs path vs SQL vs freeform message vs secret) survives, so a downstream analyzer can still reason about external-integration shape and coupling. The *content* (specific URLs, paths, JIRA IDs, business strings) is destroyed. Repeated references to the same literal survive as repeated tags, preserving "this code is coupled to that one endpoint" as a structural feature.

## Context the agent needs

### Spec excerpt (from the design doc)

> **Mechanism.** Scan all string literals; classify each into a type-class (URL, email, file path, SQL, regex, error message, UUID, secret/key, freeform). Replace with `<TYPE-CLASS:n>` where `n` is a per-class counter; uses of the same source literal share the same `n`.
>
> **Inference contract.** The consuming LLM sees that there is a literal of class `URL` at a position — enough to reason about external-integration shape — without seeing `https://api.acme-internal.example.com/v3/customers`. Repeated literal references survive as repeated `<URL:7>`s, preserving coupling-to-that-endpoint as a structural feature.
>
> **Crumb level — knob: *type-class granularity*.**
> - L0: `<LIT>` for every string. No class.
> - L1: Coarse class: `<URL>`, `<PATH>`, `<MSG>`, `<KEY>`.
> - L2: Fine class: `<URL:HTTPS>`, `<PATH:RELATIVE>`, `<MSG:USER-FACING>`, `<SQL:SELECT>`.
> - L3: Class + structural skeleton: `<URL:HTTPS:HOST?:/v?/<segment>/<segment>>`.

### Inline endpoint contract (must conform)

The host service is FastAPI. Solutions are auto-discovered from `app/solutions/*.py`. Register via decorator:

```python
from app.registry import register

@register(slug="<slug>", name="<Name>", description="<one-line>")
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    ...
    return output, meta
```

The endpoint becomes `POST /husk/<slug>`. Request body: `{"input": str, "crumb_level": 0..3, "options": {}}`. Response body: `{"output": str, "solution": str, "crumb_level": int, "meta": {}}`.

### Where you write code

- **Create:** `app/solutions/literal_tagging.py` (one file)
- **Create:** `tests/test_literal_tagging.py`
- **Do not modify** `requirements.txt` (this solution uses only stdlib).
- **Do not modify** anything in `app/main.py`, `app/contract.py`, `app/registry.py`, `app/solutions/__init__.py`, `app/solutions/_example.py`, or any other solution files.

## Implementation plan

### Step 1 — File header

Create `app/solutions/literal_tagging.py`:

```python
"""I3 — String-Literal & PII Tagging with Type-Class Placeholders.

Replaces every string literal in the input with a typed placeholder
(<URL:n>, <PATH:n>, <MSG:n>, ...). Same literal content → same placeholder
across the whole input (deduplication / coupling preserved).
"""

import re
from typing import Iterable
from urllib.parse import urlparse

from app.registry import register
```

### Step 2 — Literal extraction

Find string literals in three flavors, in priority order. Use a single combined regex with named groups so positions and quote styles are tracked together.

```python
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
```

For each match, the *content* is the literal with quotes stripped (one char each side for single-quoted, three for triple). The *quote style* is one of `"`, `'`, `\`\`\``, `"""`, `'''`.

```python
def _strip_quotes(lit: str) -> tuple[str, str]:
    """Return (content, quote_style)."""
    for q in ('"""', "'''"):
        if lit.startswith(q) and lit.endswith(q):
            return lit[3:-3], q
    for q in ('"', "'", "`"):
        if lit.startswith(q) and lit.endswith(q):
            return lit[1:-1], q
    return lit, '"'
```

### Step 3 — Classifier

Classify the *content* into one of these classes. Order matters — first match wins:

```python
_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s]+$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_PATH_RE = re.compile(r"^(?:/|\./|\.\./|~/|[A-Za-z]:[\\/]|[A-Za-z0-9_.\-]+/)[\w./\\\-]*$")
_SECRET_PREFIX_RE = re.compile(r"^(?:sk_|pk_|ghp_|ghs_|AKIA|ASIA|xox[abp]-|AIza)[A-Za-z0-9_\-]{8,}$")
_SECRET_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")
_SQL_KEYWORDS_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|CREATE\s+TABLE)\b", re.IGNORECASE)

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
    # High-entropy random-looking strings without classification → likely a key/token
    if _SECRET_HIGH_ENTROPY_RE.match(s) and not s.isalpha():
        return "KEY"
    return "MSG"
```

### Step 4 — Sub-classification (for L2/L3)

```python
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
        # Heuristic: looks like a sentence with whitespace and ending punct → user-facing
        if " " in s and any(s.rstrip().endswith(p) for p in (".", "!", "?")):
            return "USER-FACING"
        return "INTERNAL"
    return None
```

### Step 5 — Skeleton (for L3 — URLs and PATHs only)

```python
def _skeleton(klass: str, content: str) -> str | None:
    s = content.strip()
    if klass == "URL":
        try:
            u = urlparse(s)
            scheme = (u.scheme or "?").upper()
            host = "HOST" if u.hostname else "?"
            path_segments = [p for p in u.path.split("/") if p]
            path_repr = "/" + "/".join("<seg>" for _ in path_segments) if path_segments else "/"
            return f"{scheme}:{host}:{path_repr}"
        except Exception:
            return None
    if klass == "PATH":
        segs = [p for p in re.split(r"[\\/]", s) if p]
        return "/" + "/".join("<seg>" for _ in segs) if segs else "/"
    return None
```

### Step 6 — Placeholder builder

```python
def _format_placeholder(klass: str, idx: int, crumb_level: int, content: str) -> str:
    if crumb_level == 0:
        return f"<LIT:{idx}>"
    if crumb_level == 1:
        return f"<{klass}:{idx}>"
    if crumb_level == 2:
        sub = _subclass(klass, content)
        return f"<{klass}:{sub}:{idx}>" if sub else f"<{klass}:{idx}>"
    # crumb_level == 3
    sub = _subclass(klass, content)
    skel = _skeleton(klass, content)
    pieces = [klass]
    if sub:
        pieces.append(sub)
    if skel:
        pieces.append(skel)
    pieces.append(str(idx))
    return "<" + ":".join(pieces) + ">"
```

### Step 7 — Replacement walk

```python
def _replace_literals(input_str: str, crumb_level: int) -> tuple[str, dict[str, int]]:
    # Map (class, content) → idx so identical literals share an index per class.
    indices: dict[tuple[str, str], int] = {}
    counters: dict[str, int] = {}
    by_class: dict[str, int] = {}

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
        # Wrap placeholder in original quote style so it's still a syntactically valid string literal
        if quote in ('"""', "'''"):
            return f"{quote}{placeholder}{quote}"
        return f"{quote}{placeholder}{quote}"

    output = _LITERAL_RE.sub(replace, input_str)
    return output, by_class
```

### Step 8 — Register

```python
@register(
    slug="literal-tagging",
    name="String-Literal Type-Class Tagging (I3)",
    description="Replaces every string literal with a typed placeholder. Repeated literals → repeated tags.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    output, by_class = _replace_literals(input, crumb_level)
    return output, {
        "literals_by_class": by_class,
        "total_literals_replaced": sum(by_class.values()),
    }
```

### Step 9 — Tests

Create `tests/test_literal_tagging.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _post(body: dict):
    r = client.post("/husk/literal-tagging", json=body)
    assert r.status_code == 200, r.text
    return r.json()

def test_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "literal-tagging" in slugs

def test_url_classified():
    src = 'fetch("https://api.example.com/v1/users")'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<URL:0>" in out
    assert "https://api.example.com" not in out

def test_path_classified():
    src = "open('./config/settings.json')"
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<PATH:0>" in out

def test_sql_classified():
    src = 'db.exec("SELECT * FROM users WHERE id = 1")'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<SQL:0>" in out

def test_secret_classified():
    src = 'token = "ghp_AbCdEf1234567890XYZabcdEf12345678"'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<KEY:0>" in out

def test_dedup_same_literal_same_index():
    src = 'a = "https://x.example/api"; b = "https://x.example/api"; c = "https://y.example/api"'
    out = _post({"input": src, "crumb_level": 1})["output"]
    # Two URL:0s and one URL:1
    assert out.count("<URL:0>") == 2
    assert out.count("<URL:1>") == 1

def test_l0_collapses_classes():
    src = 'a = "https://x"; b = "/etc/passwd"; c = "hello world."'
    out = _post({"input": src, "crumb_level": 0})["output"]
    assert "<LIT:0>" in out
    assert "<LIT:1>" in out
    assert "<LIT:2>" in out
    assert "URL" not in out
    assert "PATH" not in out

def test_l2_fine_class():
    src = 'fetch("https://api.example.com/v1/users")'
    out = _post({"input": src, "crumb_level": 2})["output"]
    assert "HTTPS" in out

def test_l3_skeleton():
    src = 'fetch("https://api.example.com/v1/users/42/orders")'
    out = _post({"input": src, "crumb_level": 3})["output"]
    # Skeleton should contain segment markers
    assert "<seg>" in out

def test_meta_counts():
    src = 'fetch("https://x"); read("/tmp/y"); say("hi")'
    body = _post({"input": src, "crumb_level": 1})
    counts = body["meta"]["literals_by_class"]
    assert counts.get("URL", 0) >= 1
    assert counts.get("PATH", 0) >= 1
    assert counts.get("MSG", 0) >= 1
```

## Acceptance criteria

1. `pytest tests/test_literal_tagging.py` — all tests pass.
2. With the server running:
   ```
   curl -X POST http://localhost:8000/husk/literal-tagging \
        -H 'content-type: application/json' \
        -d '{"input":"fetch(\"https://api.example.com/v1/users\"); fetch(\"https://api.example.com/v1/users\")", "crumb_level": 1}'
   ```
   Returns a 200 response where both URL literals were replaced with `"<URL:0>"` (same index because content was identical).
3. `meta.literals_by_class` is a dict with class names as keys and counts as values.
4. `GET /solutions` includes `{"slug": "literal-tagging", ...}`.

## Testing on a real codebase + resilience expectations

> **Editor's note — the corpus this section names is not part of this repository.**
> This brief was written against a third-party fixture codebase that is not
> published here. It was replaced by `corpus/stacks/` — a synthetic
> public-library catalog and circulation app written from `corpus/stacks/SPEC.md`
> and size-matched to the files this brief asked for. The paths below will not resolve; read them as a
> record of what was asked for at the time. Current results live in
> `algorithmTests.md` and `evals/runs/`.
>
> This handoff is **build history and is not rewritten** — root `CLAUDE.md`
> keeps `docs/handoffs/01-06` as the per-component build record. Where it
> disagrees with the code, the code wins.

Before declaring this handoff complete (or declaring the approach unviable), validate the implementation against a real mixed-language codebase already on disk at:

    <repo-root>/membership/

This corpus contains:
- A Go HTTP API under `membership/api/` — a `cmd/` daemon entrypoint, an `internal/api/` package of five handler files (a server, two resource handlers, an admin handler and an error helper), an `internal/` mapper onto a standard record type for the domain, an `internal/ingest/` parser for the domain's flat-file interchange format, an `internal/model/` struct set and an `internal/store/` persistence layer — plus `*_test.go` siblings.
- A React/TypeScript frontend under `membership/app/src/` (`App.tsx`, `auth.ts`, `api/client.ts`, and six components — an auth gate, a login page, a record detail view, a record edit form, a results table and a search form — plus `__tests__/` siblings).

Pick at least three representative files spanning Go, TSX, and TS, run each through your `/husk/literal-tagging` endpoint at crumb levels 0, 1, 2, and 3, and answer the three evaluation questions below with evidence (excerpts of input and husked output).

### Three evaluation questions

1. **Dependency detection.** After husking, can the import graph still be reconstructed? This is the question MOST AT RISK for this solution: Go `import "fmt"`, TS `import x from "./components/Foo"`, and `require("path")` all use string literals as the import target. Your transformation rewrites string literals — verify whether import paths get tagged as `<PATH:n>` or `<MSG:n>` and become unrecoverable. Report honestly. Consider whether import-shaped string literals should be a special class (`<IMPORT:n>` or skipped entirely).
2. **Diagram creation.** Can a downstream tool produce a module/struct/component diagram from the husked output? Identifiers and structure are untouched by this solution, so this should still work — confirm with a real example. Look at coupling that survives: e.g. multiple files referencing the same `<URL:0>` placeholder is a structural signal preserved.
3. **Code-smell detection.** Pick three smells the original membership codebase exhibits and check whether each is still identifiable from the husk. Specifically test: SQL-as-string-literals (a smell on its own — tagged as `<SQL:n>` — does the smell survive as a signal?), magic-string state machines (`if status == "ACTIVE"` patterns — does the literal-as-enum problem flagged in the spec actually bite?), and one structural smell of your choice (long functions, deep nesting, copy-paste).

### Resilience expectations (literal-tagging-specific)

Before declaring this approach "not viable":

- Try at least 3 inputs from the corpus (mix Go + TSX + TS).
- Try crumb levels 0 → 3.
- If your literal regex misses or over-matches on a real input shape (Go raw-strings with backticks, TSX template literals with `${...}` interpolation, multi-line Go string concatenation), debug the root cause and patch the regex — don't just skip the input.
- Try at least one alternative classifier ordering or threshold (e.g. is the SQL detector firing on innocuous text containing `FROM`?).
- If you find import-path strings collapsing into `<PATH:n>` and breaking dependency analysis, try adding an `IMPORT` class that activates only for literals appearing as direct arguments to `import`/`require`/`from` constructs — surface this as a finding even if you don't add it to the implementation.
- TSX JSX text content (between tags like `<p>Hello world</p>`) is technically not a string literal in the regex sense — verify your regex behavior on this and document.

### Writing the verdict

Write findings to `<repo-root>/algorithmTests.md` (repo root — that is one directory ABOVE the husk-api project, not inside it).

- If the file does not exist, create it.
- If it exists, **append** a section under the heading `## Solution: literal-tagging`. Do not overwrite or reorder other agents' sections.

The section must contain:
- **Verdict:** `viable` / `viable-with-caveats` / `not-viable`
- **Test inputs used:** list of file paths under `membership/` that you ran through the endpoint
- **Findings — dependency detection:** concrete example (input snippet + husked snippet) — pay particular attention to import-path survival
- **Findings — diagram creation:** same shape
- **Findings — code-smell detection:** the three smells you picked from the original, and whether each is still detectable from the husk
- **Failure modes encountered + mitigations attempted:** what broke, what you tried, what worked / didn't
- **Recommendation:** keep / iterate / drop, with one paragraph of reasoning

If your verdict is `not-viable`, you may stop after writing this file — the standard acceptance criteria above are waived. The verdict must include enough specific evidence (failing inputs, attempted mitigations) for a human reviewer to confirm the call.

Even if your verdict is `viable`, write the section anyway — the user wants a complete record across all three solutions.

## Out of scope

- **Do not** rewrite identifiers. Identifier-shaped tokens are handled by a different solution.
- **Do not** parse the input as a specific language (no AST / tree-sitter). Regex-based literal extraction is the spec.
- **Do not** add a real PII detector (Microsoft Presidio, spaCy NER). The simple class regexes above are sufficient for the demo. If a Presidio-shaped extension is wanted later it can be added behind an `options.use_presidio` flag — but not in this handoff.
- **Do not** modify `app/main.py`, `app/contract.py`, `app/registry.py`, or any other solution file.
- **Do not** redact comments or identifier-like content inside literals beyond what the classifier does.

## Open questions

Flag rather than guess:

- The classifier prioritizes URL > EMAIL > UUID > KEY > SQL > PATH > MSG. If a real input falls through unexpectedly (e.g. a regex pattern stored as a string is classified as MSG), surface an example — do not silently add new classes.
- L3 skeleton is implemented for URL and PATH only. SQL skeletons (column lists, table-name placeholders) are intentionally out of scope.
- Backtick template literals containing interpolation (`${...}`) are treated as plain strings — the interpolation expression is part of the placeholder. If preserving template-literal structure becomes important, surface it.
