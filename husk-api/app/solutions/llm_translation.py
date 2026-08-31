"""I4 — LLM Domain Translation with Pathology Anchors.

Sends the input to an LLM with a system prompt instructing it to translate
the code into a different domain while preserving every architectural
pathology. Defaults to local Ollama running qwen2.5-coder:14b; configurable
via env vars to point at any OpenAI-compatible endpoint.

Target selection: see _TARGET_CATALOG below. crumb_level is accepted on the
wire for contract uniformity but is IGNORED by this solution — see handoff 06.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI, APIConnectionError, APITimeoutError, APIError

from app.registry import register
from app.solutions._husk_check import PassthroughDetected, check


# Load husk-api/.env into the process environment if present. The host app
# (app.main) does not call load_dotenv() and the handoff forbids touching host
# code, so this solution loads its own config here. override=False keeps real
# platform env vars (e.g. Railway) authoritative; a no-op when .env is absent.
# Without this, LLM_BASE_URL is unset and _make_client falls back to the local
# Ollama default (localhost:11434), which 502s when Ollama isn't running.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ModuleNotFoundError:
    pass


# Catalog of target domains. Selection is by id (options.target_id), by
# free-text override (options.target_domain), or by deterministic mapping
# from the source content (default).
#
# Order is significant for the deterministic default: entries earlier in
# the catalog are "stronger anonymizers" (per the 14B finding in
# algorithmTests.md and docs/draft-1.md §5.4) — they commit more
# thoroughly to the target domain and leak less source-domain framing.
# The deterministic default lands within this list with uniform
# probability; the ordering matters only when a human reads the catalog
# or when the UI presents a default-sorted list.
_TARGET_CATALOG: list[dict[str, str]] = [
    # Strong-anonymizing: abstract / generic targets (formerly L0)
    {"id": "graph-traversal",    "label": "Graph traversal",    "domain": "abstract graph traversal over labelled nodes"},
    {"id": "tensor-pipeline",    "label": "Tensor pipeline",    "domain": "a pure computation pipeline over numeric tensors"},
    {"id": "event-scheduler",    "label": "Event scheduler",    "domain": "a generic event-loop scheduler over opaque tasks"},

    # Strong-anonymizing: unrelated industry verticals (formerly L1)
    {"id": "chess-engine",       "label": "Chess engine",       "domain": "a chess engine with positions, moves, and evaluations"},
    {"id": "recipe-manager",     "label": "Recipe manager",     "domain": "a recipe-management app with ingredients, steps, and meal plans"},
    {"id": "wildlife-tracker",   "label": "Wildlife tracker",   "domain": "a wildlife tracking system with species, sightings, and migration routes"},

    # Weaker-anonymizing: adjacent verticals (formerly L2). Keep for cases
    # where a more natural-looking husk is wanted for human inspection of
    # the husk itself; the privacy-leak inversion in docs/draft-1.md §5.4
    # says these leak source-domain framing more than the strong-
    # anonymizing entries above.
    {"id": "logistics-dispatch", "label": "Logistics dispatch", "domain": "a logistics dispatch system with shipments, routes, and carriers"},
    {"id": "music-streaming",    "label": "Music streaming",    "domain": "a music streaming service with tracks, playlists, and listeners"},
    {"id": "hotel-booking",      "label": "Hotel booking",      "domain": "a hotel booking platform with rooms, reservations, and guests"},
]

_CATALOG_BY_ID: dict[str, dict[str, str]] = {e["id"]: e for e in _TARGET_CATALOG}


def _pick_target(source: str, options: dict) -> tuple[str, str | None]:
    """Return (domain_prose, target_id_or_None).

    Precedence:
      1. options.target_domain — free-text override; target_id is None.
      2. options.target_id — catalog lookup; raises ValueError if unknown.
      3. Deterministic sha256(source) mod len(catalog).
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

    digest = hashlib.sha256(source.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "big") % len(_TARGET_CATALOG)
    entry = _TARGET_CATALOG[idx]
    return entry["domain"], entry["id"]


def _write_catalog_json() -> None:
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    path = static_dir / "llm-translation-targets.json"
    payload = {"targets": [{"id": e["id"], "label": e["label"]} for e in _TARGET_CATALOG]}
    body = json.dumps(payload, indent=2) + "\n"
    # This file is git-TRACKED. Write only when the content actually changes, so
    # merely importing this module (a test run, `--help`, any tooling that loads
    # the solutions package) cannot dirty the working tree.
    if not path.exists() or path.read_text() != body:
        path.write_text(body)


_write_catalog_json()


# The prompt is measured, not decorative. Its previous form said "DO NOT: Refactor
# or improve the code in any way", which a strong instruction-follower reads as
# "do not change the text" — Qwen2.5-Coder-32B honoured it by translating the
# docstrings and returning the code body byte-identical (77% of code lines
# verbatim, one file changed by a single word). See
# evals/runs/20260819-husker-scale/RESULT.md. The rule that clause was reaching
# for is about STRUCTURE (keep the defects), so it now says so explicitly and
# separately from the rewrite requirement.
# PROVENANCE: this is the prompt evaluated as "v3" in
# evals/runs/20260819-prompt-fix-32b/ (RATCHET.md), with the few-shot example
# rewritten for publication: the input half moved off its original domain, and
# the output half's verb was renamed with it so the pair stays coherent
# (settle_booking -> issue_booking). Every INSTRUCTION, the ordering and the
# example's structure -- same lines, same FIXME position, same control flow --
# are unchanged. The text is 4793 bytes against the artifact's 4795.
# evals/runs/20260819-prompt-fix-32b/prompts/v3.txt is the byte-exact text the
# recorded numbers were produced with and is deliberately NOT updated to match
# this file. No recorded number was re-measured after this change.
_SYSTEM_PROMPT = """You are a code husker. You rewrite source code into a DIFFERENT problem domain so that it can be analysed without revealing what the original code was about.

A husk is a REWRITE, not an edit. Every name and every piece of prose in the input belongs to the source domain, so all of it has to be replaced with vocabulary from the target domain. Returning the input unchanged, or changing only its comments and docstrings, is the single worst answer you can give: the caller believes they received a husk, and what they actually received is their own source code.

RENAME EVERYTHING. There are no "generic enough to keep" identifiers:
- Every module, package, class, function, method, variable, parameter, field and constant name
- Every string literal — format strings, log lines, error messages, dict keys, enum values
- Every comment and every docstring: rewritten into the target domain, never deleted, never left alone
- Every URL, file path, file name, table or column name, ticket/PR/issue reference, proper noun, date-stamped note

Three kinds of content are missed most often, so they are called out:
- ACRONYMS AND ABBREVIATIONS are domain names, in identifiers, in string literals, in SQL, and in comments. Replace each one with an invented target-domain acronym, and use the same replacement everywhere it appears.
- DATA LITERALS ARE CONTENT. Company names, people, places, product names, codes, account numbers and IDs sitting inside lists, dicts, constants or fixtures are the most identifying text in the file. Invent target-domain replacements. Real-looking names surviving in your output is an outright failure, not a detail.
- DATABASE TABLE AND COLUMN NAMES, JSON keys, enum values, log event names, CLI flags and config keys are identifiers like any other. Rename them, and keep every SQL statement consistent with the names you chose.

The ONLY names that survive unchanged are the ones the language owns: keywords, builtins, standard-library symbols, and public third-party package APIs (`json.dumps`, `http.StatusOK`, `pd.DataFrame`, `logging.Logger`). Never invent a replacement for one of those — a renamed standard-library symbol is a broken husk, not a private one. Imports of the input's OWN modules ARE renamed, consistently with the names you gave those things.

KEEP THE SHAPE EXACTLY. The husk must have the same architecture — and the same problems — as the input:
- Control flow shape (every if/else/for/while/try in the same place)
- Function and method count, parameter count, and arity
- Class hierarchy and module structure
- Coupling and call relationships (if A calls B in the input, A' calls B' in the output)
- Dead code (if the input has unused functions, the output has unused functions)
- God-objects (if a class has 40 methods in the input, its translation has 40 methods)
- Cycles in dependencies (if A imports B and B imports A, preserve that)
- Comment POSITION and SPEECH ACT (a TODO stays a TODO in the same place, a FIXME stays a FIXME, a prescriptive rule stays a prescriptive rule) — only the wording moves domain
- Naming morphology — long names stay long, abbreviations stay abbreviated, hungarian-prefix density is preserved
- The language and syntax style of the input
- Length. If the input is 300 lines, the output is about 300 lines. Never summarise a body into a comment, a `pass`, or a TODO stub.

DO NOT IMPROVE ANYTHING. The defects in the input are the object of study:
- Do not fix bugs, remove duplication, simplify long functions, split god classes, tidy dead code, or make names clearer than their originals
- Do not add commentary about what you changed

"Do not improve" constrains STRUCTURE ONLY. It is not a licence to leave code as you found it: the body must be rewritten word for word into the target domain.

OUTPUT FORMAT:
Return ONLY the rewritten source code. No preamble, no explanation, no markdown fences. The first character of your response is the first character of the husk.

EXAMPLE of the required intensity (target domain: hotel booking):

    input:   def issue_permit(permit_id: str, lot_ref: str) -> Decision:
                 # FIXME: lot 0042 rejects zero-hour permits
                 if not permit_id.startswith("PRM"):
                     raise ValueError(f"bad permit id {permit_id}")

    output:  def issue_booking(booking_id: str, hotel_ref: str) -> Outcome:
                 # FIXME: hotel 0042 rejects zero-night bookings
                 if not booking_id.startswith("BKG"):
                     raise ValueError(f"bad booking id {booking_id}")

Same lines, same FIXME in the same position, same control flow, same length — and not one word of the input's domain left in it.

Before you answer, reread your output for words belonging to the input's domain. If you find any, replace them."""


def _user_prompt(target: str, code: str) -> str:
    return (
        f"Target domain: {target}\n\n"
        "Rewrite the source below into that domain. Every identifier, string, comment and "
        "docstring becomes target-domain vocabulary; the structure, the defects and the "
        "length stay as they are. Code left byte-identical to the input is a failed husk.\n\n"
        f"{code}"
    )


def _make_client() -> OpenAI:
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("LLM_API_KEY", "ollama")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def _complete(client, model: str, messages: list, temperature: float,
              max_tokens: int) -> tuple[str, object]:
    """One completion, checked for liveness only. Split out of husk() so the
    post-condition retry does not duplicate any of it."""
    # Deferred import to avoid a circular import at module-load time:
    # app.main imports app.solutions (which imports this module).
    from app.main import BackendUnavailable

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (APIConnectionError, APITimeoutError) as e:
        raise BackendUnavailable(
            f"LLM backend unreachable at {os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')}: {e}"
        ) from e
    except APIError as e:
        # Other API errors — let the host turn them into 500s. Surface the
        # real upstream status code when present (APIStatusError subclasses
        # carry .status_code) so it isn't swallowed by the generic message.
        status = getattr(e, "status_code", None)
        prefix = f"LLM API error (status {status})" if status is not None else "LLM API error"
        raise RuntimeError(f"{prefix}: {e}") from e

    # Some OpenAI-compatible backends return an empty choices list on certain error/moderation
    # conditions; surface it explicitly rather than letting resp.choices[0] raise a bare IndexError.
    if not resp.choices:
        raise RuntimeError(f"LLM returned no choices (model={model})")
    choice = resp.choices[0]

    # Truncation: the OpenAI-compatible API returns finish_reason == "length"
    # when the response hit max_tokens. Swallowing this surfaces downstream as
    # a confusing parse/empty-result failure, so make it explicit. The caller
    # (/husk) expects a complete husk and does not tolerate truncation.
    if getattr(choice, "finish_reason", None) == "length":
        raise RuntimeError(
            f"LLM response truncated at max_tokens (LLM_MAX_TOKENS={max_tokens}); "
            "raise LLM_MAX_TOKENS or shorten input"
        )

    raw_content = choice.message.content

    # Empty/None content is not a successful husk — returning "" downstream
    # looks like success. Surface it explicitly instead.
    if raw_content is None or not raw_content.strip():
        raise RuntimeError(
            f"LLM returned empty content (model={model}, "
            f"finish_reason={getattr(choice, 'finish_reason', None)!r})"
        )

    return _strip_code_fence(raw_content.strip()), getattr(resp, "usage", None)


def _infer_suffix(code: str) -> str:
    """Guess the comment/string syntax family. Only three answers matter to the
    post-condition: hash comments, slash comments, or triple-quoted blocks."""
    head = code[:4000]
    if "package " in head and "func " in head:
        return ".go"
    if any(t in head for t in ("=> ", "const ", "interface ", "export ", "function ")) \
            and "def " not in head:
        return ".ts"
    return ".py"


# What a retry says to the model. Naming the copied span is the whole point:
# "try again" on a stochastic transform is a coin flip, whereas the model can
# act on "you copied 36 consecutive lines".
_RETRY_NUDGE = (
    "Your previous attempt was rejected: {reason}. That is the one outcome that "
    "makes a husk worthless — the caller gets their own source back. Produce the "
    "husk again, and rewrite EVERY line of the region you copied. Same structure, "
    "same defects, same length; different words."
)


@register(
    slug="llm-translation",
    name="LLM Domain Translation (I4)",
    description="Translates the input into a different domain while preserving pathology. Backend: configurable OpenAI-compatible.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    # crumb_level is unused — see handoff 06. Target selection is from
    # options.target_domain / options.target_id / deterministic default.
    del crumb_level

    target_domain, target_id = _pick_target(input, options)
    # Per-request model override (UI model dropdown sends options.model);
    # falls back to the server's LLM_MODEL env default when unset.
    _model_override = options.get("model") if isinstance(options, dict) else None
    model = (
        _model_override.strip()
        if isinstance(_model_override, str) and _model_override.strip()
        else os.environ.get("LLM_MODEL", "qwen2.5-coder:14b")
    )
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
    retries = max(0, int(os.environ.get("HUSK_CHECK_RETRIES", "1")))
    # The wire contract is a bare string with no filename, so the comment syntax
    # has to be inferred or the post-condition strips prose with the wrong rules
    # on Go/TS input. options.suffix overrides when the caller knows.
    suffix = (options.get("suffix") if isinstance(options, dict) else None) or _infer_suffix(input)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(target_domain, input)},
    ]

    client = _make_client()
    attempts: list[dict] = []
    try:
        for attempt in range(retries + 1):
            output_text, usage = _complete(
                client, model, messages,
                # Nudge temperature on retry: repeating a sampling that just
                # produced a copy, at the same temperature, mostly reproduces it.
                temperature if attempt == 0 else min(temperature + 0.3, 1.0),
                max_tokens,
            )
            try:
                report = check(input, output_text, suffix)
            except PassthroughDetected as e:
                reasons = e.report.get("reasons") or [str(e)]
                attempts.append({"attempt": attempt + 1, "rejected": str(e),
                                 "reasons": reasons})
                if attempt == retries:
                    # Fail closed. The alternative is handing back source code
                    # labelled as a husk, which the caller cannot detect.
                    raise
                messages = messages + [
                    {"role": "assistant", "content": output_text},
                    {"role": "user", "content": _RETRY_NUDGE.format(
                        reason="; ".join(reasons))},
                ]
                continue
            break
    finally:
        # A fresh OpenAI client is built per request and owns an httpx connection pool; close it
        # (responses are fully materialized for these non-streaming calls) so we don't leak fds.
        client.close()

    meta: dict[str, Any] = {
        "model": model,
        "base_url": os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
        "target_domain": target_domain,
        "target_id": target_id,
        "temperature": temperature,
        # The caller cannot compare the husk to their own input the way this
        # service just did, so the evidence travels with the response.
        "postcondition": report,
    }
    if attempts:
        meta["postcondition_retries"] = attempts
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
    first_nl = s.find("\n")
    if first_nl == -1:
        return s
    body = s[first_nl + 1 :]
    if body.endswith("```"):
        body = body[:-3]
    return body.rstrip()
