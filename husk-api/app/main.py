from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import solutions  # noqa: F401 — triggers solution auto-discovery
from app.contract import (
    HuskRequest, HuskResponse, SolutionInfo, SolutionsList, ErrorResponse,
    DehuskRequest, DehuskResponse,
)
from app.dehusk import reverse_substitute
from app.registry import get, all_solutions


# Solutions can raise this to surface a 502 (e.g. LLM endpoint unreachable).
class BackendUnavailable(Exception):
    pass


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


@app.get("/")
def root():
    return RedirectResponse(url="/ui/", status_code=307)


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
    # Lift the opt-in re-identification map out of meta into a dedicated,
    # clearly-sensitive response field. It is only present when the request set
    # options.emit_map on a reversible solution; the service never logs or
    # persists it (it is stateless), and it is omitted otherwise.
    reidentify_map = meta.pop("reidentify_map", None) if isinstance(meta, dict) else None
    return HuskResponse(
        output=output,
        solution=slug,
        crumb_level=req.crumb_level,
        meta=meta,
        reidentify_map=reidentify_map,
    )


@app.post("/dehusk", response_model=DehuskResponse, responses={
    500: {"model": ErrorResponse},
})
def dehusk(req: DehuskRequest):
    """Reverse half of the round-trip: rewrite an LLM's diagnosis of husked code
    back into the real identifiers/literals, using a pseudonym -> original map
    obtained from a husk call made with options.emit_map.

    The service is stateless and holds no maps of its own — the caller supplies
    the (sensitive) map with the request, and it is never logged or persisted.
    """
    try:
        output, substitutions = reverse_substitute(req.input, req.map)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error="dehusk_failed", detail=str(e)).model_dump(),
        )
    return DehuskResponse(
        output=output,
        substitutions=substitutions,
        meta={"map_entries": len(req.map)},
    )


# Static UI mount. static/ holds the hand-authored UI (index.html, app.js, style.css).
_static_dir = Path(__file__).resolve().parent.parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")
