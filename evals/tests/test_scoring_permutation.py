"""permutation_baseline p-values carry the +1 correction, and single-domain cells are not computable (STAT-4).

A Monte Carlo permutation p counts the observed labelling as one of the permutations, so it can
never be 0. A cell whose files all carry one domain has a null equal to the observed value by
construction, which used to print as "+0.000, p=1.0", i.e. as "no signal beyond response bias".
"""
import permutation_baseline as pb


def test_p_has_plus_one_and_single_domain_cell_is_degenerate():
    draws = 200
    files = [f"f{i}" for i in range(30)]
    truth = {f: "ABC"[i // 10] for i, f in enumerate(files)}
    right = pb.permutation_cell(
        [{"source_path": f, "true_domain_id": truth[f], "answer_id": truth[f]} for f in files],
        draws=draws)
    assert right["p"] == 1 / (draws + 1)

    one_domain = pb.permutation_cell(
        [{"source_path": f"f{i}", "true_domain_id": "A", "answer_id": "A"}
         for i in range(3) for _ in range(3)], draws=draws)
    assert one_domain["degenerate"] and "corrected" not in one_domain and "p" not in one_domain
    text = pb.render({"run": "r", "draws": draws, "seed": 1, "attribution": {},
                      "cells": {"arm|a/A": one_domain, "arm2|a/A": right}})
    assert "not computable" in text
