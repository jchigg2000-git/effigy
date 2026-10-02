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
too. The same holds for the replacement fields of a Python f-string or t-string
(f"{order.total!r:>{width}}"): the expressions are code and are enciphered,
while the literal text, the conversion and the format-spec text stay verbatim.

Crumb levels control which tokens are spared (kept as-is) vs ciphered.
"""

import functools
import os
import logging
import hmac
import hashlib
import re
import string
import dataclasses
from dataclasses import dataclass
from typing import Callable

from app.registry import register
from app.solutions.literal_tagging import _JS_LANGUAGES, _template_end


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
def _token_re(slash_comments: bool, hash_comments: bool, *,
              c_directives: bool = False, rust: bool = False) -> re.Pattern[str]:
    return re.compile(
        # C/C++ preprocessor: a directive name, an #include <...> path and a whole
        # #pragma line pass through verbatim; the rest of a directive line is code,
        # so a #define'd name gets the same pseudonym as its uses.
        (r"(?m:^[ \t]*\#[ \t]*(?:include|include_next|import)[ \t]*<[^>\n]*>"
         r"|^[ \t]*\#[ \t]*pragma\b[^\n]*"
         r"|^[ \t]*\#[ \t]*[A-Za-z_]\w*)|" if c_directives else "")
        # Rust: an attribute's name (#[derive(...)], #![allow(...)]) passes through
        # verbatim and its arguments are code; a raw string r"..." / r#"..."#
        # (b-prefixed too) opens here and is closed by _substitute; and only a
        # char literal pairs a single quote: 'a in <'a> is a lifetime, not the
        # opener of a string.
        + (r"\#!?\[[ \t]*[A-Za-z_]\w*|(?P<rawopen>(?<!\w)b?r(?P<hashes>\#*)\")"
           r"|'(?:[^'\\\n]|\\(?:u\{[0-9A-Fa-f_]{1,8}\}|x[0-9A-Fa-f]{2}|.))'|" if rust else "")
        # quoted literal or /* block comment */
        + (r"(?P<open>\"|/\*)" if rust else r"(?P<open>'''|[`\"']|/\*)")
        + (r"|//[^\n]*" if slash_comments else "")   # // line comment
        # # line comment (Python, shell), but not JS `this.#field`; where # is
        # code, only a #! line at the very start is a comment (not in Rust, where
        # #![...] is an attribute)
        + (r"|(?<!\.)\#[^\n]*" if hash_comments else "" if rust else r"|\A\#![^\n]*")
        + r"|(?<!\w)\d\w*"              # number (0x1F, 0o755, 1_000); its tail is not an identifier
        # identifier (2+ chars, so `i`/`x` are never clobbered), except a two-letter string
        # prefix (Python/Rust rf, Rb, br, rt, ...) glued to its quote, which is part of the literal
        + r"|(?![rRbBfFuUtT]{2}['\"])[^\W\d]\w+"
    )


# Without options.language both comment syntaxes apply, so Python floor division
# (a // b) and a JS #private declaration hide the rest of their line.
_TOKEN_RE = _token_re(slash_comments=True, hash_comments=True)


@dataclass(frozen=True)
class _Lexer:
    """What options.language changes about tokenizing."""
    name: str
    token_re: re.Pattern[str]
    # A template literal nested in a ${...} stays part of the outer one.
    js_templates: bool = False
    # The code in a backtick literal's ${...} is enciphered. Go's raw strings
    # have no interpolation, so under "go" they pass through like any literal.
    backtick_interpolation: bool = True
    # The language's reserved words, spared at every crumb level, and its
    # predeclared types and standard names, spared from crumb 1 (L1).
    keywords: frozenset[str] = frozenset()
    builtins: frozenset[str] = frozenset()
    # Kotlin string templates: "$name" and "${expr}" in a double-quoted string
    # are code and are enciphered; the string's text stays verbatim.
    dq_templates: bool = False


# C, and C++ on top of it. `defined` is the preprocessor operator.
_C_KEYWORDS = frozenset({
    "auto", "char", "double", "extern", "float", "int", "long", "register",
    "restrict", "short", "signed", "sizeof", "typedef", "union", "unsigned",
    "volatile", "inline", "bool", "alignas", "alignof", "static_assert",
    "thread_local", "typeof", "typeof_unqual", "constexpr", "nullptr",
    "_Bool", "_Complex", "_Imaginary", "_Alignas", "_Alignof", "_Atomic",
    "_Generic", "_Noreturn", "_Static_assert", "_Thread_local", "defined",
})
_CPP_KEYWORDS = _C_KEYWORDS | frozenset({
    "template", "typename", "virtual", "override", "friend", "operator",
    "explicit", "mutable", "noexcept", "decltype", "const_cast", "static_cast",
    "dynamic_cast", "reinterpret_cast", "consteval", "constinit", "co_await",
    "co_return", "co_yield", "concept", "requires", "wchar_t", "char8_t",
    "char16_t", "char32_t", "xor", "bitand", "bitor", "compl", "and_eq",
    "or_eq", "xor_eq", "not_eq", "typeid",
})
_C_BUILTINS = frozenset({
    "size_t", "ssize_t", "ptrdiff_t", "intptr_t", "uintptr_t", "intmax_t",
    "uintmax_t", "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t",
    "uint16_t", "uint32_t", "uint64_t", "wchar_t", "FILE", "NULL", "EOF",
    "errno", "stdin", "stdout", "stderr", "printf", "fprintf", "sprintf",
    "snprintf", "scanf", "sscanf", "puts", "fputs", "fgets", "fopen", "fclose",
    "fread", "fwrite", "malloc", "calloc", "realloc", "free", "exit", "abort",
    "memcpy", "memmove", "memset", "memcmp", "strlen", "strcmp", "strncmp",
    "strcpy", "strncpy", "strcat", "strchr", "strstr", "atoi", "strtol", "assert",
})
_CPP_BUILTINS = _C_BUILTINS | frozenset({
    "std", "vector", "string_view", "unordered_map", "unordered_set",
    "unique_ptr", "shared_ptr", "weak_ptr", "make_unique", "make_shared",
    "optional", "variant", "pair", "array", "deque", "cout", "cerr", "endl",
    "move", "forward", "size", "begin", "end", "push_back", "emplace_back",
})
_RUST_KEYWORDS = frozenset({
    "crate", "dyn", "loop", "match", "mod", "move", "mut", "pub", "ref",
    "Self", "unsafe", "where", "macro_rules", "union", "box", "become",
    "priv", "unsized", "virtual", "macro",
})
_RUST_BUILTINS = frozenset({
    "i8", "i16", "i32", "i64", "i128", "isize", "u8", "u16", "u32", "u64",
    "u128", "usize", "f32", "f64", "char", "str",
    "Option", "Some", "Result", "Ok", "Err", "Vec", "Box", "Rc", "Arc",
    "RefCell", "Cell", "Mutex", "HashMap", "HashSet", "BTreeMap", "BTreeSet",
    "VecDeque", "ToString", "Into", "From", "TryFrom", "TryInto", "AsRef",
    "Iterator", "IntoIterator", "Default", "Drop", "Fn", "FnMut", "FnOnce",
    "Send", "Sync", "Sized", "Copy", "Clone", "Debug", "Display", "PartialEq",
    "Eq", "PartialOrd", "Ord", "Hash", "std", "core", "alloc", "fmt",
    "collections", "println", "eprintln", "format", "vec", "write", "writeln",
    "panic", "assert", "assert_eq", "assert_ne", "matches", "todo",
    "unimplemented", "unreachable", "unwrap", "expect", "clone", "iter",
    "into", "to_string", "as_str", "new", "test", "feature",
})

_JAVA_KEYWORDS = frozenset({
    "boolean", "byte", "char", "double", "float", "int", "long", "short",
    "synchronized", "throws", "transient", "native", "strictfp", "volatile",
    "goto", "record", "sealed", "permits", "yield",
})
_JAVA_BUILTINS = frozenset({
    "Integer", "Long", "Double", "Float", "Character", "Byte", "Short", "Void",
    "List", "ArrayList", "LinkedList", "HashMap", "TreeMap", "LinkedHashMap",
    "HashSet", "TreeSet", "Optional", "Stream", "Collectors", "System", "out",
    "err", "println", "printf", "Objects", "Arrays", "Collections",
    "Iterable", "Iterator", "Comparable", "Comparator", "Runnable", "Thread",
    "StringBuilder", "CharSequence", "Throwable", "IllegalArgumentException",
    "IllegalStateException", "NullPointerException", "UnsupportedOperationException",
    "IOException", "Override", "Deprecated", "FunctionalInterface",
    "SuppressWarnings", "SafeVarargs", "BigDecimal", "BigInteger", "equals",
    "hashCode", "toString", "valueOf", "size", "get", "put", "add", "isEmpty",
})
# Kotlin, hard and soft keywords alike: enciphering `data` in `data class` or
# `value` in a setter breaks the parse as surely as enciphering `val`.
_KOTLIN_KEYWORDS = frozenset({
    "val", "when", "object", "typealias", "companion", "data", "sealed",
    "inner", "open", "override", "lateinit", "vararg", "inline", "noinline",
    "crossinline", "reified", "suspend", "tailrec", "operator", "infix",
    "external", "annotation", "out", "by", "get", "set", "field", "it",
    "constructor", "where", "expect", "actual", "value", "dynamic", "file",
    "property", "receiver", "param", "setparam", "delegate",
})
_KOTLIN_BUILTINS = frozenset({
    "Int", "Long", "Double", "Float", "Char", "Byte", "Short", "Unit", "Any",
    "Nothing", "Array", "IntArray", "List", "MutableList", "MutableMap",
    "MutableSet", "Sequence", "Pair", "Triple", "Result", "Throwable",
    "Comparable", "Iterable", "Collection", "listOf", "mutableListOf", "mapOf",
    "mutableMapOf", "setOf", "mutableSetOf", "emptyList", "emptyMap", "arrayOf",
    "println", "require", "requireNotNull", "check", "checkNotNull", "error",
    "let", "also", "apply", "run", "with", "takeIf", "lazy", "to", "repeat",
    "TODO", "IllegalArgumentException", "IllegalStateException", "JvmStatic",
    "JvmField", "JvmOverloads", "Suppress", "Deprecated", "toString",
    "equals", "hashCode", "size", "isEmpty", "map", "filter", "forEach",
})


_DEFAULT_LEXER = _Lexer("default", _TOKEN_RE)
_C_TOKEN_RE = _token_re(slash_comments=True, hash_comments=False, c_directives=True)
_LEXERS = {
    **dict.fromkeys(("py", "pyi", "pyw", "python"),
                    _Lexer("python", _token_re(slash_comments=False, hash_comments=True))),
    **dict.fromkeys(_JS_LANGUAGES,
                    _Lexer("js", _token_re(slash_comments=True, hash_comments=False),
                           js_templates=True)),
    **dict.fromkeys(("go", "golang"),
                    _Lexer("go", _token_re(slash_comments=True, hash_comments=False),
                           backtick_interpolation=False)),
    **dict.fromkeys(("c", "h"),
                    _Lexer("c", _C_TOKEN_RE, backtick_interpolation=False,
                           keywords=_C_KEYWORDS, builtins=_C_BUILTINS)),
    **dict.fromkeys(("cpp", "c++", "cc", "cxx", "hpp", "hh", "hxx"),
                    _Lexer("cpp", _C_TOKEN_RE, backtick_interpolation=False,
                           keywords=_CPP_KEYWORDS, builtins=_CPP_BUILTINS)),
    **dict.fromkeys(("java",),
                    _Lexer("java", _token_re(slash_comments=True, hash_comments=False),
                           backtick_interpolation=False,
                           keywords=_JAVA_KEYWORDS, builtins=_JAVA_BUILTINS)),
    # A Kotlin backtick quotes an identifier; it still passes through verbatim.
    **dict.fromkeys(("kt", "kts", "kotlin"),
                    _Lexer("kotlin", _token_re(slash_comments=True, hash_comments=False),
                           backtick_interpolation=False, dq_templates=True,
                           keywords=_KOTLIN_KEYWORDS, builtins=_KOTLIN_BUILTINS)),
    **dict.fromkeys(("rs", "rust"),
                    _Lexer("rust", _token_re(slash_comments=True, hash_comments=False, rust=True),
                           backtick_interpolation=False,
                           keywords=_RUST_KEYWORDS, builtins=_RUST_BUILTINS)),
}


# How deep a template literal nested in ${...} is still tracked as one literal.
_MAX_NESTING = 32


def _lexer_for(options: dict) -> _Lexer:
    """The lexer for options.language, spelled as literal-tagging takes it (any
    case, an optional leading dot). Unknown or absent: the language-blind default."""
    return _LEXERS.get(str(options.get("language") or "").lower().lstrip("."), _DEFAULT_LEXER)

# A Python f-string or t-string prefix (f, rf, Fr, t, tR, ...). It is not a
# token of its own: the one-letter forms are too short for the identifier
# branch, and the two-letter forms are excluded from it above.
_FIELD_PREFIX_RE = re.compile(r"[fFtT][rR]?|[rR][fFtT]")
# The same prefix at the head of a token _substitute hands to replace().
_FIELD_HEAD_RE = re.compile(r"(?:[fFtT][rR]?|[rR][fFtT])(?=['\"])")

# Body of each quoted literal up to, not including, its closing quote. A body
# is consumed one escape pair or one other character at a time, so the literal
# is terminated exactly when the longest body is followed by the closing quote.
_QUOTE_BODY = {
    "`": re.compile(r"(?:[^`\\]|\\.)*", re.DOTALL),   # backtick raw string / JS template literal
    '"': re.compile(r'(?:[^"\\]|\\.)*', re.DOTALL),   # double-quoted string
    # Python ''' string. It needs its own branch because a '...' literal stops
    # at a newline; """ strings already pair up through the '"' branch.
    "'''": re.compile(r"(?:[^\\']|\\.|'(?!''))*", re.DOTALL),
    # Python """ string, scanned as one literal only for an f- or t-string, whose
    # replacement fields have to be found inside the whole of it. Any other """
    # string still pairs up through the '"' branch.
    '"""': re.compile(r'(?:[^\\"]|\\.|"(?!""))*', re.DOTALL),
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


def _field_prefix_len(text: str, start: int) -> int:
    """Length of the f-/t-string prefix glued to the quote at text[start], or 0."""
    for n in (2, 1):
        b = start - n
        if (b >= 0 and _FIELD_PREFIX_RE.fullmatch(text, b, start)
                and (b == 0 or not (text[b - 1].isalnum() or text[b - 1] == "_"))):
            return n
    return 0


def _substitute(text: str, replace: Callable[[str], str],
                lexer: _Lexer = _DEFAULT_LEXER) -> str:
    """Pass every token in `text` through replace(); keep the text between tokens.

    An f- or t-string reaches replace() with its prefix (f"...", rt'''...''').
    """
    out: list[str] = []
    dead: dict[str, int] = {}
    js_templates = lexer.js_templates
    kept = pos = 0
    while (m := lexer.token_re.search(text, pos)) is not None:
        start, stop = m.span()
        opener = m.group("open")
        if raw := m.groupdict().get("rawopen"):
            # Rust raw string: no escapes, ends at the first quote followed by as
            # many # as opened it. A failed search fails from every later opener
            # with the same closer, so it is paid for once.
            closer = '"' + m.group("hashes")
            close = -1 if "raw" + closer in dead else text.find(closer, stop)
            if close < 0:
                dead["raw" + closer] = len(text)
                pos = start + 1
                continue
            stop = close + len(closer)
            out.append(text[kept:start])
            out.append(text[start:stop])       # verbatim, like any literal
            kept = pos = stop
            continue
        if opener is not None:
            prefix = _field_prefix_len(text, start) if opener in ("'''", '"', "'") else 0
            if prefix and text.startswith('"""', start):
                opener = '"""'
            stop = -1
            if opener == "`" and js_templates:
                stop = _template_end(text, start)
                # Unterminated: the plain first-backtick rule from here on, so a
                # failed scan to the end of the input is paid only once.
                js_templates = stop >= 0
            if stop < 0:
                stop = _span_end(text, start, opener, dead, len(text))
            if stop < 0 and opener in ("'''", '"""'):
                stop = _span_end(text, start, opener[0], dead, len(text))
            if stop < 0:
                # Unterminated: the opener is ordinary text and scanning resumes
                # right after it, exactly as a failed regex alternative would.
                pos = start + 1
                continue
            start -= prefix
        out.append(text[kept:start])
        out.append(replace(text[start:stop]))
        kept = pos = stop
    out.append(text[kept:])
    return "".join(out)


# Literal text of a template, up to the next ${ (or the end).
_TEMPLATE_TEXT_RE = re.compile(r"(?:[^\\$]|\\.|\$(?!\{))*", re.DOTALL)
# Kotlin string text, up to the next ${ or $name.
_DQ_TEMPLATE_TEXT_RE = re.compile(r"(?:[^\\$]|\\.|\$(?![{A-Za-z_]))*", re.DOTALL)
_DQ_TEMPLATE_NAME_RE = re.compile(r"[A-Za-z_]\w*")
# Code inside ${...}, up to the next quote or brace (or backtick, for JS).
_INTERPOLATION_CODE_RE = re.compile(r"[^'\"{}]*")
_INTERPOLATION_CODE_JS_RE = re.compile(r"[^'\"{}`]*")


def _map_interpolations(template: str, fn: Callable[[str], str],
                        js_templates: bool = False, simple_names: bool = False) -> str:
    """Apply fn to the code inside each ${...} of a backtick literal token (or,
    with simple_names, of a Kotlin string, where $name is code too) and keep
    the literal text around it verbatim. Braces inside quoted strings in that
    code do not count towards finding the closing brace, nor, with js_templates,
    braces inside a nested template literal."""
    code_re = _INTERPOLATION_CODE_JS_RE if js_templates else _INTERPOLATION_CODE_RE
    text_re = _DQ_TEMPLATE_TEXT_RE if simple_names else _TEMPLATE_TEXT_RE
    out = [template[0]]
    dead: dict[str, int] = {}
    end = len(template) - 1          # the closing backtick or quote
    i = 1
    while True:
        j = text_re.match(template, i, end).end()
        if simple_names and j < end and not template.startswith("${", j, end):
            out.append(template[i:j + 1])
            name = _DQ_TEMPLATE_NAME_RE.match(template, j + 1, end)
            out.append(fn(name.group()))
            i = name.end()
            continue
        if not template.startswith("${", j, end):
            out.append(template[i:end])
            break
        out.append(template[i:j])
        body = k = j + 2
        depth = 0
        while (k := code_re.match(template, k, end).end()) < end:
            ch = template[k]
            if ch == "`":
                stop = _template_end(template, k)
                k = stop if 0 <= stop < end else end
                continue
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
    out.append(template[-1])
    return "".join(out)


# f-/t-string literal text up to the next replacement field: {{ and }} are
# escaped braces, and outside a raw string \N{...} is a named character escape.
_FIELD_TEXT_RE = re.compile(r"(?:[^{}\\]|\{\{|\}\}|\\N\{[^}\n]*\}|\\[^{}]|\\)*")
_FIELD_TEXT_RAW_RE = re.compile(r"(?:[^{}]|\{\{|\}\})*")
# Expression code inside a replacement field, up to the next character that can
# open a string, change the bracket depth, or end the expression.
_FIELD_CODE_RE = re.compile(r"[^'\"()\[\]{}!:]*")
# A conversion (!r, !s, !a) up to the format spec or the closing brace.
_FIELD_CONVERSION_RE = re.compile(r"![^:{}]*")
# Format-spec text up to a nested field or the closing brace.
_FIELD_SPEC_RE = re.compile(r"[^{}]*")
# Python nests replacement fields in a format spec at most two deep.
_FIELD_MAX_DEPTH = 2


def _map_field(lit: str, i: int, end: int, fn: Callable[[str], str],
               dead: dict[str, int], nest: int) -> tuple[str, int] | None:
    """Rewrite the replacement field opening at lit[i] == "{": fn on the
    expression and on any expression nested in its format spec, the conversion
    and format-spec text verbatim. Returns (rewritten field, index after it), or
    None when the field does not close before `end`."""
    k = body = i + 1
    depth = 0
    while True:
        k = _FIELD_CODE_RE.match(lit, k, end).end()
        if k >= end:
            return None
        ch = lit[k]
        if ch in "'\"":
            stop = _span_end(lit, k, ch, dead, end)
            if stop < 0:
                return None
            k = stop
            continue
        if ch in "([{":
            depth += 1
        elif depth:
            if ch in ")]}":
                depth -= 1
        elif ch == "}" or ch == ":" or (ch == "!" and not lit.startswith("!=", k)):
            break
        k += 1
    parts = ["{", fn(lit[body:k])]
    if lit[k] == "!":
        stop = _FIELD_CONVERSION_RE.match(lit, k, end).end()
        parts.append(lit[k:stop])
        k = stop
    if k < end and lit[k] == ":":
        parts.append(":")
        k += 1
        while k < end:
            stop = _FIELD_SPEC_RE.match(lit, k, end).end()
            parts.append(lit[k:stop])
            k = stop
            if k >= end or lit[k] == "}":
                break
            if nest >= _FIELD_MAX_DEPTH:
                return None
            nested = _map_field(lit, k, end, fn, dead, nest + 1)
            if nested is None:
                return None
            parts.append(nested[0])
            k = nested[1]
    if k >= end or lit[k] != "}":
        return None
    parts.append("}")
    return "".join(parts), k + 1


def _map_fields(tok: str, prefix: int, fn: Callable[[str], str]) -> str:
    """Apply fn to the expressions in each replacement field of an f-/t-string
    token (prefix and quotes included) and keep its literal text verbatim. A
    field that does not close leaves the rest of the literal verbatim."""
    quote = tok[prefix:prefix + 3] if tok.startswith(('"""', "'''"), prefix) else tok[prefix]
    if len(tok) < prefix + 2 * len(quote):
        return tok
    text_re = _FIELD_TEXT_RAW_RE if "r" in tok[:prefix].lower() else _FIELD_TEXT_RE
    out = [tok[:prefix + len(quote)]]
    dead: dict[str, int] = {}
    end = len(tok) - len(quote)
    i = prefix + len(quote)
    while i < end:
        j = text_re.match(tok, i, end).end()
        out.append(tok[i:j])
        if j >= end:
            break
        if tok[j] == "}":
            # A lone } (not valid Python): keep it and carry on.
            out.append("}")
            i = j + 1
            continue
        field = _map_field(tok, j, end, fn, dead, 1)
        if field is None:
            out.append(tok[j:end])
            break
        out.append(field[0])
        i = field[1]
    out.append(tok[end:])
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
    # Go predeclared types and builtins, and TS primitive types: the language's
    # own names, as L1 spares them. Enciphered, `(id string) (Holding, error)`
    # read as three unknown types and hid every error-handling path.
    "string", "error", "byte", "rune", "uint", "uintptr", "any", "comparable",
    "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
    "float32", "float64", "complex64", "complex128",
    "append", "make", "cap", "panic", "recover", "iota",
    "number", "boolean", "bigint", "symbol", "unknown", "never", "undefined",
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
def _spared_words(crumb_level: int, lexer: _Lexer = _DEFAULT_LEXER) -> frozenset[str]:
    """The fixed word lists kept as-is at this crumb level, for this language."""
    words = _BASELINE_KEYWORDS | lexer.keywords
    if crumb_level >= 1:
        words |= _STDLIB_NAMES | lexer.builtins
    if crumb_level >= 2:
        words |= _GENERIC_DOMAIN_NOUNS
    return words


def _should_skip(token: str, crumb_level: int, lexer: _Lexer = _DEFAULT_LEXER) -> bool:
    if token in _spared_words(crumb_level, lexer):
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
    lexer = _lexer_for(options)
    reserved = _spared_words(crumb_level, lexer)
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
    flat = dataclasses.replace(lexer, js_templates=False)

    nesting = 0

    def substitute_code(code: str) -> str:
        """Encipher the code inside a ${...} or an f-string field. Past
        _MAX_NESTING levels a nested template ends at its first backtick, which
        bounds the recursion on adversarial input."""
        nonlocal nesting
        nesting += 1
        try:
            return _substitute(code, replace, lexer if nesting < _MAX_NESTING else flat)
        finally:
            nesting -= 1

    def replace(tok: str) -> str:
        nonlocal skipped, replaced, collisions, non_ascii
        first = tok[0]
        if first == "`" and "${" in tok and lexer.backtick_interpolation:
            return _map_interpolations(tok, substitute_code, lexer.js_templates)
        if first == '"' and lexer.dq_templates and "$" in tok and len(tok) > 1:
            return _map_interpolations(tok, substitute_code, simple_names=True)
        if first in "fFtTrR" and (head := _FIELD_HEAD_RE.match(tok)):
            return _map_fields(tok, head.end(), substitute_code)
        # Strings, comments and numbers: pass through verbatim
        if not (first.isalpha() or first == "_"):
            return tok
        if _should_skip(tok, crumb_level, lexer):
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

    output = _substitute(input, replace, lexer)

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
        "lexer": lexer.name,
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
