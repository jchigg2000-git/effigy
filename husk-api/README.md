# Husk API

FastAPI service that "husks" source code through pluggable anonymization
solutions. Solutions self-register via a decorator, so adding one is a
drop-in file. A hand-authored static UI ships with the service.

## Setup

    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[test]"

Runtime dependencies live in `pyproject.toml`; `requirements.txt` is the same
install spelled for `pip install -r`.

## Run

    uvicorn app.main:app --reload --port 8000

- API docs:  http://localhost:8000/docs
- Health:    http://localhost:8000/health
- UI:        http://localhost:8000/ui/

The UI is live as soon as uvicorn is running — there is no frontend build
step. `static/` (index.html, app.js, style.css) is hand-authored and mounted
directly via `StaticFiles` (`app/main.py`), and only if the directory exists.
A built wheel carries the same files as `app/static`.

Importing the app writes nothing to disk, so it starts on a read-only
filesystem. `static/llm-translation-targets.json` is committed rather than
regenerated at import; after editing the target catalog, regenerate it with

    .venv/bin/python -c 'from app.solutions.llm_translation import _write_catalog_json as w; w()'

and `tests/test_service_hardening.py` fails if the file drifts from the catalog.

## API

| Method | Path            | Purpose |
| ------ | --------------- | ------- |
| GET    | `/`             | 307 redirect to `/ui/` |
| GET    | `/ui/`          | Static single-page UI |
| GET    | `/health`       | `{"status": "ok"}` |
| GET    | `/solutions`    | List registered solutions (`slug`, `name`, `description`) |
| POST   | `/husk/{slug}`  | Run one solution over the request body |
| POST   | `/dehusk`       | Reverse a diagnosis of husked code back to real identifiers |
| GET    | `/docs`         | Auto-generated OpenAPI docs |

`POST /husk/{slug}` request body:

    {
      "input":       "<source to husk>",   // required, max 200,000 chars
      "crumb_level": 1,                     // 0–3, default 1
      "options":     {}                     // solution-specific, optional
    }

Responses:

| Status | `error` | When |
| ------ | ------- | ---- |
| `200` | — | `{output, solution, crumb_level, meta, reidentify_map}` |
| `404` | `unknown_solution` | No solution registered under that slug |
| `502` | `backend_unavailable` | LLM endpoint unreachable or timed out, or it returned 408 or 5xx |
| `503` | `backend_rate_limited` | LLM endpoint returned 429 |
| `500` | `solution_failed` | Anything else: a post-condition refusal, a truncated or empty response, commentary outside a single fenced husk, or another upstream status (a 403 spending cap, 400, 401) |

The OpenAI client retries timeouts, 408, 429 and 5xx twice on its own before
any of these, so a hung backend costs up to 3 × `LLM_TIMEOUT_SECONDS` (540 s
at the default) before the `502`. Before 2026-09-26 an upstream 429 or 5xx
came back as the service's own `500`.

### Round-trip: `options.emit_map` + `POST /dehusk`

The reversible solutions (`fpe`, `literal-tagging`) can return the exact
pseudonym → original map they build internally, so an LLM's diagnosis of the
*husked* code can be rewritten back onto the real source — the reverse half of
the promise in the top-level README.

Set `options.emit_map: true` (the JSON boolean; any other value, the string
`"true"` included, leaves it off) on a husk request and the response gains a
top-level `reidentify_map` (a `{pseudonym: original}` object; `null` when not
requested or when the solution can't reverse, e.g. `llm-translation`):

    POST /husk/fpe
    { "input": "...", "crumb_level": 1, "options": {"emit_map": true} }
    → { "output": "...", "reidentify_map": {"D7AOUPo2k4QD4GxxUl": "get_customer_email", ...}, ... }

Feed a diagnosis and that map to `POST /dehusk` to re-identify it:

    POST /dehusk
    { "input": "<LLM diagnosis referencing pseudonyms>", "map": {<reidentify_map>} }
    → { "output": "<diagnosis with real identifiers>", "substitutions": 2, "meta": {...} }

Substitution is longest-match-first, and identifier-shaped pseudonyms are only
rewritten at token boundaries so they don't collide with substrings of larger
words in the prose (`app/dehusk.py`). The UI does the same substitution
client-side in its **Dehusk a diagnosis** panel.

**The map is sensitive** — it re-identifies your source. It is strictly
opt-in, returned only when you ask for it, and the (stateless) service never
logs or persists it. The UI keeps the map in the browser tab and never sends
it back.

## Solutions

Registered solutions (see `GET /solutions` for the live list):

| Slug             | Name                                    | Notes |
| ---------------- | --------------------------------------- | ----- |
| `fpe`            | Format-Preserving Encryption (O1)       | Deterministic, length-preserving identifier rewrite. |
| `literal-tagging`| String-Literal Type-Class Tagging (I3)  | Replaces each string literal with a typed placeholder. |
| `llm-translation`| LLM Domain Translation (I4)             | Translates the code into another domain, preserving pathology. Needs an LLM backend — see Config. |
| `example`        | Passthrough Example                     | **Test-only, off by default.** Reference template (`_example.py`); reverses the input. Registered only when `HUSK_ENABLE_EXAMPLE=1` is in the process environment. |

`example` is off by default because a reversed string is a trivially
reversible "husk" and has no place on the public API. Setting
`HUSK_ENABLE_EXAMPLE=1` in `husk-api/.env` has no effect: `_example.py` is
imported before `llm-translation` loads `.env`. `tests/conftest.py` sets it
before importing the app, so the contract tests still drive the registry
through it.

What each solution adds to `meta`, beyond its counts:

- `fpe` — `pseudonym_collisions` counts two identifiers that would share a
  pseudonym, and since 2026-09-26 also a crumb-3 pseudonym equal to a token
  left in plain text; with `options.emit_map` either one is refused.
  `non_ascii_identifiers` counts distinct non-ASCII identifiers enciphered
  (always present, 0 for ASCII input). Some pseudonyms changed on 2026-09-26,
  so a map saved earlier under the same `FPE_KEY` goes stale for those tokens
  ([LIMITATIONS.md](../LIMITATIONS.md) §6).
  The expressions inside a Python f-string's or t-string's replacement fields
  (`f"{order.total!r:>{width}}"`) are code and are enciphered, as `${...}` in
  a backtick literal is; the literal text, conversion and format-spec text
  around them stay verbatim. `options.language` (as `literal-tagging` takes
  it, plus `python`/`py` and `go`/`golang`) picks the language's comment
  syntax: under `python` a `//` is floor division, not a comment; under a
  JS/TS name a `#` is code (`#private` fields) apart from a leading `#!`
  line, and a nested template literal stays one literal; under `go` a
  backtick raw string passes through verbatim, `${...}` included. Any other
  value, or none, keeps the language-blind rules, where both `//` and `#`
  start a comment. `meta.lexer` names the rules used (`default`, `python`,
  `js` or `go`).
- `literal-tagging` — set `options.language` to `js`, `jsx`, `ts`, `tsx`,
  `javascript` or `typescript` to have a nested template literal tagged as one
  literal. Without it the first inner backtick ends the literal, as before,
  because a Go raw string containing `${` would otherwise swallow the code
  after it.
- `llm-translation` — `meta.postcondition` is the gate's full report, now
  with `retries_allowed`. `meta.usage` is summed over every post-condition
  attempt, with `reasoning_tokens`, and `meta.usage_attempts` lists each
  attempt; both appear only when the backend reported usage. When the model
  wrapped the husk in a fence with commentary around it, the commentary is
  dropped and counted in `meta.discarded_outside_fence_chars`; any other
  layout of fences is refused (`500`). Above 30,000 characters the gate skips
  the exact similarity ratio when a cheap upper bound shows it cannot reach
  `HUSK_CHECK_RATIO`, and reports `similarity_ratio: null` with
  `similarity_ratio_upper_bound`; the verdict is the same either way.

## Config (.env)

`husk-api/.env` is auto-loaded at startup (via python-dotenv, with
`override=False` so real platform env vars win). Copy `.env.example` to
`.env` and edit. All vars are optional; without them the solutions fall
back to the defaults below.

`llm-translation` — reads (`app/solutions/llm_translation.py`):

| Var                   | Default                      | Purpose |
| --------------------- | ---------------------------- | ------- |
| `LLM_BASE_URL`        | `http://localhost:11434/v1`  | OpenAI-compatible chat endpoint. |
| `LLM_MODEL`           | `qwen2.5-coder:14b`          | Model name (per-request override via `options.model`). The default is the model the service was first built against; the recorded evidence favours the 7B — see the root `README.md`, *Status* item 6. |
| `LLM_API_KEY`         | `ollama`                     | API key. This is the only token var — there is **no** separate `HF_TOKEN`. |
| `LLM_TIMEOUT_SECONDS` | `180`                        | Request timeout. |
| `LLM_TEMPERATURE`     | `0.2`                        | Sampling temperature. |
| `LLM_MAX_TOKENS`      | `4096`                       | Max output tokens. |

With no config, `llm-translation` defaults to a local Ollama instance
(`localhost:11434`) and returns **502** if Ollama isn't running. Point
`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` at any OpenAI-compatible endpoint
(HF Inference, OpenAI, vLLM) to use a remote model.

`fpe` — reads:

| Var | Default | Purpose |
| --- | ------- | ------- |
| `FPE_KEY` | *(none — random per process)* | Hex-encoded key, must decode to **≥16 bytes** (first 16 used). **Set this for any real use.** |
| `FPE_DEMO_KEY` | unset | If truthy, encipher under the **public, source-baked** demo key. Output is trivially reversible by anyone with this source. Exists only so previously-recorded evaluation outputs stay reproducible. |
| `EFFIGY_ENV` | unset | If `production`, `fpe` refuses to run without `FPE_KEY`. |
| `FPE_ALLOW_EPHEMERAL_KEY` | unset | Overrides the above production check. |

Generate a key with:

    python3 -c 'import secrets; print(secrets.token_hex(16))'

**Behaviour when `FPE_KEY` is absent or bad:**

- **Absent** — a random key is generated per process and a warning is logged.
  Husks are valid within one run, but pseudonyms change on restart, so a
  re-identification map from an earlier process will no longer dehusk.
- **Set but malformed** (bad hex, or under 16 bytes) — **raises**. It does not
  fall back. An operator who believes they configured a key while the service
  enciphers under a published one is worse off than one who gets an error.

**What the key does and does not protect:** it protects *identifier tokens*
only. String literals and comments are passed through verbatim by design, so
import paths, URLs, SQL and error messages survive into the husk regardless of
the key. See [LIMITATIONS.md](../LIMITATIONS.md).

### Post-condition gate (`llm-translation` only)

Eight variables tune the fail-closed post-condition check that `llm-translation`
runs on its own output — the only mechanical enforcement in the service (there
is no verifier; see [LIMITATIONS.md §5](../LIMITATIONS.md#5-there-is-no-verifier)).
`fpe` and `literal-tagging` are deterministic transforms and have no gate.
Loosening these disables it.

| Variable | Default | Effect |
|---|---|---|
| `HUSK_CHECK_RUN_LINES` | `20` | A verbatim run this many lines long counts as copied |
| `HUSK_CHECK_RUN_SHARE` | `0.15` | ...or this share of the input's code lines |
| `HUSK_CHECK_COPIED_SHARE` | `0.35` | Total copied-span share that fails the husk |
| `HUSK_CHECK_RETENTION` | `0.92` | Identifier retention that fails the husk |
| `HUSK_CHECK_RATIO` | `0.95` | Whole-file similarity, or share of output code lines found verbatim in the input, that fails the husk (either one, together with `RETENTION`) |
| `HUSK_CHECK_MIN_LINES` | `12` | Inputs with fewer *code* lines than this (comments and docstrings not counted) are never failed by the similarity triggers; the module-name check still runs |
| `HUSK_CHECK_MODULE_NAMES` | `1` | `0` disables the input-module-name check |
| `HUSK_CHECK_RETRIES` | `1` | Retries before the gate raises |

Two things the gate does not see, both open
([LIMITATIONS.md](../LIMITATIONS.md) §5): a comment or docstring copied word
for word, because every line measure runs on code with prose stripped; and an
input under `HUSK_CHECK_MIN_LINES` code lines, which can come back
byte-identical with a `200`. The module-name check reads Go import paths: bare
module names, and the org and repo segments of a host-prefixed path when an
import has an `internal/` segment. It applies Go rules whenever the input has a
`package` clause, whatever `options.suffix` says. `options.suffix` may be
given with or without the dot, in any case (`ts`, `.TS`).

Other variables:

| Variable | Default | Effect |
|---|---|---|
| `HUSK_ENABLE_EXAMPLE` | unset | `1` registers the test-only `example` solution. Read from the process environment only; `.env` is loaded too late. |

## Test

    pytest

100 tests, offline: model clients are mocked, and `tests/conftest.py` strips
every `HUSK_CHECK_*` and `LLM_*` variable, plus `FPE_KEY`, `FPE_DEMO_KEY`,
`FPE_ALLOW_EPHEMERAL_KEY` and `EFFIGY_ENV`, that a local `.env` would set, so
the suite runs against the documented defaults.
By file: `test_llm_translation.py` 27, `test_fpe.py` 21, `test_dehusk.py` 18,
`test_literal_tagging.py` 17, `test_service_hardening.py` 11,
`test_contract.py` 6.

## Adding a solution

Drop a file into `app/solutions/` that uses `@register(...)` from
`app.registry`. It is auto-discovered at import (`app/solutions/__init__.py`)
and immediately available at `/husk/<slug>`. See `app/solutions/_example.py`
for the template (a real solution applies `@register` unconditionally). A new
*subpackage* of `app`, as opposed to a new file, must also be added to the
explicit `packages` list in `pyproject.toml`, or a built wheel will leave it out.

## Scripts

- `scripts/build_models_catalog.py` — queries the configured
  OpenAI-compatible `/models` endpoint and curates it into
  `static/llm-translation-models.json`, which the UI's Model dropdown
  consumes (`static/app.js` `loadModels`, `static/index.html` `#model`).
  A selected model is sent per-request as `options.model`. Run:
  `.venv/bin/python scripts/build_models_catalog.py`.
