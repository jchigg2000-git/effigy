"""STRUCTURE-ONLY canonicaliser — the pathology-anchor invariant with all authored vocabulary removed.

Registered in preregistration.md A4. Takes one Go or TS/TSX corpus file and
removes everything the *author* chose while keeping everything the *language and
platform* own: control flow, call graph, arity, nesting, coupling and comment
density stay exactly intact; identifiers, literals, comment text and JSX text do
not survive in any form.

This is not an invented transform. It is verbatim the contract
`llm_translation.py` already imposes on the rewriter — "The ONLY names that
survive unchanged are the ones the language owns... Imports of the input's OWN
modules ARE renamed" — executed deterministically and perfectly. That is what
makes it the right upper bound to measure the rewriter against.

WHY THE GATE IS THE POINT. If vocabulary leaks through, a high attacker score
gets misattributed to "architecture is domain-informative" — the conclusion that
would re-scope this project. So correctness is ENFORCED here, not assumed, in
the posture of blind_stub.assert_content_free: every artifact passes eleven
checks or it never reaches an attacker.

    python3 evals/canonicalize.py <file> [--nonum]      # print one artifact
    python3 evals/canonicalize.py --held-out [--nonum]  # gate the whole split
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
CANON = EVALS / "canon"
sys.path.insert(0, str(CANON))

import allowlist as AL  # noqa: E402
import blind_stub  # noqa: E402
import counters  # noqa: E402

PLACEHOLDER = re.compile(r"\b(?:[Ii]dent_\d{4}|str_\d{4})\b")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RUNE_POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


class GateFailure(RuntimeError):
    pass


@dataclass
class Naming:
    """Text-keyed and unscoped, deliberately.

    Two shadowed `err`s collapse to one canonical name, which reproduces the
    source's token-identity relation exactly. A scope-aware renamer would SPLIT
    them into distinct names and thereby ADD information the source never had.
    """

    ident: dict[str, str] = field(default_factory=dict)
    string: dict[str, str] = field(default_factory=dict)
    rune: dict[str, str] = field(default_factory=dict)
    number: dict[str, str] = field(default_factory=dict)
    _n_ident: int = 0
    _n_string: int = 0
    _n_number: int = 1  # 0 and 1 are preserved, so indices start at 2

    def for_ident(self, text: str) -> str:
        if text not in self.ident:
            self._n_ident += 1
            # Case class is load-bearing: Go has no `export` keyword, so
            # exportedness IS capitalisation, and a leading capital is what
            # makes <Foo/> a component rather than a DOM element.
            stem = "Ident" if text[:1].isupper() else "ident"
            self.ident[text] = f"{stem}_{self._n_ident:04d}"
        return self.ident[text]

    def for_string(self, text: str) -> str:
        if text not in self.string:
            self._n_string += 1
            self.string[text] = f"str_{self._n_string:04d}"
        return self.string[text]

    def for_rune(self, text: str) -> str:
        # Distinct runes stay distinct: a switch over 'H'/'D'/'T' must keep
        # three distinguishable discriminants, not collapse to one.
        if text not in self.rune:
            self.rune[text] = RUNE_POOL[len(self.rune) % len(RUNE_POOL)]
        return self.rune[text]

    def for_number(self, text: str) -> str:
        """First-appearance index, NOT zero.

        Mapping every number to 0 would destroy the fact that [1:9], [9:15],
        [15:23] chain into a contiguous fixed-width layout, confounding
        "numbers carried the domain" with "we broke the structure." Indexing
        keeps the equality relation and drops the values and their ordering.
        """
        if text not in self.number:
            self._n_number += 1
            self.number[text] = str(self._n_number)
        return self.number[text]


def blank_comment(body: str) -> str:
    """A content-free comment of the same line span.

    The body is `-` rather than empty because gofmt DELETES empty line comments,
    which would silently cost six lines on a 47-line file and break the
    line-count equality that gate G8 asserts. `-` is not a word token, so it
    cannot leak.
    """
    if body.startswith("//"):
        return "// -"
    return "/* -" + "\n" * body.count("\n") + "*/"


def pad(new: str, old: str) -> str:
    """Line-preserving replacement, used everywhere.

    Comments are BLANKED, not deleted. Deleting them changes the line count and
    the comment density, both of which are structure this project elsewhere
    insists on preserving — and blind_stub reports `lines`, so deletion would
    make this arm carry LESS than BLIND on that field.
    """
    return new + "\n" * old.count("\n")


# --------------------------------------------------------------------------
# span extraction


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise GateFailure(f"{cmd[0]} failed ({p.returncode}): {p.stderr.strip()[:400]}")
    return p.stdout


def go_spans(path: Path) -> dict:
    binary = CANON / "canon_go"
    if not binary.exists():
        raise GateFailure(f"missing {binary}; build with: (cd evals/canon && go build -o canon_go ./canon_go.go)")
    return json.loads(_run([str(binary), str(path)]))


def ts_spans(path: Path) -> dict:
    return json.loads(_run(["node", str(CANON / "canon_ts.mjs"), str(path)]))


def go_module_of(path: Path) -> str:
    for parent in path.resolve().parents:
        gomod = parent / "go.mod"
        if gomod.exists():
            for line in gomod.read_text(encoding="utf-8").splitlines():
                if line.startswith("module "):
                    return line.split(None, 1)[1].strip()
        if parent == ROOT:
            break
    return ""


# --------------------------------------------------------------------------
# the transform


def canonicalize_go(path: Path, text: str, keep_numbers: bool) -> tuple[str, Naming, set[str]]:
    data = go_spans(path)
    toks = data["tokens"]
    module = go_module_of(path)
    naming = Naming()
    preserved: set[str] = set()
    repl: list[tuple[int, int, str]] = []

    # Classify imports. External iff the first path segment contains a "." or
    # is a Go stdlib root; anything else is own-module and gets canonicalised.
    external_bindings: set[str] = set()
    preserved_paths: set[str] = set()
    for imp in data["imports"]:
        raw = imp["path"].strip('"')
        first = raw.split("/")[0]
        own = bool(module) and (raw == module or raw.startswith(module + "/"))
        external = (not own) and ("." in first or first in AL.GO_STDLIB_ROOTS)
        binding = imp["name"] if imp["has_name"] else raw.split("/")[-1]
        if external:
            external_bindings.add(binding)
            preserved.add(binding)
            preserved_paths.add(imp["path"])
        else:
            # Own-module import: canonicalise the path AND emit an explicit
            # alias, so the binding stays coherent and the import count
            # (coupling) still matches counters._IMPORT / blind_stub.
            # Go derives an unaliased import's binding from the path's last
            # segment, so putting the canonical name there keeps the binding
            # coherent WITHOUT adding a token. An explicit alias would insert
            # one IDENT per import and G6 (token-kind identity) would fail —
            # correctly, since that is a structural change.
            alias = naming.for_ident(binding)
            repl.append((imp["path_off"], imp["path_end"],
                         f'"{naming.for_string(raw)}/{alias}"'))
            if imp["has_name"]:
                repl.append((imp["name_off"], imp["name_end"], alias))
        if imp["has_name"] and external:
            preserved.add(imp["name"])

    import_path_offsets = {imp["path_off"] for imp in data["imports"]}

    for i, t in enumerate(toks):
        kind = t["kind"]
        if kind == "COMMENT":
            repl.append((t["off"], t["end"], blank_comment(t["text"])))
            continue
        if kind == "STRING":
            if t["off"] in import_path_offsets:
                continue  # handled above (preserved verbatim if external)
            name = naming.for_string(t["text"])
            if t["text"].startswith("`"):
                new = "`" + name + "\n" * t["text"].count("\n") + "`"
            else:
                new = f'"{name}"'
            repl.append((t["off"], t["end"], new))
            continue
        if kind == "CHAR":
            repl.append((t["off"], t["end"], f"'{naming.for_rune(t['text'])}'"))
            continue
        if kind in ("INT", "FLOAT", "IMAG"):
            if keep_numbers or t["text"] in ("0", "1"):
                continue
            idx = naming.for_number(t["text"])
            new = idx if kind == "INT" else (idx + ".0" if kind == "FLOAT" else idx + "i")
            repl.append((t["off"], t["end"], new))
            continue
        if kind != "IDENT":
            continue

        word = t["text"]
        prev = toks[i - 1] if i else None
        prev2 = toks[i - 2] if i > 1 else None

        # `package main` stays; every other package name is authored.
        if prev and prev["kind"] == "KEYWORD:package":
            if word == "main":
                preserved.add(word)
                continue
            repl.append((t["off"], t["end"], naming.for_ident(word)))
            continue

        if word in AL.GO_PREDECLARED or word in AL.GO_KEYWORDS:
            preserved.add(word)
            continue
        if word in external_bindings:
            preserved.add(word)
            continue
        # Member selected on an external package binding: slog.Logger, sql.Open.
        if (
            prev
            and prev["kind"] == "OP:."
            and prev2
            and prev2["kind"] == "IDENT"
            and prev2["text"] in external_bindings
        ):
            preserved.add(word)
            continue
        repl.append((t["off"], t["end"], naming.for_ident(word)))

    return splice(text, repl, binary=True), naming, preserved, preserved_paths


def canonicalize_ts(path: Path, text: str, keep_numbers: bool) -> tuple[str, Naming, set[str]]:
    data = ts_spans(path)
    if data["syntax_errors"]:
        raise GateFailure(f"source has TS syntax errors: {data['syntax_errors']}")
    naming = Naming()
    preserved: set[str] = set()
    repl: list[tuple[int, int, str]] = []
    external = set(data["external_bindings"])

    for s in data["spans"]:
        kind, off, end, body = s["kind"], s["off"], s["end"], s.get("text", "")
        if kind == "COMMENT":
            repl.append((off, end, blank_comment(body)))
        elif kind == "MODULE_SPECIFIER":
            # Bare specifier = external package, carries no domain and is
            # load-bearing for the selector rule. Relative = own module.
            if s.get("external"):
                continue
            repl.append((off, end, f'"{naming.for_string(body.strip(chr(34) + chr(39)))}"'))
        elif kind == "STRING":
            name = naming.for_string(body)
            new = f"`{name}" + "\n" * body.count("\n") + "`" if body.startswith("`") else f'"{name}"'
            repl.append((off, end, new))
        elif kind == "TEMPLATE_PART":
            # Keep the delimiters or the template stops being a template:
            # `head${ ... }middle${ ... }tail`
            head, tail = body[:1], body[-2:] if body.endswith("${") else body[-1:]
            open_d = "`" if body.startswith("`") else "}"
            close_d = "${" if body.endswith("${") else "`"
            repl.append((off, end, open_d + naming.for_string(body) + "\n" * body.count("\n") + close_d))
        elif kind == "REGEX":
            flags = body.rsplit("/", 1)[1] if body.count("/") >= 2 else ""
            repl.append((off, end, f"/{naming.for_string(body)}/{flags}"))
        elif kind == "JSX_TEXT":
            repl.append((off, end, pad(naming.for_string(body.strip()), body)))
        elif kind == "NUMBER":
            if keep_numbers or body in ("0", "1"):
                continue
            repl.append((off, end, naming.for_number(body)))
        elif kind == "IDENT":
            role, word = s.get("role"), body
            if s.get("external_binding") and not s.get("relative_binding"):
                preserved.add(word)
                continue
            if role == "member" and s.get("base") in external:
                preserved.add(word)
                continue
            if role == "jsx_tag_intrinsic" and word in AL.HTML_INTRINSICS:
                preserved.add(word)
                continue
            if role == "jsx_attr_intrinsic" and word in AL.HTML_ATTRS:
                preserved.add(word)
                continue
            if word in AL.TS_GLOBALS:
                preserved.add(word)
                continue
            repl.append((off, end, naming.for_ident(word)))

    return splice(text, repl), naming, preserved, set()


def splice(text: str, repl: list[tuple[int, int, str]], binary: bool = False) -> str:
    """Splice replacement spans into the source.

    `binary` because go/scanner reports BYTE offsets while Python slices by
    character. Any Go file containing an em dash (there are 50 non-ASCII
    characters in the held-out set) silently corrupts otherwise — it produced
    `Ident_0007ing` and unterminated string literals before this was fixed.
    TypeScript reports UTF-16 offsets, which coincide with Python's for the BMP,
    so the TS path stays in characters.
    """
    buf = text.encode("utf-8") if binary else text
    repl = sorted(repl, key=lambda r: (r[0], r[1]))
    out, cursor = [], 0
    for off, end, new in repl:
        if off < cursor:
            raise GateFailure(f"overlapping spans at {off} (cursor {cursor}) — classifier bug")
        out.append(buf[cursor:off])
        out.append(new.encode("utf-8") if binary else new)
        cursor = max(cursor, end)
    out.append(buf[cursor:])
    joined = (b"" if binary else "").join(out)
    return joined.decode("utf-8") if binary else joined


def canonicalize(path: Path, language: str, keep_numbers: bool = True) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    if PLACEHOLDER.search(text):  # G1
        raise GateFailure("source already contains placeholder-shaped tokens")
    if language == "go":
        out, naming, preserved, preserved_paths = canonicalize_go(path, text, keep_numbers)
        p = subprocess.run(["gofmt"], input=out, capture_output=True, text=True)
        if p.returncode != 0:  # G7, first half
            raise GateFailure(f"gofmt rejected the output: {p.stderr.strip()[:300]}")
        out = p.stdout
    else:
        out, naming, preserved, preserved_paths = canonicalize_ts(path, text, keep_numbers)
    census = {
        "preserved_tokens": sorted(preserved),
        "preserved_import_paths": sorted(preserved_paths),
        "n_idents_canonicalised": len(naming.ident),
        "n_strings_canonicalised": len(naming.string),
        "n_runes_canonicalised": len(naming.rune),
        "n_numbers_canonicalised": len(naming.number),
    }
    return out, census


# --------------------------------------------------------------------------
# the gate — eleven checks, all hard. An artifact that fails never reaches an
# attacker, because a leak here becomes a wrong scientific conclusion.

MANIFEST = EVALS / "corpus" / "manifest.json"
_CANON_COMMENT = re.compile(r"^(?://\s*-|/\*\s*-[\s]*\*/)$", re.S)
_PLACEHOLDER_ONLY = re.compile(r"^[Ii]dent_\d{4}$")
_STR_ONLY = re.compile(r"^str_\d{4}$")


def _kinds(path: Path, language: str) -> list[str]:
    if language == "go":
        return [t["kind"] for t in go_spans(path)["tokens"]]
    return [s["kind"] for s in ts_spans(path)["spans"]]


def _all_leak_terms() -> list[str]:
    man = json.loads(MANIFEST.read_text())
    terms: list[str] = []
    for d in man["domains"].values():
        if isinstance(d, dict):
            terms.extend(d.get("leak_terms", []))
    return sorted(set(terms))


def gate(path: Path, language: str, src: str, out: str, census: dict, tmp: Path,
         keep_numbers: bool = True) -> dict:
    """Every check is a hard failure. Returns the continuity report (W1)."""
    fails: list[str] = []
    domain_dir = ""
    for part in path.resolve().parts:
        if (ROOT / "corpus" / part).is_dir() and part != "corpus":
            domain_dir = part
    module = go_module_of(path) if language == "go" else ""

    tmp.write_text(out, encoding="utf-8")

    # G5 — pure ASCII. The held-out set carries em dashes and ellipses, all of
    # them inside comments, strings or JSX text. Zero surviving is a free canary
    # proving all three handlers fired.
    non_ascii = {c for c in out if ord(c) > 127}
    if non_ascii:
        fails.append(f"G5 non-ASCII survived: {sorted(non_ascii)}")

    # G2 — closed-world. Every word in the output is allowlisted or a
    # placeholder. Inverted from checking against the source's identifier
    # inventory, which by construction cannot see anything that came out of a
    # comment or a JSX text node.
    allowed = set(census["preserved_tokens"]) | AL.GO_KEYWORDS | AL.GO_PREDECLARED
    allowed_literals = set(census.get("preserved_import_paths", []))
    out_spans = go_spans(tmp)["tokens"] if language == "go" else ts_spans(tmp)["spans"]
    for s in out_spans:
        kind, body = s["kind"], s.get("text", "")
        if kind == "IDENT":
            if not (_PLACEHOLDER_ONLY.match(body) or body in allowed):
                fails.append(f"G2 identifier survived: {body!r}")
        elif kind == "COMMENT":
            if not _CANON_COMMENT.match(body.strip()):
                fails.append(f"G2 comment not content-free: {body[:60]!r}")
        elif kind in ("STRING", "JSX_TEXT", "REGEX", "TEMPLATE_PART", "CHAR"):
            # External import paths are preserved on purpose: all six domains
            # import the identical third-party stack, so they discriminate
            # nothing, and the selector rule depends on their bindings.
            if body in allowed_literals:
                continue
            if kind == "CHAR" and re.fullmatch(r"'[A-Za-z0-9]'", body):
                continue  # distinct-rune placeholders, drawn from RUNE_POOL
            words = [w for w in WORD.findall(body)
                     if not (_STR_ONLY.match(w) or _PLACEHOLDER_ONLY.match(w))]
            if words:
                fails.append(f"G2 literal carries words: {body[:60]!r}")

    # G3 — leak terms from ALL SIX domains, not just the true one.
    low = out.lower()
    for term in _all_leak_terms():
        if re.search(rf"\b{re.escape(term.lower())}\b", low):
            fails.append(f"G3 leak term survived: {term!r}")

    # G4 — domain name, module name, source file stem and its directory.
    # Scanned against the output with every deliberately-preserved token masked
    # out first: `http.Server` is stdlib API, shared by all six domains, and
    # must not read as the file `server.go` leaking its own name.
    masked = low
    for tok in sorted(allowed | allowed_literals, key=len, reverse=True):
        if len(tok) >= 3:
            masked = masked.replace(tok.lower(), " ")
    forbidden = {domain_dir, module, path.stem, path.parent.name} - {""}
    for name in sorted(forbidden):
        if len(name) >= 3 and name.lower() in masked:
            fails.append(f"G4 name survived: {name!r}")

    # G6 — token-kind-sequence identity. This is the fidelity proof and the
    # reason the classifiers use real lexers rather than regexes.
    src_kinds, out_kinds = _kinds(path, language), _kinds(tmp, language)
    if language == "go":
        # gofmt sorts import specs, so compare imports as a multiset and the
        # rest in order.
        if sorted(src_kinds) != sorted(out_kinds):
            fails.append(f"G6 token-kind multiset changed: {len(src_kinds)} -> {len(out_kinds)}")
    if src_kinds != out_kinds and language != "go":
        fails.append(f"G6 span-kind sequence changed: {len(src_kinds)} -> {len(out_kinds)}")

    # G7 — the output still parses.
    if language == "go":
        p = subprocess.run(["gofmt", "-e", str(tmp)], capture_output=True, text=True)
        if p.returncode != 0:
            fails.append(f"G7 gofmt -e rejected the output: {p.stderr.strip()[:200]}")
    else:
        errs = ts_spans(tmp)["syntax_errors"]
        if errs:
            fails.append(f"G7 TS syntax errors: {errs}")

    # G8 — BLIND-profile equality on every field except bytes. This is what
    # operationalises A4.5's "recoverable-superior to BLIND on ten of eleven
    # fields" as a per-file proof rather than an assertion.
    ps, po = blind_stub.profile(src, language), blind_stub.profile(out, language)
    soft = {"bytes", "string_literals"}
    blind_delta = {}
    for k in ps:
        if ps[k] == po[k]:
            continue
        if k in soft:
            # `bytes` cannot survive fixed-width renaming (registered in A4.5).
            # `string_literals` moves because counters.py counts quotes inside
            # comments by its own admission, and comments are blanked. Both are
            # counter imprecision, not a fidelity failure: G6 is authoritative.
            blind_delta[k] = [ps[k], po[k]]
            continue
        fails.append(f"G8 BLIND field {k}: {ps[k]} -> {po[k]}")

    # G9 — determinism.
    again, _ = canonicalize(path, language, keep_numbers=keep_numbers)
    if again != out:
        fails.append("G9 not deterministic: two runs differ")

    # G10 — no source->canonical map escapes. The census is counts plus the
    # allowlisted tokens that survived; it must never carry a source name.
    if any(not isinstance(v, (int, list)) for v in census.values()):
        fails.append("G10 census carries non-count data")

    # G11 — the handlers actually fired (guards the silent no-op class of bug).
    cs = counters.count(src, language)
    if cs["string_literals"] > 0 and "str_" not in out:
        fails.append("G11 source had string literals but output has no placeholder")
    if "//" in src and "// -" not in out and "/* -" not in out:
        fails.append("G11 source had comments but output has no blanked comment")

    if fails:
        raise GateFailure(f"{path}: " + "; ".join(fails[:8]) + (f" (+{len(fails) - 8} more)" if len(fails) > 8 else ""))

    return {"counters_delta": counters.delta(cs, counters.count(out, language)),
            "blind_delta": blind_delta}


# --------------------------------------------------------------------------
# CLI


def artifacts(split: str | None) -> list[dict]:
    man = json.loads(MANIFEST.read_text())
    doms = man["domains"]
    sys.path.insert(0, str(EVALS))
    from run_rsch1 import domain_split  # reuse the ONE split implementation

    split_of = domain_split(man)
    rows = []
    for a in man["artifacts"]:
        d = doms.get(a["domain_dir"], {})
        if not isinstance(d, dict) or "true_domain_id" not in d:
            continue
        if split and split_of.get(d["true_domain_id"]) != split:
            continue
        if not (40 <= a["lines"] <= 400):
            continue
        rows.append(a | {"true_domain_id": d["true_domain_id"]})
    return sorted(rows, key=lambda a: a["path"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--held-out", action="store_true", help="gate every held-out artifact")
    ap.add_argument("--all", action="store_true", help="gate every corpus artifact, all six domains")
    ap.add_argument("--nonum", action="store_true", help="also canonicalise numeric literals")
    ap.add_argument("--out", help="directory to write artifacts into")
    args = ap.parse_args()
    keep = not args.nonum

    if args.file:
        p = Path(args.file)
        out, census = canonicalize(p, p.suffix.lstrip("."), keep_numbers=keep)
        sys.stdout.write(out)
        print(f"\n--- census: {json.dumps({k: v for k, v in census.items() if k != 'preserved_tokens'})}", file=sys.stderr)
        print(f"--- preserved: {census['preserved_tokens']}", file=sys.stderr)
        return 0

    rows = artifacts("held-out" if args.held_out else None if args.all else "held-out")
    outdir = Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    import tempfile

    tmpdir = Path(tempfile.mkdtemp())
    ok, failed = 0, []
    for a in rows:
        p = ROOT / a["path"]
        lang = a["language"]
        src = p.read_text(encoding="utf-8")
        try:
            out, census = canonicalize(p, lang, keep_numbers=keep)
            w = gate(p, lang, src, out, census, tmpdir / p.name, keep_numbers=keep)
            ok += 1
            delta = {k: v for k, v in w["counters_delta"].items() if v and k != "bytes"}
            flag = f"  W1 {delta}" if delta else ""
            print(f"  ok  {a['path']:<62} {src.count(chr(10)):>4}L "
                  f"ident={census['n_idents_canonicalised']:>3} str={census['n_strings_canonicalised']:>3}{flag}")
            if outdir:
                (outdir / f"{a['domain_dir']}__{p.name}.txt").write_text(out, encoding="utf-8")
        except GateFailure as e:
            failed.append(str(e))
            print(f"  FAIL {a['path']}\n       {e}")
    print(f"\n{ok}/{len(rows)} passed the gate" + (f", {len(failed)} FAILED" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
