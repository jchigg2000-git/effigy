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
