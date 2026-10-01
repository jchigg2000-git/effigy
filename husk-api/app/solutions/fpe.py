"""O1 - Format-Preserving Encryption of identifiers.

Replaces every identifier token in the input with a deterministic, length-
preserving pseudonym. Same source token -> same output token (referential
integrity), and distinct tokens -> distinct pseudonyms (injectivity).

SCOPE OF PROTECTION: only *identifier tokens* are enciphered, and only those
are unrecoverable without the key. String literals and comments are passed
through VERBATIM by design (see _TOKEN_RE below) and are NOT protected at all
-- import paths, URLs, SQL, error messages and any secret embedded in a literal
survive into the output unchanged. This transform is not, on its own,
sufficient to strip source-domain signal. See LIMITATIONS.md.

The one exception is the code inside a backtick literal's ${...}: that is
JavaScript, not literal text, so it is enciphered like the rest of the file.
Go raw strings have no interpolation, but the tokenizer cannot tell them apart,
so a Go raw string containing ${...} has the identifiers inside it enciphered
too.

Crumb levels control which tokens are spared (kept as-is) vs ciphered.
"""

import functools
import os
import logging
import hmac
import hashlib
import re
import string
from typing import Callable

from app.registry import register


# Tokenizer: matches strings, comments, numbers and identifiers in priority order.
# String literals, comments and numbers are passed through verbatim (per handoff:
# "Do not rewrite string literals or comments"). This protects Go import paths,
# SQL in backtick raw strings, JSX class names inside double quotes, etc. Bare
# JSX text nodes still leak through (no parser), which is acknowledged as a
# limitation.
#
# Quoted literals and /* */ comments match only their opener here and are
# scanned by _span_end. In a single alternation, re.sub retried an unterminated
# opener at every later opener, each retry scanning to the end of the input, so
# one 200 KB request of escaped quotes held the process for minutes.
_TOKEN_RE = re.compile(
    r"(?P<open>'''|[`\"']|/\*)"     # quoted literal or /* block comment */
    r"|//[^\n]*"                    # // line comment
    r"|(?<!\.)\#[^\n]*"             # # line comment (Python, shell), but not JS `this.#field`
    r"|(?<!\w)\d\w*"                # number (0x1F, 0o755, 1_000); its tail is not an identifier
    # identifier (2+ chars, so `i`/`x` are never clobbered), except a two-letter string
    # prefix (Python/Rust rf, Rb, br, ...) glued to its quote, which is part of the literal
    r"|(?![rRbBfFuU]{2}['\"])[^\W\d]\w+"
)

# Body of each quoted literal up to, not including, its closing quote. A body
# is consumed one escape pair or one other character at a time, so the literal
# is terminated exactly when the longest body is followed by the closing quote.
_QUOTE_BODY = {
    "`": re.compile(r"(?:[^`\\]|\\.)*", re.DOTALL),   # backtick raw string / JS template literal
    '"': re.compile(r'(?:[^"\\]|\\.)*', re.DOTALL),   # double-quoted string
    # Python ''' string. It needs its own branch because a '...' literal stops
    # at a newline; """ strings already pair up through the '"' branch.
    "'''": re.compile(r"(?:[^\\']|\\.|'(?!''))*", re.DOTALL),
    # Single-quoted string / Go rune. A raw newline ends it: Go, JS/TS, Python
    # and C do not allow one there, and without the stop an apostrophe in a
    # comment or JSX text paired with a quote lines later and hid the code between.
    "'": re.compile(r"(?:[^'\\\n]|\\.)*", re.DOTALL),
}


def _span_end(text: str, start: int, opener: str, dead: dict[str, int], end: int) -> int:
    """End of the quoted literal or block comment opening at text[start], or -1.

    `dead` maps an opener to a position before which it is known not to
    terminate. A failed scan from `start` stops at the same place as a scan from
    any later opener it passed over (that opener was escaped, so both scans are
    in step after it), so each failure is paid for once and the tokenizer stays
    linear. Every call sharing a `dead` must use the same text and `end`.
    """
    if start < dead.get(opener, -1):
        return -1
    if opener == "/*":
        close = text.find("*/", start + 2, end)
        if close >= 0:
            return close + 2
        dead[opener] = end
        return -1
    stop = _QUOTE_BODY[opener].match(text, start + len(opener), end).end()
    if text.startswith(opener, stop, end):
        return stop + len(opener)
    dead[opener] = stop
    return -1


def _substitute(text: str, replace: Callable[[str], str]) -> str:
    """Pass every token in `text` through replace(); keep the text between tokens."""
    out: list[str] = []
    dead: dict[str, int] = {}
    kept = pos = 0
    while (m := _TOKEN_RE.search(text, pos)) is not None:
        start, stop = m.span()
        opener = m.group("open")
        if opener is not None:
            stop = _span_end(text, start, opener, dead, len(text))
            if stop < 0 and opener == "'''":
                stop = _span_end(text, start, "'", dead, len(text))
            if stop < 0:
                # Unterminated: the opener is ordinary text and scanning resumes
                # right after it, exactly as a failed regex alternative would.
                pos = start + 1
                continue
        out.append(text[kept:start])
        out.append(replace(text[start:stop]))
        kept = pos = stop
    out.append(text[kept:])
    return "".join(out)


# Literal text of a template, up to the next ${ (or the end).
_TEMPLATE_TEXT_RE = re.compile(r"(?:[^\\$]|\\.|\$(?!\{))*", re.DOTALL)
# Code inside ${...}, up to the next quote or brace.
_INTERPOLATION_CODE_RE = re.compile(r"[^'\"{}]*")


def _map_interpolations(template: str, fn: Callable[[str], str]) -> str:
    """Apply fn to the code inside each ${...} of a backtick literal token and keep
    the literal text around it verbatim. Braces inside quoted strings in that
    code do not count towards finding the closing brace."""
    out = ["`"]
    dead: dict[str, int] = {}
    end = len(template) - 1          # the closing backtick
    i = 1
    while True:
        j = _TEMPLATE_TEXT_RE.match(template, i, end).end()
        if not template.startswith("${", j, end):
            out.append(template[i:end])
            break
        out.append(template[i:j])
        body = k = j + 2
        depth = 0
        while (k := _INTERPOLATION_CODE_RE.match(template, k, end).end()) < end:
            ch = template[k]
            if ch in "'\"":
                stop = _span_end(template, k, ch, dead, end)
                k = stop if stop >= 0 else k + 1
                continue
            if ch == "{":
                depth += 1
            elif depth == 0:
                break
            else:
                depth -= 1
            k += 1
        if k >= end:
            # No closing brace: a quote in this code was not a string opener (a
            # regex such as /"/g) and paired with a later quote, so the walk ran
            # into template text. Leave the rest verbatim rather than encipher it.
            out.append(template[j:end])
            break
        out.append("${" + fn(template[body:k]))
        i = k
    out.append("`")
    return "".join(out)


_BASELINE_KEYWORDS = frozenset({
    "if", "else", "elif", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "return", "yield", "throw", "raise", "try", "except",
    "catch", "finally", "with", "in", "is", "as", "of", "from", "import",
    "export", "module", "package", "namespace", "use", "using",
    "def", "func", "function", "fn", "fun", "method", "class", "interface",
    "struct", "enum", "trait", "impl", "extends", "implements", "abstract",
    "let", "const", "var", "static", "final", "public", "private", "protected",
    "internal", "void", "null", "None", "True", "False", "true", "false",
    "self", "this", "super", "new", "delete", "typeof", "instanceof",
    "async", "await", "lambda", "pass", "and", "or", "not", "nil",
    # Go and Python reserved words; enciphering one breaks the parse.
    "go", "defer", "map", "chan", "select", "goto", "fallthrough", "range", "type",
    "assert", "del", "global", "nonlocal",
    # TypeScript contextual keywords; enciphering one breaks the parse.
    "keyof", "readonly", "declare", "satisfies",
})

_STDLIB_NAMES = frozenset({
    "print", "println", "log", "console", "len", "range", "list", "dict",
    "set", "tuple", "str", "int", "float", "bool", "object", "type",
    "Array", "Object", "String", "Number", "Boolean", "Map", "Set", "Promise",
    "JSON", "Math", "Date", "Error", "Exception", "RuntimeException",
    "useState", "useEffect", "useMemo", "useCallback", "useRef",
    "Component", "Fragment", "render", "props", "state",
    "DataFrame", "Series", "ndarray", "Tensor", "nn", "torch", "tf", "np", "pd",
    "main", "init", "setup", "teardown", "open", "read", "write", "close",
})

_GENERIC_DOMAIN_NOUNS = frozenset({
    "User", "Account", "Order", "Item", "Product", "Customer", "Client",
    "Service", "Handler", "Controller", "Manager", "Repository", "Repo",
    "Store", "Cache", "Queue", "Worker", "Job", "Task", "Event", "Message",
    "Request", "Response", "Result", "Status", "Error", "Config", "Settings",
    "user", "account", "order", "item", "product", "customer", "client",
    "service", "handler", "controller", "manager", "repository", "repo",
    "store", "cache", "queue", "worker", "job", "task", "event", "message",
    "request", "response", "result", "status", "error", "config", "settings",
})


# Must hold every ASCII character _TOKEN_RE's identifier branch can produce.
# "_" is in that branch, so it must be here: an earlier sanitizer mapped it via
# ord("_") % 62 == 33 -> "H", making foo_bar and fooHbar collide. Identifiers
# with non-ASCII characters go to the keyed HMAC fallback instead.
_ALPHABET_MIXED = string.ascii_letters + string.digits + "_"


@functools.cache
def _spared_words(crumb_level: int) -> frozenset[str]:
    """The fixed word lists kept as-is at this crumb level."""
    words = _BASELINE_KEYWORDS
    if crumb_level >= 1:
        words |= _STDLIB_NAMES
    if crumb_level >= 2:
        words |= _GENERIC_DOMAIN_NOUNS
    return words


def _should_skip(token: str, crumb_level: int) -> bool:
    if token in _spared_words(crumb_level):
        return True
    if crumb_level >= 3:
        humps = len(re.findall(r"[A-Z][a-z]+", token))
        underscores = token.count("_")
        if humps < 3 and underscores < 3 and len(token) < 12:
            return True
    return False


def _usable(pseudo: str, reserved: frozenset[str]) -> bool:
    """A pseudonym must itself be an identifier, and must not be a word left in
    plain text: /dehusk could not tell the two apart and would rewrite both."""
    return (pseudo[0].isalpha() or pseudo[0] == "_") and pseudo not in reserved


def _make_cipher(key: bytes, alphabet: str, reserved: frozenset[str]) -> Callable[[str], str]:
    import pyffx
    cache: dict[int, "pyffx.String"] = {}

    def encrypt(token: str) -> str:
        if not token:
            return token
        n = len(token)
        c = cache.get(n)
        if c is None:
            c = pyffx.String(key, alphabet=alphabet, length=n)
            cache[n] = c
        out = c.encrypt(token)
        # Cycle-walk: FFX permutes alphabet^n, so re-enciphering until the result
        # is usable stays a bijection on the tokens that get enciphered, which are
        # all usable themselves. A token whose first ciphertext is usable keeps it.
        while not _usable(out, reserved):
            out = c.encrypt(out)
        return out

    return encrypt


def _make_cipher_fallback(key: bytes, alphabet: str, reserved: frozenset[str]) -> Callable[[str], str]:
    base = len(alphabet)

    def encrypt(token: str) -> str:
        if not token:
            return token
        msg = token.encode("utf-8")
        while True:
            digest = hmac.new(key, msg, hashlib.sha256).digest()
            stream = digest
            while len(stream) < len(token):
                stream += hmac.new(key, stream, hashlib.sha256).digest()
            out = "".join(alphabet[b % base] for b in stream[: len(token)])
            if token[0] == "_":
                out = "_" + out[1:]
            elif token[0].isupper():
                out = out[0].upper() + out[1:].lower()
            else:
                out = out.lower()
            if _usable(out, reserved):
                return out
            # Not a permutation, so there is no cycle to walk: re-hash instead.
            # The caller's reverse-dict check still catches any collision.
            msg = digest

    return encrypt


_log = logging.getLogger(__name__)


# The historical default key. It is baked into public source, so anything
# enciphered under it is decryptable by anyone holding this file. Retained ONLY
# behind an explicit opt-in so previously-recorded evaluation outputs stay
# reproducible. Its name is the warning.
_DEMO_KEY = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc\xdd\xee\xff"

_KEY_HINT = (
    "Generate one with:  python3 -c \'import secrets; print(secrets.token_hex(16))\'"
)

# Process-lifetime ephemeral key. Cached at module scope so every request in a
# process shares one key -- referential integrity across separate husk calls
# depends on this.
_EPHEMERAL_KEY: bytes | None = None


def _load_key() -> tuple[bytes, str]:
    """Resolve the FPE key. Returns (key, key_id).

    Never falls back to a baked-in constant silently: a rejected FPE_KEY raises,
    because an operator who believes they configured a key while the service
    enciphers under a published one is strictly worse off than an error.
    """
    global _EPHEMERAL_KEY

    hex_key = os.environ.get("FPE_KEY")
    if hex_key:
        try:
            k = bytes.fromhex(hex_key)
        except ValueError:
            raise ValueError(f"FPE_KEY is set but is not valid hex. {_KEY_HINT}") from None
        if len(k) < 16:
            raise ValueError(
                f"FPE_KEY is set but decodes to {len(k)} bytes; 16 are required. {_KEY_HINT}"
            )
        return k[:16], "env"

    if os.environ.get("FPE_DEMO_KEY"):
        _log.warning(
            "FPE_DEMO_KEY is set: enciphering under the PUBLIC, source-baked demo key. "
            "Output is trivially reversible by anyone with this source. Never use on real code."
        )
        return _DEMO_KEY, "insecure-demo"

    if os.environ.get("EFFIGY_ENV") == "production" and not os.environ.get(
        "FPE_ALLOW_EPHEMERAL_KEY"
    ):
        raise ValueError(
            "FPE_KEY is required when EFFIGY_ENV=production. "
            f"{_KEY_HINT}  (Set FPE_ALLOW_EPHEMERAL_KEY=1 to override.)"
        )

    if _EPHEMERAL_KEY is None:
        import secrets

        _EPHEMERAL_KEY = secrets.token_bytes(16)
        _log.warning(
            "FPE_KEY is not set; generated a random ephemeral key for this process. "
            "Pseudonyms will NOT be stable across restarts and /dehusk will not work "
            "against a map from a previous process. %s", _KEY_HINT,
        )
    return _EPHEMERAL_KEY, "ephemeral"


@register(
    slug="fpe",
    name="Format-Preserving Encryption (O1)",
    description=(
        "Deterministic, length-preserving identifier rewrite. Same token -> same pseudonym. "
        "Enciphers IDENTIFIERS ONLY -- string literals and comments pass through verbatim and "
        "are NOT protected. Set FPE_KEY (32 hex chars) for stable, private pseudonyms; without "
        "it a random per-process key is used."
    ),
)
def husk(input: str, crumb_level: int, options: dict) -> tuple[str, dict]:
    key, key_id = _load_key()
    reserved = _spared_words(crumb_level)
    fallback = _make_cipher_fallback(key, _ALPHABET_MIXED, reserved)
    backend_name = "pyffx"
    try:
        encrypt = _make_cipher(key, _ALPHABET_MIXED, reserved)
        encrypt("probe")
    except Exception:
        encrypt = fallback
        backend_name = "hmac-fallback"

    seen: dict[str, str] = {}
    # pseudonym -> original. Maintained alongside `seen` so a collision is
    # detected at the moment it happens rather than silently swallowed by a
    # dict comprehension at map-build time.
    reverse: dict[str, str] = {}
    spared: set[str] = set()
    skipped = 0
    replaced = 0
    collisions = 0
    non_ascii = 0
    # Only the JSON boolean true opts in: the map re-identifies the source, so
    # a string such as "false" must not switch it on by being truthy.
    emit_map = options.get("emit_map") is True

    def replace(tok: str) -> str:
        nonlocal skipped, replaced, collisions, non_ascii
        first = tok[0]
        if first == "`" and "${" in tok:
            return _map_interpolations(tok, lambda code: _substitute(code, replace))
        # Strings, comments and numbers: pass through verbatim
        if not (first.isalpha() or first == "_"):
            return tok
        if _should_skip(tok, crumb_level):
            skipped += 1
            spared.add(tok)
            return tok
        if tok not in seen:
            if not tok.isascii():
                # FFX needs a fixed alphabet, so these take the keyed fallback.
                non_ascii += 1
                pseudo = fallback(tok)
            else:
                try:
                    pseudo = encrypt(tok)
                except Exception:
                    # Per-token fallback if the primary cipher rejects this length/charset
                    pseudo = fallback(tok)
            prior = reverse.get(pseudo)
            if prior is not None and prior != tok:
                # Two distinct source identifiers mapped to one pseudonym. The
                # asymmetry below is deliberate: with a map requested, a wrong
                # identifier silently rewritten into a diagnosis is worse than an
                # error, so we refuse. Without one, the husk is still usable and
                # the collision only degrades referential integrity, which the
                # caller can see in meta.
                if emit_map:
                    raise ValueError(
                        f"pseudonym collision: {prior!r} and {tok!r} both encipher to "
                        f"{pseudo!r}; refusing to emit a lossy re-identification map"
                    )
                collisions += 1
            else:
                reverse[pseudo] = tok
            seen[tok] = pseudo
        replaced += 1
        return seen[tok]

    output = _substitute(input, replace)

    # The cipher never lands on a word the fixed lists spare, but the crumb-3
    # heuristic spares arbitrary short tokens, so a pseudonym can still equal a
    # token left in plain text elsewhere in the input. Same asymmetry as above.
    for tok, pseudo in seen.items():
        if pseudo in spared:
            if emit_map:
                raise ValueError(
                    f"pseudonym collision: {tok!r} enciphers to {pseudo!r}, which is also "
                    f"left in plain text; refusing to emit an ambiguous re-identification map"
                )
            collisions += 1

    meta = {
        "cipher_backend": backend_name,
        "identifiers_replaced": replaced,
        "identifiers_skipped": skipped,
        "unique_tokens_replaced": len(seen),
        "key_id": key_id,
        "pseudonym_collisions": collisions,
        "non_ascii_identifiers": non_ascii,
    }
    if key_id == "ephemeral":
        meta["key_warning"] = (
            "random per-process key; pseudonyms are not stable across restarts"
        )
    elif key_id == "insecure-demo":
        meta["key_warning"] = (
            "PUBLIC source-baked demo key; output is trivially reversible"
        )

    # Opt-in re-identification map. `seen` is original -> pseudonym; invert it to
    # pseudonym -> original so the diagnosis can be dehusked back to the source.
    # Strictly opt-in (options.emit_map) because it re-identifies the source;
    # main.py lifts it into a dedicated top-level response field and it is never
    # logged or persisted.
    if emit_map:
        # Built from `reverse`, not by re-inverting `seen`. A dict comprehension
        # over seen.items() silently drops one side of any collision; `reverse`
        # is collision-checked above, so this cannot lose an entry.
        meta["reidentify_map"] = dict(reverse)

    return output, meta
