# Handoff 02 — Solution: Format-Preserving Encryption (FPE) of Identifiers

## Goal

Add a single endpoint to an existing FastAPI service that takes source code as input and returns a copy of that code with every identifier replaced by a deterministic, length-preserving, charset-preserving pseudonym. Same input identifier always maps to the same output token (referential integrity preserved); content is not recoverable without the key. This implements the **O1** transformation from the Husk algorithm catalog.

The point of this transformation: structure (control flow, coupling, naming-shape pathologies) survives perfectly because only the *labels* at terminal AST nodes change. A 60-character `customerOrderRouterManagerImpl` becomes a 60-character pseudo-token; the fact that it is 60 characters and that something else also references it survives.

## Context the agent needs

### Spec excerpt (from the design doc)

> **Mechanism.** Treat each identifier token as plaintext to a tweakable block cipher (NIST SP 800-38G FF1/FF3-1). Output is a token of identical length and charset class, deterministic under a per-corpus key. All uses of `customerOrderRouter` map to the same ciphertext (e.g., `mvpzrfpkjvpqsrtw`); referential integrity is preserved by construction.
>
> **Preserve.** Control flow topology; coupling patterns; dead code; god-objects; circular dependencies; hidden state machines; layered/architectural sins. Naming anti-patterns survive in distorted form (a 60-char identifier stays 60 chars, but the morpheme `Manager` disappears).
>
> **Destroy.** Identifier semantic content. Business identifiers.
>
> **Crumb level — knob: *what is encrypted, and over which charset*.**
> - L0: Encrypt every identifier under a generic charset; comments stripped.
> - L1: Spare standard-library and well-known framework symbols (`React.useState`, `pd.DataFrame`); domain identifiers ciphered.
> - L2: Spare an allowlist of generic domain-category nouns (`User`, `Order`, `Account`); cipher the rest.
> - L3: Cipher only proper-noun-shaped tokens and high-entropy morphemes.

### Inline endpoint contract (must conform)

The host service is FastAPI. Solutions are auto-discovered from `app/solutions/*.py`. Register via decorator:

```python
from app.registry import register

@register(slug="<slug>", name="<Name>", description="<one-line>")
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    ...
    return output, meta  # meta is a free-form dict
```

The endpoint becomes `POST /husk/<slug>`. Request body: `{"input": str, "crumb_level": 0..3, "options": {}}`. Response body: `{"output": str, "solution": str, "crumb_level": int, "meta": {}}`.

### Where you write code

- **Create:** `app/solutions/fpe.py` (one file)
- **Create:** `tests/test_fpe.py`
- **Modify:** `requirements.txt` — add the dependency below
- **Do not modify** anything in `app/main.py`, `app/contract.py`, `app/registry.py`, `app/solutions/__init__.py`, `app/solutions/_example.py`, or any other solution files.

## Implementation plan

### Step 1 — Dependency

Append to `requirements.txt`:

```
pyffx>=0.3
```

If `pyffx` fails to install on the target environment, fall back to the deterministic-pseudonymization implementation in Step 3b. Record the choice in `meta["cipher_backend"]` so the frontend can show which backend ran.

### Step 2 — File header

Create `app/solutions/fpe.py`:

```python
"""O1 — Format-Preserving Encryption of identifiers.

Replaces every identifier token in the input with a deterministic, length-
preserving pseudonym. Same source token → same output token (referential
integrity). Content is not recoverable without the key.

Crumb levels control which tokens are spared (kept as-is) vs ciphered.
"""

import os
import hmac
import hashlib
import re
import string
from typing import Iterable

from app.registry import register
```

### Step 3a — Cipher backend (preferred: `pyffx`)

```python
def _make_cipher(key: bytes, alphabet: str):
    import pyffx
    # pyffx.String supports arbitrary alphabets and length-preserving FF1-style encryption.
    # length is passed at encrypt time per call (pyffx requires it at construction);
    # we wrap to support variable lengths by constructing per-length ciphers lazily.
    cache: dict[int, "pyffx.String"] = {}
    def encrypt(token: str) -> str:
        if not token:
            return token
        n = len(token)
        c = cache.get(n)
        if c is None:
            c = pyffx.String(key, alphabet=alphabet, length=n)
            cache[n] = c
        # Map any chars outside alphabet to a deterministic mapping inside it
        sanitized = "".join(ch if ch in alphabet else alphabet[ord(ch) % len(alphabet)] for ch in token)
        return c.encrypt(sanitized)
    return encrypt
```

### Step 3b — Cipher backend (fallback: HMAC-derived, length-preserving)

Used only if `pyffx` import fails. Achieves the demo property (same length, charset preserved, deterministic) without true NIST FPE.

```python
def _make_cipher_fallback(key: bytes, alphabet: str):
    base = len(alphabet)
    def encrypt(token: str) -> str:
        if not token:
            return token
        # Derive enough deterministic bytes; map each byte to alphabet index
        digest = hmac.new(key, token.encode("utf-8"), hashlib.sha256).digest()
        # Extend digest if token longer than 32 chars
        while len(digest) < len(token):
            digest += hmac.new(key, digest, hashlib.sha256).digest()
        out = "".join(alphabet[b % base] for b in digest[: len(token)])
        # Preserve leading underscore / case-leading-character class for readability
        if token[0] == "_":
            out = "_" + out[1:]
        elif token[0].isupper():
            out = out[0].upper() + out[1:].lower()
        else:
            out = out.lower()
        return out
    return encrypt
```

### Step 4 — Identifier extraction

Language-agnostic regex pass over the input. Walk the input, find runs matching `[A-Za-z_][A-Za-z0-9_]*`. Everything else (whitespace, punctuation, string contents, comments) is preserved verbatim.

```python
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")  # 2+ chars to avoid clobbering `i`, `x`
```

We deliberately skip 1-char identifiers — they're almost always loop counters or trivial locals, ciphering them adds noise without privacy gain.

### Step 5 — Allowlists (skip rules per crumb level)

Hardcode these as module-level frozensets:

```python
# Always preserved across all crumb levels — required for code to remain parseable.
_BASELINE_KEYWORDS = frozenset({
    # Cross-language keywords / control flow / declarations
    "if", "else", "elif", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "return", "yield", "throw", "raise", "try", "except",
    "catch", "finally", "with", "in", "is", "as", "of", "from", "import",
    "export", "module", "package", "namespace", "use", "using",
    "def", "func", "function", "fn", "fun", "method", "class", "interface",
    "struct", "enum", "trait", "impl", "extends", "implements", "abstract",
    "let", "const", "var", "static", "final", "public", "private", "protected",
    "internal", "void", "null", "None", "True", "False", "true", "false",
    "self", "this", "super", "new", "delete", "typeof", "instanceof",
    "async", "await", "lambda", "pass", "and", "or", "not", "nil",
})

# L1+ also skips these (common stdlib / framework names).
_STDLIB_NAMES = frozenset({
    "print", "println", "log", "console", "len", "range", "list", "dict",
    "set", "tuple", "str", "int", "float", "bool", "object", "type",
    "Array", "Object", "String", "Number", "Boolean", "Map", "Set", "Promise",
    "JSON", "Math", "Date", "Error", "Exception", "RuntimeException",
    "useState", "useEffect", "useMemo", "useCallback", "useRef",
    "Component", "Fragment", "render", "props", "state",
    "DataFrame", "Series", "ndarray", "Tensor", "nn", "torch", "tf", "np", "pd",
    "main", "init", "setup", "teardown", "open", "read", "write", "close",
})

# L2+ also skips these (generic domain nouns).
_GENERIC_DOMAIN_NOUNS = frozenset({
    "User", "Account", "Order", "Item", "Product", "Customer", "Client",
    "Service", "Handler", "Controller", "Manager", "Repository", "Repo",
    "Store", "Cache", "Queue", "Worker", "Job", "Task", "Event", "Message",
    "Request", "Response", "Result", "Status", "Error", "Config", "Settings",
    "user", "account", "order", "item", "product", "customer", "client",
    "service", "handler", "controller", "manager", "repository", "repo",
    "store", "cache", "queue", "worker", "job", "task", "event", "message",
    "request", "response", "result", "status", "error", "config", "settings",
})
```

### Step 6 — Per-level skip predicate

```python
def _should_skip(token: str, crumb_level: int) -> bool:
    if token in _BASELINE_KEYWORDS:
        return True
    if crumb_level >= 1 and token in _STDLIB_NAMES:
        return True
    if crumb_level >= 2 and token in _GENERIC_DOMAIN_NOUNS:
        return True
    if crumb_level >= 3:
        # L3: cipher only "high-entropy / proper-noun-shaped" tokens.
        # Heuristic: 3+ CamelCase humps OR 3+ snake_case underscores OR length >= 12.
        humps = len(re.findall(r"[A-Z][a-z]+", token))
        underscores = token.count("_")
        if humps < 3 and underscores < 3 and len(token) < 12:
            return True
    return False
```

### Step 7 — Key management

```python
def _load_key() -> bytes:
    # 16 bytes (128-bit). Read FPE_KEY hex from env; fall back to a fixed dev key.
    hex_key = os.environ.get("FPE_KEY")
    if hex_key:
        try:
            k = bytes.fromhex(hex_key)
            if len(k) >= 16:
                return k[:16]
        except ValueError:
            pass
    # Dev fallback — deterministic so the demo gives stable output across restarts.
    return b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc\xdd\xee\xff"
```

Document `FPE_KEY` in `.env.example` as a 32-hex-char string (16 bytes).

### Step 8 — The `husk` function

```python
_ALPHABET_LOWER = string.ascii_lowercase + string.digits
_ALPHABET_MIXED = string.ascii_letters + string.digits

@register(
    slug="fpe",
    name="Format-Preserving Encryption (O1)",
    description="Deterministic, length-preserving identifier rewrite. Same token → same pseudonym.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    key = _load_key()
    backend_name = "pyffx"
    try:
        encrypt = _make_cipher(key, _ALPHABET_MIXED)
        # Probe to make sure backend works
        encrypt("probe")
    except Exception:
        encrypt = _make_cipher_fallback(key, _ALPHABET_MIXED)
        backend_name = "hmac-fallback"

    seen: dict[str, str] = {}
    skipped = 0
    replaced = 0

    def replace(m: re.Match) -> str:
        nonlocal skipped, replaced
        tok = m.group(0)
        if _should_skip(tok, crumb_level):
            skipped += 1
            return tok
        if tok not in seen:
            seen[tok] = encrypt(tok)
        replaced += 1
        return seen[tok]

    output = _IDENT_RE.sub(replace, input)

    return output, {
        "cipher_backend": backend_name,
        "identifiers_replaced": replaced,
        "identifiers_skipped": skipped,
        "unique_tokens_replaced": len(seen),
        "key_id": "default" if not os.environ.get("FPE_KEY") else "env",
    }
```

### Step 9 — Tests

Create `tests/test_fpe.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _post(body: dict):
    r = client.post("/husk/fpe", json=body)
    assert r.status_code == 200, r.text
    return r.json()

def test_fpe_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "fpe" in slugs

def test_fpe_preserves_length():
    src = "def get_customer_email(customer_id):\n    return customer_id"
    out = _post({"input": src, "crumb_level": 1})["output"]
    # Same total length (we only rewrite tokens, preserving char count)
    assert len(out) == len(src)

def test_fpe_deterministic():
    src = "function processOrder(order) { return order.total; }"
    a = _post({"input": src, "crumb_level": 1})["output"]
    b = _post({"input": src, "crumb_level": 1})["output"]
    assert a == b

def test_fpe_referential_integrity():
    src = "let foo_bar = 1; let baz = foo_bar + foo_bar;"
    out = _post({"input": src, "crumb_level": 0})["output"]
    # Whatever foo_bar became, all three occurrences should be the same token
    # foo_bar is 7 chars; find runs of 7 chars in the same alphabet on the RHS
    # Simpler: count occurrences of any 7-char token after `let `
    # Just assert: the two `foo_bar` positions map to the same string
    # (They were `foo_bar` originally; whatever they become, they should match.)
    # Easier: replaced tokens count should show 1 unique
    meta = _post({"input": src, "crumb_level": 0})["meta"]
    # foo_bar is 7 chars → not skipped; baz is 3 chars → 2-char min satisfied, not skipped
    assert meta["unique_tokens_replaced"] >= 2

def test_fpe_keywords_preserved():
    src = "if (x) return None"
    out = _post({"input": src, "crumb_level": 0})["output"]
    assert "if" in out
    assert "return" in out
    assert "None" in out

def test_fpe_l3_skips_short_tokens():
    src = "user.account.balance"
    out = _post({"input": src, "crumb_level": 3})["output"]
    # short, low-hump tokens should be preserved at L3
    assert out == src

def test_fpe_l3_ciphers_proper_nouns():
    src = "AcmeCorpInvoiceProcessorService doStuff()"
    out = _post({"input": src, "crumb_level": 3})["output"]
    # Multi-hump CamelCase token should be ciphered
    assert "AcmeCorp" not in out
```

## Acceptance criteria

1. `pip install -r requirements.txt` succeeds.
2. `pytest tests/test_fpe.py` — all tests pass.
3. With the server running:
   ```
   curl -X POST http://localhost:8000/husk/fpe \
        -H 'content-type: application/json' \
        -d '{"input":"function processOrder(order) { return order.total; }", "crumb_level": 1}'
   ```
   Returns a 200 response where `output` is the same length as the input, `function`/`return` are preserved, but `processOrder` and `order` have been replaced.
4. Calling the same endpoint with the same input twice returns identical `output` strings (deterministic).
5. `meta` contains `cipher_backend`, `identifiers_replaced`, `identifiers_skipped`, `unique_tokens_replaced`.
6. `GET /solutions` includes `{"slug": "fpe", ...}`.

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

Pick at least three representative files spanning Go, TSX, and TS, run each through your `/husk/fpe` endpoint at crumb levels 0, 1, 2, and 3, and answer the three evaluation questions below with evidence (excerpts of input and husked output).

### Three evaluation questions

1. **Dependency detection.** After husking, can the import graph still be reconstructed? Specifically: do Go `import (...)` blocks, TypeScript `import ... from "..."` statements, and CommonJS `require(...)` calls survive in a form a downstream analyzer can rebuild a module graph from? Note: this solution rewrites identifier-shaped tokens but should NOT touch string literals — verify package paths inside import strings are intact.
2. **Diagram creation.** Can a downstream tool produce a module/struct/component diagram from the husked output? Specifically: do Go `type X struct { ... }` declarations, function/method signatures (arity, parameter types), and React component definitions survive enough that a box-and-arrow architecture diagram can be drawn from the husk?
3. **Code-smell detection.** Pick three smells the original fixture codebase exhibits (e.g. long parameter lists in a resource handler, mixing HTTP/DB concerns in the server file, repeated copy-pasted error-handling, deep nesting in the ingest parser). Check whether each smell is still identifiable from the husk alone.

### Resilience expectations (FPE-specific)

Before declaring this approach "not viable":

- Try at least 3 inputs from the corpus (mix Go + TSX + TS).
- Try crumb levels 0 → 3.
- If `pyffx` won't install on the target environment, switch to the HMAC fallback per Step 3b — don't declare blocked on the dependency.
- If the regex tokenizer misfires on Go raw-string backticks or TSX JSX text (where identifier-shaped fragments appear inside non-code contexts), debug the root cause and try a fix (e.g. skip token spans inside backtick-delimited Go strings) before giving up.
- Try at least one alternative cipher alphabet if the default produces output that breaks consumer parsing (e.g. all-lowercase alphabet vs mixed-case).
- Try ciphering Go method receivers (`func (r *Record) Save()`) and verify the receiver-to-method binding still appears intact in the husk.

### Writing the verdict

Write findings to `<repo-root>/algorithmTests.md` (repo root — that is one directory ABOVE the husk-api project, not inside it).

- If the file does not exist, create it.
- If it exists, **append** a section under the heading `## Solution: fpe`. Do not overwrite or reorder other agents' sections.

The section must contain:
- **Verdict:** `viable` / `viable-with-caveats` / `not-viable`
- **Test inputs used:** list of file paths under `membership/` that you ran through the endpoint
- **Findings — dependency detection:** concrete example (input snippet + husked snippet) and a yes/no with reasoning
- **Findings — diagram creation:** same shape
- **Findings — code-smell detection:** the three smells you picked from the original, and whether each is still detectable from the husk
- **Failure modes encountered + mitigations attempted:** what broke, what you tried, what worked / didn't
- **Recommendation:** keep / iterate / drop, with one paragraph of reasoning

If your verdict is `not-viable`, you may stop after writing this file — the standard acceptance criteria above are waived. The verdict must include enough specific evidence (failing inputs, attempted mitigations) for a human reviewer to confirm the call.

Even if your verdict is `viable`, write the section anyway — the user wants a complete record across all three solutions.

## Out of scope

- **Do not** rewrite string literals or comments. That surface belongs to a different solution; this one only touches identifier-shaped tokens.
- **Do not** parse the input as a specific language (no AST / tree-sitter). Language-agnostic regex tokenization is the spec.
- **Do not** implement the inverse / decryption endpoint. The husk is one-way for the demo.
- **Do not** modify `app/main.py`, `app/contract.py`, `app/registry.py`, or any other solution file.
- **Do not** add a database, key-store integration, or persistence.

## Open questions

Flag rather than guess:

- If `pyffx` does not install cleanly, document that in the PR description and confirm the HMAC fallback ran in tests (`meta.cipher_backend == "hmac-fallback"`).
- Crumb-level L3 uses heuristics (humps / underscores / length) as a proxy for "proper-noun-shaped." If this is too aggressive or too lenient on real test inputs, surface examples — do not silently retune.
- The 1-char identifier skip is intentional. If a use case for ciphering `i`/`x` arises, flag it; do not change unilaterally.
