# Husk API

FastAPI service that "husks" source code through pluggable anonymization
solutions. Solutions self-register via a decorator, so adding one is a
drop-in file. A hand-authored static UI ships with the service.

## Setup

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pip install -e .

## Run

    uvicorn app.main:app --reload --port 8000

- API docs:  http://localhost:8000/docs
- Health:    http://localhost:8000/health
- UI:        http://localhost:8000/ui/

The UI is live as soon as uvicorn is running — there is no frontend build
step. `static/` (index.html, app.js, style.css) is hand-authored and mounted
directly via `StaticFiles` (`app/main.py`).

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

Responses: `200` with `{output, solution, crumb_level, meta, reidentify_map}`;
`404` `unknown_solution`; `502` `backend_unavailable` (e.g. LLM endpoint
unreachable); `500` `solution_failed`.

### Round-trip: `options.emit_map` + `POST /dehusk`

The reversible solutions (`fpe`, `literal-tagging`) can return the exact
pseudonym → original map they build internally, so an LLM's diagnosis of the
*husked* code can be rewritten back onto the real source — the reverse half of
the promise in the top-level README.

Set `options.emit_map: true` on a husk request and the response gains a
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
| `example`        | Passthrough Example                     | Reference template (`_example.py`); reverses the input. |

## Config (.env)

`husk-api/.env` is auto-loaded at startup (via python-dotenv, with
`override=False` so real platform env vars win). Copy `.env.example` to
`.env` and edit. All vars are optional; without them the solutions fall
back to the defaults below.

`llm-translation` — reads (`app/solutions/llm_translation.py`):

| Var                   | Default                      | Purpose |
| --------------------- | ---------------------------- | ------- |
| `LLM_BASE_URL`        | `http://localhost:11434/v1`  | OpenAI-compatible chat endpoint. |
| `LLM_MODEL`           | `qwen2.5-coder:14b`          | Model name (per-request override via `options.model`). |
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
the key. See `LIMITATIONS.md`.

## Test

    pytest

## Adding a solution

Drop a file into `app/solutions/` that uses `@register(...)` from
`app.registry`. It is auto-discovered at import (`app/solutions/__init__.py`)
and immediately available at `/husk/<slug>`. See `app/solutions/_example.py`
for the template.

## Scripts

### Post-condition gate

Eight variables tune the shipped fail-closed post-condition check — the only
mechanical enforcement in the service (there is no verifier; see
`LIMITATIONS.md` §5). Loosening them disables it.

| Variable | Default | Effect |
|---|---|---|
| `HUSK_CHECK_RUN_LINES` | `20` | A verbatim run this many lines long counts as copied |
| `HUSK_CHECK_RUN_SHARE` | `0.15` | ...or this share of the input's code lines |
| `HUSK_CHECK_COPIED_SHARE` | `0.35` | Total copied-span share that fails the husk |
| `HUSK_CHECK_RETENTION` | `0.92` | Identifier retention that fails the husk |
| `HUSK_CHECK_RATIO` | `0.95` | Whole-file similarity that fails the husk |
| `HUSK_CHECK_MIN_LINES` | `12` | Inputs shorter than this skip the gate entirely |
| `HUSK_CHECK_MODULE_NAMES` | `1` | `0` disables the input-module-name check |
| `HUSK_CHECK_RETRIES` | `1` | `llm-translation` only: retries before the gate raises |

- `scripts/build_models_catalog.py` — queries the configured
  OpenAI-compatible `/models` endpoint and curates it into
  `static/llm-translation-models.json`, which the UI's Model dropdown
  consumes (`static/app.js` `loadModels`, `static/index.html` `#model`).
  A selected model is sent per-request as `options.model`. Run:
  `.venv/bin/python scripts/build_models_catalog.py`.
