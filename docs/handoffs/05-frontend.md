# Handoff 05 — Frontend Test UI

## Goal

Build a single-page test UI that lets a user paste source code into a textarea, pick which "husk" transformation to run, click a "Husk it" button, and see the result. The UI is for evaluation — pure utility, minimal styling. It calls an existing FastAPI backend that exposes one endpoint per transformation and a `GET /solutions` endpoint that lists what's available.

The UI is **vanilla HTML + JS + CSS** — no build step, no framework, no npm. Three files dropped into the existing `static/` directory and served by the API at `http://localhost:8000/ui/`.

## Context the agent needs

### Inline endpoint contract

The host service already runs at `http://localhost:8000`. The frontend will be served from the same origin (`/ui/`), so use **same-origin relative URLs** — no CORS handling needed in the frontend itself.

**`GET /solutions`** — returns the list of registered transformations:
```json
{
  "solutions": [
    {"slug": "fpe", "name": "Format-Preserving Encryption (O1)", "description": "..."},
    {"slug": "literal-tagging", "name": "String-Literal Type-Class Tagging (I3)", "description": "..."},
    {"slug": "llm-translation", "name": "LLM Domain Translation (I4)", "description": "..."}
  ]
}
```

The frontend should **not** hardcode the solutions list. It must fetch this endpoint on page load and populate the picker dynamically — this way new solutions added to the backend appear in the UI automatically.

**`POST /husk/{slug}`** — runs the chosen transformation:

Request body:
```json
{
  "input": "string",
  "crumb_level": 1,
  "options": {}
}
```

Success response (200):
```json
{
  "output": "string",
  "solution": "string",
  "crumb_level": 1,
  "meta": {}
}
```

Error responses:
- 404: `{"error": "unknown_solution", "detail": "<slug>"}`
- 422: FastAPI validation error
- 500: `{"error": "solution_failed", "detail": "..."}`
- 502: `{"error": "backend_unavailable", "detail": "..."}` (LLM endpoint can return this)

### Where you write code

- **Create:** `static/index.html`
- **Create:** `static/app.js`
- **Create:** `static/style.css`
- **Do not modify** anything in `app/`, `requirements.txt`, or any other solution file. The backend already mounts `static/` at `/ui` — your files appear at `http://localhost:8000/ui/` automatically.

## Implementation plan

### Step 1 — `static/index.html`

Single page. Layout (top to bottom):

1. Header: title `Husk` and a one-line subtitle.
2. **Input area** — `<textarea>` for the source code, monospace, ~12 rows visible, full width.
3. **Controls row**:
   - A `<select>` (or radio group) labeled `Solution:` populated from `/solutions` on page load.
   - A `<select>` labeled `Crumb level:` with options `0`, `1` (default), `2`, `3`.
   - An optional `<input type="text">` labeled `Target domain (LLM only):` for overriding `options.target_domain`. Disabled unless the LLM solution is selected.
   - The `Husk it` button.
4. **Status line** — shows "Idle" / "Running…" / "Error: …" / "Done in 1.2s".
5. **Output area** — `<textarea readonly>` (or `<pre>`), monospace, ~12 rows visible, full width. Right-aligned "Copy" button above it.
6. **Meta panel** — collapsed by default, shows the JSON of `meta` from the response in a `<pre>`.

Write exactly:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Husk — Transformation Tester</title>
<link rel="stylesheet" href="style.css" />
</head>
<body>
<main>
  <header>
    <h1>Husk</h1>
    <p class="sub">Paste code, pick a transformation, see the husked result.</p>
  </header>

  <section class="io">
    <label for="input">Input</label>
    <textarea id="input" rows="14" spellcheck="false" placeholder="Paste source code here…"></textarea>
  </section>

  <section class="controls">
    <div class="ctrl">
      <label for="solution">Solution</label>
      <select id="solution"></select>
      <p id="solution-desc" class="hint"></p>
    </div>

    <div class="ctrl">
      <label for="crumb">Crumb level</label>
      <select id="crumb">
        <option value="0">0 — pure structure</option>
        <option value="1" selected>1 — domain category</option>
        <option value="2">2 — subdomain</option>
        <option value="3">3 — process shape</option>
      </select>
    </div>

    <div class="ctrl ctrl-target">
      <label for="target">Target domain <span class="muted">(LLM only)</span></label>
      <input type="text" id="target" placeholder="e.g. a chess engine" disabled />
    </div>

    <div class="ctrl ctrl-action">
      <button id="run" type="button">Husk it</button>
    </div>
  </section>

  <section class="status">
    <span id="status">Idle.</span>
  </section>

  <section class="io">
    <div class="output-header">
      <label for="output">Output</label>
      <button id="copy" type="button" class="copy">Copy</button>
    </div>
    <textarea id="output" rows="14" spellcheck="false" readonly placeholder="(output appears here)"></textarea>
  </section>

  <details class="meta">
    <summary>Response metadata</summary>
    <pre id="meta">(empty)</pre>
  </details>
</main>
<script src="app.js"></script>
</body>
</html>
```

### Step 2 — `static/style.css`

Legible, minimal. Monospace where text is code; sans for chrome. Dark-friendly via system color scheme. Write exactly:

```css
:root {
  color-scheme: light dark;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --gap: 0.75rem;
  --radius: 6px;
  --border: rgba(127, 127, 127, 0.35);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 1.5rem;
  line-height: 1.4;
}

main {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

header h1 {
  margin: 0 0 0.25rem;
  font-size: 1.5rem;
  letter-spacing: -0.02em;
}

header .sub {
  margin: 0;
  opacity: 0.7;
  font-size: 0.95rem;
}

label {
  display: block;
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

textarea, select, input[type="text"], button {
  font: inherit;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: transparent;
  color: inherit;
  padding: 0.5rem 0.6rem;
}

textarea {
  width: 100%;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.9rem;
  min-height: 8rem;
}

button {
  cursor: pointer;
  font-weight: 600;
  padding: 0.55rem 1rem;
}

button:hover { background: rgba(127, 127, 127, 0.12); }
button:disabled { opacity: 0.5; cursor: not-allowed; }

.controls {
  display: grid;
  grid-template-columns: 2fr 1fr 2fr auto;
  gap: var(--gap);
  align-items: end;
}

@media (max-width: 720px) {
  .controls { grid-template-columns: 1fr 1fr; }
  .ctrl-action { grid-column: 1 / -1; }
}

.hint {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  opacity: 0.65;
}

.muted { opacity: 0.5; font-weight: normal; }

.status {
  font-size: 0.9rem;
  font-family: ui-monospace, monospace;
  opacity: 0.85;
  min-height: 1.2em;
}

.status.error { color: #c0392b; }
.status.running { color: #1f6feb; }
.status.ok { color: #16a34a; }

.output-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
}

.copy {
  padding: 0.25rem 0.6rem;
  font-size: 0.8rem;
}

details.meta pre {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-wrap: break-word;
  background: rgba(127, 127, 127, 0.08);
  padding: 0.6rem;
  border-radius: var(--radius);
  margin: 0.5rem 0 0;
}
```

### Step 3 — `static/app.js`

Vanilla, no dependencies. Write exactly:

```javascript
"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  input: $("input"),
  output: $("output"),
  solution: $("solution"),
  solutionDesc: $("solution-desc"),
  crumb: $("crumb"),
  target: $("target"),
  run: $("run"),
  copy: $("copy"),
  status: $("status"),
  meta: $("meta"),
};

let solutions = [];

function setStatus(text, kind) {
  els.status.textContent = text;
  els.status.className = "status" + (kind ? " " + kind : "");
}

function isLlmSolution(slug) {
  return /llm/i.test(slug || "");
}

function syncTargetEnabled() {
  const slug = els.solution.value;
  els.target.disabled = !isLlmSolution(slug);
}

function updateDescription() {
  const slug = els.solution.value;
  const found = solutions.find((s) => s.slug === slug);
  els.solutionDesc.textContent = found ? found.description : "";
}

async function loadSolutions() {
  setStatus("Loading solutions…", "running");
  try {
    const r = await fetch("/solutions");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const body = await r.json();
    solutions = (body.solutions || []).filter((s) => s.slug !== "example");
    if (solutions.length === 0) {
      // Show example anyway if it's the only one (so the page is useful even before
      // real solutions are wired up).
      solutions = body.solutions || [];
    }
    els.solution.innerHTML = "";
    for (const s of solutions) {
      const opt = document.createElement("option");
      opt.value = s.slug;
      opt.textContent = s.name + "  (" + s.slug + ")";
      els.solution.appendChild(opt);
    }
    updateDescription();
    syncTargetEnabled();
    setStatus("Idle.", null);
  } catch (e) {
    setStatus("Failed to load /solutions: " + e.message, "error");
  }
}

function buildOptions() {
  const opts = {};
  if (isLlmSolution(els.solution.value)) {
    const td = els.target.value.trim();
    if (td) opts.target_domain = td;
  }
  return opts;
}

async function run() {
  const slug = els.solution.value;
  if (!slug) {
    setStatus("Pick a solution first.", "error");
    return;
  }
  const body = {
    input: els.input.value,
    crumb_level: parseInt(els.crumb.value, 10),
    options: buildOptions(),
  };

  els.run.disabled = true;
  els.output.value = "";
  els.meta.textContent = "(running)";
  setStatus("Running " + slug + "…", "running");
  const t0 = performance.now();

  try {
    const r = await fetch("/husk/" + encodeURIComponent(slug), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const dt = ((performance.now() - t0) / 1000).toFixed(2);
    const text = await r.text();
    let parsed;
    try { parsed = JSON.parse(text); } catch { parsed = null; }

    if (!r.ok) {
      const errMsg = parsed && parsed.error
        ? `${parsed.error}: ${parsed.detail || ""}`
        : `HTTP ${r.status}: ${text.slice(0, 300)}`;
      setStatus(`Error (${r.status}, ${dt}s) — ${errMsg}`, "error");
      els.meta.textContent = parsed ? JSON.stringify(parsed, null, 2) : text;
      return;
    }
    els.output.value = parsed.output ?? "";
    els.meta.textContent = JSON.stringify(parsed.meta ?? {}, null, 2);
    setStatus(`Done in ${dt}s.`, "ok");
  } catch (e) {
    const dt = ((performance.now() - t0) / 1000).toFixed(2);
    setStatus(`Network error (${dt}s) — ${e.message}`, "error");
  } finally {
    els.run.disabled = false;
  }
}

async function copyOutput() {
  if (!els.output.value) return;
  try {
    await navigator.clipboard.writeText(els.output.value);
    const prev = els.copy.textContent;
    els.copy.textContent = "Copied";
    setTimeout(() => { els.copy.textContent = prev; }, 900);
  } catch {
    els.output.select();
    document.execCommand("copy");
  }
}

// Wire events
els.run.addEventListener("click", run);
els.copy.addEventListener("click", copyOutput);
els.solution.addEventListener("change", () => {
  updateDescription();
  syncTargetEnabled();
});
els.input.addEventListener("keydown", (e) => {
  // Cmd/Ctrl+Enter triggers run
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    run();
  }
});

// Boot
loadSolutions();
```

## Acceptance criteria

1. With the API server running (`uvicorn app.main:app --port 8000`), open `http://localhost:8000/ui/` in a browser.
2. The page loads, no console errors.
3. The solution dropdown is populated dynamically from `/solutions` (verify by checking the dropdown contains the slugs that `curl http://localhost:8000/solutions` returns).
4. The `Target domain` input is disabled unless an LLM solution is selected.
5. Pasting code into the input, clicking `Husk it`, and waiting → the output area populates with the response's `output` field.
6. The status line shows `Running…`, then `Done in N.NNs.` (or an error message).
7. The metadata `<details>` shows the `meta` JSON from the response.
8. Hitting `Cmd+Enter` (mac) or `Ctrl+Enter` (linux/windows) inside the input area triggers a run.
9. The `Copy` button copies the output to the clipboard.
10. When the LLM endpoint returns a 502 (backend unavailable), the status line shows the error clearly and the user can fix and retry without reloading.

## Out of scope

- **Do not** add a build step, npm, bundler, framework (React/Vue/Svelte), or transpilation. Vanilla HTML/JS/CSS only.
- **Do not** add syntax highlighting, line numbers, or fancy editor features. Plain `<textarea>` is correct.
- **Do not** add diff view between input and output. (Useful, but a separate handoff.)
- **Do not** add a history / saved-runs feature.
- **Do not** add authentication.
- **Do not** modify anything in `app/`, `requirements.txt`, or any other solution file. The frontend lives entirely in `static/`.

## Open questions

Flag rather than guess:

- The "is this an LLM solution" check uses a regex on the slug (`/llm/i`). If solution slugs change to not contain "llm", surface this rather than hardcoding a list.
- Crumb level 3 is shown but solutions vary in how meaningful it is per algorithm. The UI doesn't try to tell the user — that's surface for the spec, not the test UI.
- No request size limit enforced in the frontend. The backend caps at 200_000 chars; if a user pastes more, they'll see a 422. If the UX is bad enough that we want client-side feedback, surface it.
