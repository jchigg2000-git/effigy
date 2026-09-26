"""The TS canonicaliser blanks every comment, and the gate catches surviving comment text on its own.

Comments whose next token is `)`, `]` or `}`, and JSX `{/* ... */}`, once sat at no AST node's
full start and were copied through verbatim; the gate re-lexed the output with the same
classifier and so could not see them either. Needs node and the TypeScript install that
canon_ts.mjs uses.
"""
import shutil

import pytest

import canonicalize as C

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not (C.ROOT / "corpus/stacks/app/node_modules/typescript").is_dir(),
    reason="needs node and corpus/stacks/app/node_modules/typescript (npm ci --prefix corpus/stacks/app)",
)

# One ordinary comment, then one before each punctuation token the classifier used to miss.
# `<p>// ...</p>` is JSX text, not a comment; it used to crash with overlapping spans.
FIXTURE = """\
import { useState } from "react";

// fathomline ordinary leading comment
export function Panel(props: { depth: number }) {
  const [rows] = useState<number[]>([]);
  const total = run(/* tidegauge */);
  const sum = rows.reduce((a, b) => a + b /* salinity */, props.depth);
  if (sum > total) {
    run();
    // bathymetry
  }
  return (
    <div className="panel">
      {/* hydrographic */}
      <p>// soundings</p>
      <span>{total}</span>
    </div>
  );
}
function run(): number { return 2; }
"""
COMMENT_WORDS = ("fathomline", "tidegauge", "salinity", "bathymetry", "hydrographic")


def test_comments_before_punctuation_are_blanked_and_gate_is_independent(tmp_path, monkeypatch):
    src_path = tmp_path / "zzpanel.tsx"
    src_path.write_text(FIXTURE, encoding="utf-8")

    out, census = C.canonicalize(src_path, "tsx")
    assert not [w for w in COMMENT_WORDS if w in out]
    assert "soundings" not in out  # JSX text, replaced by a string placeholder
    C.gate(src_path, "tsx", FIXTURE, out, census, tmp_path / "out.tsx")

    # Splice a comment back in, and hand the gate a classifier with the old blind spot
    # (no COMMENT spans at all). The text-level G2 scan must still fail it.
    leaked = out.replace("/* -*/", "/* tidegauge */", 1)
    assert leaked != out
    real = C.ts_spans

    def comment_blind(path):
        data = real(path)
        data["spans"] = [s for s in data["spans"] if s["kind"] != "COMMENT"]
        return data

    monkeypatch.setattr(C, "ts_spans", comment_blind)
    with pytest.raises(C.GateFailure, match=r"G2 words outside the allowlist: \[.*'tidegauge'"):
        C.gate(src_path, "tsx", FIXTURE, leaked, census, tmp_path / "leaked.tsx")
