# Handoff 06 — Replace `crumb_level` with a flat target-domain catalog in `llm-translation`

## Goal

Reformulate target-domain selection in `husk-api/app/solutions/llm_translation.py` from a four-level "crumb" gradient into a flat, explicit catalog of target domains. This is the v2 design recommendation from `docs/draft-1.md` §6.3 and from the `qwen2.5-coder:14b` re-evaluation in `algorithmTests.md` ("Re-evaluation: qwen2.5-coder:14b"): on a capable backend the four levels do not produce a meaningful gradient — they collapse into "which target the deterministic picker happens to land on" — and §5.4 found a *privacy-leak inversion* where the levels designed for closer translation (L2/L3) leak source-domain structural identifiers (`package api`, `Server`, `corsMiddleware`) more than the levels designed for distant translation (L0/L1).

The user-visible change is small: `crumb_level` becomes a no-op for this one solution, and target selection moves to a flat catalog selectable by id (`options.target_id`), by free-text override (`options.target_domain`, already supported), or by deterministic mapping from the source content (the new default).

The contract-level `crumb_level` field stays in `app/contract.py` because the other two solutions (`fpe`, `literal-tagging`) still consume it. This handoff does not touch them.

## Context the agent needs

### What the empirical findings say

From `algorithmTests.md` ("Re-evaluation: qwen2.5-coder:14b"):

> All four crumb levels at 14B produce structurally-equivalent translations of the source — meaning a downstream code-smell or dependency analyzer would see roughly the same call graph regardless of level. The "very different (L0) → very similar (L3)" knob the spec describes does *not* manifest at 14B; the levels differ only in which target domain the deterministic picker lands on. If the goal is to *hide* the source domain (privacy / target-set obfuscation), L0 and L1 are the strongest cells: they translate the package name (`graphapi`, `chessapi`) and most identifiers. L2 and L3 retain source-domain identifiers (`package api`, `Server`, `corsMiddleware`) and so leak the original framing.

From `docs/draft-1.md` §6.3:

> **Reformulate the crumb-level taxonomy as a target-domain catalog.** §5.3 establishes that on capable models the four levels do not form a meaningful gradient. The taxonomy should be replaced with an explicit catalog of target domains, each chosen for distance from a defined set of source domains and for adversarial diversity. Users would select a target either explicitly or via deterministic mapping from the source. The "level" abstraction is a 7B-era artifact that the empirical results do not support.

This handoff implements that recommendation for the `llm-translation` solution only.

### What stays the same

- The `HuskRequest` contract in `app/contract.py` is unchanged. `crumb_level` continues to be accepted on the wire (range 0–3, default 1) because `fpe` and `literal-tagging` use it.
- `options.target_domain` (free-text override) keeps working exactly as it does today. It remains the highest-precedence selector.
- The system prompt (`_SYSTEM_PROMPT`) is unchanged. The prompt is independent of how the target is selected.
- All env vars (`LLM_*`) keep their meanings.
- The 502 path on `APIConnectionError` / `APITimeoutError` is unchanged.

### What changes

- `_TARGETS_BY_LEVEL` (dict keyed by 0/1/2/3) is replaced with `_TARGET_CATALOG`, a flat list of structured entries.
- `_pick_target(crumb_level, options)` is replaced with `_pick_target(input, options)`. The new precedence is: `options.target_domain` (free text) → `options.target_id` (catalog key) → deterministic `hash(input) % len(catalog)` mapping. `crumb_level` is no longer consulted by this solution.
- `meta` gains `target_id` (catalog key, or `null` if a free-text override was used) alongside the existing `target_domain` field.
- The frontend's "Crumb level" dropdown is decoupled from this solution: when `solution == "llm-translation"`, the crumb dropdown is hidden (or marked "ignored") and a "Target domain" picker is shown that lists catalog entries. The free-text override input keeps working.

### Where you write code

- **Modify:** `husk-api/app/solutions/llm_translation.py` — replace `_TARGETS_BY_LEVEL`, replace `_pick_target`, extend `meta`.
- **Modify:** `husk-api/tests/test_llm_translation.py` — drop the obsolete `test_crumb_levels_pick_different_pools`, add catalog-driven tests.
- **Add:** `GET /solutions/llm-translation/targets` route, or expose the catalog as a constant the frontend can fetch. Pick one — see Step 4.
- **Modify:** `husk-api/static/app.js` and `husk-api/static/index.html` — add a target picker that activates only for `llm-translation`.
- **Modify:** `husk-api/.env.example` — add a one-line note that `crumb_level` is ignored by `llm-translation`.
- **Append a short subsection** to `<repo-root>/algorithmTests.md` under the existing `## Solution: llm-translation` heading — see "Writing the result" below.
- **Do not modify** `app/main.py`, `app/contract.py`, `app/registry.py`, `app/solutions/fpe.py`, `app/solutions/literal_tagging.py`, or `_example.py`.
- **Do not modify** `docs/draft-1.md` or `docs/working-paper.md`. Those are the design record; this handoff is the implementation record.

## Implementation plan

### Step 1 — The catalog

Replace `_TARGETS_BY_LEVEL` in `app/solutions/llm_translation.py` with a flat catalog. Carry the existing entries forward; drop the vague L3 placeholder ("different sub-segment of the same domain"); keep the L2 entries even though §5.4 found they commit less to the target — they're still useful when a more natural-looking husk is wanted for human inspection (the §6.3 caveat).

```python
# Catalog of target domains. Selection is by id (options.target_id),
# by free-text override (options.target_domain), or by deterministic
# mapping from the source content (default).
#
# Order is significant for the deterministic default: entries earlier
# in the catalog are "stronger anonymizers" (per the 14B finding in
# algorithmTests.md and docs/draft-1.md §5.4) — they commit more
# thoroughly to the target domain and leak less source-domain framing.
# The deterministic default lands within this list with uniform
# probability; the ordering matters only when a human reads the
# catalog or when the UI presents a default-sorted list.
_TARGET_CATALOG: list[dict[str, str]] = [
    # Strong-anonymizing: abstract / generic targets (formerly L0)
    {"id": "graph-traversal",   "label": "Graph traversal",      "domain": "abstract graph traversal over labelled nodes"},
    {"id": "tensor-pipeline",   "label": "Tensor pipeline",      "domain": "a pure computation pipeline over numeric tensors"},
    {"id": "event-scheduler",   "label": "Event scheduler",      "domain": "a generic event-loop scheduler over opaque tasks"},

    # Strong-anonymizing: unrelated industry verticals (formerly L1)
    {"id": "chess-engine",      "label": "Chess engine",         "domain": "a chess engine with positions, moves, and evaluations"},
    {"id": "recipe-manager",    "label": "Recipe manager",       "domain": "a recipe-management app with ingredients, steps, and meal plans"},
    {"id": "wildlife-tracker",  "label": "Wildlife tracker",     "domain": "a wildlife tracking system with species, sightings, and migration routes"},

    # Weaker-anonymizing: adjacent verticals (formerly L2). Keep for
    # cases where a more natural-looking husk is wanted for human
    # inspection of the husk itself; the privacy-leak inversion in
    # docs/draft-1.md §5.4 says these leak source-domain framing more
    # than the strong-anonymizing entries above.
    {"id": "logistics-dispatch","label": "Logistics dispatch",   "domain": "a logistics dispatch system with shipments, routes, and carriers"},
    {"id": "music-streaming",   "label": "Music streaming",      "domain": "a music streaming service with tracks, playlists, and listeners"},
    {"id": "hotel-booking",     "label": "Hotel booking",        "domain": "a hotel booking platform with rooms, reservations, and guests"},
]

_CATALOG_BY_ID: dict[str, dict[str, str]] = {e["id"]: e for e in _TARGET_CATALOG}
```

The `id` field is the stable wire identifier. `label` is for the UI. `domain` is the prose dropped into the user prompt — the same shape the existing code already feeds to the model, so the prompt path is unchanged.

Do not add a "tier" or "commitment_strength" field. The §5.4 finding is sharp enough to record in a comment but too noisy to expose as a typed parameter; surfacing it as a tier invites a future agent to re-introduce a gradient and undo this handoff.

### Step 2 — Selection function

Replace `_pick_target`:

```python
import hashlib

def _pick_target(source: str, options: dict) -> tuple[str, str | None]:
    """Return (domain_prose, target_id_or_None).

    Precedence:
      1. options.target_domain — free-text override; target_id is None.
      2. options.target_id — catalog lookup; raises ValueError if unknown.
      3. Deterministic hash(source) % len(catalog).
    """
    if isinstance(options, dict):
        override = options.get("target_domain")
        if isinstance(override, str) and override.strip():
            return override.strip(), None

        target_id = options.get("target_id")
        if isinstance(target_id, str) and target_id.strip():
            entry = _CATALOG_BY_ID.get(target_id.strip())
            if entry is None:
                raise ValueError(f"unknown target_id: {target_id!r}")
            return entry["domain"], entry["id"]

    # Deterministic default: stable across reruns of identical source.
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "big") % len(_TARGET_CATALOG)
    entry = _TARGET_CATALOG[idx]
    return entry["domain"], entry["id"]
```

Notes:
- The deterministic mapping uses `sha256` rather than `hash()` because Python's built-in `hash` is salted per-process and would not be stable across server restarts.
- `ValueError` from an unknown `target_id` is caught by the FastAPI handler in `app/main.py` (the generic `except Exception`) and surfaces as a 500 with `{"error": "solution_failed", "detail": "unknown target_id: ..."}`. That's acceptable — it's a client error in shape but the existing host doesn't distinguish 4xx from 5xx for solution failures, and changing the host is out of scope for this handoff. Flag it as a future cleanup.

### Step 3 — Wire selection into `husk()` and update meta

In the `husk()` body, replace:

```python
target = _pick_target(crumb_level, options)
```

with:

```python
target_domain, target_id = _pick_target(input, options)
```

Then in the `meta` dict, replace:

```python
"target_domain": target,
```

with:

```python
"target_domain": target_domain,
"target_id": target_id,  # catalog id, or None when target_domain was a free-text override
```

The existing `target_domain` key in `meta` is preserved by name and meaning, so any caller (frontend, tests, the algorithmTests.md report) that already keys on it keeps working.

The `crumb_level` parameter to `husk()` continues to exist (the contract still passes it) but is no longer consulted. Do **not** silently delete the parameter from the function signature — it is part of the registered solution shape that `app/main.py` calls. Add a one-line `# unused — see handoff 06` comment next to the parameter or near the top of the function.

### Step 4 — Expose the catalog over HTTP

The frontend needs the catalog to populate a dropdown. Pick one of these two — the first is preferred:

**Option A (preferred): a dedicated route on the solution.** The host doesn't currently support per-solution custom routes; adding one requires touching `app/main.py`, which this handoff forbids. So instead, expose the catalog through the existing `GET /solutions` listing by enriching `SolutionInfo`. Skip — that touches the contract, also forbidden.

**Option B (chosen): a static endpoint under `/static/`.** Generate `husk-api/static/llm-translation-targets.json` at module import time from `_TARGET_CATALOG`, written to disk by `app/solutions/llm_translation.py` once at import:

```python
import json
from pathlib import Path

def _write_catalog_json() -> None:
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    path = static_dir / "llm-translation-targets.json"
    payload = {"targets": [{"id": e["id"], "label": e["label"]} for e in _TARGET_CATALOG]}
    path.write_text(json.dumps(payload, indent=2) + "\n")

_write_catalog_json()
```

The frontend fetches `/ui/llm-translation-targets.json` at page load (the static mount serves the file). This keeps the host untouched and the catalog is always in sync with code because the JSON is regenerated on every server start.

If you find a cleaner mechanism — for example, returning the catalog inside `meta` on a sentinel request, or shipping the catalog as a JS constant — flag it in the open-questions section rather than implementing a third option mid-handoff.

### Step 5 — Frontend changes (`static/app.js`, `static/index.html`)

Two small UI changes. Read both files first.

In `index.html`:
- Add a new control between the `Crumb level` block and the `Target domain` block:
  ```html
  <div class="ctrl ctrl-target-id">
    <label for="target-id">Target preset <span class="muted">(LLM only)</span></label>
    <select id="target-id" disabled>
      <option value="">— deterministic default —</option>
    </select>
  </div>
  ```
- Leave the existing `Crumb level` and free-text `Target domain` controls in place.

In `app.js`:
- Add `targetId: $("target-id")` to the `els` map.
- On page load, fetch `/ui/llm-translation-targets.json`, populate the `<select>` from `targets[]`.
- When the user changes the `Solution` dropdown:
  - If `slug == "llm-translation"`: enable the target-id dropdown, enable the free-text override input, and change the crumb dropdown's label to "Crumb level (ignored for this solution)" (or visually grey it out — pick the lighter touch).
  - Otherwise: disable target-id and free-text inputs (current behavior), restore the crumb label.
- When building the request body, include `options.target_id` if the dropdown has a non-empty value AND the free-text override is empty. The free-text override still wins on the backend; clarify in `placeholder` text that the free-text overrides the preset.

Do not remove the crumb dropdown. The other two solutions still need it. The dropdown's label change is the only signal that it doesn't apply to `llm-translation`.

### Step 6 — `.env.example` note

Append one line to the existing `# === Solution: llm-translation ===` block:

```
# Note: crumb_level is accepted on the wire for contract uniformity but is
# IGNORED by this solution. Target selection uses options.target_id (catalog)
# or options.target_domain (free-text override). See handoff 06.
```

### Step 7 — Tests

Edit `husk-api/tests/test_llm_translation.py`:

1. **Keep:** `test_registered`, `test_happy_path_returns_translated_code`, `test_strips_code_fences`, `test_backend_unavailable_returns_502`, `test_target_domain_override`. These are unchanged in spirit and should keep passing as-is — `target_domain` override precedence is preserved.
2. **Drop:** `test_crumb_levels_pick_different_pools`. The behavior it asserts (different levels pick different targets) is what this handoff explicitly removes.
3. **Add:**

```python
def test_target_id_selects_from_catalog():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_id": "chess-engine"},
        })
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["target_id"] == "chess-engine"
    assert "chess" in body["meta"]["target_domain"].lower()


def test_unknown_target_id_returns_500():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_id": "no-such-target"},
        })
    # The host wraps ValueError into a 500 solution_failed; see handoff 06
    # "Step 2 — Selection function" notes for why this is acceptable.
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    assert "no-such-target" in r.json()["detail"]


def test_deterministic_default_is_stable_across_runs():
    fake = _mock_completion("output")
    targets = []
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        for _ in range(3):
            r = client.post("/husk/llm-translation", json={
                "input": "the same input twice",
                "crumb_level": 1,
            })
            targets.append((r.json()["meta"]["target_id"], r.json()["meta"]["target_domain"]))
    assert len(set(targets)) == 1
    assert targets[0][0] is not None  # default selection populates target_id


def test_free_text_override_clears_target_id():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_domain": "a coffee-shop ordering system"},
        })
    body = r.json()
    assert body["meta"]["target_domain"] == "a coffee-shop ordering system"
    assert body["meta"]["target_id"] is None


def test_free_text_overrides_target_id_when_both_supplied():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {
                "target_id": "chess-engine",
                "target_domain": "a coffee-shop ordering system",
            },
        })
    body = r.json()
    assert body["meta"]["target_domain"] == "a coffee-shop ordering system"
    assert body["meta"]["target_id"] is None  # free-text wins, target_id discarded


def test_crumb_level_is_ignored_by_llm_translation():
    fake = _mock_completion("output")
    targets = []
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        for lvl in (0, 1, 2, 3):
            r = client.post("/husk/llm-translation", json={
                "input": "identical input",
                "crumb_level": lvl,
            })
            targets.append(r.json()["meta"]["target_id"])
    assert len(set(targets)) == 1  # all four levels produce the same default
```

The full test file should be 10 tests. Run `pytest -q` from `husk-api/` and confirm all pass under mocking, with no live LLM required.

### Step 8 — Smoke test against a real backend (optional, gated on Ollama)

If `qwen2.5-coder:14b` is pulled and Ollama is running, run two small smoke checks (do not write a full re-eval — that's not the point of this handoff):

```
# Default deterministic mapping, same input twice → same target
curl -s -X POST http://localhost:8765/husk/llm-translation \
  -H 'content-type: application/json' \
  -d '{"input":"package main\nfunc main(){}","crumb_level":1}' \
  | python3 -c 'import sys,json; m=json.load(sys.stdin)["meta"]; print(m["target_id"], "|", m["target_domain"])'

# Catalog selection
curl -s -X POST http://localhost:8765/husk/llm-translation \
  -H 'content-type: application/json' \
  -d '{"input":"x=1","crumb_level":1,"options":{"target_id":"chess-engine"}}' \
  | python3 -c 'import sys,json; m=json.load(sys.stdin)["meta"]; print(m["target_id"], "|", m["target_domain"])'
```

The first should print the same `target_id` on repeated runs. The second should print `chess-engine | a chess engine with positions, moves, and evaluations`.

If Ollama is not running, skip this step entirely — the unit tests cover the wiring.

## Acceptance criteria

1. `pytest tests/test_llm_translation.py` passes with 10 tests, no live LLM required.
2. Full suite still green (`pytest` from `husk-api/`).
3. `GET /ui/llm-translation-targets.json` returns the catalog as `{"targets": [{"id": ..., "label": ...}, ...]}` with at least 9 entries.
4. `POST /husk/llm-translation` with `options.target_id="chess-engine"` returns `meta.target_id == "chess-engine"` and `meta.target_domain` contains `"chess"`.
5. `POST /husk/llm-translation` twice with identical `input` and no `options` returns the same `meta.target_id` both times.
6. `POST /husk/llm-translation` with the same `input` at `crumb_level=0,1,2,3` returns the same `meta.target_id` for all four (the level is ignored).
7. `POST /husk/fpe` and `POST /husk/literal-tagging` continue to honor `crumb_level` — confirm by running their existing test files.
8. The frontend at `/ui/` shows the target-id dropdown only when the LLM solution is selected; the crumb dropdown is visually de-emphasized when the LLM solution is selected; the free-text override still works.
9. `algorithmTests.md` has a new subsection appended under `## Solution: llm-translation`, dated, recording that the catalog reformulation has shipped.

## Writing the result

Append a `### Handoff 06: target-domain catalog (replaces crumb_level for this solution)` subsection at the **end** of the existing `## Solution: llm-translation` section in `<repo-root>/algorithmTests.md`. **Do not rewrite the 7B section or the 14B re-evaluation section.** The new subsection should be short — under 200 words — and contain:

- One sentence stating that `crumb_level` is now ignored by `llm-translation` and target selection uses a flat catalog.
- The list of catalog ids that ship in this handoff.
- The selection precedence (free-text > target_id > deterministic).
- A pointer to this handoff for the rationale.

Do not re-litigate the §5.3 / §5.4 findings here. They live in `docs/draft-1.md` and the 14B re-evaluation; the algorithmTests.md entry is a record of the implementation change, not a new piece of the empirical record.

## Out of scope

- **Cache-key honesty.** `docs/draft-1.md` §6.3 also recommends the cache key be `(input_hash, model, temperature, target_domain, sampling_seed)`. That is a separate handoff. Do not add a `cache_key` field to `meta` here, and do not implement caching.
- **Verifier-enforced rewrite loop.** §4.3 describes a CPG-isomorphism + density + comment-distribution verifier with rejection feedback. Out of scope for this handoff and for the foreseeable future of this repo.
- **Rewriting the system prompt.** The §5.4 finding hints that the L2/L3-style "adjacent vertical" framing was what produced the leak; the prompt itself is unchanged in this handoff because target framing is now data (the catalog entry's `domain` prose), not a prompt-section selector.
- **Touching `fpe` or `literal-tagging`.** They use `crumb_level` in ways this handoff has not evaluated.
- **Changing the host contract** in `app/contract.py` to add a per-solution `options` schema. The current dict-typed `options` is sufficient for this handoff; a typed per-solution options schema is its own design problem.
- **Removing the `crumb_level` field from the wire protocol.** Other solutions still need it. A future handoff can revisit if `llm-translation` is the only solution that survives.
- **Pulling `:32b` or any other model.** The catalog reformulation is independent of model choice.

## Open questions to flag, not answer

- Should `target_id` show up in `meta` even when the user supplied a free-text override? This handoff sets it to `None` in that case (so the metadata cleanly distinguishes "catalog-driven" from "user-driven" runs). If a future agent prefers a denormalized "best-effort id match against the override string" they should propose it as a new handoff with explicit motivation, not change it under this one.
- Should the deterministic default also key on the model name and temperature, so that switching backends produces a different target? Today the answer is no — the same source maps to the same target regardless of backend, which is consistent with the goal of "the user sees stable behavior." But if cache-key honesty (§6.3) is implemented later, that handoff may want to revisit this.
- Should the catalog's "weaker-anonymizing" entries (`logistics-dispatch`, `music-streaming`, `hotel-booking`) be flagged in the JSON exposed to the frontend so a privacy-aware UI can sort or warn? This handoff does not flag them. If a future evaluation of the privacy-leak inversion produces a quantitative threshold, that's the time to add the flag.
- The host wraps a `ValueError` from `husk()` into a 500. A 4xx would be more accurate for an unknown `target_id`. Updating `app/main.py` to distinguish a `BadRequest` exception class is a small, separate cleanup.
