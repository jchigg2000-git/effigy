# Husk Algorithms — Outer & Inner Layer Design

A catalog and evaluation of transformation algorithms that realize the two-layer Husk pipeline (commodity outer + aggressive inner) and feed the Effigy artifact downstream. This document is design work, not implementation guidance: it ideates candidates, maps each to the spec's preserve/destroy lists, names the runtime knob that tunes the crumb level, and pressure-tests the strongest pairings against pathologies of real-world codebases.

---

## 1. Design Constraints (Restated)

- **Preserve diagnostic pathology**, not surface cleanliness — control-flow shape, coupling, anti-pattern naming morphology, dead code, god-objects, dependency cycles, hidden state machines, prescriptive comments, layered/architectural violations. These are the product; destroying them destroys the product.
- **Destroy content fingerprint** — identifier text, string literals, business identifiers, prose revealing domain — at strength sufficient to defeat re-attribution to the source organization.
- **The outer layer must be commodity.** Built on cited primitives (NIST FPE, refactoring, CPG equivalence, k-anonymity) so the moat is the format spec and inference contract, not the math. If outer-layer cleverness is the IP, the IP is fragile.
- **The inner layer must leave enough contextual residue** that a consuming LLM can re-infer role and relationship at runtime from structure, neighbor patterns, and type-class hints alone. Destroying recoverability of names is required; destroying inferability of role from context is failure.
- **Privacy is a calibrated knob (Levels 0–3), not a binary cliff.** Per-file, per-region, runtime-selectable. Each level's behavior is the result of named parameters in the algorithms below — never a recompile or a fork.

---

## 2. Outer-Layer Catalog

### O1 — Format-Preserving Encryption of Identifiers (FF1/FF3)

**Mechanism.** Treat each identifier token as plaintext to a tweakable block cipher (NIST SP 800-38G FF1/FF3-1). Output is a token of identical length and charset class, deterministic under a per-corpus key, reversible only with that key. All uses of `customerOrderRouter` map to the same ciphertext (e.g., `mvpzrfpkjvpqsrtw`); referential integrity is preserved by construction. Apply the same scheme — with type-class prefixes — to string literals classified as identifier-shaped (URL paths, file paths, ENV var names, JSON keys). Salt is destroyed after husking unless a re-identification audit is intentionally retained.

**Preserve.** Control flow topology; coupling patterns; dead code; god-objects; circular dependencies; hidden state machines; layered/architectural sins — all live in AST/CFG and are invariant under bijective rename. Naming anti-patterns survive in distorted form (a 60-char identifier stays 60 chars, but the morpheme `Manager` disappears).

**Destroy.** Identifier semantic content. Business identifiers. Any literal piped through the same FPE.

**Crumb level — knob: *what is encrypted, and over which charset*.**
- L0: Encrypt every identifier and every string literal under a generic charset; comments stripped.
- L1: Spare standard-library and well-known framework symbols (`React.useState`, `pd.DataFrame`); domain identifiers ciphered.
- L2: Spare an allowlist of generic domain-category nouns (`User`, `Order`, `Account`); cipher the rest.
- L3: Cipher only proper-noun-shaped tokens and high-entropy morphemes (`AcmeCorpInvoice` → ciphered; `Invoice` survives).

**Failure mode.** Reflection (`Class.forName("com.acme.OrderRouter")`), DI containers reading bean names from XML/YAML, ORM column-name attributes, JSON wire-format keys consumed by external systems — anywhere an identifier appears as a string outside the AST, FPE breaks the binding unless the literal scanner shares the same key. Polyglot repos require a synchronized key across language toolchains. **What the consumer LLM loses when it does:** entry-point clarity (it sees a router but the route table is now ciphered strings) and any external-integration hypothesis weakens; god-object detection still holds, but reasoning about the *boundary* the god-object sits on degrades.

**Prior art.** NIST SP 800-38G (FF1/FF3-1). Production-deployed for PII tokenization at scale; commodity, well-audited.

> **Implementation note (2026-08-19) — what shipped is NOT FF1/FF3-1.** This
> document is design work (see the header). The `fpe` solution in
> `husk-api/app/solutions/fpe.py` uses [`pyffx`](https://github.com/emulbreh/pyffx)
> 0.3.0, a pure-Python balanced Feistel construction that is **not** an
> SP 800-38G cipher: its round function is HMAC-SHA1 rather than AES, and it has
> **no tweak parameter at all** — tweakability being the defining feature of
> SP 800-38G and the thing that would bind a key to a corpus. The package is
> unmaintained. Nothing in the shipped service is NIST-compliant, well-audited,
> or suitable for protecting real secrets; treat the running code as a
> feasibility demonstration of the *shape* of O1, not of its security. Note also
> that deterministic encryption over a 2-character identifier is a 63² = 3,969
> element domain — a codebook, not a cipher. See `LIMITATIONS.md`.

---

### O2 — Refactoring-Based Alpha-Renaming with Behavior-Preservation Proof Obligations

**Mechanism.** Apply only the rename subset of Opdyke/Fowler refactorings — `Rename Variable`, `Rename Method`, `Rename Class`, `Rename Package` — driven by a deterministic mapping (FPE-derived, hash-derived, or model-derived). Each rename is checked against the language's binding rules so that scope-resolution outcomes are preserved. AST shape, type graph, call graph: exactly preserved. Only labels at terminal nodes change. Ride existing IDE/tooling implementations (IntelliJ, Roslyn, rust-analyzer, ts-morph) rather than re-implementing.

**Preserve.** A strict superset of O1 (every guarantee of O1 plus: husk still compiles, still passes its existing test suite). Strong proof obligation that no diagnostic property dependent on AST/CFG/PDG shape is altered.

**Destroy.** Identifier semantic content. Literals and comments untouched (handled by I3, O5).

**Crumb level — knob: *which symbols are in scope for renaming*.**
- L0: All user-defined symbols.
- L1: All user-defined symbols outside an allowlist of stdlib/framework re-exports.
- L2: All user-defined symbols whose canonical form does not match a domain-category lexicon.
- L3: Only symbols with high-entropy or proper-noun morphology.

**Failure mode.** External-string-binding issues identical to O1, plus a category O1 doesn't have: failure to soundly model dynamic dispatch in dynamically typed languages where the renamer can't prove a call site resolves to the renamed definition (Python `getattr`, Ruby `method_missing`, JS bracket access, Smalltalk-style metaprogramming). When the renamer refuses to rename certain symbols out of caution, the consumer LLM sees that some symbols are *not* renamed and infers "these were the scary ones" — leaking a coarse signal about reflection density even when names are gone.

**Prior art.** Opdyke 1992 PhD dissertation, *Refactoring Object-Oriented Frameworks*; Fowler 1999/2018, *Refactoring*. Modern IDEs implement these soundly; commodity.

---

### O3 — Code-Property-Graph Equivalence as a Preservation Contract

**Mechanism.** Adopt Yamaguchi et al.'s Code Property Graph (CPG = AST ⋃ CFG ⋃ PDG) as the canonical structure that any Husk transformation must preserve up to relabeling. A candidate transformation `T` is admissible iff `CPG(T(P))` is isomorphic to `CPG(P)` after stripping label payloads to type-tags. **This is a specification, not a transformation** — it is the validation harness any inner-layer pipeline runs against.

**Preserve.** Every pathology in the spec maps to a CPG-detectable property: god-objects = high-fan-in nodes; cycles = SCCs in the call graph; dead code = unreachable subgraphs; hidden state machines = recurring data-flow patterns through mutable fields; layering violations = edges crossing a declared module hierarchy. Preserving the CPG preserves all of them.

**Destroy.** Nothing on its own — this is the invariant, not the operation.

**Crumb level — knob: *which CPG label classes survive as type-tags*.**
- L0: All labels stripped to type-tags only (`<id>`, `<lit>`, `<class>`).
- L1: Categorical labels survive (`<id:db-handle>`, `<lit:url>`).
- L2: Subdomain labels survive (`<id:order-store>`, `<lit:payment-endpoint>`).
- L3: Process-shape labels survive (`<id:checkout-flow-step-3>`).

**Failure mode.** Generated code, macros, and metaprogramming break CPG construction itself — the CPG of generated code is the CPG of the generator's *output*, not its source. If the husk is built from source, generated-code pathology is invisible; if built from compiled artifacts, comments-as-rules vanish (compilers don't preserve them). Polyglot repos require per-language CPG implementations; not all exist with equal fidelity (Joern is strong on C/Java, weaker on Rust/Swift). The consumer LLM may diagnose pathology that exists in source but vanishes in the husk because the underlying CPG implementation drops it.

**Prior art.** Yamaguchi, Golde, Arzt, Rieck, "Modeling and Discovering Vulnerabilities with Code Property Graphs," IEEE S&P 2014; Joern (open-source CPG implementation).

---

### O4 — k-Anonymous Identifier Vocabulary Collapse

**Mechanism.** Borrow Sweeney's k-anonymity: across the corpus, ensure every replacement token is shared by at least k distinct source identifiers. Achieved by clustering identifiers (by morphology, type, or co-occurrence) and assigning each cluster a single replacement token. Re-identification probability of any given symbol is bounded by 1/k.

**Preserve.** Population-level distribution of "name-shape badness" (long names, hungarian-prefix density, abbreviation rates) survives if clustering is morphology-aware. Naming anti-patterns persist as a statistical property.

**Destroy.** Identifier uniqueness for low-frequency symbols. Cross-reference power: two distinct variables that clustered into the same bucket become indistinguishable in the husk.

**Crumb level — knob: *the value of k*.**
- L0: k → ∞ (every identifier collapses to a single token per cluster).
- L1: k = 100.
- L2: k = 25.
- L3: k = 5.

**Failure mode.** k > 1 explicitly destroys binding, conflicting with the requirement that god-objects (detected by reference fan-in to a *single* symbol) survive. The consumer LLM cannot distinguish "one god-object" from "many small objects whose names happened to cluster" once k is high enough to merge them. **Probably wrong as a primary outer-layer transformation; viable only as a secondary knob applied to leaf identifiers (loop counters, parameter shadows) where ambiguity is harmless.**

**Prior art.** Sweeney 2002, "k-anonymity: a model for protecting privacy," IJUFKS. Application to *code* is a non-trivial adaptation that introduces the binding-loss problem above. **Mark as adaptation, not direct prior art.**

---

### O5 — Comment Paraphrase Preserving Speech-Act and Directionality

**Mechanism.** A small LLM (or rule-based rewriter) takes each comment block and emits a replacement that preserves its speech-act class — TODO, FIXME, prescriptive rule, descriptive label, deprecation notice, warning, dead-code marker — and its directionality (instructs reader / describes code / cites external authority) while destroying domain content. Output is funneled through a content classifier that flags surviving proper nouns, ticket IDs, URLs, names, dates.

**Preserve.** **Comments-as-rules** — a first-class spec target. Density and distribution of FIXME/HACK/XXX/TODO markers (a major architectural-sin signal) survives at the population level. Prescriptive force survives if the speech-act classifier is reliable.

**Destroy.** Specific business rules encoded in prose ("don't run this on Tuesdays because of the Acme batch"), JIRA links, author names, dates, customer references.

**Crumb level — knob: *generality of the substitute corpus*.**
- L0: Replace every comment with a generic stub of matching speech-act class.
- L1: Substitute corpus drawn from generic open-source code in the same language.
- L2: Substitute corpus drawn from same domain category.
- L3: Substitute corpus drawn from same subdomain, allowing process-shape phrases to survive.

**Failure mode.** Speech-act classifiers are noisy; a directive disguised as a description ("This list is in priority order — never reorder") risks downgrade to a generic descriptive comment, losing prescriptive force. The consumer LLM then misses an architectural-sin signal because the husk reads cleaner than the original. Comments embedded in non-comment positions (Python module docstrings, JSDoc bound to declarations, in-string annotations in DSLs) need separate handling.

**Prior art.** Speech-act classification of comments: Pascarella & Bacchelli, "Classifying Code Comments in Java OSS," MSR 2017. Using *paraphrase* as a privacy primitive while preserving speech-act class is a **novel synthesis** — no direct citation I'm confident in.

---

## 3. Inner-Layer Catalog

### I1 — Type-Conditioned Generic Identifier Resampling

**Mechanism.** Run static or gradual type inference over the husk. For each identifier, compute its inferred type and contextual role (parameter / local / field / method / class / package). Replace with a freshly minted name drawn from a generic vocabulary keyed by `(type, role)` — a `List<String>` parameter becomes `paramList0`, a `Map<K, V>` field becomes `fieldMap3`. Identical role+type combinations get distinguishable suffixes so binding is preserved.

**Inference contract — what residue must survive.** The consuming LLM recovers role from (a) inferred type printed at use-sites, (b) call-graph neighborhood ("this method is called by something that looks like an HTTP handler"), and (c) literal-type-tag residue from I3. It cannot recover that `paramList0` was originally `pendingRefundsForCohortB` — that's the privacy goal — but it *can* tell the parameter is a list-typed input to a layer-3 service, which is enough to diagnose architectural sins around it.

**Crumb level — knob: *granularity of the type lexicon*.**
- L0: `var0`, `var1` regardless of type. Minimum residue.
- L1: Type-prefix only: `listVar0`, `mapVar3`.
- L2: Type + coarse role: `paramList0`, `fieldMap3`, `loopVar7`.
- L3: Type + role + lexical-class hint (`storeService0`, `repoFor1`) — preserves enough to suggest layered architecture roles.

**Failure mode.** Languages with weak/no static types (Python, Ruby, JS-without-TS) yield sparse type info; output collapses toward L0 even when L2/L3 is requested. Heavy dynamic dispatch (Visitor, double dispatch, ad-hoc polymorphism through duck typing) leaves the consumer guessing at virtual call destinations. The LLM loses the ability to differentiate same-shape components ("which `List<Order>` is which") and may miss data-flow-specific pathology.

**Prior art.** Naming prediction from program properties: Raychev, Vechev, Krause, "Predicting Program Properties from Big Code," POPL 2015 (JSNice). Allamanis, Barr, Devanbu, Sutton, "A Survey of Machine Learning for Big Code and Naturalness," ACM Computing Surveys 2018. Using their *inverse* direction — generate generic names from inferred properties — is straightforward but I'm not aware of a peer-reviewed paper that frames it as a privacy primitive. **Mark as routine inverse application, not novel.**

---

### I2 — Markov / N-gram Identifier Generation Conditioned on AST Context

**Mechanism.** Train (or use a pre-trained) statistical model over identifier morphology in a generic open-source corpus. For each identifier in the husk, sample a replacement conditioned on local AST context (parent and sibling node types) and the original's length distribution. Output names look natural — `processItem`, `validateInput`, `computeTotal` — but are sampled from a domain-neutral distribution.

**Inference contract.** Names are plausible-but-generic. The LLM gets no domain leak from the names but can still parse them as natural identifiers (avoiding the out-of-distribution-tokenization quality drop seen with hash-style names). Role inference comes entirely from structure and types, never from name content.

**Crumb level — knob: *the conditioning corpus*.**
- L0: Synthetic noise; non-words.
- L1: Generic open-source corpus across languages.
- L2: Same-language, generic-domain corpus.
- L3: Same-language, sibling-domain corpus (e.g., for fintech source, condition on retail or logistics — close enough to feel right, far enough to leak nothing).

**Failure mode.** Stylometry-style attacks (Caliskan et al. 2015) exploit *distributional* properties of identifier choice — n-gram frequencies, abbreviation patterns. If the husk preserves these (even with substitute content), an attacker may correlate to a target codebase's known style and re-attribute. Conditioning the output on a *generic* corpus mitigates this — but also flattens the "naming anti-pattern" signal we want to preserve. **Real tension; see pressure test §5.**

**Prior art.** DeGuard: Bichsel, Raychev, Tsankov, Vechev, "Statistical Deobfuscation of Android Applications," CCS 2016. JSNice: Raychev et al., POPL 2015. Same machinery; using it for privacy is **less established**. The relevant attacker citation is Caliskan, Harvey, Liu, Narayanan, Voss, Yamaguchi, Greenstadt, "De-anonymizing Programmers via Code Stylometry," USENIX Security 2015.

---

### I3 — String-Literal & PII Tagging with Type-Class Placeholders

**Mechanism.** Scan all string literals; classify each into a type-class (URL, email, file path, SQL, regex, error message, UUID, secret/key, freeform). Replace with `<TYPE-CLASS:n>` where `n` is a per-class counter; uses of the same source literal share the same `n`. Optional second pass: detect PII and entity names within freeform text (Presidio-style) and apply the same placeholder scheme.

**Inference contract.** The consuming LLM sees that there is a literal of class `URL` at a position — enough to reason about external-integration shape — without seeing `https://api.acme-internal.example.com/v3/customers`. Repeated literal references survive as repeated `<URL:7>`s, preserving coupling-to-that-endpoint as a structural feature. The literal *role* is the residue; the literal *content* is gone.

**Crumb level — knob: *type-class granularity*.**
- L0: `<LIT>` for every string. No class.
- L1: Coarse class: `<URL>`, `<PATH>`, `<MSG>`, `<KEY>`.
- L2: Fine class: `<URL:HTTPS>`, `<PATH:RELATIVE>`, `<MSG:USER-FACING>`, `<SQL:SELECT>`.
- L3: Class + structural skeleton: `<URL:HTTPS:HOST?:/v?/<segment>/<segment>>`.

**Failure mode.** String literals that *encode logic* (`if (status == "PENDING_REVIEW_AFTER_2024_MIGRATION")`) get tagged as `<MSG>` and the migration-shaped state machine becomes invisible. Mitigation: route string literals appearing as comparison targets through identifier-style scrambling (treat as enum members) instead of literal redaction. PII detectors miss ad-hoc identifiers (project codenames, internal product names that don't match any NER class).

**Prior art.** Microsoft Presidio (PII detection in unstructured text); secret scanning (TruffleHog, Gitleaks). Type-classed placeholders preserving external-integration shape while destroying content are **routine engineering on top of NER**; no single-paper citation.

---

### I4 — LLM-Based Domain Translation with Pathology Anchors

**Mechanism.** Feed each module to a rewrite LLM with a system prompt: *"Translate this code into a different domain. Preserve every architectural pathology — cycles, god-objects, layering violations, dead code, comments-as-rules. Replace every domain-specific name and literal with a same-shape name from the target domain. Do not refactor. Do not improve."* A pathology-anchor checker validates output: CPG-isomorphic to input (using O3), same anti-pattern density, same comment speech-act distribution. Reject and retry on failure.

**Inference contract.** The most aggressive scrambling option. Produces a husk that reads as *natural code in a chosen target domain* — a fintech codebase comes out as a chess engine or a logistics codebase. The consuming LLM treats it at face value — it analyzes a chess engine — and the diagnosis is valid because pathology was anchor-preserved. **The consumer does not need to "see through" the disguise.** It needs to find the pathology, and the pathology survived the translation.

**Crumb level — knob: *distance between source and target domain*.**
- L0: Target = generic / abstract domain (graph traversal, pure-computation pipeline).
- L1: Target = unrelated industry vertical.
- L2: Target = adjacent vertical with similar shape (retail ↔ logistics).
- L3: Target = same vertical, different sub-segment (consumer banking ↔ commercial banking).

**Failure mode.** This is the highest-risk option.
1. Modern LLMs may smuggle leakage through stylistic choices that correlate with the source — a fintech-ism in a "chess" rewrite.
2. The pathology-anchor checker is the safety net; its coverage determines whether the rewrite preserved diagnostic value. Hidden state machines spread across multiple modules are exactly the kind of pathology the rewriter may "naturally" reorganize.
3. Determinism is hard; same input can yield different outputs across runs, weakening the inference contract that depends on consistent renaming across files.
4. Compute cost is high.
5. Original code passes through a model. **If the rewrite LLM is hosted, the privacy promise depends on that vendor's data handling**, undermining the "code never moved" guarantee — unless the rewriter runs entirely in-tenant.

**Prior art.** **Novel as a privacy primitive.** Adjacent: TransCoder (Roziere, Lachaux, Chanussot, Lample, "Unsupervised Translation of Programming Languages," NeurIPS 2020) for cross-language transpilation; LLM-based refactoring tools more broadly. None claim privacy properties or pathology-anchor preservation. **Mark clearly as speculative/novel.**

---

### I5 — Cryptographic-Hash Identifier Replacement (Truncated, Tagged)

**Mechanism.** For each identifier compute `SHA-256(secret_salt || identifier)`, base32-encode, truncate to a context-appropriate length, prefix with a type-tag. `customerId` → `idStr_4kxq2m`. Deterministic; same identifier → same hash. Not reversible without the salt; salt is destroyed after husking. Distinct from FPE in that it gives no length/charset preservation and explicitly breaks the "looks like a real name" property.

**Inference contract.** The consumer LLM receives only the type-tag prefix plus a noise suffix. Role inference depends entirely on structural signal and the type-tag — almost no name-content residue.

**Crumb level — knob: *length and richness of the prefix*.**
- L0: No prefix; `_4kxq2m`.
- L1: `<id>_4kxq2m`, `<lit>_4kxq2m`.
- L2: Type-class prefix: `idStr_`, `idMap_`, `idHandler_`.
- L3: Type-class + role: `svcHandlerOrder_4kxq2m` — leaks domain category but lets the consumer trace layered architecture.

**Failure mode.** Names look out-of-distribution to many LLMs; tokenization quality may drop and downstream analysis quality with it. Compared to I2 (which produces natural-looking names), I5 is more aggressive against stylometry but trades off consumer-side analysis fidelity. Best as a fallback when stylometry attacks are explicitly part of the threat model.

**Prior art.** HMAC-based pseudonymization is commodity (GDPR Art. 4(5) cites it as a recognized technique). Application to source-code identifiers is **routine**.

---

## 4. Composition Matrix

|                            | I1 Type-cond | I2 Markov | I3 Lit-tag | I4 LLM-translate | I5 Crypto-hash |
|----------------------------|:------------:|:---------:|:----------:|:----------------:|:--------------:|
| **O1 FPE**                 | ⚠            | ✓         | ✓ (comp.)  | ✗ (collision)    | ✓ (redundant)  |
| **O2 Refactor-rename**     | ✓✓           | ✓✓        | ✓ (comp.)  | ⚠                | ✓              |
| **O3 CPG-as-contract**     | ✓✓           | ✓✓        | ✓✓         | ✓✓               | ✓              |
| **O4 k-anonymity**         | ⚠ (binding)  | ⚠         | ⚠ (binding)| ✗                | ⚠              |
| **O5 Comment paraphrase**  | comp.        | comp.     | comp.      | subsumed by I4   | comp.          |

✓✓ = strong, complementary · ✓ = workable · ⚠ = composes only with care · ✗ = conflicts · comp. = handles a different surface and combines with anything

**Notable interactions.**

- **O1 + I4 conflict.** FPE is a deterministic bijection on identifiers. I4 re-creates identifiers from scratch in a target domain. Run together, FPE's bijection is destroyed by the rewrite; I4's pathology-anchor check breaks because post-FPE the AST has alphabet-soup identifiers it must treat as opaque tokens. Pick one.
- **O1 + I5 redundant.** Both deterministically rewrite identifiers without semantic preservation. Choose I5 if you specifically want unrecoverability without keys; choose O1 if you want optional reversibility under audit.
- **O2 + I1 / O2 + I2 are the safe defaults.** Refactor-renaming gives a clean, behavior-preserved husk; the inner layer fills it with plausible names. Standard, implementable, defensible.
- **O3 (CPG-as-contract) composes with everything** because it is a specification, not a transformation. Anything that respects CPG-isomorphism is admissible. **Use it as the validation harness over any pairing**, not as an alternative to one.
- **O4 k-anonymity is brittle as a primary outer.** It conflicts with binding preservation, which is required to detect god-objects and cycles. Useful only on leaf identifiers (loop counters, throwaway locals).
- **O5 comment paraphrase** has its own surface (prose) and is independent of all inner-layer choices — it should always run, except when subsumed by I4 (which rewrites comments as part of the domain translation).

---

## 5. Pressure Test — Two Strongest Pairings

### Candidate A: **O2 (refactor-rename) + I1 (type-conditioned resampling) + I3 (literal tagging) + O5 (comment paraphrase)**, validated against **O3 (CPG-as-contract)**

The "boring, defensible" stack. Each component has clear peer-reviewed prior art. Failure modes are understood, outputs are deterministic, husks compile and pass tests, pathology survives because every transformation is provably non-structural. Crumb level is set per-component by independent runtime knobs.

### Candidate B: **O3 (CPG-as-contract) + I4 (LLM domain translation) + I3 (literal tagging) + O5 (comment paraphrase)**

The "ambitious, novel" stack. Aggressive — produces husks that read as natural code in a chosen target domain. Inference contract holds *because* the CPG-equivalence checker enforces pathology preservation. Crumb level is set primarily by the domain-distance parameter to the rewrite LLM.

### Evidence That Would Shift Confidence Between Them

| Evidence | Direction |
|---|---|
| Frontier LLM diagnostic accuracy on architecture-pathology benchmarks (god-object, cycle, layering) is within a small margin on A's husks vs. originals | → A |
| Same study run on B shows accuracy *higher* than A because B's natural-looking domain reads as in-distribution to the LLM | → B |
| Re-identification study using Caliskan-2015 stylometry methodology successfully re-attributes A's husks via preserved name-morphology distribution | → B |
| B's pathology-anchor checker found to have systematic blind spots (cross-module hidden state machines reorganized "naturally" by the rewriter) | → A |
| B requires a hosted rewrite LLM and the customer's threat model rejects that | → A |
| A's deterministic outputs enable diff-friendly re-husking on each commit; B's nondeterminism breaks longitudinal analysis | → A |
| A flattens "naming anti-pattern" signals (long names, hungarian, abbreviations) that B preserves through cross-domain analogy | → B |

### Codebase Properties Most Likely to Break Either

| Hazard | Hits A | Hits B | Mitigation |
|---|---|---|---|
| **Reflection / dynamic class lookup** (`Class.forName`, `getattr`, `eval`) | strong | strong | Literal-table cross-mapper that scans literals for identifier shapes and applies the same renaming; mark unresolved as `<RESOLVED-DYNAMIC>` |
| **Dynamic dispatch in dynamically-typed languages** | strong (I1 starves) | medium (I4 may invent type info from context) | Per-file type-inference confidence reported in the envelope |
| **Generated code (protobuf, ORM, code-gen)** | medium — pathology is in the generator, not the output | medium | Husk the generator inputs; tag generated regions explicitly so the consumer doesn't diagnose the boilerplate |
| **Polyglot repos (Python + C ext, JVM + JS)** | high — FFI symbol tables aren't rename-safe across language boundaries | high — per-language translation risks losing cross-language coupling signals | Per-language tooling sharing a symbol-translation table; coupling signals tracked across the boundary as first-class envelope edges |
| **Build / DI configuration (Spring XML, Guice, Dagger, hcl/tf)** | high — bean names are strings, not identifiers | high | Treat config files as first-class corpus; apply the identifier table to string-form references |
| **Macros / metaprogramming (C macros, Scala macros, Lisp, Ruby DSLs)** | high — AST shape post-expansion ≠ source layout | high | Husk post-expansion or skip; declare the choice in the envelope so the consumer knows what it's looking at |
| **Comments containing JIRA/PR/URL with sensitive paths** | medium (O5 catches most) | medium | Post-paraphrase entity-leak scan with a strict allowlist; reject husks that fail |
| **Literals encoding domain logic** (status enums as strings, magic constants encoding business rules) | strong — I3 collapses to `<MSG>` | strong | Promote enum-shaped literals (literals appearing as comparison targets) to identifier-style scrambling, not literal redaction |
| **Cross-repo coupling** (microservices sharing contracts via filenames or URL paths) | strong — coupling becomes invisible | strong — translation may swap target domains inconsistently across repos | Husk the *fleet* with a shared symbol+literal table; cross-repo coupling promoted to first-class envelope edges |
| **Stylometry-style re-attribution attack** | strong — preserved morphology is the attack surface | weaker — domain translation more aggressively flattens stylistic signal | If threat model includes this, prefer B or layer I5 onto A for high-risk modules |

### Provisional Recommendation

Ship **A as the floor** — defensible, peer-reviewed, predictable, deterministic, deployable on-prem without a hosted LLM. Develop **B in parallel behind a feature flag** for clients whose threat model includes stylometric re-identification or whose privacy posture forbids any preserved morphology.

The format spec must support both. Per the spec's "moat is the standard, not the math" principle, the envelope is invariant under the choice of pipeline; a header field names the active stack so the consumer can apply the right inference contract. Crumb level is a per-pipeline runtime knob, not a per-pipeline parameter — the envelope declares Level 0..3 and each algorithm honors it through its own configured selector.

---

## Appendix — Honest Uncertainty Markers

- **O4 (k-anonymity for code)** — adapted from tabular-data k-anonymity; the binding-loss problem is the author's analysis, not a cited result. Treat as an unproven adaptation.
- **O5 (speech-act-preserving comment paraphrase)** — speech-act classification of comments has prior art (Pascarella & Bacchelli 2017), but using paraphrase for privacy while preserving speech-act class is a synthesis with no direct citation.
- **I1 (type-conditioned generic resampling as privacy primitive)** — uses well-cited machinery (JSNice, big-code naming) in a privacy direction not specifically published.
- **I2 (Markov names as privacy primitive)** — same status as I1; the relevant *attacker* literature (Caliskan 2015) is solid, the privacy use is less so.
- **I4 (LLM domain translation with pathology anchors)** — speculative. Adjacent to TransCoder but the pathology-anchor framing is novel. The biggest open question in this entire design.
- The **crumb-level gradient itself** as a calibrated 0–3 knob is a Husk-IP framing; conceptually adjacent to ε in differential privacy but not formally analogous.

When implementing, the components with strong prior art (O1 FPE, O2 refactor, O3 CPG-equivalence, I3 literal tagging, I5 hashing, O5 paraphrase mechanics) are the substrate. The novel pieces (I4, the crumb-level binding) are what need empirical validation before they ship as guarantees rather than features.
