"""HAR-5: every attacker attempt records the tokens it was billed for.

call_model used to drop `usage`, so the cost of a run was unrecoverable from its
own records. Fields are int-or-None: a usage object whose fields are not ints (a
MagicMock, an odd provider) must not make the record unserialisable.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import run_rsch1
import score_rsch1


def _client(usage):
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"choice": 2, "confidence": 1}'),
                                 finish_reason="stop")],
        model="m", usage=usage)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: resp)))


def test_call_model_records_usage_as_ints_or_none():
    full = SimpleNamespace(prompt_tokens=100, completion_tokens=40, total_tokens=140,
                           completion_tokens_details=SimpleNamespace(reasoning_tokens=30))
    bare = SimpleNamespace(prompt_tokens=100, completion_tokens=40, total_tokens=140)
    got = [run_rsch1.call_model(_client(u), "m", "p", 16, "forced_choice")["usage"]
           for u in (full, bare, None, MagicMock())]
    assert got[0] == {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140,
                      "reasoning_tokens": 30}
    assert got[1] == {**got[0], "reasoning_tokens": None}
    assert got[2] is None
    assert set(got[3].values()) == {None}
    json.dumps(got)

    # Additive for readers: scoring a record is unchanged by the new field.
    rec = {"attempts": [{"text": '{"choice": 2, "confidence": 1}', "usage": got[0]}],
           "parsed": {"choice": 2, "confidence": 1}, "truth_option": 2,
           "menu_order": ["x", "y"]}
    bare_rec = {**rec, "attempts": [{"text": rec["attempts"][0]["text"]}]}
    assert score_rsch1.scored_choice(rec) == score_rsch1.scored_choice(bare_rec)
