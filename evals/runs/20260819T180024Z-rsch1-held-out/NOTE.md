# NOT A RESULT — harness smoke test

`--limit 2`. **Two source files, both from one domain** (`water-utility-metering`), against a
design that requires six. Every number in `summary.md` here is a machinery check, not a
measurement, and none of it may be cited.

What it was for, and what it caught:

1. **`LLM_MAX_TOKENS=32768` exceeded the provider's combined input+output budget** — every
   `llm-translation` husk failed with a 422 before any of this ran.
2. **`LLM_MODEL` pointed at `Qwen/Qwen2.5-7B-Instruct`**, a model this repo's own evaluation
   *excluded on context window*. The recommended husker is `Qwen2.5-Coder-7B-Instruct`. The husk
   arm would silently have measured the wrong model.
3. **Attacker parse failure was 29%**, against §8's 5% ceiling. Cause: on this router a reasoning
   model's internal deliberation is billed against `max_tokens` even when it never reaches the
   content channel, so at 3072 both attackers returned an empty string with
   `finish_reason=length`. Fixed by pinning providers that support forced structured output and
   raising the budget to 16000. Re-ran: **52/52 parsed, 0%**.
4. Confirmed the shipped post-condition gate **refuses** passthrough husks (3 of 3 replicates of
   one file), which is what motivated the `llm-translation-ungated` arm — see preregistration A3
   and the arm's comment in `run_rsch1.py`.

Kept rather than deleted because §12 rule 3 keeps discarded output committed, and because the
three defects above are worth not rediscovering.
