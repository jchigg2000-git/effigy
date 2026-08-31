from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_solutions_lists_example():
    r = client.get("/solutions")
    assert r.status_code == 200
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "example" in slugs


def test_unknown_solution_404():
    r = client.post("/husk/does-not-exist", json={"input": "abc"})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_solution"


def test_example_passthrough():
    r = client.post("/husk/example", json={"input": "hello", "crumb_level": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["output"] == "olleh"
    assert body["solution"] == "example"
    assert body["crumb_level"] == 2
    assert body["meta"]["length"] == 5


def test_crumb_level_out_of_range():
    r = client.post("/husk/example", json={"input": "abc", "crumb_level": 9})
    assert r.status_code == 422


def test_input_required():
    r = client.post("/husk/example", json={})
    assert r.status_code == 422
