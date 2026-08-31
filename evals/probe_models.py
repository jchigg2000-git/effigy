#!/usr/bin/env python3
"""Probe every model in the shipped catalog for reachability at the configured endpoint.

The UI offers a 32-model dropdown, selectable per request. None of those models
had any recorded evaluation, and a substantial fraction are not reachable at all
— so the dropdown promised capability the service could not deliver. This script
turns that into a dated, reproducible measurement.

It is a REACHABILITY probe, not a quality measurement: it asks each model for a
two-character reply and records whether a usable answer came back. Quality
ranking is run_models.py's job.

Results are POINT-IN-TIME facts about a third-party routing service. Provider
routing changes without notice, so every result file is stamped and nothing here
should be cited as current without a re-run.

    python3 evals/probe_models.py                    # probe the shipped catalog
    python3 evals/probe_models.py --from-endpoint    # probe what the router ACTUALLY serves
    python3 evals/probe_models.py --quiet            # exit code only

Reads LLM_BASE_URL / LLM_API_KEY from husk-api/.env. The API key is never
recorded — only the base-URL host.

**Prefer `--from-endpoint`.** The shipped catalog is a frozen local list and goes
stale silently: on 2026-08-19 it named 32 models while the router served 130, so a
catalog-sourced probe reported "13 usable" against an inventory nearly four times
larger and missed every frontier-class model on the endpoint. `--from-endpoint`
asks the router for `/models` and probes that, recording each model's live
provider count, maximum context length, and cheapest advertised price alongside
the reachability result. Catalog mode is retained only to reproduce older runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "husk-api" / "static" / "llm-translation-models.json"
RUNS = REPO / "evals" / "runs"

PROBE_PROMPT = "Reply with exactly: OK"
PROBE_MAX_TOKENS = 16

# Emitted by models that stream reasoning into the content channel. A husk
# containing these is corrupt, so they are recorded as a distinct failure class
# rather than lumped in with transport errors.
REASONING_MARKERS = ("<think>", "<PAD>", "Hmm,", "First, I", "The user")


def classify(text: str, finish_reason: str | None) -> str:
    t = (text or "").strip()
    if not t:
        # A reasoning model can spend this probe's whole 16-token budget on
        # reasoning tokens before emitting any content. That is an artifact of
        # the PROBE, not a property of the model -- real husk requests use 4096.
        # Distinguished from a genuinely empty response so nobody reads this
        # file as "the model returns nothing."
        return "budget-exhausted" if finish_reason == "length" else "empty"
    if any(m in t for m in REASONING_MARKERS):
        return "reasoning-leak"
    return "ok"


def fetch_served(base: str, key: str) -> list[dict]:
    """Ask the router which models it actually serves, with provider metadata.

    Returns one row per model id carrying the fields that decide whether a model
    is usable for a given job: how many providers are LIVE behind it (zero means
    the id is listed but unroutable), the largest context window any live
    provider offers, and the cheapest advertised input/output price. None of
    this is discoverable from the shipped catalog, which carries ids only.
    """
    req = urllib.request.Request(
        base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        payload = json.load(r)
    rows = []
    for m in payload.get("data", payload):
        live = [p for p in m.get("providers", []) if p.get("status") == "live"]
        prices = [p["pricing"] for p in live if p.get("pricing")]
        rows.append({
            "id": m["id"],
            "family": m.get("owned_by") or m["id"].split("/")[0],
            "live_providers": len(live),
            "max_context": max((p.get("context_length") or 0 for p in live), default=0),
            "price_in": min((x["input"] for x in prices), default=None),
            "price_out": min((x["output"] for x in prices), default=None),
        })
    return sorted(rows, key=lambda r: r["id"])


def probe(client_factory, model_id: str) -> dict:
    t0 = time.time()
    try:
        r = client_factory().chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            max_tokens=PROBE_MAX_TOKENS,
            temperature=0,
        )
        text = r.choices[0].message.content or ""
        finish = r.choices[0].finish_reason
        return {
            "model": model_id,
            "reachable": True,
            "status": classify(text, finish),
            "latency_s": round(time.time() - t0, 2),
            "served_model": getattr(r, "model", None),
            "finish_reason": finish,
            "sample": text.strip()[:60],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — a failure is the datum
        msg = str(exc)
        code = next((c for c in ("400", "401", "403", "404", "429", "503", "500")
                     if c in msg[:200]), "error")
        return {
            "model": model_id,
            "reachable": False,
            "status": f"http-{code}" if code != "error" else "error",
            "latency_s": round(time.time() - t0, 2),
            "served_model": None,
            "finish_reason": None,
            "sample": None,
            "error": msg[:200].replace("\n", " "),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--from-endpoint", action="store_true",
                    help="probe what the router serves now, not the frozen catalog")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    sys.path.insert(0, str(REPO / "husk-api"))
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(REPO / "husk-api" / ".env")
    from openai import OpenAI  # noqa: PLC0415

    base = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    key = os.environ.get("LLM_API_KEY", "ollama")
    if not key:
        print("no LLM_API_KEY set", file=sys.stderr)
        return 2

    if a.from_endpoint:
        served = fetch_served(base, key)
        ids = [m["id"] for m in served]
        source = "endpoint"
        meta = {m["id"]: m for m in served}
    else:
        catalog = json.loads(CATALOG.read_text())
        entries = catalog["models"] if isinstance(catalog, dict) and "models" in catalog else catalog
        ids = [m.get("id") or m.get("model") for m in entries]
        source = "catalog"
        meta = {}

    def factory():
        return OpenAI(base_url=base, api_key=key, timeout=60)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(lambda m: probe(factory, m), ids))
    for r in rows:
        r.update({k: v for k, v in meta.get(r["model"], {}).items() if k != "id"})

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    doc = {
        "probed_at": stamp,
        "endpoint_host": urlparse(base).netloc,  # host only, never the key
        "source": source,
        "catalog_size": len(ids),
        "note": (
            "Point-in-time reachability against a third-party routing service. "
            "Provider routing changes without notice; re-run before citing. "
            "source=endpoint means the id list came from the router's own /models; "
            "source=catalog means it came from the frozen local catalog, which has "
            "gone stale before and understated the served inventory by 98 models."
        ),
        "summary": {
            s: sum(1 for r in rows if r["status"] == s)
            for s in sorted({r["status"] for r in rows})
        },
        "results": sorted(rows, key=lambda r: (not r["reachable"], r["latency_s"])),
    }
    outdir = RUNS / f"{stamp}-model-probe"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "probe.json").write_text(json.dumps(doc, indent=2) + "\n")

    if not a.quiet:
        usable = [r for r in rows if r["status"] in ("ok", "budget-exhausted")]
        print(f"{len(usable)}/{len(ids)} are usable candidates at {doc['endpoint_host']}")
        print("(budget-exhausted = ran out of probe tokens on reasoning; retest at full budget)\n")
        for s, n in doc["summary"].items():
            print(f"  {s:16s} {n}")
        print(f"\n-> {outdir.relative_to(REPO)}/probe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
