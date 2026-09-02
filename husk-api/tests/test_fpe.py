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
