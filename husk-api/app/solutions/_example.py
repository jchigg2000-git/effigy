"""Template solution. Returns input reversed. Useful for verifying the registry wiring.

Solution agents: copy the structure of this file. Do NOT delete this file —
it is the canonical example.

Registered only when HUSK_ENABLE_EXAMPLE=1 is set in the process environment
(tests/conftest.py sets it). A reversed string is a trivially reversible "husk",
so it has no place on the public API by default. This module is imported before
llm_translation loads husk-api/.env, so setting the flag in .env has no effect.
A real solution applies @register unconditionally."""

import os

from app.registry import register


def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    return input[::-1], {"length": len(input), "crumb_level_received": crumb_level}


if os.environ.get("HUSK_ENABLE_EXAMPLE") == "1":
    register(
        slug="example",
        name="Passthrough Example",
        description="Reverses the input. Reference implementation for the contract.",
    )(husk)
