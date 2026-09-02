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

Crumb levels control which tokens are spared (kept as-is) vs ciphered.
"""

import os
import logging
import hmac
import hashlib
import re
import string
from typing import Callable

from app.registry import register


# Combined tokenizer: matches strings, comments, and identifiers in priority order.
# String literals and comments are passed through verbatim (per handoff: "Do not
# rewrite string literals or comments"). This protects Go import paths, SQL in
# backtick raw strings, JSX class names inside double quotes, etc. Bare JSX text
# nodes still leak through (no parser), which is acknowledged as a limitation.
_TOKEN_RE = re.compile(
    r"`(?:[^`\\]|\\.)*`"            # backtick raw string / JS template literal
    r'|"(?:[^"\\]|\\.)*"'           # double-quoted string
    r"|'(?:[^'\\]|\\.)*'"           # single-quoted string / Go rune
    r"|//[^\n]*"                    # // line comment
    r"|\#[^\n]*"                    # # line comment (Python, shell)
    r"|/\*(?:[^*]|\*(?!/))*\*/"     # /* block comment */
    r"|[A-Za-z_][A-Za-z0-9_]+",     # identifier (2+ chars, so `i`/`x` are never clobbered)
    re.DOTALL,
)


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


# Must be a superset of every character _TOKEN_RE's identifier branch can
# produce, or the sanitizer below silently maps out-of-alphabet chars onto
# in-alphabet ones and the transform stops being injective. "_" is in that
# branch, so it must be here:
# without it, ord("_") % 62 == 33 -> "H", making foo_bar and fooHbar collide.
_ALPHABET_MIXED = string.ascii_letters + string.digits + "_"


def _should_skip(token: str, crumb_level: int) -> bool:
    if token in _BASELINE_KEYWORDS:
        return True
    if crumb_level >= 1 and token in _STDLIB_NAMES:
        return True
    if crumb_level >= 2 and token in _GENERIC_DOMAIN_NOUNS:
        return True
    if crumb_level >= 3:
        humps = len(re.findall(r"[A-Z][a-z]+", token))
        underscores = token.count("_")
        if humps < 3 and underscores < 3 and len(token) < 12:
            return True
    return False


def _make_cipher(key: bytes, alphabet: str) -> Callable[[str], str]:
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
        sanitized = "".join(
            ch if ch in alphabet else alphabet[ord(ch) % len(alphabet)]
            for ch in token
        )
        return c.encrypt(sanitized)

    return encrypt


def _make_cipher_fallback(key: bytes, alphabet: str) -> Callable[[str], str]:
    base = len(alphabet)

    def encrypt(token: str) -> str:
        if not token:
            return token
        digest = hmac.new(key, token.encode("utf-8"), hashlib.sha256).digest()
        while len(digest) < len(token):
            digest += hmac.new(key, digest, hashlib.sha256).digest()
        out = "".join(alphabet[b % base] for b in digest[: len(token)])
        if token[0] == "_":
            out = "_" + out[1:]
        elif token[0].isupper():
            out = out[0].upper() + out[1:].lower()
        else:
            out = out.lower()
        return out

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
    backend_name = "pyffx"
    try:
        encrypt = _make_cipher(key, _ALPHABET_MIXED)
        encrypt("probe")
    except Exception:
        encrypt = _make_cipher_fallback(key, _ALPHABET_MIXED)
        backend_name = "hmac-fallback"

    seen: dict[str, str] = {}
    # pseudonym -> original. Maintained alongside `seen` so a collision is
    # detected at the moment it happens rather than silently swallowed by a
    # dict comprehension at map-build time.
    reverse: dict[str, str] = {}
    skipped = 0
    replaced = 0
    collisions = 0
    emit_map = bool(options.get("emit_map"))

    def replace(m: re.Match) -> str:
        nonlocal skipped, replaced, collisions
        tok = m.group(0)
        # Strings and comments: pass through verbatim
        first = tok[0]
        if not (first.isalpha() or first == "_"):
            return tok
        if _should_skip(tok, crumb_level):
            skipped += 1
            return tok
        if tok not in seen:
            try:
                pseudo = encrypt(tok)
            except Exception:
                # Per-token fallback if the primary cipher rejects this length/charset
                pseudo = _make_cipher_fallback(key, _ALPHABET_MIXED)(tok)
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

    output = _TOKEN_RE.sub(replace, input)

    meta = {
        "cipher_backend": backend_name,
        "identifiers_replaced": replaced,
        "identifiers_skipped": skipped,
        "unique_tokens_replaced": len(seen),
        "key_id": key_id,
        "pseudonym_collisions": collisions,
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
