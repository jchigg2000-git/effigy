"""Re-identification (the "dehusk" reverse half of the round-trip).

The reversible solutions (``fpe``, ``literal-tagging``) can emit a deterministic
pseudonym -> original map alongside their output when a husk request sets
``options.emit_map``. Once a consumer LLM has diagnosed the *husked* code, that
diagnosis is written in terms of the pseudonyms; :func:`reverse_substitute`
rewrites it back into the real identifiers/literals so the diagnosis maps onto
the original source. This closes the loop the project is pitched on
(README.md:6, docs/draft-1.md §6.1 "after applying the bijection").

The substitution is deliberately careful about two collision modes:

* **Longest-match first.** When one pseudonym is a prefix of another
  (``abc`` and ``abcd``), the longer one must win. We sort keys longest-first
  so an ordered regex alternation matches the longest applicable pseudonym at
  each position.
* **Token boundaries for word-shaped pseudonyms.** An ``fpe`` pseudonym
  such as ``xY7q`` must not be rewritten when it appears *inside* a larger word
  in the diagnosis prose. Any key made entirely of word characters
  (``[A-Za-z0-9_]``) is matched only at non-word boundaries. This deliberately
  includes digit-leading keys: ``fpe`` ciphers over ``ascii_letters + digits``
  without pinning the first character, so real pseudonyms routinely start with
  a digit and need the same guard (and the same ability to match standalone).
  Placeholder-shaped keys (e.g. ``<URL:0>``, whose ``<`` / ``>`` already
  delimit them) are matched literally.
"""

import re

# Any key composed entirely of word characters gets the boundary guard. NOTE:
# this must NOT require a leading alpha/underscore — fpe pseudonyms are
# ciphered over letters+digits and often start with a digit.
_WORD_KEY_RE = re.compile(r"[A-Za-z0-9_]+")


def reverse_substitute(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Rewrite ``text``, replacing each pseudonym with its original.

    ``mapping`` is pseudonym -> original, exactly as emitted by a husk call with
    ``options.emit_map``. Returns ``(rewritten_text, substitution_count)``.
    An empty or all-empty mapping is a no-op.
    """
    # Drop empty keys defensively; an empty pattern would match everywhere.
    keys = [k for k in mapping if k]
    if not keys:
        return text, 0

    # Longest-first so a longer pseudonym wins over any shorter one it contains.
    keys.sort(key=len, reverse=True)

    parts: list[str] = []
    for k in keys:
        esc = re.escape(k)
        if _WORD_KEY_RE.fullmatch(k):
            # Word-shaped (including digit-leading fpe pseudonyms): only match
            # at word boundaries so the pseudonym is not rewritten inside a
            # larger token in the diagnosis text.
            parts.append(rf"(?<![A-Za-z0-9_]){esc}(?![A-Za-z0-9_])")
        else:
            parts.append(esc)

    pattern = re.compile("|".join(parts))

    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return mapping[m.group(0)]

    return pattern.sub(repl, text), count
