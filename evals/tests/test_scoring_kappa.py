"""kappa_judge pairs each worksheet row with its OWN attacker's guess and judge label (STAT-1).

One item attacked by two models yields two guesses and two judge labels under the same item id.
Keying on the item id alone showed one attacker's guess on the other's rows and scored rows against
the wrong judge label, capping a perfect rater's kappa below 1.
"""
import json

import kappa_judge


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def test_rows_use_their_own_attackers_guess_and_label(tmp_path, monkeypatch):
    item = "qsolog__contact.go__fpe__r0"
    cases = {"a/Alpha": ("alpha guess", "MATCH"), "b/Beta": ("beta guess", "MISS")}
    for atk, (guess, label) in cases.items():
        safe = atk.replace("/", "-")
        _write(tmp_path / "raw" / f"{item}__{safe}__open_ended.json",
               {"item_id": item, "attacker": atk, "mode": "open_ended",
                "true_domain_id": "ham-radio-logbook",
                "parsed": {"domain": guess, "specific_identifiers": []}})
        _write(tmp_path / "judge" / f"{item}__{safe}.json",
               {"item_id": item, "attacker": atk, "label": label})
    monkeypatch.setattr(kappa_judge, "SAMPLE_FRACTION", 1.0)

    assert kappa_judge.cmd_sample(tmp_path) == 0
    ws = tmp_path / "kappa_worksheet.jsonl"
    rows = [json.loads(line) for line in ws.read_text().splitlines()]
    assert {r["attacker"]: r["guess_domain"] for r in rows} == {
        atk: guess for atk, (guess, _) in cases.items()}

    # A perfect rater labels each row with its own attacker's judge label.
    for r in rows:
        r["human_label"] = cases[r["attacker"]][1]
    ws.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert kappa_judge.cmd_score(tmp_path) == 0
    doc = json.loads((tmp_path / "kappa.json").read_text())
    assert doc["n_pairs"] == 2 and doc["kappa"] == 1.0
