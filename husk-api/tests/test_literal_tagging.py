import time

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _post(body: dict):
    r = client.post("/husk/literal-tagging", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "literal-tagging" in slugs


def test_url_classified():
    src = 'fetch("https://api.example.com/v1/users")'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<URL:0>" in out
    assert "https://api.example.com" not in out


def test_path_classified():
    src = "open('./config/settings.json')"
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<PATH:0>" in out


def test_sql_classified():
    src = 'db.exec("SELECT * FROM users WHERE id = 1")'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<SQL:0>" in out


def test_secret_classified():
    src = 'token = "ghp_AbCdEf1234567890XYZabcdEf12345678"'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "<KEY:0>" in out


def test_dedup_same_literal_same_index():
    src = 'a = "https://x.example/api"; b = "https://x.example/api"; c = "https://y.example/api"'
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert out.count("<URL:0>") == 2
    assert out.count("<URL:1>") == 1


def test_l0_collapses_classes():
    src = 'a = "https://x"; b = "/etc/passwd"; c = "hello world."'
    out = _post({"input": src, "crumb_level": 0})["output"]
    assert "<LIT:0>" in out
    assert "<LIT:1>" in out
    assert "<LIT:2>" in out
    assert "URL" not in out
    assert "PATH" not in out


def test_l2_fine_class():
    src = 'fetch("https://api.example.com/v1/users")'
    out = _post({"input": src, "crumb_level": 2})["output"]
    assert "HTTPS" in out


def test_l3_skeleton():
    src = 'fetch("https://api.example.com/v1/users/42/orders")'
    out = _post({"input": src, "crumb_level": 3})["output"]
    assert "<seg>" in out


def test_meta_counts():
    src = 'fetch("https://x"); read("/tmp/y"); say("hi")'
    body = _post({"input": src, "crumb_level": 1})
    counts = body["meta"]["literals_by_class"]
    assert counts.get("URL", 0) >= 1
    assert counts.get("PATH", 0) >= 1
    assert counts.get("MSG", 0) >= 1


def test_comment_apostrophe_does_not_pair_across_lines():
    # SOL-1: the apostrophe in "Don't" used to pair with the next quote on a
    # later line, swallowing the code between and leaking the real literal.
    src = "// Don't log the key.\nconst stripeKey = 'sk_example_not_a_real_key';"
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert "sk_example" not in out
    assert "stripeKey" in out
    assert "'<KEY:0>'" in out


def test_nested_template_is_one_literal_when_language_is_js():
    # SOL-4: a template nested in ${...} used to end the outer literal early.
    src = 'const s = `a ${f(`b ${c}`)} d`; const t = "x";'
    out = _post({"input": src, "crumb_level": 1, "options": {"language": "ts"}})["output"]
    assert out == 'const s = `<MSG:0>`; const t = "<MSG:1>";'
    # Without a JS language the plain rule stays: a Go raw string holding "${"
    # must not run on into the next line's key.
    go = 'var tmpl = `price: ${`\nvar key = "sk_example_not_a_real_key"'
    out = _post({"input": go, "crumb_level": 1})["output"]
    assert out == 'var tmpl = `<MSG:0>`\nvar key = "<KEY:0>"'



def test_quote_inside_interpolation_that_is_not_a_string_falls_back():
    # A regex or comment quote inside ${...} is not a string opener. Scanning on
    # from it used to swallow the following lines into one placeholder.
    src = ('function render(s) {\n  const a = `${s.replace(/\'/g, "")}`;\n'
           '  const key = "sk_example_not_a_real_key";\n  return a;\n}\nconst b = `x`;\n')
    ts = _post({"input": src, "crumb_level": 1, "options": {"language": "ts"}})["output"]
    plain = _post({"input": src, "crumb_level": 1})["output"]
    assert ts == plain
    assert '  const key = "<KEY:0>";\n  return a;\n}' in ts

def test_mime_type_is_not_a_path():
    # SOL-7: "application/json" matched the relative-path pattern.
    src = (
        'w.Header().Set("Content-Type", "application/json"); '
        'open("./config/settings.json"); load("image/logo.png")'
    )
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert out == (
        'w.Header().Set("<MSG:0>", "<MSG:1>"); '
        'open("<PATH:0>"); load("<PATH:1>")'
    )


def test_dates_and_everyday_slash_pairs_are_not_paths():
    # SOL-7: "and/or", "N/A", "km/h", dates and fractions matched the path pattern.
    src = (
        'a("and/or"); b("N/A"); c("km/h"); d("09/26/2026"); e("1/2"); '
        'f("src/lib"); g("v1/2.json")'
    )
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert out == (
        'a("<MSG:0>"); b("<MSG:1>"); c("<MSG:2>"); d("<MSG:3>"); e("<MSG:4>"); '
        'f("<PATH:0>"); g("<PATH:1>")'
    )


def test_unterminated_quote_is_linear():
    # SOLV-1: the old alternation regex rescanned to the end from every
    # escaped quote, so this took ~40 s. Nothing terminates, so nothing changes.
    src = "'" + "\\'" * 50000
    t0 = time.perf_counter()
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert time.perf_counter() - t0 < 2
    assert out == src


def test_rune_literals_stay_single_characters():
    # SOLV-2: '<MSG:0>' is a multi-character rune, which Go and C reject.
    src = "var m = map[byte]string{'S': \"SCHEDULED\"}; if b == '\\n' {}"
    out = _post({"input": src, "crumb_level": 1})["output"]
    assert out == "var m = map[byte]string{'S': \"<MSG:0>\"}; if b == '\\n' {}"
