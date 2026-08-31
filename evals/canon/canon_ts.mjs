// canon_ts.mjs — TS/TSX span classifier for evals/canonicalize.py.
//
// Emits the spans of one TypeScript or TSX file as JSON and NOTHING ELSE. It
// holds no allowlist, no naming scheme, and no gate; all policy lives in
// canonicalize.py.
//
// The TS compiler API rather than a regex, because three span kinds in this
// corpus are not lexically decidable and each is a live leak:
//   * JSX text  — `<h1>qsolog</h1>` is the domain name as a text node.
//   * Regex literals — `/^X[0-9][A-Z]{3}$/` IS the ham callsign format, and a
//     regex tokenizer that does not know regex literals leaves it verbatim.
//   * Template literals with substitutions — treating the whole thing as one
//     opaque string deletes live calls from the call graph.
// It also decides JSX attribute position, which the allowlist depends on:
// `value` on a <input> is platform vocabulary, `read` on a <ReadDetail> is not.
//
//   node evals/canon/canon_ts.mjs <file.tsx>
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

// verify_domains.py already depends on a local tsc from this same install, so
// this is existing practice rather than new debt. Fail loudly, never skip:
// a silently skipped classifier would ship an uncanonicalised artifact.
let ts;
try {
  ts = require(path.join(here, "../../corpus/stacks/app/node_modules/typescript"));
} catch {
  try {
    ts = require("typescript");
  } catch {
    console.error(
      "typescript not found. Run: npm ci --prefix corpus/stacks/app\n" +
        "(node_modules/ is gitignored; verify_domains.py has the same dependency.)"
    );
    process.exit(3);
  }
}

const file = process.argv[2];
if (!file) {
  console.error("usage: node canon_ts.mjs <file.ts|tsx>");
  process.exit(2);
}
const text = readFileSync(file, "utf8");
const kind = file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);

const spans = [];
const seenComment = new Set();
const externalBindings = new Set();
const relativeBindings = new Set();

const isIntrinsic = (tag) => {
  if (!tag) return false;
  const t = tag.getText ? tag.getText() : "";
  return /^[a-z]/.test(t) && !t.includes(".");
};

function addComments(node) {
  const full = node.getFullStart();
  for (const fn of [ts.getLeadingCommentRanges, ts.getTrailingCommentRanges]) {
    const ranges = fn(text, full) || [];
    for (const r of ranges) {
      if (seenComment.has(r.pos)) continue;
      seenComment.add(r.pos);
      spans.push({ kind: "COMMENT", off: r.pos, end: r.end, text: text.slice(r.pos, r.end) });
    }
  }
}

// Import/export bindings first, so identifier classification can consult them.
function collectBindings(node) {
  const spec = node.moduleSpecifier;
  if (!spec || !ts.isStringLiteral(spec)) return;
  const external = !spec.text.startsWith(".");
  const bucket = external ? externalBindings : relativeBindings;
  const clause = node.importClause;
  if (clause) {
    if (clause.name) bucket.add(clause.name.text);
    const nb = clause.namedBindings;
    if (nb) {
      if (ts.isNamespaceImport(nb)) bucket.add(nb.name.text);
      else if (ts.isNamedImports(nb)) for (const el of nb.elements) bucket.add(el.name.text);
    }
  }
  spans.push({
    kind: "MODULE_SPECIFIER",
    off: spec.getStart(sf),
    end: spec.getEnd(),
    text: spec.getText(sf),
    external,
  });
}
(function pre(node) {
  if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) collectBindings(node);
  ts.forEachChild(node, pre);
})(sf);

const moduleSpecifierOffsets = new Set(
  spans.filter((s) => s.kind === "MODULE_SPECIFIER").map((s) => s.off)
);

(function walk(node) {
  addComments(node);

  if (ts.isIdentifier(node) || ts.isPrivateIdentifier(node)) {
    const p = node.parent;
    const rec = {
      kind: "IDENT",
      off: node.getStart(sf),
      end: node.getEnd(),
      text: node.text ?? node.getText(sf),
    };
    if (p && (ts.isJsxOpeningElement(p) || ts.isJsxSelfClosingElement(p) || ts.isJsxClosingElement(p)) && p.tagName === node) {
      rec.role = isIntrinsic(node) ? "jsx_tag_intrinsic" : "jsx_tag_component";
    } else if (p && ts.isJsxAttribute(p) && p.name === node) {
      const owner = p.parent && p.parent.parent;
      rec.role = owner && isIntrinsic(owner.tagName) ? "jsx_attr_intrinsic" : "jsx_attr_component";
    } else if (p && ts.isPropertyAccessExpression(p) && p.name === node) {
      rec.role = "member";
      if (ts.isIdentifier(p.expression)) rec.base = p.expression.text;
    } else if (p && ts.isQualifiedName(p) && p.right === node) {
      rec.role = "member";
      if (ts.isIdentifier(p.left)) rec.base = p.left.text;
    } else {
      rec.role = "plain";
    }
    if (externalBindings.has(rec.text)) rec.external_binding = true;
    if (relativeBindings.has(rec.text)) rec.relative_binding = true;
    spans.push(rec);
  } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    if (!moduleSpecifierOffsets.has(node.getStart(sf))) {
      spans.push({ kind: "STRING", off: node.getStart(sf), end: node.getEnd(), text: node.getText(sf) });
    }
  } else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
    spans.push({ kind: "TEMPLATE_PART", off: node.getStart(sf), end: node.getEnd(), text: node.getText(sf) });
  } else if (ts.isRegularExpressionLiteral(node)) {
    spans.push({ kind: "REGEX", off: node.getStart(sf), end: node.getEnd(), text: node.getText(sf) });
  } else if (ts.isNumericLiteral(node) || ts.isBigIntLiteral(node)) {
    spans.push({ kind: "NUMBER", off: node.getStart(sf), end: node.getEnd(), text: node.getText(sf) });
  } else if (node.kind === ts.SyntaxKind.JsxText) {
    if (node.getText(sf).trim().length) {
      spans.push({ kind: "JSX_TEXT", off: node.getStart(sf), end: node.getEnd(), text: node.getText(sf) });
    }
  }
  ts.forEachChild(node, walk);
})(sf);

// Syntax-error check, mirroring verify_domains.py: only TS1xxx counts.
const syntactic = sf.parseDiagnostics || [];
const fatal = syntactic.filter((d) => d.code >= 1000 && d.code < 2000);

spans.sort((a, b) => a.off - b.off);
process.stdout.write(
  JSON.stringify({
    spans,
    external_bindings: [...externalBindings].sort(),
    relative_bindings: [...relativeBindings].sort(),
    syntax_errors: fatal.map((d) => `TS${d.code}`),
    typescript_version: ts.version,
  })
);
