"""G4 looks for the module name inside preserved third-party import paths too.

External paths are kept verbatim because every domain shares them; a dependency named after
the file's own module (`github.com/acme/tidepool-shared`) is not shared, and used to pass G4
because the preserved paths were masked out before the name search.
"""
import shutil

import pytest

import canonicalize as C

pytestmark = pytest.mark.skipif(
    not (C.CANON / "canon_go").exists() or not shutil.which("gofmt"),
    reason="needs the gitignored evals/canon/canon_go binary and gofmt",
)

GAUGE = """\
package gauge

import "github.com/acme/tidepool-shared/units"

const unit = "fathom"

func Depth(f float64) float64 {
\treturn units.FathomsToMeters(f)
}
"""


def test_module_named_dependency_path_fails_g4(tmp_path):
    (tmp_path / "go.mod").write_text("module tidepool\n\ngo 1.22\n", encoding="utf-8")
    path = tmp_path / "gauge.go"
    path.write_text(GAUGE, encoding="utf-8")
    out, census = C.canonicalize(path, "go")
    assert '"github.com/acme/tidepool-shared/units"' in out  # preserved by design
    with pytest.raises(C.GateFailure, match="G4 name survived: 'tidepool'"):
        C.gate(path, "go", GAUGE, out, census, tmp_path / "out.go")
