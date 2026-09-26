"""Gate checks that fired on correct output: regex flags (G2), braces inside literals (G8), and a
`//` that is not a comment (G11). Each must pass without loosening the check it belongs to.
"""
import shutil

import pytest

import canonicalize as C

HAS_TS = bool(shutil.which("node")) and (C.ROOT / "corpus/stacks/app/node_modules/typescript").is_dir()
HAS_GO = (C.CANON / "canon_go").exists() and bool(shutil.which("gofmt"))

# A callsign validator: `/i` flags, a `{3}` quantifier, and a URL string in a file with no comments.
RX = """\
export const isCall = (s: string): boolean => /^[A-Z]\\d[A-Z]{3}$/i.test(s);
export const home = "http://qrz.example/";
"""


@pytest.mark.skipif(not HAS_TS, reason="needs node and corpus/stacks/app/node_modules/typescript")
def test_regex_flags_braces_and_urls_pass_but_regex_words_still_fail(tmp_path):
    src_path = tmp_path / "zzcall.ts"
    src_path.write_text(RX, encoding="utf-8")
    out, census = C.canonicalize(src_path, "ts")
    assert "/str_0001/i" in out
    report = C.gate(src_path, "ts", RX, out, census, tmp_path / "out.ts")
    assert report["blind_delta"]["max_brace_depth"] == [1, 0]  # recorded, not failed

    leaked = out.replace("/str_0001/i", "/station/i")
    with pytest.raises(C.GateFailure, match=r"G2 literal carries words: '/station/'"):
        C.gate(src_path, "ts", RX, leaked, census, tmp_path / "leaked.ts")


@pytest.mark.skipif(not HAS_GO, reason="needs the gitignored evals/canon/canon_go binary and gofmt")
def test_marc21_string_braces_do_not_fail_g8(tmp_path):
    # Raw depth 7 comes from the string "{dollar}"; the code itself nests 6 deep in both.
    path = C.ROOT / "corpus/stacks/api/internal/ingest/marc21.go"
    src = path.read_text(encoding="utf-8")
    out, census = C.canonicalize(path, "go")
    report = C.gate(path, "go", src, out, census, tmp_path / path.name)
    assert report["blind_delta"]["max_brace_depth"] == [7, 6]
