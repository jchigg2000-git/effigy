#!/usr/bin/env python3
"""Build the curated model catalog for the llm-translation UI dropdown.

Queries the configured OpenAI-compatible endpoint's `/models` list (the HF
router serves ~120 models), then curates it down to a meaningfully-distinct
set:

  * keep only models with at least one `live` provider
  * drop anything we can't size, or that is > 120B parameters
  * drop non-chat / non-text variants (embeddings, rerank, vision,
    guard/safeguard, base (non-instruct) checkpoints)
  * de-duplicate "similar results": one representative per
    (vendor family x role x size-bucket), preferring instruct/coder tunes
    and the largest/most-served member of the group

Cost badge ($ / $$ / $$$ / $$$$):
  * primary: blended provider price = min over live providers of
    (input + output) / 2, in USD per 1M tokens
        $  <= 0.20   $$  <= 0.60   $$$  <= 1.50   $$$$  > 1.50
  * fallback (no provider exposes price): parameter scale
        $  <= 8B     $$  <= 34B     $$$  <= 80B    $$$$  81-120B

Output: static/llm-translation-models.json
        -> {"models":[{id,label,cost,params_b,price_per_mtok}]}
Run:    .venv/bin/python scripts/build_models_catalog.py
Env:    LLM_BASE_URL, LLM_API_KEY (reads husk-api/.env if python-dotenv present)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
MAX_PARAMS_B = 120.0

# Models whose id carries no parseable size. Approx total params (B).
KNOWN_SIZE = {
    "deepseek-ai/deepseek-r1": 671, "deepseek-ai/deepseek-v3": 671,
    "deepseek-ai/deepseek-v3.1": 671, "deepseek-ai/deepseek-v3.2-exp": 671,
    "moonshotai/kimi-k2-instruct": 1000, "zai-org/glm-4.6": 355,
    "zai-org/glm-4.5": 355, "zai-org/glm-4.5-air": 110, "zai-org/glm-4.5v": 106,
    "minimaxai/minimax-m2": 230, "openai/gpt-oss-120b": 120,
    "openai/gpt-oss-20b": 20, "openai/gpt-oss-safeguard-20b": 20,
}

# Substrings that mark a model as not a general text-chat translator.
EXCLUDE_SUBSTR = (
    "embed", "rerank", "guard", "safeguard", "whisper", "tts", "stt",
    "-vl", "-vision", "vlm", "ocr", "-base",
)

PRICE_TIERS = ((0.20, "$"), (0.60, "$$"), (1.50, "$$$"))   # else $$$$
PARAM_TIERS = ((8, "$"), (34, "$$"), (80, "$$$"))           # else $$$$


def parse_params_b(model_id: str) -> float | None:
    s = model_id.lower()
    if s in KNOWN_SIZE:
        return float(KNOWN_SIZE[s])
    m = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*b", s)  # MoE 8x7b
    if m:
        return float(m.group(1)) * float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*b[-_ ]a\d", s)  # active form 30b-a3b -> 30
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", s)  # generic NNb
    if m:
        return float(m.group(1))
    return None


def blended_price(providers: list[dict]) -> float | None:
    """Min over live providers of (input+output)/2, USD per 1M tokens."""
    prices = []
    for p in providers:
        if p.get("status") != "live":
            continue
        pr = p.get("pricing") or {}
        i, o = pr.get("input"), pr.get("output")
        if i is None or o is None:
            continue
        prices.append((float(i) + float(o)) / 2.0)
    return min(prices) if prices else None


def cost_tier(price: float | None, params_b: float) -> str:
    if price is not None:
        for ceil, tag in PRICE_TIERS:
            if price <= ceil:
                return tag
        return "$$$$"
    for ceil, tag in PARAM_TIERS:
        if params_b <= ceil:
            return tag
    return "$$$$"


def size_bucket(params_b: float) -> str:
    """Capability bucket for dedup ('similar results' axis), not cost."""
    if params_b <= 8:
        return "s"
    if params_b <= 34:
        return "m"
    if params_b <= 80:
        return "l"
    return "xl"


def role(model_id: str) -> str:
    s = model_id.lower()
    if "coder" in s or "code" in s:
        return "coder"
    if any(k in s for k in ("-r1", "reason", "thinking", "qwq")):
        return "reasoning"
    return "general"


def family(model_id: str) -> str:
    return model_id.split("/", 1)[0].lower()


def nice_label(model_id: str) -> str:
    return model_id.split("/", 1)[-1]


def fetch_models() -> list[dict]:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        sys.exit("LLM_BASE_URL / LLM_API_KEY not set (need husk-api/.env)")
    r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=60)
    r.raise_for_status()
    return r.json().get("data", [])


def curate(raw: list[dict]) -> list[dict]:
    def score(m: dict) -> tuple:
        s = m["id"].lower()
        instruct = any(k in s for k in ("instruct", "-it", "chat"))
        live = sum(1 for p in m.get("providers", []) if p.get("status") == "live")
        return (live, instruct, m["_params_b"], s)

    groups: dict[tuple, dict] = {}
    for m in raw:
        mid = m.get("id", "")
        s = mid.lower()
        live = sum(1 for p in m.get("providers", []) if p.get("status") == "live")
        if live < 1 or any(x in s for x in EXCLUDE_SUBSTR):
            continue
        if re.search(r"\d(?:\.\d+)?v\b", s):  # vision variants, e.g. glm-4.5v
            continue
        pb = parse_params_b(mid)
        if pb is None or pb > MAX_PARAMS_B:
            continue
        m["_params_b"] = pb
        key = (family(mid), role(mid), size_bucket(pb))
        if key not in groups or score(m) > score(groups[key]):
            groups[key] = m

    out = []
    for m in groups.values():
        pb = m["_params_b"]
        price = blended_price(m.get("providers", []))
        out.append({
            "id": m["id"],
            "label": nice_label(m["id"]),
            "cost": cost_tier(price, pb),
            "params_b": int(pb) if float(pb).is_integer() else pb,
            "price_per_mtok": round(price, 2) if price is not None else None,
        })
    order = {"$": 0, "$$": 1, "$$$": 2, "$$$$": 3}
    out.sort(key=lambda x: (order[x["cost"]], x["label"].lower()))
    return out


def main() -> None:
    raw = fetch_models()
    models = curate(raw)
    out_path = ROOT / "static" / "llm-translation-models.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({"models": models}, indent=2) + "\n", encoding="utf-8")
    print(f"{len(raw)} available -> {len(models)} curated  ->  {out_path}")
    for m in models:
        price = f"${m['price_per_mtok']}/M" if m["price_per_mtok"] is not None else "n/a"
        print(f"  {m['cost']:<4} {str(m['params_b'])+'B':>6}  {price:>9}  {m['label']}")


if __name__ == "__main__":
    main()
