# Pathology-Anchored Domain Translation: A Privacy Primitive for LLM-Assisted Code Review

*Preliminary version — feasibility study and design proposal*

**Justin Higgins**
Independent Researcher

---

> **Status note added 2026-08-30 — this document is superseded on its central claim.**
> The text below states that the privacy claim "remains empirically untested." That was true when
> it was written and is no longer. The pre-registered adversarial experiment (RSCH-1) ran on
> 2026-08-19 and **all four solutions failed it**, and a follow-up (RSCH-1B, 2026-08-20) found that
> the preserved architecture is *itself* domain-informative — carrying roughly half the leak a husk
> carries — which cuts against this document's premise that a verifier enforcing the
> pathology-anchor invariant would close the gap. The body is preserved as written rather than
> rewritten. **`LIMITATIONS.md` §2 and §2.0.2 are authoritative; read them first.**

## Abstract

Architectural code review increasingly relies on large language models, but organizations whose code is itself proprietary cannot submit it to third-party LLM services without exposing sensitive domain information. Existing privacy-preserving approaches — embedding-space obfuscation, prompt encryption, in-tenant inference with weaker models — force a tradeoff between diagnostic quality and source confidentiality. We propose a third option: translate the source code into a different domain using a code-specialized LLM, preserving architectural pathologies (god-objects, layering violations, duplication, hidden state machines) while replacing domain-specific names and literals. A consumer LLM diagnoses the translated husk; the diagnosis is valid for the source because pathology is structural, not lexical.

We frame this technique as a privacy primitive distinct from prior cross-domain rename work, formalize a *pathology-anchor invariant* — code property graph isomorphism, anti-pattern density preservation, and comment speech-act distribution preservation between source and husk — and argue this invariant must be verifier-enforced rather than prompt-requested. We report a preliminary feasibility study across two model scales (qwen2.5-coder 7B and 14B) on three input files in two languages, finding that pathology preservation is achievable on capable models with prompt-only enforcement; that the four-level crumb taxonomy proposed in our design collapses to a target-domain catalog without internal ordering on capable models; and that a counterintuitive privacy-leak inversion suggests the levels designed for minimal translation leak source-domain framing more than levels designed for maximal translation. The privacy claim itself — that an adversary cannot recover the source domain from the husk — remains empirically untested and is identified as the next research priority.

## 1. Introduction

Architectural code review increasingly relies on large language models. A senior engineer who once spent days tracing layering violations across a service boundary now pastes a module into a chat window and gets a diagnosis in seconds. For organizations whose code is itself the product — fintech, healthcare, defense, proprietary trading — this workflow is unavailable. The code cannot leave the tenant, and in-tenant models lag the frontier by a generation or more. The choice presented today is between weak diagnosis on private code and strong diagnosis on exposed code.

We propose a third option. Instead of redacting, encrypting, or tokenizing the source, *translate it into a different domain*. A membership-management service becomes a logistics dispatcher; a derivatives pricing library becomes a chess engine; a healthcare records API becomes a graph traversal service. The translation preserves the architectural pathologies of the original — god-objects, circular dependencies, layering violations, error-handling duplication, hidden state machines — because pathology is structural, not lexical. A consumer LLM, asked to review the translated artifact, diagnoses a chess engine. The diagnosis is valid for the source because the pathology survived the translation.

This shifts the privacy primitive's design center. Existing approaches to privacy-preserving code analysis — embedding-space perturbation [Lin et al. 2024a], prompt encryption [Lin, Hua, Zhang 2024], cross-language transpilation [Roziere et al. 2020] — preserve *functional semantics*: does the program still compute what it computed before. Our invariant is different. We preserve *diagnostic structure*: does the program still exhibit the same maintainability defects, the same coupling patterns, the same architectural smells. Functional semantics are neither necessary nor sufficient for the use case; the husk does not need to run, and a husk that runs but has been silently refactored has lost the property that made it useful.

We make three contributions.

First, we frame cross-domain LLM translation as a privacy primitive for code review, distinct from prior cross-domain rename work [Nikiema et al. 2025; Le et al. 2025] which uses the same technique as a benchmark for testing whether LLMs cheat via naming priors. Privacy is not their goal; pathology preservation is not their invariant.

Second, we formalize the *pathology-anchor invariant* — a verifiable structural property requiring code property graph isomorphism, anti-pattern density preservation within tolerance, and comment speech-act distribution preservation between source and husk. We argue this invariant must be *verifier-enforced* rather than *prompt-requested*. Our empirical results show that even capable models, when asked in the system prompt not to refactor, will silently improve code under some conditions. The verifier is the load-bearing piece of the design; without it, the privacy primitive degenerates into a stochastic rewriter with no diagnostic guarantee.

Third, we report a preliminary empirical characterization across two model scales (qwen2.5-coder 7B and 14B) on three input files in two languages. The findings are mixed and instructive. Pathology preservation is achievable on capable models with prompt-only enforcement, suggesting the verifier's role is consistency enforcement rather than catastrophic-failure prevention. The crumb-level taxonomy proposed in our design — four levels of source-target domain distance, intended as a privacy/utility slider — does not produce a meaningful gradient on capable models; the levels function as target-domain selectors with no internal ordering. We find a counterintuitive *privacy-leak inversion*: levels designed for "minimal translation" leak source-domain structural identifiers (package names, type names) while levels designed for "maximal translation" commit to the target framing more thoroughly. Determinism across runs is tighter than weaker models produce but is not byte-stable, with drift concentrated at entity-name boundaries where the source-to-target mapping is ambiguous.

We position this paper as a feasibility study and design proposal, not a deployment-ready system. The technique is operable today on a defined envelope; the privacy claim — that a consumer LLM cannot recover the source domain from the husk — remains empirically untested and is identified as the next research priority. We release this preprint to establish priority on the framing and the invariant, and to invite collaboration on the verifier and the adversarial evaluation that the full claim requires.

The remainder of the paper is organized as follows. §2 specifies the threat model and design goals. §3 surveys adjacent work. §4 presents the method, formalizes the pathology-anchor invariant, and describes the verifier-enforced rewrite loop. §5 reports preliminary empirical results across two model scales. §6 discusses limitations and the path to a full evaluation. §7 concludes.

## 2. Threat Model and Design Goals

**Adversary.** The adversary is the operator of a third-party large language model service to which the user wishes to submit code for architectural review. We assume the adversary is honest-but-curious in the cryptographic sense: they execute the requested inference faithfully and return a meaningful diagnosis, but they may log, retain, train on, or analyze the submitted prompts. The adversary's goal is to recover identifying information about the source — the organization, the product line, the proprietary algorithm, the regulatory domain, the customer base — from the prompts they receive. We do not assume the adversary is actively malicious in the sense of returning manipulated diagnoses; that threat model is orthogonal and addressed by other mechanisms (e.g., consensus across providers, signed model outputs).

We exclude from the threat model two adversaries that warrant explicit mention. First, an adversary with access to the rewriter's weights or activations can defeat the primitive trivially by inverting the translation. Our privacy claim is contingent on the rewriter executing in-tenant or in an environment the user trusts to the same degree they would trust their own infrastructure. Second, an adversary with access to side-channels orthogonal to the prompt content — submission timing, prompt length distribution, organizational network metadata — can defeat the primitive without inverting the translation. Mitigating these side-channels (batching, padding, traffic shaping) is standard practice for privacy-preserving systems and is not the contribution of this work.

**User.** The user is an engineer or engineering organization in possession of a proprietary code artifact who wishes to obtain an architectural diagnosis of that artifact from a strong general-purpose LLM. The user trusts their own infrastructure (where the rewriter runs) and trusts the LLM provider to execute the inference faithfully but does not trust the LLM provider with the source artifact in plaintext. The user has access to a static analyzer for the artifact's language and is willing to run it locally as part of the submission pipeline.

**Diagnostic-validity goal.** A diagnosis produced by the consumer LLM on the husk must be valid for the source. Concretely: if the consumer LLM identifies a god-object in the husk, the source must contain a corresponding god-object; if the consumer LLM identifies a circular import, the source must contain a corresponding circular import; if the consumer LLM identifies a copy-pasted error-handling ladder across four handlers in the husk, the source must contain a corresponding ladder across four handlers. The mapping from husk-finding to source-finding is structural — it operates on the bijection established by the pathology-anchor invariant — and is computed by the user's submission pipeline after the diagnosis returns.

**Source-domain confidentiality goal.** The consumer LLM, given the husk and its diagnostic prompt, cannot recover the source domain with probability meaningfully greater than chance over a defined target-domain catalog. We state this informally here and acknowledge that operationalizing it requires an adversarial evaluation we have not yet conducted. The naive operationalization — "ask a strong LLM to guess the source domain from the husk" — is the obvious starting point, but we expect the real evaluation to require a more sophisticated attacker that combines husk content with auxiliary signals (idiomatic patterns, library choices, comment style) the rewriter may leak.

**Auditability goal.** The user's submission pipeline must be able to certify, before transmission, that a candidate husk satisfies the pathology-anchor invariant. Certification is local — it does not depend on the consumer LLM — and is reproducible: re-running the verifier on the same source and husk yields the same accept/reject decision. This goal distinguishes our design from approaches that rely on the rewriter's good behavior or on post-hoc evaluation of diagnostic agreement. The verifier is the user's mechanism for trusting the primitive without trusting the rewriter.

**Fail-closed behavior.** When the verifier rejects a candidate husk and a regeneration budget is exhausted, the system surfaces the failure to the user rather than transmitting an uncertified husk. The user is then offered three options: increase the budget and retry, modify the input (e.g., split a too-large file into smaller units), or abandon the translation and submit the source directly under their original threat model. The system never silently downgrades the privacy guarantee; either the husk is verifier-certified or it is not transmitted.

**Non-goals.** We explicitly do not claim functional equivalence between source and husk. The husk is not expected to compile, run, or pass tests. We do not claim resistance to membership-inference attacks against the rewriter's training data; if the rewriter was trained on the source, the source domain may leak through stylistic regularities the verifier does not check. We do not claim utility for tasks other than architectural review — code completion, bug-fixing, test generation, and other LLM-assisted coding workflows have different invariants and would require their own analyses.

## 3. Related Work

We organize related work into three buckets, ordered by proximity to our contribution.

**Cross-domain identifier substitution as benchmark.** The closest technical antecedent to our rewriter is the cross-domain rename transformation studied as an obfuscation benchmark by Nikiema et al. in *The Code Barrier* [Nikiema et al. 2025] and by Le et al. in *When Names Disappear*, which releases the CLASSEVAL-OBF benchmark [Le et al. 2025]. Both papers replace identifiers in source code with terms drawn from an unrelated domain — physics terms substituted into pathfinding code, engineering terms substituted into physics code — and measure whether LLM code-understanding performance degrades. Their finding is that capable models partially see through the substitution but suffer measurable comprehension loss, particularly on intent-summarization tasks. A subsequent paper, *Poisoned Identifiers Survive LLM Deobfuscation* [Guzmán Lorenzo 2026], reports a complementary observation: when cross-domain renames produce a *coherent* alternative domain (rather than a random mix), models actively preserve the renamed identifiers in their output rather than reverting them, suggesting the rewrite is robust to deobfuscation attempts.

These works share our technique but not our purpose. The benchmark literature treats cross-domain renaming as a probe for what LLMs understand; we treat it as the core operation of a privacy primitive. The benchmark literature operates at the identifier level; we operate at the program level (full translation including control-flow narrative, comment text, and string literals). The benchmark literature does not specify a verifiable invariant; the rename is "successful" if it confuses the model. We define the pathology-anchor invariant explicitly and predicate the privacy claim on its verification. The empirical finding from *Poisoned Identifiers* — that coherent cross-domain renames are deobfuscation-resistant — is directly favorable to our threat model and we cite it as supporting evidence for the source-domain confidentiality goal.

**Privacy-preserving code analysis.** The most direct prior work on the same problem we address is CodeCipher [Lin et al. 2024a], which obfuscates source code at the token-embedding level before submission to a remote LLM. CodeCipher constructs a token-to-token confusion mapping by perturbing the LLM's embedding matrix and projecting back to nearest valid tokens, optimized to preserve task-specific output. The result is code that is unintelligible to humans but produces approximately correct LLM responses on completion, summarization, and translation tasks. EmojiCrypt [Lin, Hua, Zhang 2024] follows a similar philosophy at the prompt level, using emoji sequences as an encryption layer. Both approaches preserve *task output equivalence* — the obfuscated input produces approximately the same response as the original — under the assumption that the user trusts the obfuscation mapping but not the LLM service.

Our approach diverges in three respects. First, our invariant is structural rather than output-equivalence: we preserve diagnostic properties of the source rather than the consumer LLM's output on the source. This matters because architectural diagnosis is *generative* — the consumer LLM produces novel claims about the program — and output equivalence under obfuscation would require the consumer's diagnosis on the obfuscated input to match its diagnosis on the source, which is precisely what we cannot verify without exposing the source. Second, our husk is human-readable: it reads as natural code in the target domain. CodeCipher's output is gibberish to the user; ours can be inspected and reasoned about. Third, our verifier is the source-side certification mechanism; CodeCipher has no analog.

A closer cousin in framing, though not in code, is Cross-Domain Query Translation for Network Troubleshooting [Tran et al. 2026], which performs tiered anonymization of network telemetry preserving "relational patterns for diagnosis" while redacting PII. The diagnostic-preservation invariant they describe at the data layer is structurally analogous to the pathology-preservation invariant we describe at the code layer.

**Cross-language transpilation.** TransCoder [Roziere et al. 2020] and successors [Feng et al. 2020; Guo et al. 2021] perform unsupervised translation between programming languages — Python to Java, C++ to Python — using monolingual code corpora. The technique is mechanically similar to ours (LLM-driven code-to-code translation with structure preservation) but the goal is different: cross-language transpilation aims at *behavioral* equivalence, with the translated program expected to compile and produce identical outputs on identical inputs. Privacy is not a goal; the source language is assumed public. We adopt the technique's core insight — that LLMs can perform structure-preserving code translation reliably — and redirect it from a behavioral target to a structural one.

**Architectural smell detection with LLMs.** The downstream consumer of our primitive is an LLM-based architectural reviewer. Recent work in this space includes Tessa, Bochicchio, and Arcelli Fontana's comparison of Gemini against the Arcan architectural-smell detector [Tessa et al. 2025], iSMELL's hybrid LLM-plus-toolset approach to smell detection [Wu et al. 2024], and SmellCC's LLM-driven smell-cleaning pipeline [Xue et al. 2025]. These works establish that capable LLMs can identify architectural smells with recall comparable to or exceeding specialized tools, particularly for smells whose detection requires semantic context (high cognitive complexity, naming-convention violations) rather than purely structural pattern matching. They do not address the privacy problem; they assume the source code is available to the LLM in plaintext. Our primitive is positioned as a privacy-preserving frontend to this class of tools — the consumer LLM reviewing our husk is precisely the tool these papers evaluate.

## 4. Method

The system has three components: a rewriter that translates source to husk, an invariant that defines what preservation means, and a verifier that certifies a candidate husk against the invariant before transmission. §4.1 describes the rewriter and the target-domain selection mechanism. §4.2 formalizes the invariant. §4.3 describes the verifier and the rejection-and-retry loop that aligns the rewriter's behavior with the invariant.

### 4.1 The Rewriter

The rewriter is a single call to a code-specialized LLM with a structured system prompt and a deterministic target-domain selection mechanism. We describe the prompt structure first, then the selection mechanism, then the four-level taxonomy as originally specified — flagging that §5 finds the taxonomy does not behave as intended on capable models.

**System prompt.** The rewriter prompt has four sections. The first establishes the task: translate the input source code into the specified target domain, replacing domain-specific names and literals with target-domain equivalents. The second establishes the constraint: do not refactor, do not improve, do not add or remove code. Preserve the function signatures, the control flow, the import structure, the comment placement, the error-handling patterns, and the duplication. The third specifies the target-domain vocabulary at varying levels of detail depending on crumb level (described below). The fourth requests the output in raw form without markdown fences or explanatory prose.

The "do not refactor" constraint is doing nontrivial work. Code-specialized models are trained on benchmarks that reward refactoring — collapsing duplicated error handlers into helper functions, breaking long parameter lists into struct arguments, simplifying nested conditionals. These behaviors are exactly the failure modes the primitive cannot tolerate, because the pathologies the primitive is supposed to preserve are precisely what those benchmarks reward removing. We instruct against the behavior explicitly in the prompt; §5 reports the empirical results of that instruction's effectiveness, which vary by model scale.

**Target-domain selection.** The user invokes the rewriter with a source artifact and a crumb level $L \in \{0, 1, 2, 3\}$. The rewriter computes a deterministic hash of the source content and uses the hash to index into a per-level catalog of target domains, producing a single target. Optional override allows the user to specify a target directly, used in our evaluation but not the default deployment path. Determinism in target selection ensures that re-running the rewriter on the same input at the same level produces the same target domain (though, as §5.5 reports, not necessarily byte-equivalent output text).

**Crumb levels (as originally framed in the design).** The four-level taxonomy was designed as a privacy/utility slider with the following intuition. L0 selects a generic or abstract target domain — graph traversal, pure-computation pipeline — maximizing distance from any plausible source. L1 selects an unrelated industry vertical — a chess engine, a logistics dispatcher — maximizing realism while still committing to a frame distant from the source. L2 selects an adjacent vertical with similar architectural shape — retail next to logistics, healthcare records next to clinical research — preserving more idiomatic structure at the cost of less domain distance. L3 selects a different sub-segment of the same vertical — consumer banking next to commercial banking, membership-management next to HR — minimizing translation effort while still removing the most identifying source-domain markers.

The original intuition was that increasing $L$ would trade source-domain confidentiality for translation fidelity: at L0 the husk reads as a different program entirely; at L3 the husk reads as a closely-related cousin. §5.3 reports that this intuition does not survive contact with capable models, and §6.3 recommends reformulating the taxonomy as an explicit target-domain catalog.

**Output.** The rewriter returns the translated husk and a metadata record including the target domain selected, the model and parameters used, and the deterministic seed. The metadata is what the verifier needs to audit a husk after the fact and what the cache key requires (§5.5).

### 4.2 The Pathology-Anchor Invariant

The privacy primitive's value depends on a single property: a diagnosis produced from the husk must be valid for the source. This property is not a consequence of functional equivalence and is not enforceable by prompt. It is an explicit invariant, and the verifier's job is to certify that a candidate husk satisfies it before the husk is transmitted to the consumer LLM.

We define the pathology-anchor invariant as the conjunction of three preservation conditions between source program $S$ and husk program $H$.

**Code property graph isomorphism.** Let $\text{CPG}(P)$ denote the code property graph of program $P$ — a labeled multigraph whose nodes represent program elements (functions, basic blocks, statements, expressions) and whose edges represent control flow, data flow, and abstract syntax tree containment, following the construction of Yamaguchi et al. [Yamaguchi et al. 2014]. The invariant requires that $\text{CPG}(S)$ and $\text{CPG}(H)$ be isomorphic as labeled multigraphs under a bijective node relabeling that respects edge type but does not constrain node identifier strings. In practice, exact isomorphism is too strict — translated programs may differ in trivial ways such as expression-level reordering of commutative operations or insertion of language-idiomatic boilerplate. We relax to *graph edit distance bounded by $\epsilon$* on a defined CPG dialect, where the dialect specifies which node and edge types contribute to the distance. The dialect we use in this work weights control-flow and data-flow edges fully, AST containment edges at half, and ignores edges to literal-value nodes; literal values are expected to translate.

**Anti-pattern density preservation.** Let $\mathcal{A}$ be a fixed catalog of anti-patterns — god-object, feature-envy, layering violation, circular dependency, copy-pasted error-handling, magic-string state machine, long parameter list, and so on. For each anti-pattern $a \in \mathcal{A}$, let $\rho_a(P)$ be the per-thousand-lines occurrence count of $a$ in program $P$, computed by a static analyzer ($\rho_a$ thus depends on the analyzer; we treat the analyzer as a black-box oracle and report invariant satisfaction relative to the chosen analyzer). The invariant requires $|\rho_a(S) - \rho_a(H)| \leq \tau_a$ for each $a$, with per-anti-pattern tolerances $\tau_a$ specified in advance. Tolerances are loosest for anti-patterns whose detection is least stable across syntactic variation (e.g., feature-envy) and tightest for anti-patterns whose detection is purely structural (e.g., circular dependency, where $\tau = 0$).

**Comment speech-act distribution preservation.** Comments in real codebases are not uniform; they encode rules ("// must hold the lock before calling"), warnings ("// known to break on macOS"), TODOs, doc-strings, and dead-code markers. These speech acts are themselves diagnostic — a high density of warnings clustered in one module indicates a known-fragile boundary; a high density of TODOs indicates incomplete work. We draw on the comment taxonomy of Pascarella and Bacchelli [Pascarella & Bacchelli 2017], who classify Java comments into six top-level categories (Purpose, Notice, Code, Metadata, Discarded, Other) with sixteen subcategories. We adapt their schema to a domain-relevant five-class projection — rules, warnings, TODOs, doc-strings, and dead-code markers — which maps onto subsets of their Purpose, Code, and Discarded categories. We partition comments into these classes and require that the per-class density in $H$ be within tolerance of $S$. We do not require comment *content* to be preserved — comments may be translated along with code — only that the distribution over speech-act classes be preserved.

The three conditions are independent. CPG isomorphism alone does not guarantee anti-pattern preservation: an LLM can produce a structurally identical program that happens to lack a god-object because the original god-object's "godliness" depended on which methods were colocated, and the translation split them across two newly-introduced helper types. Anti-pattern density alone does not guarantee CPG isomorphism: an LLM can preserve the count of layering violations while reorganizing which modules participate in them. Comment distribution alone is the weakest of the three but catches a specific failure mode — silent removal of warning comments during translation — that the other two conditions miss.

**Why the invariant is verifier-enforced rather than prompt-requested.** The system prompt in our implementation explicitly instructs the rewriter to preserve all architectural pathologies and to refrain from refactoring. Empirically (§5), this instruction is honored on capable models for some inputs and violated on others. On weaker models, the instruction is violated routinely — the rewriter stubs out functions, drops conditional branches, and removes domain-specific scaffolding. Even on capable models, the rewriter occasionally "improves" code in ways that reduce a diagnostic signal: error-handling duplication is silently consolidated, a long parameter list is silently broken into two helpers. These behaviors are not adversarial; they reflect the rewriter's training distribution, which rewards refactoring on most code-quality benchmarks.

The implication is that prompt-only enforcement of the invariant is a category error. The rewriter's loss function and the privacy primitive's invariant are not aligned, and no amount of prompt engineering closes the gap reliably. The verifier — which computes $\text{CPG}$, $\rho_a$, and the comment distribution on both $S$ and a candidate $H$, and rejects-and-retries when any condition fails — is what aligns them. A husk that the verifier accepts has been certified to preserve the diagnostic structure that makes the consumer LLM's diagnosis meaningful. A husk that the verifier rejects is regenerated until it passes or until a budget is exhausted, in which case the system fails closed: the user is told the input could not be safely translated and is offered the option to send the source directly under their original threat model.

We note three limitations of the invariant as stated. First, it is *static* — it makes no claim about runtime behavior, performance characteristics, or concurrency patterns. Pathologies that manifest only under load (e.g., lock contention, cache-line false sharing) are outside the invariant's scope. Second, it is *analyzer-relative* — different static analyzers will compute different $\rho_a$ and disagree on whether a given husk satisfies the invariant. We treat the choice of analyzer as a deployment parameter and recommend that organizations using this primitive standardize on a fixed analyzer per language. Third, it is *necessary but not sufficient* for diagnostic validity — a husk satisfying the invariant may still produce a diagnosis the source's authors disagree with, because the consumer LLM itself is fallible. The invariant guarantees that whatever diagnosis the consumer produces is one that *would have been produced on a structurally equivalent program*; it does not guarantee that the diagnosis is correct.

### 4.3 Verifier-Enforced Rewrites

The verifier sits between the rewriter and the consumer LLM. It accepts a source $S$ and a candidate husk $H$, computes the three preservation conditions defined in §4.2, and emits an accept/reject decision with a structured rejection reason on failure. The rewriter wraps this verifier in a rejection-and-retry loop with a regeneration budget, and the system surfaces a fail-closed error to the user when the budget is exhausted.

**Verifier inputs and outputs.** The verifier takes as input the source artifact $S$, a candidate husk $H$, the target-domain metadata produced by the rewriter (§4.1), and a verifier configuration specifying the CPG dialect, the anti-pattern catalog $\mathcal{A}$ with per-pattern tolerances $\tau_a$, the comment speech-act taxonomy, and the graph-edit-distance bound $\epsilon$. The verifier emits one of three outcomes: *accept*, in which case the husk is forwarded to the consumer LLM along with the bijection that maps husk findings back to source findings; *reject with reason*, in which case the rejection reason is structured (which preservation condition failed, with what magnitude) and is fed back into the regeneration prompt; or *reject as invalid*, in which case the candidate is malformed (e.g., does not parse) and is discarded without contributing a feedback signal beyond a regeneration request.

**Computing the conditions.** CPG construction uses an existing tooling chain — Joern[^joern] is the canonical implementation and our recommended starting point — applied to both $S$ and $H$. Graph edit distance is computed under the dialect specified in §4.2 and compared against $\epsilon$. Anti-pattern densities $\rho_a(S)$ and $\rho_a(H)$ are computed by the user-configured static analyzer for each $a \in \mathcal{A}$, and the per-pattern absolute differences are compared against $\tau_a$. Comment speech-act classes are assigned by a small classifier over comment text trained on the Pascarella–Bacchelli taxonomy projection (§4.2); this is the component most likely to require a separate model, and we discuss in §6 the option to defer comment-distribution preservation to v2 if a satisfactory classifier is unavailable.

[^joern]: The Joern open-source CPG implementation is available at https://joern.io. Joern provides language frontends for C/C++, Java, JavaScript/TypeScript, Python, Go, and several others, and serves as our reference CPG construction in this work.

The three conditions are computed in order of increasing cost. Graph edit distance over the CPG dialect is the most expensive in absolute terms but produces the strongest signal when it fails, because the failure mode it catches (control-flow restructuring, function inlining, branch elimination) is the most damaging to diagnostic validity. Anti-pattern density is computed second; failures here typically indicate that the rewriter performed a local refactor (collapsed an error ladder, inlined a small helper) that the CPG dialect's edit-distance threshold did not catch. Comment-distribution preservation is computed last and catches the cheapest-to-execute failure mode (silent comment removal during translation), which is also the failure mode least likely to be caught by the other two conditions.

**Deployment-relative parameters.** The CPG dialect, the per-pattern tolerances $\tau_a$, and the graph-edit-distance bound $\epsilon$ are named in §4.2 but not assigned numerical values in this paper, by design. All three are *deployment parameters* rather than universal constants. The CPG dialect should be drawn from an existing implementation — we recommend adopting Joern's defaults wholesale and citing them, rather than specifying a custom node/edge weighting scheme that would require its own validation. The tolerances $\tau_a$ depend on the static analyzer chosen and on the organization's tolerance for diagnostic noise; a security-critical deployment will set $\tau_a = 0$ for circular dependencies and god-objects and accept the resulting higher rejection rate, while a cost-sensitive deployment will accept $\tau_a > 0$ on syntactically-fragile patterns like feature-envy. The graph-edit-distance bound $\epsilon$ similarly depends on input size and analyzer behavior; bounds calibrated on a per-corpus basis (using verified-clean source/husk pairs to establish a baseline) are more defensible than a global default. We leave formal calibration to v2 of this work and recommend that organizations using this primitive treat all three parameters as configuration items subject to local audit, not as values inherited from this paper.

**Rejection-and-retry loop.** The rewriter produces an initial candidate husk $H_0$. The verifier evaluates $H_0$. If accepted, $H_0$ is forwarded. If rejected, the structured rejection reason is appended to the rewriter prompt as a regeneration constraint ("the previous attempt collapsed the error-handling block at lines 47–51 into a helper function; preserve this duplication exactly"), and the rewriter is invoked again, producing $H_1$. The loop continues with $H_2, H_3, \ldots$ up to a budget $B$. If $H_B$ is still rejected, the system enters its fail-closed state.

The rejection feedback is the lever that distinguishes verifier-enforced from prompt-only rewriting. The rewriter does not need to satisfy the invariant on the first try — it needs to satisfy it eventually, and the structured feedback narrows the search space across attempts. The §5 results suggest that on capable models the first-attempt accept rate may be high enough to make $B = 1$ or $B = 2$ adequate in most cases, but our results predate the verifier's implementation and the actual operating point for $B$ is open.

**Cross-file consistency and the glossary.** The verifier as described above operates per-file. For multi-file inputs, an additional consistency layer is required to prevent the cross-file referential integrity drift observed in §5.2 (the source entity `Member` translated as `Shipment` in one file's GET handler and `Carrier` in another file's PATCH handler). We address this with a glossary pre-extraction step.

Before invoking the rewriter on any file, the system performs a static analysis pass over the full multi-file input to identify cross-file symbol references — type names exported from one file and imported in another, function names called across module boundaries, struct field names whose types are defined elsewhere. The set of such symbols, along with their reference structure, forms the glossary. The glossary is translated once, atomically, by a single rewriter call dedicated to glossary translation: every cross-file symbol gets a target-domain equivalent, and the mapping is fixed for the duration of the per-codebase translation session. Subsequent per-file rewriter calls receive the glossary as a constraint in the prompt: "the source symbol `Member` must be translated as `Shipment` everywhere it appears."

The glossary serves two purposes. First, it eliminates the cross-file drift failure mode by removing the rewriter's degree of freedom on entity-name choices for cross-file symbols. Second, it makes the husk auditable at the symbol level — given a husk diagnosis that mentions `Shipment`, the user can look up `Shipment` in the glossary and recover the source-level meaning. The glossary itself is metadata that travels with the husk through the verifier and is destroyed before the husk is sent to the consumer LLM.

**The bijection.** When the verifier accepts a husk, it produces a bijection $\phi: H \to S$ that maps husk-level program elements to source-level program elements. The bijection is computed from the CPG isomorphism witness (which establishes node-to-node correspondence) and the glossary (which establishes symbol-to-symbol correspondence). The bijection is what the user's submission pipeline uses to translate a consumer LLM's diagnosis ("the `Shipment.Cancel` method is too long") back into a source-level finding ("the `Member.Terminate` method is too long"). Without the bijection, a husk diagnosis is an opaque output; with it, the diagnosis is precisely as actionable as a source-level diagnosis would be.

**Failure modes the verifier does not catch.** The verifier as specified catches failures of the three preservation conditions. It does not catch failures that lie outside those conditions. Examples include: stylistic regularities that leak source-domain framing without violating any structural condition (a fintech codebase rewritten as a chess engine that still uses `decimal.Decimal` for piece values); semantic regressions that preserve structure but lose meaning (the rewriter swapping the order of two arguments to a constructor in a way the CPG considers equivalent but which changes the program's intent); and adversarial-grade leakage where the rewriter is trained on the source and produces a husk whose statistical features identify the source despite passing all three conditions. These failure modes require additional preservation conditions or out-of-band defenses, and we identify them as open work in §6.

## 5. Preliminary Empirical Evaluation

We report a feasibility study across two model scales on three input files in two languages. The study's purpose is to characterize the operating envelope of the rewriter component — specifically, whether prompt-only enforcement of the pathology-anchor invariant is sufficient on current models, and how the crumb-level taxonomy proposed in §4.1 manifests in practice. The verifier component is described in §4.2 and §4.3 but not yet implemented; this section reports rewriter behavior unconditionally, leaving verifier-enforced behavior to v2 of this work.

We emphasize at the outset what this section is not. It is not a benchmark — three files in two languages with one model family is too small a corpus to support quantitative comparisons against baselines. It is not an evaluation of the source-domain confidentiality goal stated in §2 — that goal requires an adversarial evaluation we identify as future work. It is a characterization of the rewriter's behavior sufficient to (a) establish that the technique is operable on current models, (b) identify the failure modes the verifier must catch, and (c) inform v2's design.

### 5.1 Setup

**Models.** We evaluate two open code-specialized models served via Ollama: qwen2.5-coder:7b and qwen2.5-coder:14b, the latter using Q4_K_M quantization. Both models were selected for local-execution feasibility consistent with the threat model in §2 (the rewriter must run in-tenant). The 14B model is the spec's recommended default; the 7B model is included to characterize model-scale sensitivity. We did not evaluate qwen2.5-coder:32b for resource reasons and identify it as a future direction.

**Sampling.** All runs use temperature 0.2. We did not evaluate temperature 0 because Ollama's deterministic-sampling behavior at very low temperatures has known sharp transitions on some hardware; 0.2 is a stable operating point that still produces near-deterministic output for most prompts. Two-run determinism is reported as part of §5.5.

**Inputs.** Three files from a real membership-management codebase, listed in Table 1. The corpus is small and skewed toward HTTP-handler / API-client code, which is the most common target for cross-organization architectural review. Larger and more varied corpora are needed before quantitative claims; we discuss the implications in §6.

| File | Language | Lines | Salient features |
|---|---|---|---|
| `server.go` | Go | 115 | HTTP server with chi router; mixed HTTP+DB concerns; copy-pasted error handling |
| `client.ts` | TypeScript | 166 | API client; 7 interfaces; URL builder with conditional params |
| `SearchForm.tsx` | TSX | 118 | React form; 6 fields; placeholder strings with domain leakage |

*Table 1: Input corpus.*

**Crumb levels.** The four levels specified in §4.1 are evaluated in their nominal interpretation: L0 = generic/abstract domain, L1 = unrelated industry vertical, L2 = adjacent vertical, L3 = same vertical / different sub-segment. Target-domain selection is deterministic given (input hash, level), with overrides available for evaluation purposes.

### 5.2 Operating Envelope: Model-Scale Sensitivity

The most consequential finding of this study is that pathology preservation on the rewriter side is *gated by model capability*, and the 7B and 14B results sit on opposite sides of that gate. We report both runs because the contrast is itself the result.

**On qwen2.5-coder:7b.** The rewriter exhibits four distinct failure modes across the four crumb levels, summarized in Table 2.

| Level | Behavior | Failure mode |
|---|---|---|
| L0 (graph) | Invents a new program | 80-line `Graph`/`Node` library replaces 115-line input |
| L1 (chess) | Stubs implementations | 27 lines, 6 methods (76% LoC reduction) on `server.go`; 42 lines, 2 stub functions on `client.ts` |
| L2 (logistics) | Near-isomorphic translation | Single working operating point |
| L3 (sub-segment) | Identity passthrough | Returns input verbatim with no translation |

*Table 2: 7B per-level failure modes.*

L0 fails because the model treats the abstract-domain prompt as license to reimagine. L1 fails because the model interprets "translate" as "describe and stub." L3 fails because the model interprets "different sub-segment of the same domain" as "no change required." Only L2, where the target domain is concrete enough to anchor the translation but distant enough to require real work, produces structurally faithful output.

A second 7B failure mode, distinct from the per-level pattern, is *cross-file referential integrity drift*. Within a single L2 translation of `client.ts`, the source entity `Member` was translated as `Shipment` in the GET-handler call sites (`searchShipments`, `getShipment`) and as `Carrier` in the PATCH-handler call sites (`patchCarrier`, `CarrierPatch`). A consuming tool reconstructing the call graph would observe two unrelated entities where the source has one. This failure is not predicted by the per-level operating-envelope analysis — L2 is the "good" cell — and represents a separate category of failure that the verifier must catch.

**On qwen2.5-coder:14b.** All four 7B failure modes disappear. L0 produces a 115-line graph-traversal service that is structurally isomorphic to the 115-line input, with `members→nodes`, `groups→edges`, and the chi route tree preserved. L1 produces a 115-line chess engine service with `members→positions`, `groups→games`, and all seven handlers intact. L2 produces a logistics dispatcher with the same structural fidelity. L3, which was the identity passthrough at 7B, produces a real translation to an HR/benefits sub-segment with `members→employees` and `FHIR→HL7`. The cross-file integrity drift is also absent: `client.ts` at L2 uses `Shipment` consistently across `searchShipments`, `getShipment`, and `patchShipment`.

The per-level behavior at 14B is summarized in Table 3. Wall-clock latency across the four runs ranged from 47.4s to 85.8s per request on the 115–166-line inputs, roughly 2–3× the 7B model's latency on this hardware; per-level breakdowns are not reported as the underlying timing data captured only the range.

| Level | Target | Output lines | Pathology preservation |
|---|---|---|---|
| L0 | graph traversal | 115 | Full |
| L1 | chess engine | 115 | Full |
| L2 | logistics | 117 | Full |
| L3 | employee/HR | 116 | Full |

*Table 3: 14B per-level behavior on `server.go` (115 input lines). Latency across runs: 47.4s–85.8s.*

### 5.3 The Crumb-Level Taxonomy Does Not Ladder on Capable Models

The taxonomy proposed in §4.1 specifies the four levels as a privacy/utility slider — L0 maximally hides the source domain at the cost of producing the most artificial-looking husk; L3 minimally hides at the benefit of producing the most natural-looking husk. The 7B results, taken alone, would partially support this framing: L2 is the "useful" middle, L0 and L3 are the broken endpoints. The 14B results falsify the framing.

At 14B, all four levels produce structurally isomorphic translations of the source. The levels differ only in *which target domain the deterministic picker selects* — graph traversal vs. chess engine vs. logistics dispatcher vs. employee lookup. There is no internal ordering; no level is "more aggressive" than another in a way that would justify a privacy/utility tradeoff curve. A user choosing between L0 and L1 at 14B is choosing between target domains, not between privacy levels.

This finding has three implications. First, the four-level taxonomy as specified is a design artifact of weaker models, where the levels were distinguishable because the model's failure modes differed across them. On capable models the failure modes are absent and the levels collapse into a domain catalog. Second, the privacy/utility slider should be reformulated for v2 as a *target-domain catalog* with explicit selection rather than as an implicit gradient. Users who care about which target domain the husk reads as should be able to specify it directly; users who do not care should accept the deterministic default. Third, evaluating the privacy claim under the original taxonomy is incoherent at 14B — there is no "high privacy" level to evaluate. The privacy evaluation must instead operate over the catalog as a whole, asking whether an adversary can recover the source domain given a husk in any target.

### 5.4 The Privacy-Leak Inversion

A counterintuitive observation from the 14B run reverses the spec's intuition about which crumb levels best serve the source-domain confidentiality goal. We report it here as a design finding rather than a quantitative result; the underlying phenomenon warrants formal evaluation in v2.

At 14B, levels L0 and L1 commit more thoroughly to the target domain than levels L2 and L3. On `server.go`, L0 (graph) renames the package to `graphapi` and the struct to a graph-appropriate type; L1 (chess) renames the package to `chessapi`. By contrast, L2 (logistics) and L3 (employee/HR) preserve source-domain structural identifiers — `package api`, `type Server struct`, `corsMiddleware`, `NewServer` — while only translating the domain nouns appearing in route paths and field names. The route tree at L2 reads `r.Route("/shipments", ...)` but the surrounding scaffolding reads as the source.

This inverts the spec's framing. The levels designed for "minimal translation" — closer target domains intended to produce the most natural husks — leak source-domain framing more, because the model interprets "adjacent vertical" as "translate the domain nouns but otherwise preserve." The levels designed for "maximal translation" leak less, because the model treats "unrelated industry" as license to commit to the new framing.

The design implication is that L0 and L1 are the appropriate defaults for the source-domain confidentiality goal, opposite the spec's recommendation. We carry this finding into §6 as a design recommendation but flag that it is based on three input files and one model and requires broader evaluation.

### 5.5 Determinism

We characterize determinism by running `client.ts` at L1 twice with identical sampling parameters and measuring divergence between the two outputs.

At 7B, the two outputs are 42 lines and 76 lines, with disjoint top-level function sets. The runs do not converge on the same translation; they produce two different programs from the same input. This level of drift makes hash-based caching unsafe and complicates audit (a re-run of the verifier on a different rewriter output may yield a different accept/reject decision).

At 14B, the two outputs are 144 lines and 159 lines with 15 vs. 16 top-level exports. Most identifiers and function bodies are byte-equivalent across the two runs: `buildSearchUrl`, `searchPlayers`, `getPlayer`, `ApiError`, `SearchFilters`, `SearchResponse`, `hasAnyFilter`, and `pgnExportUrl` appear identically in both. The drift concentrates at the PATCH-entity boundary: run 1 emits `patchGame` returning `Game` with `PositionPatch`+`MovePatch`; run 2 emits `patchPlayer` returning `Player` with `AddressPatch`+`PlayerPatch`. Both are valid translations of the source `patchMember` shape and differ only in which target-domain entity the model selected for the source `Member`.

The 14B determinism is tighter than 7B's by a substantial margin but is not byte-stable. The implication for caching is that the input hash alone is insufficient as a cache key; the honest cache key is `(input_hash, model, temperature, target_domain, sampling_seed)`. The implication for the verifier is that consistency-across-runs is a property the verifier must enforce explicitly — two acceptable husks of the same source may diagnose differently if the consumer LLM keys on entity-name choices.

### 5.6 Pathology Preservation: A Closer Look at Three Smells

We examined three smells in the source codebase and tracked preservation across crumb levels and models.

**Mixed HTTP/DB concerns** (`server.go`). The `Server` struct holds `*sql.DB` directly, with `handleReady` issuing an inline `SELECT count(*)` against the primary record table. At 14B the smell survives at all four levels (e.g., L2 renders `Dispatcher` holding `*sql.DB` with `handleAvailability` running `SELECT count(*) FROM shipments`). At 7B it survives at L2 but is erased at L1 (no DB import) and L0 (fresh program with different concerns).

**Copy-pasted error-handling ladder.** The four-line `errors.Is(err, sql.ErrNoRows)` block repeats verbatim across multiple handlers in the source. At 14B the duplication is preserved across all crumb levels; at 7B it is preserved at L2 and erased at L1 along with the rest of the DB-access shape.

**Domain-leaking string literals** (`SearchForm.tsx`). The source contains hardcoded search-placeholder literals — a record-ID pattern, a group code and a ZIP code, withheld here — that are diagnostic of the source domain. At 14B L2 these translate into the target domain as `"SH00001"`, `"FEDEX"`, and `"90210"` — the source-domain leakage is closed. At 7B L2, all five[^placeholders] source-domain placeholders are kept verbatim, defeating the privacy goal at the literal-content level.

[^placeholders]: Five placeholders in total in `SearchForm.tsx`; the three most diagnostic are shown here.

The pattern is consistent across the three smells: 14B preserves architectural pathology at all levels; 7B preserves it only at L2. This is the empirical foundation of the model-scale claim in §5.2.

### 5.7 Summary

The empirical findings can be stated as four claims, ordered by confidence.

*High confidence:* On capable code-specialized models (qwen2.5-coder:14b in this study), prompt-only enforcement of the pathology-anchor invariant is sufficient for architectural smells in the corpus we evaluated. The rewriter does not silently refactor; the smells survive translation across all crumb levels.

*High confidence:* On weaker models (qwen2.5-coder:7b), prompt-only enforcement fails in distinct, level-specific ways: invention at L0, stubbing at L1, identity-passthrough at L3, with cross-file referential integrity drift as a separate failure mode at L2. The verifier described in §4.2 and §4.3 is necessary on weaker models and remains advisable on capable models for failures we did not observe in this corpus.

*Moderate confidence:* The four-level crumb taxonomy as specified does not produce a privacy/utility gradient on capable models. It functions instead as a target-domain catalog with no internal ordering. The taxonomy should be reformulated for v2.

*Low confidence (preliminary):* The privacy-leak inversion — that L0/L1 leak source-domain framing less than L2/L3 — is real on the three files we evaluated. Whether it generalizes requires broader evaluation and a formal adversarial probe.

The corpus is small enough that none of these claims should be read as quantitative. They are characterizations sufficient to guide v2's evaluation design and to identify which questions a deployment-ready evaluation must answer.

## 6. Discussion and Limitations

We discuss limitations first, in keeping with the feasibility-study character of this work, and treat design implications and forward direction as the second half of the section.

### 6.1 What We Have Not Shown

**We have not shown that the privacy claim holds.** The source-domain confidentiality goal stated in §2 — that the consumer LLM cannot recover the source domain from the husk with probability meaningfully greater than chance — is the primitive's central value proposition. We have not evaluated it. The §5 results characterize the rewriter's structural fidelity but say nothing about whether a capable adversary, given a husk, can identify the source as a membership-management system. The favorable result from *Poisoned Identifiers* [Guzmán Lorenzo 2026] — that coherent cross-domain renames are deobfuscation-resistant — supports the claim circumstantially but does not establish it for our specific construction. A formal adversarial evaluation, in which a strong general-purpose LLM is given husks and asked to identify the source domain over a defined target catalog, is the most important next experiment and is identified in §6.4.

**We have not shown that the verifier is sufficient.** §4.2 specifies the pathology-anchor invariant and §5 demonstrates that prompt-only enforcement is sometimes adequate and sometimes not, motivating the verifier's necessity. We have not implemented the verifier and therefore have not evaluated whether the three preservation conditions (CPG isomorphism, anti-pattern density, comment speech-act distribution) are jointly sufficient to certify diagnostic validity. Sufficiency is the second-most-important open question, and answering it requires a paired experiment: collect diagnoses from a consumer LLM on source/husk pairs that the verifier has accepted, and measure agreement between source-diagnosis and husk-diagnosis after applying the bijection.

**We have not shown that the technique scales.** Our corpus is three files. Real codebases are thousands of files with cross-cutting concerns that span module boundaries. Preserving CPG isomorphism within a single file is a different problem from preserving inter-module dependency structure across a multi-file rewrite, and our cross-file referential integrity finding at 7B (§5.2) suggests the latter is meaningfully harder. A whole-codebase evaluation requires either a chunking strategy that preserves cross-file references or a single-pass rewrite over a context window large enough to fit the whole codebase, neither of which we have evaluated.

**We have not shown the technique is language-agnostic.** Our results cover Go, TypeScript, and TSX. Languages with substantially different idioms — Rust with its type-state patterns, Haskell with its expression-oriented purity, embedded C with its memory-mapped I/O — may exhibit failure modes our corpus does not surface. The pathology-anchor invariant is defined over CPG dialects, and CPG construction is language-specific; extending the invariant to a new language is not free.

### 6.2 Threats to Validity

**Construct validity.** The pathology-anchor invariant operationalizes "diagnostic preservation" as three structural conditions; whether these adequately capture diagnostic validity is a construct claim defended in §4.2 but not empirically validated. A husk satisfying all three conditions may still fail to support diagnoses keyed on naming conventions, domain-specific idioms, or non-local data flows the CPG dialect underweights.

**Internal validity.** §5.6's preservation observations rest on manual inspection of three smells in three files; we did not compute $\rho_a$ via a static analyzer or measure tolerances. The categorical "preserved/erased" judgments would benefit from graded preservation against analyzer-computed densities.

**External validity.** The corpus is drawn from one industry domain (membership management) and biased toward HTTP-handler / API-client code — among the most common public-internet code shapes and thus easiest to translate. The favorable 14B results may reflect abundant training data for *translations into* our evaluated target domains (chess, logistics, graph traversal, HR/benefits); rarer targets and less common code shapes (compilers, kernel modules, scientific simulation) may produce worse results.

**Model validity.** One model family (qwen2.5-coder) at two scales. Model-scale sensitivity may not transfer; 14B's L0 success may reflect specific training-data properties other capable models lack. Multi-family evaluation (DeepSeek-Coder, CodeLlama, GPT-class) is needed before "capable models" generalizes.

### 6.3 Design Implications

The §5 findings carry three recommendations forward into v2.

**Default to L0 or L1 for the source-domain confidentiality goal.** The privacy-leak inversion in §5.4 inverts the spec's intuition: the levels designed for "minimal translation" preserve more source-domain framing than the levels designed for "maximal translation." On capable models, L0 (generic/abstract) and L1 (unrelated industry) commit more thoroughly to the target domain and leak less. We recommend L0 or L1 as defaults, with L2 and L3 reserved for cases where a more natural-looking husk is needed for human inspection of the husk itself.

**Reformulate the crumb-level taxonomy as a target-domain catalog.** §5.3 establishes that on capable models the four levels do not form a meaningful gradient. The taxonomy should be replaced with an explicit catalog of target domains, each chosen for distance from a defined set of source domains and for adversarial diversity. Users would select a target either explicitly or via deterministic mapping from the source. The "level" abstraction is a 7B-era artifact that the empirical results do not support.

**Make the cache key honest.** §5.5 establishes that input hash alone is an unsafe cache key — the same input can produce two valid but non-identical husks. The cache key should be `(input_hash, model, temperature, target_domain, sampling_seed)`, and re-runs without all five components fixed should be treated as new translations rather than cache hits. This has implications for audit: if an organization wants to certify that "the husk we sent to provider X on date D was a faithful translation of source S," the certification must record the full key, not just the input hash.

### 6.4 Forward Direction

We identify five experiments that v2 of this work should report.

**Adversarial source-domain identification.** Construct a target-domain catalog of N domains; husk a corpus of source artifacts to randomly-selected targets from the catalog; ask a strong general-purpose LLM (the adversary) to identify the source domain given only the husk. Measure recovery rate against chance ($1/N$). The privacy claim is supported if recovery rate is statistically indistinguishable from chance across an adequate corpus and target catalog.

**Verifier sufficiency.** Implement the verifier per §4.2 and §4.3; collect diagnoses from a consumer LLM on source/husk pairs the verifier accepts; measure agreement between source-diagnosis and husk-diagnosis under the structural bijection. The sufficiency claim is supported if accepted husks produce diagnoses that translate back to valid source diagnoses with high agreement.

**Multi-file evaluation.** Extend the rewriter and verifier to operate over codebases of $\geq 50$ files. Evaluate whether cross-file referential integrity holds (the 7B Member→Shipment/Carrier failure motivates this) and whether inter-module dependency structure is preserved.

**Multi-family model evaluation.** Repeat §5 across at least three model families. Characterize which findings (operating envelope, taxonomy collapse, privacy-leak inversion) generalize and which are qualitative properties of qwen2.5-coder.

**Failure-mode taxonomy.** Curate a corpus of rewriter failure modes — invention, stubbing, identity passthrough, cross-file drift, refactoring, comment removal — and measure each verifier condition's catch rate against this corpus. This characterizes the verifier's coverage and identifies which failure modes require additional preservation conditions beyond the three we propose.

We additionally identify two open design questions that we leave to community discussion. First, whether the rewriter should be a single LLM call or a multi-stage pipeline (e.g., glossary extraction, structural translation, literal translation, comment translation as separate stages) — the multi-stage approach offers more verifier hook points but introduces latency that may make in-tenant deployment impractical. Second, whether the target-domain catalog should be public or per-organization-private — a public catalog enables shared adversarial evaluation but exposes the set of plausible targets to adversaries, while a per-organization-private catalog reverses the tradeoff.

## 7. Conclusion

We have proposed pathology-anchored domain translation as a privacy primitive for LLM-assisted code review. The contribution is a framing, an invariant, and a research agenda: cross-domain translation as a privacy mechanism rather than a benchmark probe; the pathology-anchor invariant as a verifier-enforced structural property whose preservation is necessary for the diagnostic-validity goal; and an empirical characterization sufficient to guide a deployment-ready evaluation.

The preliminary results are mixed in instructive ways. On capable code-specialized models, prompt-only enforcement of the invariant is sufficient for the architectural smells we examined, suggesting the technique is operable today and that the verifier's role is consistency enforcement rather than catastrophic-failure prevention. On weaker models, the rewriter exhibits four distinct level-specific failure modes that the verifier must catch, motivating its necessity even when the technique appears to work. The crumb-level taxonomy proposed in our design does not survive contact with capable models — the four levels collapse into a target-domain catalog with no internal ordering — and a counterintuitive privacy-leak inversion suggests the levels designed for "minimal translation" are the worst defaults for the source-domain confidentiality goal. The taxonomy should be reformulated.

The privacy claim itself remains untested. The §5 results characterize the rewriter; they do not establish that an adversary cannot recover the source domain from the husk. The most important next experiment is the adversarial source-domain identification described in §6.4, paired with verifier-sufficiency evaluation. Until those experiments report, this work should be read as a design proposal with feasibility evidence, not as a deployable system.

We release this preprint to establish priority on the framing and the invariant, and to invite collaboration on the verifier and the adversarial evaluation that the full claim requires. The technique is operable today on a defined envelope; the verifier closes the gap.

---

## References

Feng, Z., Guo, D., Tang, D., Duan, N., Feng, X., Gong, M., Shou, L., Qin, B., Liu, T., Jiang, D., and Zhou, M. (2020). CodeBERT: A Pre-Trained Model for Programming and Natural Languages. In *Findings of the Association for Computational Linguistics: EMNLP 2020*, pp. 1536–1547. arXiv:2002.08155.

Guo, D., Ren, S., Lu, S., Feng, Z., Tang, D., Liu, S., Zhou, L., Duan, N., Svyatkovskiy, A., Fu, S., Tufano, M., Deng, S. K., Clement, C., Drain, D., Sundaresan, N., Yin, J., Jiang, D., and Zhou, M. (2021). GraphCodeBERT: Pre-training Code Representations with Data Flow. In *International Conference on Learning Representations (ICLR 2021)*. arXiv:2009.08366.

Guzmán Lorenzo, L. (2026). Poisoned Identifiers Survive LLM Deobfuscation: A Case Study on Claude Opus 4.6. arXiv:2604.04289.

Le, C. C., et al. (2025). When Names Disappear: Revealing What LLMs Actually Understand About Code. arXiv:2510.03178. (Releases the CLASSEVAL-OBF benchmark.)

Lin, G., Hua, W., and Zhang, Y. (2024). EmojiCrypt: Prompt Encryption for Secure Communication with Large Language Models. arXiv:2402.05868. (Subsequently retitled EmojiPrompt in v3, 2025.)

Lin, Y., Wan, C., Fang, Y., and Gu, X. (2024a). CodeCipher: Learning to Obfuscate Source Code Against LLMs. arXiv:2410.05797.

Nikiema, S. L., Samhi, J., Kaboré, A. K., Klein, J., and Bissyandé, T. F. (2025). The Code Barrier: What LLMs Actually Understand? arXiv:2504.10557.

Pascarella, L., and Bacchelli, A. (2017). Classifying Code Comments in Java Open-Source Software Systems. In *Proceedings of the 14th International Conference on Mining Software Repositories (MSR 2017)*, pp. 227–237. DOI: 10.1109/MSR.2017.63.

Roziere, B., Lachaux, M.-A., Chanussot, L., and Lample, G. (2020). Unsupervised Translation of Programming Languages. In *Advances in Neural Information Processing Systems 33 (NeurIPS 2020)*. arXiv:2006.03511.

Tessa, C., Bochicchio, M., and Arcelli Fontana, F. (2025). Exploring Architectural Smells Detection Through LLMs. In *Software Architecture* (Springer Lecture Notes in Computer Science), pp. 90–98. DOI: 10.1007/978-3-032-02138-0_6.

Tran, N. P., Jaumard, B., Premkumar, K., and Memon, S. (2026). Cross-Domain Query Translation for Network Troubleshooting: A Multi-Agent LLM Framework with Privacy Preservation and Self-Reflection. arXiv:2604.13353.

Wu, D., Mu, F., Shi, L., Guo, Z., Liu, K., Zhuang, W., Zhong, Y., and Zhang, L. (2024). iSMELL: Assembling LLMs with Expert Toolsets for Code Smell Detection and Refactoring. In *Proceedings of the 39th IEEE/ACM International Conference on Automated Software Engineering (ASE 2024)*, pp. 1345–1357. DOI: 10.1145/3691620.3695508.

Xue, Z., Zhang, X., Gao, Z., Hu, X., Gao, S., Xia, X., and Li, S. (2025). Clean Code, Better Models: Enhancing LLM Performance with Smell-Cleaned Dataset. arXiv:2508.11958. (Also published in *ACM Transactions on Software Engineering and Methodology* / FSE 2025, DOI: 10.1145/3793252.) Introduces SmellCC.

Yamaguchi, F., Golde, N., Arp, D., and Rieck, K. (2014). Modeling and Discovering Vulnerabilities with Code Property Graphs. In *2014 IEEE Symposium on Security and Privacy*, pp. 590–604. DOI: 10.1109/SP.2014.44.

---

## License

This preprint is released under the Creative Commons Attribution 4.0 International License (CC BY 4.0). Readers are free to share and adapt the material with appropriate attribution.

---

## v1 Submission Notes (deferred to v2)

The following items are intentionally deferred and noted here for transparency. Each is discussed in the body where it arises; this section consolidates the deferral list for readers and reviewers.

- **CPG dialect specification.** §4.3 adopts Joern's defaults wholesale rather than specifying a custom node/edge weighting scheme. A formal dialect specification with weighted distance metrics is left to v2.
- **Tolerances $\tau_a$ and bound $\epsilon$.** §4.3 treats these as deployment parameters subject to local audit and per-corpus calibration. Specific values are not asserted in v1; calibration methodology is v2 work.
- **Verifier implementation.** §4.3 specifies the verifier; §5 reports rewriter behavior unconditionally without verifier enforcement. Verifier-enforced rewrite results are v2.
- **Adversarial privacy evaluation.** §6.1 names this as the primary v2 experiment. The privacy claim is unevaluated in v1.
- **arXiv endorsement and submission logistics.** Endorsement path is being arranged separately; v1 is released here as a draft pending the endorsement process.

---

*Correspondence: via the project repository.*