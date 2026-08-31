<!-- Judge, prereg §6.2 pass 2. A THIRD model family, distinct from both attacker and
     rewriter, temperature 0. DELIBERATELY NOT SHOWN THE ARTIFACT: a judge that can see
     the husk can be swayed by it, and would be grading the evidence rather than the
     match. A random 20% of these are hand-labelled and Cohen's κ is reported; if
     κ < 0.6 these labels are reported as DESCRIPTIVE ONLY and only the deterministic
     leak-term pre-check counts as evidence. -->
You are grading one guess against one ground-truth label. You are **not** shown the artifact the
guess came from, and you must not speculate about it.

GROUND TRUTH — the domain the source code actually came from:
  {truth_label} — {truth_description}

THE GUESS:
  {guess}

Label the guess:

- **MATCH** — the guess names the same problem domain. Different wording, synonyms, a narrower or
  broader phrasing of the same activity all count. "Public library lending" vs "Library catalog and
  circulation" is a MATCH.
- **RELATED** — the guess lands in an adjacent or overlapping domain that shares real subject
  matter with the truth, but is not the same activity. "Archival records management" against
  "Library catalog and circulation" is RELATED.
- **MISS** — a different domain entirely, or too vague to locate ("a web service", "CRUD over a
  database", "some kind of inventory system" when the truth is far more specific).

Reply with ONLY a JSON object, no prose and no fence:

{"label": "MATCH" | "RELATED" | "MISS", "reason": "<= 20 words"}
