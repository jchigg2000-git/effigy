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
    # Opt-in re-identification map (pseudonym -> original), returned only when
    # the request sets options.emit_map on a reversible solution. This map
    # re-identifies the source, so it is sensitive: it is never logged or
    # persisted, and is omitted from the response unless explicitly requested.
    reidentify_map: dict[str, str] | None = None


class DehuskRequest(BaseModel):
    # The LLM's diagnosis text, written against the husked (pseudonymous) code.
    input: str = Field(..., max_length=200_000)
    # A pseudonym -> original map, exactly as returned by a husk call made with
    # options.emit_map. Kept client-supplied so the service stays stateless and
    # never has to hold the sensitive map itself.
    map: dict[str, str] = Field(...)


class DehuskResponse(BaseModel):
    output: str
    substitutions: int
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
