from fastapi.testclient import TestClient

from app.main import app
from app.dehusk import reverse_substitute

client = TestClient(app)


# ---- reverse_substitute unit tests -----------------------------------------

def test_reverse_substitute_basic():
    out, n = reverse_substitute(
        "the xY7q handler calls zzAb",
        {"xY7q": "get_customer_email", "zzAb": "send_invoice"},
    )
    assert out == "the get_customer_email handler calls send_invoice"
    assert n == 2


def test_reverse_substitute_empty_map_is_noop():
    out, n = reverse_substitute("nothing to do here", {})
    assert out == "nothing to do here"
    assert n == 0


def test_reverse_substitute_word_boundary_no_partial_collision():
    # The pseudonym `abc` must not be rewritten inside the larger token `abcdef`.
    out, n = reverse_substitute("abc and abcdef", {"abc": "REAL"})
    assert out == "REAL and abcdef"
    assert n == 1


def test_reverse_substitute_longest_match_first():
    # When one pseudonym is a prefix of another, the longer wins.
    out, n = reverse_substitute(
        "user userName",
        {"user": "acct", "userName": "acctHolder"},
    )
    assert out == "acct acctHolder"
    assert n == 2


def test_reverse_substitute_digit_leading_pseudonym_roundtrips():
    # fpe ciphers over letters+digits without pinning the first character, so
    # real pseudonyms routinely start with a digit. Regression: these must
    # still reverse when they stand alone as a token.
    out, n = reverse_substitute(
        "The 9qXz function leaks 42ab somewhere",
        {"9qXz": "get_customer_email", "42ab": "send_invoice"},
    )
    assert out == "The get_customer_email function leaks send_invoice somewhere"
    assert n == 2


def test_reverse_substitute_digit_leading_pseudonym_boundary_guard():
    # Regression: a digit-leading pseudonym must NOT be rewritten when it is a
    # substring of a longer identifier/word in the diagnosis text.
    out, n = reverse_substitute(
        "see var9qXz and 9qXzTail and x9qXzy but 9qXz alone",
        {"9qXz": "orig_name"},
    )
    assert out == "see var9qXz and 9qXzTail and x9qXzy but orig_name alone"
    assert n == 1


def test_reverse_substitute_numeric_pseudonym_not_replaced_inside_number():
    # An all-digit pseudonym must not corrupt longer numbers in prose.
    out, n = reverse_substitute("line 142 mentions 42", {"42": "ab"})
    assert out == "line 142 mentions ab"
    assert n == 1


def test_reverse_substitute_placeholder_style_key():
    out, n = reverse_substitute(
        'the endpoint hits "<URL:0>" repeatedly',
        {"<URL:0>": "https://api.internal.example.com/v1/orders"},
    )
    assert out == 'the endpoint hits "https://api.internal.example.com/v1/orders" repeatedly'
    assert n == 1


# ---- husk emit_map opt-in ---------------------------------------------------

def test_fpe_no_map_by_default():
    r = client.post("/husk/fpe", json={"input": "def get_customer(): pass", "crumb_level": 1})
    assert r.status_code == 200, r.text
    assert r.json()["reidentify_map"] is None


def test_fpe_emit_map_opt_in():
    src = "def get_customer_email(customer_id):\n    return customer_id"
    r = client.post("/husk/fpe", json={
        "input": src, "crumb_level": 1, "options": {"emit_map": True},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    m = body["reidentify_map"]
    assert isinstance(m, dict) and len(m) >= 1
    # Map does not leak into meta (it lives in its own field).
    assert "reidentify_map" not in body["meta"]
    # Every original in the map is a token from the source.
    for pseudo, original in m.items():
        assert original in src
        assert pseudo != original


def test_literal_tagging_emit_map_opt_in():
    src = 'url = "https://api.example.com/orders"\nmsg = "Order placed."'
    r = client.post("/husk/literal-tagging", json={
        "input": src, "crumb_level": 1, "options": {"emit_map": True},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    m = body["reidentify_map"]
    assert isinstance(m, dict) and len(m) >= 1
    # Keys are placeholders that actually appear in the output.
    for placeholder in m:
        assert placeholder in body["output"]


def test_literal_tagging_no_map_by_default():
    r = client.post("/husk/literal-tagging", json={"input": 'x = "hi"', "crumb_level": 1})
    assert r.status_code == 200, r.text
    assert r.json()["reidentify_map"] is None


# ---- full round-trip through the API ---------------------------------------

def test_fpe_full_roundtrip():
    src = "def get_customer_email(customer_id):\n    return build_email(customer_id)"
    hr = client.post("/husk/fpe", json={
        "input": src, "crumb_level": 1, "options": {"emit_map": True},
    })
    assert hr.status_code == 200, hr.text
    hbody = hr.json()
    rmap = hbody["reidentify_map"]

    # Simulate an LLM diagnosis written against the husked identifiers: it
    # references the pseudonyms verbatim.
    pseudos = list(rmap.keys())
    diagnosis = f"The function {pseudos[0]} delegates to {pseudos[-1]}."

    dr = client.post("/dehusk", json={"input": diagnosis, "map": rmap})
    assert dr.status_code == 200, dr.text
    dbody = dr.json()
    # Both referenced pseudonyms were rewritten back to real identifiers.
    assert rmap[pseudos[0]] in dbody["output"]
    assert rmap[pseudos[-1]] in dbody["output"]
    assert dbody["substitutions"] == 2


def test_fpe_digit_leading_pseudonym_full_roundtrip():
    # Force a digit-leading pseudonym through the real API: husk candidate
    # identifiers until fpe emits a pseudonym starting with a digit (the cipher
    # is deterministic per process, and ~1/6 of first characters are digits, so
    # this terminates almost immediately), then dehusk a diagnosis that
    # references it and assert the original identifier is restored.
    pseudo = original = None
    rmap = None
    for i in range(200):
        src = f"def sample_fn_{i}(arg_val_{i}):\n    return arg_val_{i}"
        hr = client.post("/husk/fpe", json={
            "input": src, "crumb_level": 1, "options": {"emit_map": True},
        })
        assert hr.status_code == 200, hr.text
        rmap = hr.json()["reidentify_map"]
        digit_leading = {p: o for p, o in rmap.items() if p[0].isdigit()}
        if digit_leading:
            pseudo, original = next(iter(digit_leading.items()))
            break
    assert pseudo is not None, "no digit-leading fpe pseudonym found in 200 candidates"

    diagnosis = (
        f"The function {pseudo} is unsafe, but prefix{pseudo} and "
        f"{pseudo}9suffix must be left alone."
    )
    dr = client.post("/dehusk", json={"input": diagnosis, "map": {pseudo: original}})
    assert dr.status_code == 200, dr.text
    dbody = dr.json()
    # The standalone pseudonym is restored to the original identifier...
    assert f"The function {original} is unsafe" in dbody["output"]
    # ...while embedded occurrences are untouched (token-boundary safety).
    assert f"prefix{pseudo}" in dbody["output"]
    assert f"{pseudo}9suffix" in dbody["output"]
    assert dbody["substitutions"] == 1


def test_dehusk_empty_map_noop():
    r = client.post("/dehusk", json={"input": "some diagnosis text", "map": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output"] == "some diagnosis text"
    assert body["substitutions"] == 0


def test_dehusk_requires_map():
    r = client.post("/dehusk", json={"input": "text"})
    assert r.status_code == 422
