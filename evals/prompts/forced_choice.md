<!-- Arm B, prereg §6.1. PRE-REGISTERED PRIMARY ENDPOINT.
     The menu is never shown in the same context as the open-ended question (§6),
     because seeing 12 options contaminates a free-text answer generated afterward.
     Option order is permuted per item by a recorded seed. There is deliberately no
     "cannot determine" option. -->
{briefing}

## The menu

Exactly one of these twelve is the original domain. Some of the others are domains this tool
rewrites *into*, so they are deliberately tempting.

{menu}

## The artifact

{artifact_label}

```{language}
{artifact}
```

## Your answer

Reply with ONLY a JSON object. No prose before it, no explanation after it, no markdown fence.

{"choice": <integer 1-12>, "confidence": <float 0.0-1.0>}

`choice` is the menu number of the **ORIGINAL** domain. You must pick one — there is no
"cannot determine" and abstaining is not available. `confidence` is your honest probability that
your choice is correct; a low confidence is not penalised and is more useful than a bluff.
