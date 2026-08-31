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
