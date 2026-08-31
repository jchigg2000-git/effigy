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
