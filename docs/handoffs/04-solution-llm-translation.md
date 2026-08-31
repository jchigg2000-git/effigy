# Handoff 04 — Solution: LLM Domain Translation with Pathology Anchors

## Goal

Add a single endpoint to an existing FastAPI service that takes source code as input, sends it to a local (or remote) Large Language Model with a system prompt instructing the model to translate the code into a different domain while preserving every architectural pathology, and returns the translated output. This implements the **I4** transformation from the Husk algorithm catalog.

The point of this transformation: the most aggressive scrambling option in the catalog. The output reads as natural code in a chosen target domain — a fintech codebase comes out as a chess engine, a logistics codebase comes out as a music streaming service. The downstream consumer treats the output at face value; the diagnostic value is preserved because pathology was anchor-preserved (cycles, god-objects, dead code, comments-as-rules).

The endpoint must default to a local Ollama backend running `qwen2.5-coder:14b`, but be configurable via environment variables so it can be repointed at a Hugging Face Inference endpoint or any other OpenAI-compatible API without code changes.

## Context the agent needs

### Spec excerpt (from the design doc)

> **Mechanism.** Feed each module to a rewrite LLM with a system prompt: *"Translate this code into a different domain. Preserve every architectural pathology — cycles, god-objects, layering violations, dead code, comments-as-rules. Replace every domain-specific name and literal with a same-shape name from the target domain. Do not refactor. Do not improve."*
>
> **Inference contract.** The most aggressive scrambling option. Produces a husk that reads as *natural code in a chosen target domain*. The consuming LLM treats it at face value — it analyzes a chess engine — and the diagnosis is valid because pathology was anchor-preserved. **The consumer does not need to "see through" the disguise.** It needs to find the pathology, and the pathology survived the translation.
>
> **Crumb level — knob: *distance between source and target domain*.**
> - L0: Target = generic / abstract domain (graph traversal, pure-computation pipeline).
> - L1: Target = unrelated industry vertical.
> - L2: Target = adjacent vertical with similar shape (retail ↔ logistics).
> - L3: Target = same vertical, different sub-segment (consumer banking ↔ commercial banking).

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

The host service exposes a `BackendUnavailable` exception class that, when raised from inside `husk(...)`, returns a 502 to the client:

```python
from app.main import BackendUnavailable
# raise BackendUnavailable("ollama not reachable at http://localhost:11434")
```

### Where you write code

- **Create:** `app/solutions/llm_translation.py` (one file)
- **Create:** `tests/test_llm_translation.py`
- **Modify:** `requirements.txt` — add `openai>=1.40` (the OpenAI SDK works against any OpenAI-compatible endpoint, including Ollama and HuggingFace TGI)
- **Modify:** `.env.example` — append the env vars documented in Step 2 below
- **Do not modify** anything in `app/main.py`, `app/contract.py`, `app/registry.py`, `app/solutions/__init__.py`, `app/solutions/_example.py`, or any other solution files.

## Implementation plan

### Step 1 — Dependencies

Append to `requirements.txt`:

```
openai>=1.40
```

The OpenAI SDK is used because Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1`, and Hugging Face TGI / Inference Endpoints / vLLM all support the same protocol. This makes "swap the backend later" a config change, not a code change.

### Step 2 — Environment variables

Append to `.env.example`:

```
# === Solution: llm-translation ===
# Base URL of an OpenAI-compatible chat completions endpoint.
# Default targets a local Ollama instance.
LLM_BASE_URL=http://localhost:11434/v1

# Model name as the backend understands it.
LLM_MODEL=qwen2.5-coder:14b

# API key. Ollama ignores it; HF Inference / OpenAI / vLLM may require it.
LLM_API_KEY=ollama

# Request timeout in seconds. Translation of large modules can take a while.
LLM_TIMEOUT_SECONDS=180

# Optional: temperature. Lower = more deterministic translations.
LLM_TEMPERATURE=0.2

# Optional: max output tokens.
LLM_MAX_TOKENS=4096
```

These env vars are read at request time (not import time), so the user can change them and re-hit the endpoint without restarting.

### Step 3 — File header

Create `app/solutions/llm_translation.py`:

```python
"""I4 — LLM Domain Translation with Pathology Anchors.

Sends the input to an LLM with a system prompt instructing it to translate
the code into a different domain while preserving every architectural
pathology. Defaults to local Ollama running qwen2.5-coder:14b; configurable
via env vars to point at any OpenAI-compatible endpoint.
"""

import os
from typing import Any

from openai import OpenAI, APIConnectionError, APITimeoutError, APIError

from app.registry import register
from app.main import BackendUnavailable
```

### Step 4 — Target-domain selector (per crumb level)

```python
# Target domains by crumb level. The frontend can override via options.target_domain.
_TARGETS_BY_LEVEL = {
    0: [
        "abstract graph traversal over labelled nodes",
        "a pure computation pipeline over numeric tensors",
        "a generic event-loop scheduler over opaque tasks",
    ],
    1: [
        "a chess engine with positions, moves, and evaluations",
        "a recipe-management app with ingredients, steps, and meal plans",
        "a wildlife tracking system with species, sightings, and migration routes",
    ],
    2: [
        # Adjacent verticals with similar shape — pick based on input shape if possible
        "a logistics dispatch system with shipments, routes, and carriers",
        "a music streaming service with tracks, playlists, and listeners",
        "a hotel booking platform with rooms, reservations, and guests",
    ],
    3: [
        # Same vertical, different sub-segment. Generic but plausibly close.
        "a different sub-segment of the same domain (small business → enterprise variant)",
    ],
}

def _pick_target(crumb_level: int, options: dict) -> str:
    override = options.get("target_domain") if isinstance(options, dict) else None
    if isinstance(override, str) and override.strip():
        return override.strip()
    pool = _TARGETS_BY_LEVEL.get(crumb_level, _TARGETS_BY_LEVEL[1])
    # Deterministic pick: first in list. Variety is achievable via the override.
    return pool[0]
```

### Step 5 — System prompt (inline, exact)

```python
_SYSTEM_PROMPT = """You are a code translator that produces "husked" copies of source code for privacy-preserving analysis.

Your job: translate the user's code into a DIFFERENT problem domain while preserving every structural and architectural property. The output must look like natural code in the target domain, not like a redacted version of the input.

PRESERVE EXACTLY:
- Control flow shape (every if/else/for/while/try in the same place)
- Function and method count, parameter count, and arity
- Class hierarchy and module structure
- Coupling and call relationships (if A calls B in the input, A' calls B' in the output)
- Dead code (if the input has unused functions, the output has unused functions)
- God-objects (if a class has 40 methods in the input, its translation has 40 methods)
- Cycles in dependencies (if A imports B and B imports A, preserve that)
- Comments — translate their CONTENT to the new domain, but keep their POSITION and SPEECH ACT (a TODO stays a TODO, a FIXME stays a FIXME, a prescriptive rule stays a prescriptive rule)
- Naming morphology — long names stay long, abbreviations stay abbreviated, hungarian-prefix density is preserved
- The choice of language and overall syntax style of the input

DESTROY COMPLETELY:
- Domain-specific identifier content (no leakage of the source domain)
- Domain-specific string literal content
- URLs, paths, business identifiers, proper nouns, JIRA/ticket/PR references
- Author names, customer names, internal product/project codenames

DO NOT:
- Refactor or improve the code in any way
- Fix bugs, simplify complex logic, deduplicate, or rename for clarity
- Add new comments explaining what you did
- Wrap the output in markdown fences or commentary
- Output anything other than the translated code

OUTPUT FORMAT:
Return ONLY the translated source code. No preamble, no explanation, no markdown fences. The first character of your response is the first character of the translated code."""

def _user_prompt(target: str, code: str) -> str:
    return f"Target domain: {target}\n\nSource code to translate (preserve all structure, translate to target domain):\n\n{code}"
```

### Step 6 — Client construction

```python
def _make_client() -> OpenAI:
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("LLM_API_KEY", "ollama")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
```

### Step 7 — The `husk` function

```python
@register(
    slug="llm-translation",
    name="LLM Domain Translation (I4)",
    description="Translates the input into a different domain while preserving pathology. Backend: configurable OpenAI-compatible.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    target = _pick_target(crumb_level, options)
    model = os.environ.get("LLM_MODEL", "qwen2.5-coder:14b")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

    client = _make_client()

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(target, input)},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (APIConnectionError, APITimeoutError) as e:
        raise BackendUnavailable(
            f"LLM backend unreachable at {os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')}: {e}"
        ) from e
    except APIError as e:
        # Other API errors — let the host turn them into 500s.
        raise RuntimeError(f"LLM API error: {e}") from e

    output_text = (resp.choices[0].message.content or "").strip()
    # Strip a stray markdown fence if the model added one despite instructions.
    output_text = _strip_code_fence(output_text)

    usage = getattr(resp, "usage", None)
    meta: dict[str, Any] = {
        "model": model,
        "base_url": os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
        "target_domain": target,
        "temperature": temperature,
    }
    if usage is not None:
        meta["usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
    return output_text, meta


def _strip_code_fence(s: str) -> str:
    """If the model wrapped output in ```...```, unwrap it. Otherwise return s unchanged."""
    s = s.strip()
    if not s.startswith("```"):
        return s
    # Drop opening fence line (```lang or ```)
    first_nl = s.find("\n")
    if first_nl == -1:
        return s
    body = s[first_nl + 1 :]
    if body.endswith("```"):
        body = body[:-3]
    return body.rstrip()
```

### Step 8 — Tests

The tests must NOT require a running LLM. Use mocking so CI / local dev passes without Ollama.

Create `tests/test_llm_translation.py`:

```python
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "llm-translation" in slugs

def _mock_completion(text: str, prompt_tokens=10, completion_tokens=20):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp

def test_happy_path_returns_translated_code():
    fake = _mock_completion("class Pawn:\n    pass\n")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "class Customer:\n    pass\n",
            "crumb_level": 1,
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Pawn" in body["output"]
    assert body["meta"]["target_domain"]
    assert body["meta"]["model"]

def test_strips_code_fences():
    fake = _mock_completion("```python\nclass Pawn:\n    pass\n```")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    out = r.json()["output"]
    assert not out.startswith("```")
    assert "class Pawn" in out

def test_backend_unavailable_returns_502():
    from openai import APIConnectionError
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 502
    assert r.json()["error"] == "backend_unavailable"

def test_target_domain_override():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_domain": "a coffee-shop ordering system"},
        })
    assert r.status_code == 200
    assert r.json()["meta"]["target_domain"] == "a coffee-shop ordering system"

def test_crumb_levels_pick_different_pools():
    fake = _mock_completion("output")
    targets = []
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        for lvl in (0, 1, 2):
            r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": lvl})
            targets.append(r.json()["meta"]["target_domain"])
    # Each level picks from a different pool — at least the L0 target should not match L1
    assert targets[0] != targets[1]
```

## Acceptance criteria

1. `pip install -r requirements.txt` succeeds (openai SDK installed).
2. `pytest tests/test_llm_translation.py` — all tests pass without a running LLM (mocks cover the API).
3. With Ollama running locally and `qwen2.5-coder:14b` pulled (`ollama pull qwen2.5-coder:14b`):
   ```
   curl -X POST http://localhost:8000/husk/llm-translation \
        -H 'content-type: application/json' \
        -d '{"input":"class Customer:\n    def get_invoice(self): pass", "crumb_level": 1}'
   ```
   Returns a 200 response where `output` is plausibly translated code in a different domain, and `meta` contains `model`, `base_url`, `target_domain`, and `usage`.
4. With Ollama NOT running:
   ```
   curl -X POST http://localhost:8000/husk/llm-translation \
        -H 'content-type: application/json' \
        -d '{"input":"x = 1", "crumb_level": 1}'
   ```
   Returns a 502 with `{"error": "backend_unavailable", "detail": "..."}`.
5. Setting `LLM_BASE_URL=https://api-inference.huggingface.co/v1`, `LLM_MODEL=<model-id>`, `LLM_API_KEY=hf_...` in the environment redirects requests to a Hugging Face endpoint without code changes.
6. `GET /solutions` includes `{"slug": "llm-translation", ...}`.

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

Pick at least three representative files spanning Go, TSX, and TS, run each through your `/husk/llm-translation` endpoint at crumb levels 0, 1, 2, and 3, and answer the three evaluation questions below with evidence (excerpts of input and translated output).

### Three evaluation questions

1. **Dependency detection.** After translation, can the import graph still be reconstructed? This solution rewrites entire files — including imports. Does the model preserve `import` block shape (same number of imports, in the same order, just with renamed paths)? Or does it collapse, reorder, or drop imports? If it renames an import path, does the same renamed path consistently refer to the "same" translated module across files? Report honestly — cross-file referential integrity is the hardest property for an LLM to maintain.
2. **Diagram creation.** Can a downstream tool produce a module/struct/component diagram from the translated output? Specifically: does the translation preserve struct/class count, method count, function arity, and call relationships? A 12-method store interface should come out the other side as a 12-method `<TranslatedThing>Store`, not a refactored 5-method version.
3. **Code-smell detection.** Pick three smells the original fixture codebase exhibits (e.g. mixing of HTTP and DB concerns in the server file, long parameter lists in a resource handler, deep nesting in the ingest parser, copy-pasted error handling). Check whether each smell SURVIVES the translation — the model is instructed not to refactor or improve, but it may still "naturally" tidy code. The pathology-anchor preservation is the entire point of this approach; if smells are silently fixed, the approach is broken.

### Resilience expectations (LLM-translation-specific)

Before declaring this approach "not viable":

- **Make sure Ollama is actually running.** `curl http://localhost:11434/api/tags` should list available models. If `qwen2.5-coder:14b` is not listed, run `ollama pull qwen2.5-coder:14b` before testing. If the pull fails, document and try a smaller compatible model (e.g. `qwen2.5-coder:7b` or `qwen2.5-coder:3b`) by setting `LLM_MODEL` and re-running — do not declare blocked on model availability.
- Try at least 3 inputs from the corpus (mix Go + TSX + TS).
- Try crumb levels 0 → 3, and try at least two `options.target_domain` overrides (e.g. `"a chess engine"` and `"a logistics dispatch system"`).
- If the model wraps output in markdown fences despite the system prompt, verify your `_strip_code_fence` handles it. If the model adds preamble text ("Here is the translation:"), surface it — don't silently trim.
- If an input exceeds the context window and returns an error, try smaller files first to confirm the pipeline works, then surface the size limit as a finding (not a blocker).
- If translation latency is too high (e.g. >2 minutes), try lowering temperature, lowering `max_tokens`, or testing on smaller files. Report wall-clock times.
- If you suspect the model is "improving" the code (fixing bugs, deduplicating, renaming for clarity), pick an input with an obvious smell (e.g. a copy-pasted error block) and confirm whether the smell survives. Document the result either way.
- Try at least one input through the endpoint twice in a row to confirm determinism is acceptable for your verdict (low temperature should give similar but not identical output — note how much it varies).

### Writing the verdict

Write findings to `<repo-root>/algorithmTests.md` (repo root — that is one directory ABOVE the husk-api project, not inside it).

- If the file does not exist, create it.
- If it exists, **append** a section under the heading `## Solution: llm-translation`. Do not overwrite or reorder other agents' sections.

The section must contain:
- **Verdict:** `viable` / `viable-with-caveats` / `not-viable`
- **Backend used:** which model was loaded (`LLM_MODEL`), which endpoint (`LLM_BASE_URL`), wall-clock latency per request (rough)
- **Test inputs used:** list of file paths under `membership/` that you ran through the endpoint
- **Findings — dependency detection:** concrete example (input snippet + translated snippet); does the import shape survive? does cross-file consistency hold?
- **Findings — diagram creation:** same shape; method/struct/function counts before vs. after
- **Findings — code-smell detection:** the three smells you picked from the original, and whether each is still detectable in the translation (or whether the model "helpfully fixed" them)
- **Failure modes encountered + mitigations attempted:** what broke, what you tried, what worked / didn't
- **Recommendation:** keep / iterate / drop, with one paragraph of reasoning. The spec marks this approach as the "highest risk, highest ceiling" option — give a clear-eyed read on whether the available local model is up to the job, or whether this is gated on a stronger backend.

If your verdict is `not-viable`, you may stop after writing this file — the standard acceptance criteria above are waived. The verdict must include enough specific evidence (failing inputs, attempted mitigations) for a human reviewer to confirm the call.

Even if your verdict is `viable`, write the section anyway — the user wants a complete record across all three solutions.

## Out of scope

- **Do not** implement the pathology-anchor checker (CPG-equivalence validation) referenced in the spec. That is a separate concern — this endpoint sends, receives, returns. Validation is a future handoff.
- **Do not** implement streaming. Single-shot request/response only for the demo.
- **Do not** chunk large inputs across multiple LLM calls. If the input is too large for the configured context window, let the SDK return an error and surface it as a 500. A chunking strategy is a separate handoff.
- **Do not** add a token-counting layer or budget enforcement. Trust the upstream timeout/`max_tokens` to cap cost.
- **Do not** implement caching of LLM responses. Every request goes to the backend.
- **Do not** modify `app/main.py`, `app/contract.py`, `app/registry.py`, or any other solution file.

## Open questions

Flag rather than guess:

- The system prompt is intentionally strict ("output ONLY the translated code, no markdown fences"). If the chosen model habitually disobeys (qwen2.5-coder is a reasonable bet but not guaranteed), surface example failures rather than silently weakening the prompt.
- The deterministic per-level target picks the first item in each pool. If you want randomized variety later, that's an `options.seed` extension — not in this handoff.
- If `qwen2.5-coder:14b` produces low-quality translations on real inputs, that is empirical evidence to be reported, not a reason to switch the default model in this handoff. The configuration surface (env vars) is the entire point — the user will repoint at a stronger backend later.
- `LLM_TIMEOUT_SECONDS` defaults to 180. If real inputs need longer, surface the data; do not bump the default.
