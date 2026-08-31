"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  input: $("input"),
  output: $("output"),
  solution: $("solution"),
  solutionDesc: $("solution-desc"),
  crumb: $("crumb"),
  crumbLabel: $("crumb-label"),
  targetId: $("target-id"),
  target: $("target"),
  model: $("model"),
  modelHint: $("model-hint"),
  run: $("run"),
  copy: $("copy"),
  status: $("status"),
  meta: $("meta"),
  emitMap: $("emit-map"),
  diagnosis: $("diagnosis"),
  dehusked: $("dehusked"),
  dehuskRun: $("dehusk-run"),
  dehuskCopy: $("dehusk-copy"),
  dehuskHint: $("dehusk-hint"),
};

let solutions = [];
// The pseudonym -> original map from the last husk that emitted one. Kept only
// in this browser tab; never sent back to the server (dehusking is client-side).
let lastReidentifyMap = null;
const CRUMB_LABEL_DEFAULT = "Crumb level";
const CRUMB_LABEL_LLM = "Crumb level (ignored for this solution)";
const MODEL_HINT_LLM = "$ cheapest → $$$$ priciest (per-token price)";
const MODEL_HINT_NON_LLM = "Switch Solution to “LLM Domain Translation” to pick a model.";

function setStatus(text, kind) {
  els.status.textContent = text;
  els.status.className = "status" + (kind ? " " + kind : "");
}

function isLlmSolution(slug) {
  return /llm/i.test(slug || "");
}

function syncTargetEnabled() {
  const slug = els.solution.value;
  const isLlm = isLlmSolution(slug);
  els.target.disabled = !isLlm;
  els.targetId.disabled = !isLlm;
  els.model.disabled = !isLlm;
  if (els.modelHint) {
    els.modelHint.textContent = isLlm ? MODEL_HINT_LLM : MODEL_HINT_NON_LLM;
    els.modelHint.classList.toggle("warn", !isLlm);
  }
  els.crumbLabel.textContent = isLlm ? CRUMB_LABEL_LLM : CRUMB_LABEL_DEFAULT;
}

async function loadTargetCatalog() {
  try {
    const r = await fetch("llm-translation-targets.json");
    if (!r.ok) return;
    const body = await r.json();
    const targets = (body.targets || []);
    // Preserve the leading "deterministic default" option.
    const placeholder = els.targetId.querySelector('option[value=""]');
    els.targetId.innerHTML = "";
    if (placeholder) els.targetId.appendChild(placeholder);
    for (const t of targets) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.label;
      els.targetId.appendChild(opt);
    }
  } catch {
    // Catalog is optional UI sugar; selection still works without it.
  }
}

async function loadModels() {
  try {
    const r = await fetch("llm-translation-models.json");
    if (!r.ok) return;
    const body = await r.json();
    const models = (body.models || []);
    // Preserve the leading "server default" option.
    const placeholder = els.model.querySelector('option[value=""]');
    els.model.innerHTML = "";
    if (placeholder) els.model.appendChild(placeholder);
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label}  ·  ${m.cost}`;
      els.model.appendChild(opt);
    }
  } catch {
    // Model catalog is optional UI sugar; the server default still applies.
  }
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
    const tid = els.targetId.value;
    if (td) {
      // Free-text override wins; backend ignores target_id when target_domain is set.
      opts.target_domain = td;
    } else if (tid) {
      opts.target_id = tid;
    }
    const model = els.model.value;
    if (model) opts.model = model;
  }
  // Opt-in re-identification map. Reversible solutions (fpe, literal-tagging)
  // honour this; others ignore it harmlessly.
  if (els.emitMap && els.emitMap.checked) opts.emit_map = true;
  return opts;
}

// Rewrite an LLM diagnosis of husked code back into real identifiers/literals,
// entirely in-browser. Mirrors app/dehusk.py: longest pseudonym first, and
// word-shaped pseudonyms only match at token boundaries so they are not
// rewritten inside a larger word. The word-shaped test must NOT require a
// leading alpha/underscore — fpe pseudonyms are ciphered over letters+digits
// and often start with a digit, and they need the same boundary guard.
function reverseSubstitute(text, mapping) {
  const keys = Object.keys(mapping || {}).filter((k) => k.length > 0);
  if (keys.length === 0) return { text, count: 0 };
  keys.sort((a, b) => b.length - a.length);
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const wordKeyRe = /^[A-Za-z0-9_]+$/;
  const parts = keys.map((k) =>
    wordKeyRe.test(k)
      ? `(?<![A-Za-z0-9_])${esc(k)}(?![A-Za-z0-9_])`
      : esc(k)
  );
  const re = new RegExp(parts.join("|"), "g");
  let count = 0;
  const out = text.replace(re, (m) => {
    count += 1;
    return mapping[m];
  });
  return { text: out, count };
}

function syncDehuskEnabled() {
  const ready = !!(lastReidentifyMap && Object.keys(lastReidentifyMap).length);
  if (els.dehuskRun) els.dehuskRun.disabled = !ready;
  if (els.dehuskHint) {
    els.dehuskHint.textContent = ready
      ? `(${Object.keys(lastReidentifyMap).length} mappings ready)`
      : "(husk with “Emit re-identification map” first)";
  }
}

function runDehusk() {
  if (!lastReidentifyMap) return;
  const { text, count } = reverseSubstitute(els.diagnosis.value, lastReidentifyMap);
  els.dehusked.value = text;
  setStatus(`Dehusked — ${count} substitution${count === 1 ? "" : "s"}.`, "ok");
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
    // Capture the opt-in re-identification map so the dehusk panel can use it.
    lastReidentifyMap = parsed.reidentify_map ?? null;
    syncDehuskEnabled();
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

async function copyDehusked() {
  if (!els.dehusked.value) return;
  try {
    await navigator.clipboard.writeText(els.dehusked.value);
    const prev = els.dehuskCopy.textContent;
    els.dehuskCopy.textContent = "Copied";
    setTimeout(() => { els.dehuskCopy.textContent = prev; }, 900);
  } catch {
    els.dehusked.select();
    document.execCommand("copy");
  }
}

// Wire events
els.run.addEventListener("click", run);
els.copy.addEventListener("click", copyOutput);
els.dehuskRun.addEventListener("click", runDehusk);
els.dehuskCopy.addEventListener("click", copyDehusked);
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
loadTargetCatalog();
loadModels();
syncDehuskEnabled();
