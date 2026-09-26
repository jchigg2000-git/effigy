"""Post-condition for husk output: is this a husk, or is it the input?

`llm-translation` sometimes returned its input nearly unchanged and reported
success. Measured at 3 of 12 file-observations under the pre-2026-08-19 prompt —
one file came back byte-identical except for a single word. Nothing in the
response distinguished that from a real husk, so a caller received their own
source code believing it had been anonymised. That is a privacy failure, and it
is a failure the caller cannot detect: they do not have the husker's output to
compare against, they only have what came back.

The prompt rewrite removed every observed instance (0 of 132 file-observations
since). This module exists because that is not the same as the failure being
impossible: a different model, a higher temperature, a longer input, or a future
prompt edit can bring it back, and prompting demonstrably cannot be relied on to
enforce a property (see evals/runs/20260819-prompt-fix-32b/RATCHET.md — a
document ID named explicitly in the prompt survived 18 runs of 18).

So the service checks its own output and fails closed.

Underscore-prefixed so the solutions loader imports it without expecting a
@register. Deliberately dependency-free and importable by file path, so the
offline scorer in evals/ uses this exact implementation rather than a second one
that can drift from it.
"""

from __future__ import annotations

import builtins
import difflib
import keyword
import os
import re

# Above this size difflib's ratio gets expensive and the cheaper line-level
# signals are sufficient on their own; ratio is reported as None.
_RATIO_MAX_CHARS = 200_000
# Between this size and the cap above, the exact character ratio costs seconds
# to minutes of CPU per attempt. check() then computes it only when its cheap
# upper bound (quick_ratio) could reach the threshold; below that the trigger
# cannot fire, so skipping it changes no verdict.
_RATIO_EXACT_CHARS = 30_000

_TRIPLE = ("'''", '"""')
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")

# Names the husker is TOLD to keep — the language and its libraries own them.
# Counting these as "retained" would read a faithful husk as an untransformed
# one. Kept in sync with evals/score_husk.py by being the same object.
_NOT_CONTENT = set(keyword.kwlist) | set(dir(builtins)) | {
    "self", "cls", "args", "kwargs", "annotations", "__future__", "__init__",
    "__str__", "__repr__", "__name__", "__main__", "dataclass", "dataclasses",
    "field", "datetime", "timedelta", "timezone", "sqlite3", "json", "pathlib",
    "Path", "typing", "Optional", "Iterable", "Sequence", "Iterator",
    "Callable", "argparse", "logging", "Logger", "collections", "defaultdict",
    "namedtuple", "itertools", "functools", "contextlib", "hashlib", "sha256",
    "time", "math", "random", "textwrap", "unicodedata", "requests",
    "append", "extend", "strip", "rstrip", "lstrip", "split", "splitlines",
    "join", "format", "encode", "decode", "lower", "upper", "startswith",
    "endswith", "replace", "keys", "values", "items", "fetchone", "fetchall",
    "execute", "executemany", "cursor", "conn", "commit", "close", "read",
    "read_text", "write", "write_text", "utf-8", "isoformat", "utcnow",
    "SELECT", "FROM", "WHERE", "ORDER", "LIMIT", "DESC", "ASC", "INSERT",
    "INTO", "VALUES", "UPDATE", "GROUP", "NULL", "AND", "NOT", "LEFT", "JOIN",
    "CREATE", "TABLE", "EXISTS", "INTEGER", "TEXT", "PRIMARY",
}

_C_FAMILY = {".go", ".ts", ".tsx", ".js", ".java", ".c", ".cc", ".cpp", ".rs"}


class PassthroughDetected(RuntimeError):
    """The husk is substantially its own input. Raised instead of returning it.

    Carries the measurements as `.report` so callers act on structured reasons
    rather than parsing the message text.
    """

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


def strip_prose(text: str, suffix: str = ".py") -> list[str]:
    """The code lines of `text`: no comments, docstrings, or blanks.

    A documented heuristic, not a parser — husks routinely fail to parse, and a
    check that crashes on the worst output is a check that only sees good output.
    """
    out: list[str] = []
    in_block: str | None = None
    c_family = suffix in _C_FAMILY
    for raw in text.splitlines():
        line = raw.strip()
        if in_block is not None:
            if in_block in line:
                in_block = None
            continue
        if not line:
            continue
        if c_family:
            if line.startswith("//"):
                continue
            if line.startswith("/*"):
                if "*/" not in line:
                    in_block = "*/"
                continue
            if line.startswith("*"):
                continue
        else:
            if line.startswith("#"):
                continue
            # A triple-quoted block can open anywhere on the line, not only at
            # its start: `SCHEMA = """CREATE TABLE ...` is the common case.
            kept, rest = [], line
            while rest:
                hits = [(rest.find(q), q) for q in _TRIPLE if q in rest]
                if not hits:
                    kept.append(rest)
                    break
                idx, delim = min(hits)
                kept.append(rest[:idx])
                after = rest[idx + 3:]
                end = after.find(delim)
                if end == -1:
                    in_block = delim
                    rest = ""
                else:
                    rest = after[end + 3:]
            line = "".join(kept).strip()
            if not line:
                continue
        if "#" in line and not c_family and '"' not in line and "'" not in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
        if "//" in line and c_family and '"' not in line and "`" not in line:
            line = line.split("//", 1)[0].strip()
            if not line:
                continue
        out.append(line)
    return out


def content_idents(code_lines: list[str]) -> set[str]:
    """Identifiers a husker is expected to REPLACE — everything the language and
    its standard libraries do not own."""
    out: set[str] = set()
    for line in code_lines:
        out.update(m.group(0) for m in _IDENT.finditer(line))
    return out - _NOT_CONTENT


# A span shorter than this is boilerplate an honest husk repeats anyway — an
# import line, a `return None`. Five consecutive lines is not.
SPAN_MIN = 5


def copied_spans(src_code: list[str], husk_code: list[str],
                 min_run: int = SPAN_MIN) -> list[int]:
    """Sizes of every run of `min_run`+ consecutive code lines the husk carries
    over from the source unchanged.

    The LONGEST such run is not the whole story, and assuming it was is a defect
    this module shipped with. Copying distributes: one husk returned 66% of its
    source — 72 lines — in spans of 5 to 14, and a longest-run trigger set at 20
    saw nothing wrong with it.
    """
    return [b.size for b in _line_blocks(src_code, husk_code) if b.size >= min_run]


def _line_blocks(src_code: list[str], husk_code: list[str]) -> list:
    """In-order runs of identical code lines. The one line-level diff that both
    span measures read; inspect() builds it once rather than once per measure."""
    return difflib.SequenceMatcher(
        None, src_code, husk_code, autojunk=False).get_matching_blocks()


def longest_identical_run(src_code: list[str], husk_code: list[str]) -> int:
    """Longest run of consecutive code lines the husk shares with the source, in
    order.

    The sharpest passthrough signal by a distance. A faithful husk repeats
    boilerplate — an import block, a chain of `))` — so its runs are short. A
    file that was never transformed carries the whole body across in one
    unbroken run. Unlike the ratio and retention signals, it does not degrade on
    files that are mostly structure.
    """
    if not src_code or not husk_code:
        return 0
    return max(b.size for b in _line_blocks(src_code, husk_code))


def inspect(source: str, husk: str, suffix: str = ".py",
            ratio_floor: float | None = None) -> dict:
    """Measure how much of `source` survived into `husk`. No verdict, just facts.

    `ratio_floor` is what check() passes: the ratio threshold it will compare
    against. Above _RATIO_EXACT_CHARS the exact ratio is then only computed when
    its upper bound can reach the floor, and is otherwise reported as None with
    the bound alongside. Callers that omit it get the exact ratio, as before.
    """
    src_code = strip_prose(source, suffix)
    husk_code = strip_prose(husk, suffix)

    src_idents = content_idents(src_code)
    retention = (len(src_idents & content_idents(husk_code)) / len(src_idents)
                 if src_idents else 0.0)

    src_lines = set(src_code)
    verbatim = sum(1 for ln in husk_code if ln in src_lines)
    blocks = _line_blocks(src_code, husk_code)
    run = max(b.size for b in blocks) if src_code and husk_code else 0
    spans = [b.size for b in blocks if b.size >= SPAN_MIN]
    copied = sum(spans)

    ratio: float | None = None
    upper: float | None = None
    size = max(len(source), len(husk))
    if size <= _RATIO_MAX_CHARS:
        sm = difflib.SequenceMatcher(None, source, husk)
        if ratio_floor is not None and size > _RATIO_EXACT_CHARS:
            upper = sm.quick_ratio()
            # Compared rounded, as the trigger compares the rounded ratio.
            if round(upper, 3) >= ratio_floor:
                ratio, upper = sm.ratio(), None
        else:
            ratio = sm.ratio()

    report = {
        "src_code_lines": len(src_code),
        "husk_code_lines": len(husk_code),
        "similarity_ratio": round(ratio, 3) if ratio is not None else None,
        "ident_retention": round(retention, 3),
        "code_verbatim": round(verbatim / len(husk_code), 3) if husk_code else 1.0,
        "longest_identical_run": run,
        "longest_identical_run_share": round(run / len(src_code), 3) if src_code else 0.0,
        "copied_spans": len(spans),
        "copied_span_lines": copied,
        "copied_span_share": round(copied / len(src_code), 3) if src_code else 0.0,
    }
    if upper is not None:
        report["similarity_ratio_upper_bound"] = round(upper, 3)
    return report


# Go stdlib path roots, used only to tell an own-module import from a stdlib one.
_GO_STDLIB_ROOTS = frozenset("""
archive bufio builtin bytes cmp compress container context crypto database
debug embed encoding errors expvar flag fmt go hash html image index io iter
log maps math mime net os path plugin reflect regexp runtime slices sort
strconv strings structs sync syscall testing text time unicode unsafe weak
""".split())

# Module names too generic to be evidence of anything. A husk legitimately
# containing the word "api" is not leaking its caller's identity.
_GENERIC_MODULE_NAMES = frozenset("""
app api src lib pkg internal cmd main core common util utils shared server
client service handler model store data test tests build dist vendor project
backend frontend web http json
""".split())

_GO_IMPORT_LINE = re.compile(r'^\s*(?:_\s+|\.\s+|[A-Za-z_]\w*\s+)?"([^"]+)"\s*$', re.M)

# Every Go file opens with a package clause, and it is the one line a Go file
# cannot omit: types-only files have no `func`, and long import or const blocks
# can push the first one far down. The optional trailing comment admits the
# legal `package math // import "math"` form. Java's `package a.b;` does not match.
_GO_PACKAGE_CLAUSE = re.compile(r"(?m)^package\s+[A-Za-z_]\w*\s*(?://.*)?$")


def has_go_package_clause(text: str) -> bool:
    """True when `text` carries a Go package clause, whatever it was labelled."""
    return _GO_PACKAGE_CLAUSE.search(text) is not None


def own_module_names(source: str, suffix: str = ".py") -> set[str]:
    """Module names the INPUT imports from itself.

    In a Go service the module name is the repository's own name, which is
    routinely the most identifying token in the whole file — in this project's
    corpus it is literally the domain label. llm_translation.py's system prompt
    already requires these to be renamed ("Imports of the input's OWN modules
    ARE renamed"); this is the mechanical enforcement of that sentence, because
    prompt-only enforcement of an invariant is the category error the working
    paper names.

    Deliberately Go-only and deliberately conservative: an import path whose
    first segment contains a dot is third-party, one in the stdlib root set is
    stdlib, and a generic first segment is not evidence.

    The one exception is a host-prefixed path (github.com/org/repo/...) with an
    `internal` segment. The Go compiler refuses to import .../internal/... from
    outside the tree rooted at internal's parent, so such a path is the
    importer's own module whatever its host. Real modules are nearly always
    host-prefixed, and without this the check only ever saw bare module names.
    Only the org and repo segments are taken: deeper directories are too often
    generic words.
    """
    if suffix != ".go":
        return set()
    names = set()
    for m in _GO_IMPORT_LINE.finditer(source):
        segs = m.group(1).split("/")
        first = segs[0]
        if first in _GO_STDLIB_ROOTS:
            continue
        if "." in first:
            if "internal" in segs[1:]:
                for seg in segs[1:min(3, segs.index("internal", 1))]:
                    if "." not in seg and len(seg) >= 4 and seg.lower() not in _GENERIC_MODULE_NAMES:
                        names.add(seg)
            continue
        if len(first) >= 4 and first.lower() not in _GENERIC_MODULE_NAMES:
            names.add(first)
    return names


def _thresholds() -> dict:
    """Operator-overridable. Defaults are calibrated in
    evals/calibrate_postcondition.py against every husk this project has
    measured; do not change them without re-running it."""
    return {
        # An absolute run matters independently of file size: 20 consecutive
        # lines of the caller's source is 20 lines of the caller's source
        # whether the file is 200 lines or 2000.
        "run_lines": int(os.environ.get("HUSK_CHECK_RUN_LINES", "20")),
        "run_share": float(os.environ.get("HUSK_CHECK_RUN_SHARE", "0.15")),
        # Total copied, not just the longest run. Set at the 95th percentile of
        # husks the run triggers alone let through (median 9%, p90 30%): a husk
        # returning a third of the caller's source in contiguous spans is not a
        # husk, however finely the copying is divided.
        "copied_share": float(os.environ.get("HUSK_CHECK_COPIED_SHARE", "0.35")),
        "retention": float(os.environ.get("HUSK_CHECK_RETENTION", "0.92")),
        "ratio": float(os.environ.get("HUSK_CHECK_RATIO", "0.95")),
        "min_code_lines": int(os.environ.get("HUSK_CHECK_MIN_LINES", "12")),
        # Own-module import names must not survive. Unlike the triggers above
        # this is not a similarity heuristic with a tunable threshold — it is a
        # named requirement of the system prompt, so it is on or off.
        "module_names": os.environ.get("HUSK_CHECK_MODULE_NAMES", "1") not in ("0", "false", ""),
    }


def check(source: str, husk: str, suffix: str = ".py") -> dict:
    """Measure, then judge. Returns the report; raises PassthroughDetected when
    the husk is substantially its input.

    Three independent triggers, any of which fails the husk:

      * a single unbroken run of identical code lines — `run_lines` of them, or
        `run_share` of the source — which is direct evidence that a span of the
        input was copied out rather than rewritten;
      * `copied_share` of the source returned across ALL spans of 5+ lines,
        which catches the same failure distributed into pieces too small to trip
        the run trigger. This is the trigger that
        earns the module: partial passthrough, where a model translates the top
        of a file and copies the bottom, is invisible to every whole-file
        measure. One observed instance scored 0% domain-vocabulary retention and
        zero leak terms while returning 26 consecutive lines of the caller's
        source, including a live URL path inside a regex;
      * `retention` of the source's own identifiers surviving AND either a
        whole-text similarity above `ratio`, or at least `ratio` of the husk's
        code lines found verbatim in the source. The similarity half catches
        diffuse copying; it cannot catch reordering, because moving whole
        functions drives whole-text similarity down. The verbatim share ignores
        order, so a husk that is the source's own lines rearranged still fails.

    Files below `min_code_lines` are reported and never failed: at that size the
    input and any honest husk of it are similar for reasons that have nothing to
    do with passthrough, and a false positive here means refusing to serve a
    correct husk.
    """
    t = _thresholds()
    report = inspect(source, husk, suffix, ratio_floor=t["ratio"])
    report["thresholds"] = t

    # Checked before the size guard: a surviving module name is a leak outright,
    # not a similarity that small files trip by coincidence. A Go package clause
    # selects Go import rules whatever `suffix` says, so a caller that guessed the
    # language wrong does not silently switch this check off.
    mod_suffix = ".go" if has_go_package_clause(source) else suffix
    leaked = sorted(n for n in own_module_names(source, mod_suffix)
                    if re.search(rf"\b{re.escape(n)}\b", husk, re.I)) if t["module_names"] else []
    report["leaked_module_names"] = leaked
    if leaked:
        report["verdict"] = "module_name_leak"
        report["reasons"] = [
            "the input's own module name" + ("s " if len(leaked) > 1 else " ")
            + ", ".join(repr(n) for n in leaked)
            + (" survive" if len(leaked) > 1 else " survives") + " in the output"
        ]
        raise PassthroughDetected(
            "husk rejected: " + report["reasons"][0]
            + ". The system prompt requires imports of the input's own modules to be renamed, and a "
              "module name is routinely the single most identifying token in a file. Retry, or "
              "disable this check deliberately via HUSK_CHECK_MODULE_NAMES=0.",
            report,
        )

    if report["src_code_lines"] < t["min_code_lines"]:
        report["verdict"] = "too_small_to_judge"
        return report

    reasons = []
    if (report["longest_identical_run"] >= t["run_lines"]
            or report["longest_identical_run_share"] >= t["run_share"]):
        reasons.append(
            f"{report['longest_identical_run']} consecutive code lines "
            f"({report['longest_identical_run_share']:.0%} of the input) are identical to the input")
    if report["copied_span_share"] >= t["copied_share"]:
        reasons.append(
            f"{report['copied_span_lines']} code lines "
            f"({report['copied_span_share']:.0%} of the input) are returned unchanged "
            f"across {report['copied_spans']} spans")
    if report["ident_retention"] >= t["retention"]:
        if report["similarity_ratio"] is not None and report["similarity_ratio"] >= t["ratio"]:
            reasons.append(
                f"{report['ident_retention']:.0%} of the input's identifiers survive "
                f"and the texts are {report['similarity_ratio']:.0%} similar")
        elif report["code_verbatim"] >= t["ratio"]:
            reasons.append(
                f"{report['ident_retention']:.0%} of the input's identifiers survive "
                f"and {report['code_verbatim']:.0%} of the output's code lines appear "
                f"verbatim in the input, in whatever order")

    if reasons:
        report["verdict"] = "passthrough"
        report["reasons"] = reasons
        raise PassthroughDetected(
            "husk rejected: the output is substantially its own input — "
            + "; ".join(reasons)
            + ". Returning it would hand the caller their own source code labelled "
              "as anonymised. Retry, or raise the thresholds deliberately via "
              "HUSK_CHECK_* if this input is genuinely mostly boilerplate.",
            report,
        )

    report["verdict"] = "ok"
    return report
