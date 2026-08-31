# effigy

**Privacy-preserving code-husking for LLMs.** Transform (redact / re-domain)
private source code so an LLM can review its *architecture* while seeing as
little as possible of the secrets, PII, and domain the code actually belongs to
— then, where the transform is reversible, map the diagnosis back to the
original.

> **That is the goal, not a claim about the shipped code.** No single solution
> here achieves it: `fpe` destroys identifiers but passes every string literal
> and comment through verbatim; `literal-tagging` does the reverse. See
> [what each solution actually destroys](#what-each-solution-actually-destroys)
> and `LIMITATIONS.md` before relying on any of this.

## The idea

For organizations whose code is the product (fintech, healthcare, defense,
proprietary trading), the source cannot leave the tenant, and in-tenant models
lag the frontier. effigy's answer is to **husk** the code: preserve the
diagnostic and architectural *pathology* — god-objects, circular dependencies,
layering violations, duplicated error handling, hidden state machines — while
destroying the *content fingerprint* (identifier text, string literals, domain
prose). Because pathology is structural rather than lexical, a consumer LLM's
diagnosis of the husk stays valid for the source.
(See `docs/working-paper.md` §1.)

## Repo map

| Path | What it is |
|------|------------|
| **`husk-api/`** | **The product.** A Python 3.11+ / FastAPI service that runs the husking transforms. Everything else in this repo is either a test corpus or design/research material. |
| `corpus/` | **The test corpus** — code the husker runs *against*, not part of effigy's product. `corpus/stacks/` is a synthetic public-library inter-branch catalog and circulation app (Go 1.22 + chi + SQLite, React/Vite/TypeScript SPA) generated from its own `SPEC.md`. |
| `evals/` | The evaluation harness and its committed runs. Every empirical claim in this repo is sourced from `evals/runs/`. |
| `docs/` + root `*.md` | Design and research docs (working paper, algorithm catalog, handoffs, architecture diagrams). |

`corpus/stacks/` builds and tests (Go + vitest). The other five domains are **husking input, not
runnable services** — `corpus/DOMAINS.md` §5 gates them on parsing, not linking, so `go build` in
those trees is expected to fail. See `LIMITATIONS.md` §9.1.

The corpus exists so the husker has realistic, pathology-bearing code to
transform. Its nine deliberate architectural defects are catalogued in
`corpus/PATHOLOGY.md` by symbol anchor. `evals/run_eval.py --verify` re-hashes
every artifact against `evals/corpus/manifest.json`, so any edit to a corpus file
fails the gate; it separately checks that each PATHOLOGY symbol anchor still
resolves somewhere in the corpus. It is deliberately **not** an answer key: no comment names the
defect it sits beside, because reviewers read the labels instead of the code when
they do.

> **Provenance.** The corpus is synthetic and spec-first. `corpus/stacks/` was
> written from `corpus/stacks/SPEC.md` — a 969-line normative spec that fixes the
> module layout, symbol inventory, literal classes and all nine pathologies by
> anchor before a line of it existed. The spec is the contract and the tree was
> generated to satisfy it; `evals/run_eval.py --verify` re-checks that it still
> does. The other five domains in `corpus/` were built the same way against
> `corpus/DOMAINS.md`. No third-party or proprietary code is part of this
> repository. An earlier fixture pair that this corpus replaced was third-party-
> derived and is not published here; results measured against it are not carried
> forward — see the note at the top of `algorithmTests.md`.

## The three husking approaches (as implemented)

All three are registered plugins in `husk-api/app/solutions/`, addressed by slug:

| Slug | Approach | Design ref |
|------|----------|-----------|
| `fpe` | **Format-Preserving Encryption** — deterministic, length-preserving pseudonym for each identifier token; same token → same pseudonym (referential integrity), distinct tokens → distinct pseudonyms (injectivity). *Identifier tokens* are unrecoverable without the key; string literals and comments are **not** enciphered. | O1 |
| `literal-tagging` | **String-Literal Type-Class Tagging** — replaces each string literal with a typed placeholder (`<URL:n>`, `<PATH:n>`, `<MSG:n>`, …); repeated literals get repeated tags. | I3 |
| `llm-translation` | **LLM Domain Translation** — sends the code to an LLM that rewrites it into a *different* problem domain while preserving every architectural pathology. Backend is a configurable OpenAI-compatible endpoint (default: local Ollama). | I4 |

### What each solution actually destroys

Read this before assuming any of them is a complete husk. The two deterministic
solutions destroy exactly the half the other preserves, and they do **not**
compose in the shipped service — `POST /husk/{slug}` runs exactly one solution
and there is no pipeline.

| | Identifiers | String literals | Comments | Import paths | Structure |
|---|---|---|---|---|---|
| `fpe` | **destroyed** | preserved verbatim | preserved verbatim | preserved verbatim | preserved |
| `literal-tagging` | preserved verbatim | **destroyed** | preserved verbatim | destroyed (they are literals) | preserved |
| `llm-translation` | rewritten | rewritten | rewritten | rewritten | *intended* to be preserved; prompt-only, unverified |

Concretely: an `fpe` husk of Go source still contains its import paths, so the
organization and problem domain remain in plaintext. A `literal-tagging` husk
still contains every type and function name. Whether `llm-translation` removes
enough is exactly the open question — see `LIMITATIONS.md`.

**`crumb_level` (0–3) is a privacy knob** that drives `fpe` (which tokens are
spared vs. ciphered) and `literal-tagging` (placeholder granularity). The
`llm-translation` solution **ignores `crumb_level`** — it accepts the field for
contract uniformity but selects a *target domain* from a catalog instead
(via `options.target_id`, `options.target_domain`, or a deterministic default).

## Running husk-api

The service is **stateless** — no database, no auth, no persistence.

```sh
cd husk-api
uvicorn app.main:app --reload --port 8000
```

Endpoints:

| Method / path | Purpose |
|---------------|---------|
| `GET /health` | Liveness (`{"status":"ok"}`). |
| `GET /solutions` | List registered solutions (slug, name, description). |
| `POST /husk/{slug}` | Husk `input` with the named solution. Set `options.emit_map` on a reversible solution (`fpe`, `literal-tagging`) to also get back the pseudonym→original `reidentify_map`. |
| `POST /dehusk` | Re-identify an LLM's diagnosis of husked code — rewrite pseudonyms back to real identifiers/literals using a `reidentify_map`. Closes the round-trip. |
| `GET /docs` | FastAPI Swagger UI. |
| `GET /ui/` | Static browser UI (also served at `/`). |

Contract (`app/contract.py`):

- **`HuskRequest`** — `input` (string, ≤ 200,000 chars), `crumb_level`
  (int 0–3, default 1), `options` (dict).
- **`HuskResponse`** — `output`, `solution`, `crumb_level`, `meta` (per-solution
  stats).

Solutions are auto-discovered `@register`-decorated plugins in
`app/solutions/`; drop a new file in that directory to add one.

**Setup and config:** see `husk-api/README.md` for full install/run/test steps.
`llm-translation`'s `LLM_*` variables (base URL, model, key, timeout,
temperature, max tokens) are documented in `husk-api/.env.example`. The `fpe`
solution also reads `FPE_KEY` (32 hex chars) directly from the environment.
**Set it for any real use.** Without it the service generates a random key per
process: husks stay valid within one run, but pseudonyms change on restart and
a re-identification map from an earlier process will no longer dehusk. A
set-but-malformed `FPE_KEY` is an error rather than a silent fallback, and
`EFFIGY_ENV=production` refuses to start without one.

## Where to read next

- **`husk-algorithms.md`** — the algorithm design catalog (outer/inner layers,
  the O*/I* candidates). Self-labeled *"design work, not implementation
  guidance."*
- **`docs/draft-1.md`** — the complete preprint: threat model, the
  pathology-anchor invariant, and the preliminary empirical results. Start here
  for the research narrative.
- **`docs/working-paper.md`** — a two-section fragment (introduction and §4.2,
  the invariant) that predates the preprint. Superseded on its central claim;
  both carry a status note pointing at `LIMITATIONS.md`.
- **`docs/architecture/diagrams/*.mmd`** — context, components, and per-solution
  sequence diagrams (Mermaid).
- **`docs/handoffs/01`–`06`** — the build history, one handoff per component
  (buildout, fpe, literal-tagging, llm-translation, frontend, target catalog).
  These are *task briefs written to the agents that built each component*, kept
  as the per-component build record. They describe intent at the time of
  writing, not current behaviour — where they disagree with the code, the code
  wins.
- **`algorithmTests.md`** — the empirical record, every number sourced from a
  committed run under `evals/runs/`: husker selection, multi-file pathology
  detection, model scale, the prompt ratchet and its null result, and the
  post-condition gate. It also states what is **not** measured, which is the more
  important half.
- **`evals/preregistration.md`** — the adversarial re-identification experiment
  (RSCH-1), committed **before** it was run, with its pass/fail criteria fixed.

## Status — honest

effigy is a **feasibility study and design proposal, not a deployment-ready
system.** Do not read the running service as a hardened product, and do not
treat any privacy statement here as a result.

The seven things a reader should know before trusting anything in this repo:

1. **The core privacy claim was measured once, completely, and it fails.** The
   pre-registered experiment (RSCH-1) ran on 2026-08-19 against the six-domain
   corpus — 986 of 998 attacker calls, all three held-out domains, validity gate
   passed. **All four solutions fail its §8 criterion**, and all four
   independently trip its hard leak-term veto. `llm-translation` is the only
   transform doing any work — it roughly halves every leakage measure — and its
   husks are still identified **78.3%** of the time (65/83) by the strongest
   attacker, against a blind arm at 33.3%, cluster-bootstrap 95% CI on the
   difference **[+0.243, +0.640]**. Two qualifiers travel with that number and
   are not optional: it is recognition on a twelve-option menu, not recall, so
   quoting it alone overstates the leak; and the corpus is synthetic, so RSCH-1
   measures **problem-domain** leakage only and says nothing about whether a husk
   protects a real organization's identity. The 33.3% blind figure is the
   attacker's own answer bias, not a structural floor.
2. **The architecture itself leaks — the most consequential limitation here.**
   Strip every identifier, string literal, comment and JSX text node, leave only
   control flow, call graph, arity, nesting and coupling, and the same attackers
   still beat their own permuted baseline by **+0.234 / +0.244** (p = 0.0014 /
   0.0031) — and by **+0.257 / +0.265** (p = 0.0008 / 0.0023) once every numeric
   literal is canonicalised too, so this is *not* a "format constants" story that
   better literal-scrubbing would fix. That is roughly half the leak a husk
   carries. effigy's premise is that architectural pathology must be preserved;
   if preserved architecture is itself domain-informative, no verifier enforcing
   that invariant can fix it. Read it with its hedges: menu recognition only, the
   open-ended endpoint was never run, and **that run's own §8 validity gate is
   recorded as failed** — it carried no source or blind arm, so its verdicts are
   NOT COMPUTABLE and these are permuted-baseline figures, not §8 verdicts.
   Coverage 111 of 120.
3. **Nothing husks file paths.** RSCH-1 shows its attacker the bytes and the
   language and nothing else — no path, no filename, no directory layout —
   deliberately, and flatteringly to the husk. So no result here may be read as
   "the husk does not leak the source domain," only as its *contents*, at this
   corpus scale, with the path channel held out.
4. **No single solution is a complete husk.** `fpe` destroys identifiers and
   preserves every string literal; `literal-tagging` does the reverse; both
   preserve comments verbatim. `POST /husk/{slug}` runs exactly one solution, so
   they do not compose in the shipped service — the `composed` arm in the
   recorded results was chained by the eval harness, not by the API.
5. **The verifier does not exist.** The design's own method section calls it
   "the load-bearing piece" and calls prompt-only enforcement of the
   pathology-anchor invariant "a category error." Nothing computes CPG
   isomorphism, anti-pattern density, or comment speech acts. What ships is a
   narrower post-condition that fails closed when a husk comes back substantially
   as its own input — a floor, not the invariant.
6. **The evidence base is narrow, and scaling up made it worse.** Three scales of
   one model family (`qwen2.5-coder` at 7B, 14B and 32B) plus a single 8B Llama
   husk, none of them repeated measurements. The 32B returned **42%** of the
   caller's source verbatim where the 7B returned **15%**, so the 7B remains the
   recommendation. The `llm-translation` fidelity results rest on three single
   files; multi-file husking exists only as eval-side harnesses, never in the
   shipped API, which takes one string and returns one string.
7. **`llm-translation` output is not byte-stable**, so a husk cannot be
   reproduced on demand.

**→ [`LIMITATIONS.md`](LIMITATIONS.md) is the authoritative version**, including
a "what would falsify this" section and one claim that has **already been
falsified and fixed**. This summary is deliberately a strict subset of it; where
the two disagree, that file is correct and this one is stale.
