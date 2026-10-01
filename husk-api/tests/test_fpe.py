import shutil
import subprocess
import time
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _post(body: dict):
    r = client.post("/husk/fpe", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_fpe_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "fpe" in slugs


def test_fpe_preserves_length():
    src = "def get_customer_email(customer_id):\n    return customer_id"
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert len(out) == len(src)


def test_fpe_deterministic():
    src = "function processOrder(order) { return order.total; }"
    a = _post({"input": src, "crumb_level": 1})["output"]
    b = _post({"input": src, "crumb_level": 1})["output"]
    assert a == b


def test_fpe_referential_integrity():
    src = "let foo_bar = 1; let baz = foo_bar + foo_bar;"
    meta = _post({"input": src, "crumb_level": 0})["meta"]
    # foo_bar and baz are both ciphered; let is a keyword
    assert meta["unique_tokens_replaced"] >= 2


def test_fpe_keywords_preserved():
    src = "if (x) return None"
    out = _post({"input": src, "crumb_level": 0})["output"]
    assert "if" in out
    assert "return" in out
    assert "None" in out


def test_fpe_l3_skips_short_tokens():
    src = "user.account.balance"
    out = _post({"input": src, "crumb_level": 3})["output"]
    assert out == src


def test_fpe_l3_ciphers_proper_nouns():
    src = "AcmeCorpInvoiceProcessorService doStuff()"
    out = _post({"input": src, "crumb_level": 3})["output"]
    assert "AcmeCorp" not in out


# --- Injectivity regression: the "_" -> "H" alphabet collision ---------------
# _TOKEN_RE's identifier branch admits "_", but _ALPHABET_MIXED used to exclude it, so the sanitizer
# in _make_cipher mapped it via alphabet[ord("_") % 62] == alphabet[33] == "H".
# foo_bar and fooHbar therefore enciphered identically, and the map inversion
# (a dict comprehension) silently dropped one of them -- so /dehusk rewrote a
# diagnosis with the WRONG source identifier, with no error and no signal.


def test_fpe_underscore_and_H_do_not_collide():
    src = "let foo_bar = 1; let fooHbar = 2;"
    body = _post({"input": src, "crumb_level": 0, "options": {"emit_map": True}})
    originals = set(body["reidentify_map"].values())
    assert {"foo_bar", "fooHbar"} <= originals
    pseudonyms = [p for p, o in body["reidentify_map"].items() if o in ("foo_bar", "fooHbar")]
    assert len(set(pseudonyms)) == 2, "distinct identifiers must get distinct pseudonyms"


def test_fpe_reidentify_map_is_injective():
    # Underscore-dense source: the highest-risk input for the old collision.
    names = [f"svc_{i}_handler_{i}" for i in range(60)] + [f"svcH{i}HhandlerH{i}" for i in range(60)]
    src = "\n".join(f"var {n} = {i};" for i, n in enumerate(names))
    body = _post({"input": src, "crumb_level": 0, "options": {"emit_map": True}})
    # One line catches any silent drop in the inversion, from any future cause.
    assert len(body["reidentify_map"]) == body["meta"]["unique_tokens_replaced"]
    assert body["meta"]["pseudonym_collisions"] == 0


def test_fpe_alphabet_includes_underscore():
    # White-box: pins intent so a later "cleanup" cannot revert the alphabet.
    from app.solutions import fpe

    assert "_" in fpe._ALPHABET_MIXED


def test_fpe_collision_roundtrip_dehusks_both():
    src = "let foo_bar = 1; let fooHbar = 2;"
    body = _post({"input": src, "crumb_level": 0, "options": {"emit_map": True}})
    rmap = body["reidentify_map"]
    pseudo = {o: p for p, o in rmap.items()}
    diagnosis = f"Both {pseudo['foo_bar']} and {pseudo['fooHbar']} are unused."
    r = client.post("/dehusk", json={"input": diagnosis, "map": rmap})
    assert r.status_code == 200, r.text
    out = r.json()
    assert "foo_bar" in out["output"] and "fooHbar" in out["output"]
    assert out["substitutions"] == 2


def test_fpe_go_husk_parses():
    # SOL-2: pseudonyms could start with a digit, Go keywords such as defer/map/go
    # were enciphered, and number tails were read as identifiers (0o755 -> 0eorf),
    # so no Go husk parsed. Under the demo key `bp` also enciphered to `of`, a
    # spared keyword, so /dehusk rewrote every English "of" in a diagnosis.
    from app.solutions import fpe

    src = (
        "package main\n\n"
        "func run(dir string, bp int) error {\n"
        "\tdefer cleanup()\n"
        "\tm := map[string]int{}\n"
        "\tgo work(m)\n"
        "\tos.MkdirAll(dir, 0o755)\n"
        "\tx := 0x1F + 1_000 + bp\n"
        "\treturn nil\n"
        "}\n"
    )
    with patch.dict("os.environ", {"FPE_DEMO_KEY": "1"}):
        body = _post({"input": src, "crumb_level": 1, "options": {"emit_map": True}})
    out = body["output"]
    for pseudo in body["reidentify_map"]:
        assert pseudo[0].isalpha() or pseudo[0] == "_", pseudo
        assert pseudo not in fpe._BASELINE_KEYWORDS | fpe._STDLIB_NAMES, pseudo
    for kept in ("\tdefer ", "map[", "\tgo ", "0o755", "0x1F", "1_000"):
        assert kept in out
    if shutil.which("gofmt"):
        r = subprocess.run(["gofmt", "-e"], input=out, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_fpe_refuses_pseudonym_equal_to_a_spared_token():
    # SOL-2: at crumb 3 the heuristic spares arbitrary short tokens, so a
    # pseudonym can equal a token left in plain text in the same input.
    from app.solutions import fpe

    for name in ("AbCdEf", "GhIjKl", "MnOpQr", "StUvWx"):
        pseudo = next(iter(fpe.husk(name, 3, {"emit_map": True})[1]["reidentify_map"]))
        if fpe._should_skip(pseudo, 3):
            break
    src = f"{name} = {pseudo}"
    with pytest.raises(ValueError, match="pseudonym collision"):
        fpe.husk(src, 3, {"emit_map": True})
    assert fpe.husk(src, 3, {})[1]["pseudonym_collisions"] == 1


def test_fpe_enciphers_template_interpolations():
    # SOL-3: a whole backtick literal passed through verbatim, so names inside
    # ${...} stayed in plain text beside their pseudonyms elsewhere in the file.
    src = 'const u = `${BASE}/reads/${readId}?q=${fmt("}", total)}`; use(readId, BASE, total);'
    out = _post({"input": src, "crumb_level": 1})["output"]
    for name in ("BASE", "readId", "fmt", "total"):
        assert name not in out
    assert '/reads/' in out and '?q=' in out and '"}"' in out



def test_fpe_quote_in_interpolation_regex_leaves_template_text_alone():
    # A quote inside a regex in ${...} paired with a later quote, and the walk then
    # enciphered the template's own text and string contents with the code's key.
    src = 'const h = `${s.replace(/"/g, "&quot;")} shows "quoted" text`; send(total);'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert '${s.replace(/"/g, "&quot;")} shows "quoted" text`' in out
    assert "total" not in out  # code after the template is still enciphered

def test_fpe_apostrophe_does_not_pair_across_lines():
    # SOL-1: the apostrophe in "Don't" paired with the one in "We'll" two lines
    # down, and every identifier in between passed through unenciphered.
    src = (
        "<p>Don't close this window.</p>\n"
        "<ClaimSummary adjudicationQueue={patientLedger.pendingClaims} />\n"
        "<p>We'll email you.</p>\n"
    )
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "patientLedger" not in out


def test_fpe_enciphers_non_ascii_identifiers_and_private_field_access():
    # SOL-5: the identifier branch was ASCII-only, so these passed through whole
    # or in plain-text fragments, and `#` in `this.#field` hid the rest of the line.
    body = _post({"input": "def 计算工资(员工): return 员工.基本工资 * größeFaktor", "crumb_level": 1})
    for name in ("计算工资", "员工", "基本工资", "ößeFaktor"):
        assert name not in body["output"]
    assert body["meta"]["non_ascii_identifiers"] == 4
    out = _post({"input": "this.#ledger += computeTariff(this.meter)", "crumb_level": 1})["output"]
    assert "computeTariff" not in out and "meter" not in out


def test_fpe_unterminated_quote_is_linear():
    # SOLV-1: the old alternation regex rescanned to the end from every escaped
    # quote, so this took tens of seconds. Nothing terminates, so nothing changes.
    src = "'" + "\\'" * 50000
    t0 = time.perf_counter()
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert time.perf_counter() - t0 < 2
    assert out == src


def test_fpe_spares_ts_contextual_keywords_and_string_prefixes():
    # SOL-5: keyof/readonly/declare/satisfies were enciphered, and a two-letter
    # string prefix (rf"...", Rb'...') was read as an identifier; both broke the parse.
    src = (
        "declare const widgetCount: number;\n"
        "class Box { readonly width: number; }\n"
        "type K = keyof Box;\n"
        "const cfg = widgetCount satisfies number;\n"
        "msg = rf\"{widgetCount}\"\n"
        "raw = Rb'x'\n"
    )
    out = _post({"input": src, "crumb_level": 1})["output"]
    for kept in ("declare const", "readonly ", "keyof ", " satisfies ", 'rf"{', "Rb'x'"):
        assert kept in out, (kept, out)
    assert "widgetCount" not in out


FSTRING_SRC = r'''line = f"Total {invoice.amount_due!r:>{col_width}} for {acct_id:,.2f} {{as-is}}"
note = f"{ledger['key}']}" + rt'{tmpl_val}' + F"""x
{multi_val}"""
doc = f"""say "hi" to {greet_name}""" + "{plain_field}"
esc = f"\N{EM DASH} {dash_val} \{slash_val} {a_val != b_val}"
'''


def test_fpe_enciphers_fstring_replacement_fields():
    # SOL-5: an f-string passed through verbatim like any literal, so every name
    # in its replacement fields stayed in plain text (378 of 378 in husk-api's and
    # evals' own Python). The fields are code; the text, conversion and format
    # spec around them are not, and a plain "{...}" string is still a literal.
    import ast
    import warnings

    body = _post({"input": FSTRING_SRC, "crumb_level": 1, "options": {"emit_map": True}})
    out = body["output"]
    for name in ("invoice", "amount_due", "col_width", "acct_id", "ledger", "tmpl_val",
                 "multi_val", "greet_name", "dash_val", "slash_val", "a_val", "b_val"):
        assert name not in out, (name, out)
    for kept in ("Total {", "!r:>{", ":,.2f}", "{{as-is}}", "['key}']", 'say "hi" to {',
                 '"{plain_field}"', r"\N{EM DASH} {", " != "):
        assert kept in out, (kept, out)
    assert len(out) == len(FSTRING_SRC)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)   # the deliberate "\{"
        ast.parse(out)
    r = client.post("/dehusk", json={"input": out, "map": body["reidentify_map"]})
    assert r.json()["output"] == FSTRING_SRC
