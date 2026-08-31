# Handoff 01 — API Buildout & Endpoint Contract

## Goal

Stand up a Python FastAPI service that hosts three "husk" transformation endpoints behind a uniform contract. You are building the scaffolding only — the three transformation algorithms are implemented in separate handoffs (02, 03, 04) by other agents. Your job is to make it possible for those agents to drop a single file into `app/solutions/` and have it auto-register as a new endpoint without touching shared code.

This service is the API layer of a "code husking" tool. Its job is to take source code as input and return a transformed, privacy-preserved version. Each endpoint implements a different transformation algorithm; the frontend (handoff 05) lets a user pick one and compare results.

## Stack

- **Python 3.11+**
- **FastAPI** — sync request/response, automatic OpenAPI docs
- **uvicorn** — ASGI server
- **pydantic v2** — request/response validation (bundled with FastAPI)
- **pytest** — tests

No database, no auth, no persistence. Pure stateless transformation API.

## Project layout (create exactly this)

```
husk-api/
├── pyproject.toml
├── requirements.txt
├── README.md
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── contract.py
│   ├── registry.py
│   └── solutions/
│       ├── __init__.py
│       └── _example.py
├── static/
│   └── .gitkeep
└── tests/
    ├── __init__.py
    └── test_contract.py
```

`static/` exists so handoff 05 can drop frontend files into it. `_example.py` is the template solution agents will copy.

## Endpoint contract (THIS IS THE PUBLIC SPEC — solution agents will quote it)

### `POST /husk/{slug}`

**Request body:**
```json
{
  "input": "string (required) — source code or text to husk",
  "crumb_level": 1,
  "options": {}
}
```

- `input`: required, string, max 200_000 chars
- `crumb_level`: optional int, 0–3 inclusive, default `1`. Higher = more domain signal preserved.
- `options`: optional object, free-form per-solution tunables. Default `{}`.

**Success response (200):**
```json
{
  "output": "string — the husked result",
  "solution": "string — the slug that ran",
  "crumb_level": 1,
  "meta": {}
}
```

- `meta`: free-form object the solution can populate (counts, target_domain, model used, etc.)

**Error responses:**

| Status | When | Body |
|---|---|---|
| 404 | unknown slug | `{"error": "unknown_solution", "detail": "<slug>"}` |
| 422 | bad request body | FastAPI default validation error |
| 400 | crumb_level out of range or input too large | `{"error": "bad_request", "detail": "..."}` |
| 500 | solution raised an exception | `{"error": "solution_failed", "detail": "<exception message>"}` |
| 502 | solution couldn't reach a backend (e.g. LLM unreachable) | `{"error": "backend_unavailable", "detail": "..."}` |

### `GET /solutions`

Returns the list of registered solutions:
```json
{
  "solutions": [
    {"slug": "example", "name": "Passthrough Example", "description": "..."}
  ]
}
```

### `GET /health`

```json
{"status": "ok"}
```

### Static UI mount

- Mount `static/` directory at `/ui` so a frontend can be served from the same origin.
- `GET /ui/` should return `static/index.html` if it exists; if not, return 404 (frontend is built in handoff 05).

### CORS

- Allow origins: `http://localhost:5173`, `http://localhost:3000`, `http://localhost:8000`
- Allow methods: `GET`, `POST`, `OPTIONS`
- Allow headers: `*`

## Implementation plan

### Step 1 — `requirements.txt`

```
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.7
python-dotenv>=1.0
pytest>=8.0
httpx>=0.27
```

`httpx` is included now so solution 04 (LLM) doesn't need to modify this file later.

### Step 2 — `pyproject.toml`

Minimal, just to make `pip install -e .` work:

```toml
[project]
name = "husk-api"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
include = ["app*"]
```

### Step 3 — `app/contract.py`

Pydantic models. Write exactly:

```python
from typing import Any
from pydantic import BaseModel, Field

class HuskRequest(BaseModel):
    input: str = Field(..., max_length=200_000)
    crumb_level: int = Field(default=1, ge=0, le=3)
    options: dict[str, Any] = Field(default_factory=dict)

class HuskResponse(BaseModel):
    output: str
    solution: str
    crumb_level: int
    meta: dict[str, Any] = Field(default_factory=dict)

class SolutionInfo(BaseModel):
    slug: str
    name: str
    description: str

class SolutionsList(BaseModel):
    solutions: list[SolutionInfo]

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
```

### Step 4 — `app/registry.py`

Plugin registry. Solutions register themselves via decorator. Write exactly:

```python
from typing import Any, Callable
from dataclasses import dataclass

# A solution is a callable: (input: str, crumb_level: int, options: dict) -> (output: str, meta: dict)
HuskFn = Callable[[str, int, dict[str, Any]], tuple[str, dict[str, Any]]]

@dataclass
class Solution:
    slug: str
    name: str
    description: str
    fn: HuskFn

_REGISTRY: dict[str, Solution] = {}

def register(slug: str, name: str, description: str):
    """Decorator. Usage:

        @register(slug="fpe", name="FPE", description="...")
        def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
            ...
            return output, meta
    """
    def deco(fn: HuskFn) -> HuskFn:
        if slug in _REGISTRY:
            raise ValueError(f"slug already registered: {slug}")
        _REGISTRY[slug] = Solution(slug=slug, name=name, description=description, fn=fn)
        return fn
    return deco

def get(slug: str) -> Solution | None:
    return _REGISTRY.get(slug)

def all_solutions() -> list[Solution]:
    return sorted(_REGISTRY.values(), key=lambda s: s.slug)
```

### Step 5 — `app/solutions/__init__.py`

Auto-discover and import every sibling module (except those starting with `_`-but-keep-`_example`). Importing the module triggers its `@register(...)` decorator. Write exactly:

```python
import importlib
import pkgutil
from pathlib import Path

_pkg_dir = Path(__file__).parent

# Import every .py module in this directory so @register decorators fire.
for mod_info in pkgutil.iter_modules([str(_pkg_dir)]):
    importlib.import_module(f"{__name__}.{mod_info.name}")
```

This lets handoffs 02/03/04 each drop a single file into `app/solutions/` with a `@register(...)` decorated `husk` function and have it appear automatically.

### Step 6 — `app/solutions/_example.py`

A passthrough solution that serves as the template for handoffs 02/03/04. Write exactly:

```python
"""Template solution. Returns input reversed. Useful for verifying the registry wiring.

Solution agents: copy the structure of this file. Do NOT delete this file —
it is the canonical example."""

from app.registry import register

@register(
    slug="example",
    name="Passthrough Example",
    description="Reverses the input. Reference implementation for the contract.",
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    return input[::-1], {"length": len(input), "crumb_level_received": crumb_level}
```

### Step 7 — `app/main.py`

Wire the FastAPI app. Write exactly:

```python
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import solutions  # noqa: F401 — triggers solution auto-discovery
from app.contract import (
    HuskRequest, HuskResponse, SolutionInfo, SolutionsList, ErrorResponse,
)
from app.registry import get, all_solutions

app = FastAPI(title="Husk API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/solutions", response_model=SolutionsList)
def list_solutions():
    return SolutionsList(
        solutions=[
            SolutionInfo(slug=s.slug, name=s.name, description=s.description)
            for s in all_solutions()
        ]
    )

@app.post("/husk/{slug}", response_model=HuskResponse, responses={
    404: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
})
def husk(slug: str, req: HuskRequest):
    sol = get(slug)
    if sol is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(error="unknown_solution", detail=slug).model_dump(),
        )
    try:
        output, meta = sol.fn(req.input, req.crumb_level, req.options)
    except BackendUnavailable as e:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(error="backend_unavailable", detail=str(e)).model_dump(),
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error="solution_failed", detail=str(e)).model_dump(),
        )
    return HuskResponse(output=output, solution=slug, crumb_level=req.crumb_level, meta=meta)

# Solutions can raise this to surface a 502 (e.g. LLM endpoint unreachable).
class BackendUnavailable(Exception):
    pass

# Static UI mount. Directory must exist; handoff 05 fills it with index.html etc.
_static_dir = Path(__file__).resolve().parent.parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")
```

Note: `BackendUnavailable` is defined here so solution 04 can `from app.main import BackendUnavailable` and raise it cleanly. Define it BEFORE the `husk` function references it — move the `class BackendUnavailable` definition above the `@app.post` decorator. (The skeleton above has it after for readability; reorder when writing.)

### Step 8 — `app/__init__.py` and `app/solutions/__init__.py`

`app/__init__.py` is empty. `app/solutions/__init__.py` is the auto-discovery code from Step 5.

### Step 9 — `tests/test_contract.py`

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_solutions_lists_example():
    r = client.get("/solutions")
    assert r.status_code == 200
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "example" in slugs

def test_unknown_solution_404():
    r = client.post("/husk/does-not-exist", json={"input": "abc"})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_solution"

def test_example_passthrough():
    r = client.post("/husk/example", json={"input": "hello", "crumb_level": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["output"] == "olleh"
    assert body["solution"] == "example"
    assert body["crumb_level"] == 2
    assert body["meta"]["length"] == 5

def test_crumb_level_out_of_range():
    r = client.post("/husk/example", json={"input": "abc", "crumb_level": 9})
    assert r.status_code == 422

def test_input_required():
    r = client.post("/husk/example", json={})
    assert r.status_code == 422
```

### Step 10 — `.env.example`

Empty for now, but create the file. Solution 04 will document its env vars here. Write a one-line comment so the file isn't empty:

```
# Per-solution environment variables. See docs/handoffs for each solution's required vars.
```

### Step 11 — `README.md`

Brief. Just enough to run:

```markdown
# Husk API

## Setup

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pip install -e .

## Run

    uvicorn app.main:app --reload --port 8000

- API docs:  http://localhost:8000/docs
- Health:    http://localhost:8000/health
- UI:        http://localhost:8000/ui/  (after frontend is built)

## Test

    pytest

## Adding a solution

Drop a file into `app/solutions/` that uses `@register(...)` from `app.registry`.
See `app/solutions/_example.py` for the template.
```

## Acceptance criteria

All of the following must pass:

1. `pip install -r requirements.txt && pip install -e .` succeeds.
2. `pytest` passes all tests in `tests/test_contract.py`.
3. `uvicorn app.main:app --port 8000` starts without errors.
4. `curl http://localhost:8000/health` → `{"status":"ok"}` (200).
5. `curl http://localhost:8000/solutions` → JSON containing the `example` slug.
6. `curl -X POST http://localhost:8000/husk/example -H 'content-type: application/json' -d '{"input":"hello"}'` → returns `{"output":"olleh", ...}` (200).
7. `curl -X POST http://localhost:8000/husk/nonexistent -H 'content-type: application/json' -d '{"input":"x"}'` → 404 with `{"error":"unknown_solution",...}`.
8. `curl http://localhost:8000/ui/` → 404 (frontend not built yet) — this is expected and correct.

## Out of scope

- Do **not** implement the FPE, literal-tagging, or LLM-translation solutions. Those are separate handoffs (02, 03, 04).
- Do **not** write any frontend HTML/JS/CSS. That is handoff 05.
- Do **not** add auth, persistence, rate limiting, or logging beyond FastAPI defaults.
- Do **not** modify `_example.py` to do anything other than reverse the input.

## Open questions

Flag if any of these arise; do not silently work around:

- If `pip install -e .` fails on the target Python version, document the working command and Python version in the README.
- If FastAPI 0.115+ is unavailable in the target environment, pin to whatever version installs cleanly and note it.
