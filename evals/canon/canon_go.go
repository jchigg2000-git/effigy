// canon_go.go — Go span classifier for evals/canonicalize.py.
//
// Emits the token stream of one Go file as JSON and NOTHING ELSE. It holds no
// allowlist, no naming scheme, and no gate: every policy decision lives in
// canonicalize.py so it exists once, in one auditable place, rather than
// triplicated per language.
//
// Uses go/scanner (not a regex) because the canonicaliser owes two proofs at
// once. Leak-freedom can be checked downstream from the output alone. Fidelity
// — "the token-kind sequence is unchanged" — cannot: proving the output's token
// stream matches the input's requires knowing the input's exactly. A regex
// approximation yields an approximate proof, which is not a proof.
//
// parser.ImportsOnly is deliberate: full type resolution would tell us whether
// a selector base is stdlib, but it needs the package to type-check, and
// preregistration A3.3 records that five of six corpus domains carry no go.sum
// and do not build. Don't design around a capability we don't have.
//
//	go run evals/canon/canon_go.go <file.go>
package main

import (
	"encoding/json"
	"fmt"
	"go/parser"
	"go/scanner"
	"go/token"
	"os"
)

type tok struct {
	Kind string `json:"kind"`
	Off  int    `json:"off"`
	End  int    `json:"end"`
	Text string `json:"text,omitempty"`
}

type imp struct {
	Path      string `json:"path"`
	PathOff   int    `json:"path_off"`
	PathEnd   int    `json:"path_end"`
	Name      string `json:"name,omitempty"`
	NameOff   int    `json:"name_off"`
	NameEnd   int    `json:"name_end"`
	HasName   bool   `json:"has_name"`
}

// Kinds whose literal text is the exact source text, so end offset is exact.
var literalKind = map[token.Token]string{
	token.IDENT:   "IDENT",
	token.STRING:  "STRING",
	token.CHAR:    "CHAR",
	token.COMMENT: "COMMENT",
	token.INT:     "INT",
	token.FLOAT:   "FLOAT",
	token.IMAG:    "IMAG",
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: canon_go <file.go>")
		os.Exit(2)
	}
	src, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	fset := token.NewFileSet()
	file := fset.AddFile(os.Args[1], fset.Base(), len(src))

	var sc scanner.Scanner
	var scanErr error
	sc.Init(file, src, func(pos token.Position, msg string) {
		if scanErr == nil {
			scanErr = fmt.Errorf("%s: %s", pos, msg)
		}
	}, scanner.ScanComments)

	toks := []tok{}
	for {
		pos, t, lit := sc.Scan()
		if t == token.EOF {
			break
		}
		off := fset.Position(pos).Offset
		if k, ok := literalKind[t]; ok {
			toks = append(toks, tok{Kind: k, Off: off, End: off + len(lit), Text: lit})
			continue
		}
		// Keywords, operators and auto-inserted semicolons. Recorded for the
		// token-kind-identity gate; never rewritten, so no end offset needed.
		kind := "OP"
		if t.IsKeyword() {
			kind = "KEYWORD"
		}
		toks = append(toks, tok{Kind: kind + ":" + t.String(), Off: off, End: off})
	}
	if scanErr != nil {
		fmt.Fprintln(os.Stderr, "scan error:", scanErr)
		os.Exit(1)
	}

	imps := []imp{}
	if f, err := parser.ParseFile(fset, os.Args[1], src, parser.ImportsOnly); err == nil {
		for _, s := range f.Imports {
			e := imp{
				Path:    s.Path.Value,
				PathOff: fset.Position(s.Path.ValuePos).Offset,
				PathEnd: fset.Position(s.Path.ValuePos).Offset + len(s.Path.Value),
			}
			if s.Name != nil {
				e.HasName = true
				e.Name = s.Name.Name
				e.NameOff = fset.Position(s.Name.NamePos).Offset
				e.NameEnd = e.NameOff + len(s.Name.Name)
			}
			imps = append(imps, e)
		}
	} else {
		fmt.Fprintln(os.Stderr, "parse error:", err)
		os.Exit(1)
	}

	out, _ := json.Marshal(map[string]any{"tokens": toks, "imports": imps})
	os.Stdout.Write(out)
}
