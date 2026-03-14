# MarkTeX v0.1

## Phase Model Specification

## 1. Scope

This document defines the end-to-end phase model of MarkTeX.

It specifies:

* the compilation phases,
* the semantic responsibility of each phase,
* what data may still remain unresolved at each boundary,
* where errors belong,
* how symbolic values move across phases,
* and the invariants that make the entire pipeline coherent.

This document is the coordination layer for all other specifications.

---

## 2. Design Law

MarkTeX is phase-separated by design.

The central law is:

> each phase must decide exactly what belongs to it, and must not steal work from a later or earlier phase.

This is not merely an implementation preference.
It is a semantic requirement.

Without phase discipline, MarkTeX would collapse into:

* parser-time evaluation,
* backend-invented semantics,
* ad hoc fallback,
* and untraceable errors.

The language therefore requires explicit phase boundaries.

---

## 3. Canonical Pipeline

The canonical pipeline is:

```text id="9xyw9l"
.mtx
-> CST
-> Surface AST
-> NIR
-> EIR
-> TIR
-> .tex
-> TeX engine pass(es)
-> PDF
```

This pipeline is normative in structure, even if an implementation fuses internal steps for optimization.

---

## 4. Phase Summary

## 4.1 CST Phase

Produces concrete syntactic structure.

Responsible for:

* tokenization,
* delimiter matching,
* source span preservation,
* line structure,
* raw syntactic containment.

Not responsible for:

* semantic normalization,
* host execution,
* backend interpretation.

---

## 4.2 Surface AST Phase

Produces parsed source constructs.

Responsible for:

* directive recognition,
* Markdown block and inline parsing,
* initial bracket-call capture,
* reference-form capture,
* raw MOS payload capture.

Not responsible for:

* bracket-call semantic disambiguation,
* patch typing,
* Python execution,
* state resolution.

---

## 4.3 NIR Phase

Produces normalized semantic IR.

Responsible for:

* resolving `[]()` into MTX inline control or Markdown fallback,
* parsing MOS into typed semantic objects,
* normalizing directives into explicit patches and regions,
* assigning patch lifetimes,
* making scope structure explicit,
* validating context legality,
* preserving host expressions without executing them.

Not responsible for:

* executing Python,
* reducing expressions by runtime value,
* backend lowering.

---

## 4.4 EIR Phase

Produces expanded semantic IR.

Responsible for:

* executing host statements,
* evaluating host expressions where possible,
* materializing generated nodes,
* constructing typed objects from host results,
* reducing concrete expressions,
* preserving symbolic expressions when concrete resolution is not yet possible.

Not responsible for:

* backend-specific realization,
* TeX runtime strategy,
* page-finalization decisions that belong to the engine.

---

## 4.5 TIR Phase

Produces backend-oriented IR.

Responsible for:

* mapping EIR semantics to backend-capable structures,
* preserving symbolic backend placeholders,
* selecting runtime primitives,
* separating preamble/runtime needs from document flow,
* classifying multi-pass dependencies.

Not responsible for:

* source-level syntax interpretation,
* arbitrary semantic invention,
* host execution.

---

## 4.6 TeX Emission Phase

Produces emitted `.tex`.

Responsible for:

* serializing TIR into a structured backend artifact,
* loading runtime support,
* preserving source/expansion traceability where possible.

Not responsible for:

* deciding language semantics,
* disambiguating source constructs,
* inventing missing runtime values.

---

## 4.7 Engine Phase

Produces backend runtime realization.

Responsible for:

* page construction,
* line breaking,
* box/glue behavior,
* current-page values,
* running marks,
* multi-pass aux generation,
* engine-resolved symbolic values.

Not responsible for:

* source parsing,
* Python evaluation,
* typed patch semantics.

---

## 5. Phase Boundaries

Each phase boundary is a contract.

The output of one phase must be a valid input to the next.

No later phase may rely on “knowing what the earlier phase probably meant.”

This implies:

* CST must preserve enough structure for Surface AST,
* Surface AST must preserve enough structure for normalization,
* NIR must remove all source-level semantic ambiguity,
* EIR must remove all host-evaluation ambiguity,
* TIR must remove all backend-structural ambiguity.

---

## 6. What Must Be Decided Where

## 6.1 Must be decided by CST

* token boundaries
* matching delimiters
* comment-line recognition
* directive-line lexical recognition
* raw span boundaries

## 6.2 Must be decided by Surface AST

* block classification
* inline container structure
* generic bracket-call capture
* generic reference capture
* directive family recognition

## 6.3 Must be decided by NIR

* `[]()` MTX vs Markdown resolution
* MOS parsing
* patch typing
* patch lifetime assignment
* scope-stack structure
* field legality by position and lifetime
* source-level ambiguity elimination

## 6.4 Must be decided by EIR

* host result materialization
* host-generated node insertion
* concrete expression reduction
* symbolic vs concrete expression classification
* host-side semantic object construction

## 6.5 Must be decided by TIR

* backend primitive selection
* symbolic lowering class
* runtime ABI usage
* multi-pass dependency registration
* page-furniture backend mapping

## 6.6 Must be decided by engine execution

* actual page numbers
* final page count
* actual page breaks
* running marks based on final pagination
* aux-file resolved cross-reference positions

---

## 7. Symbolic Value Mobility

A symbolic value may legally survive across multiple phases.

This is expected.

The allowed lifecycle is:

```text id="u4um9y"
source expression
-> NIR expression node
-> EIR symbolic value or symbolic expression
-> TIR symbolic placeholder
-> backend runtime resolution
-> final rendered value
```

A value need not become concrete in EIR merely because it is visible there.

This is especially important for:

* `PAGE.N`
* `PAGE.MAX`
* cross-reference page lookups
* running marks
* counters dependent on engine execution

---

## 8. Error Ownership

Every error belongs to a phase.

A correct implementation SHOULD report errors at the earliest phase that has enough information to identify them correctly.

This is a core design principle.

---

## 8.1 CST Errors

Examples:

* unmatched delimiter
* malformed directive introducer tokenization
* invalid raw lexical form

These are syntax-structure errors.

---

## 8.2 Surface AST Errors

Examples:

* malformed block structure
* invalid fenced-block structure
* malformed bracket outer shell
* malformed `[^ ... ]` shell

These are source-parse errors.

---

## 8.3 NIR Errors

Examples:

* invalid MOS syntax
* `[]()` payload parses as MOS but is invalid in inline context
* invalid patch field
* illegal lifetime for a field
* unmatched scope close
* leaked scope at normalization boundary

These are normalization and semantic-typing errors.

---

## 8.4 EIR Errors

Examples:

* Python syntax error in host payload
* host exception
* invalid host return type
* invalid symbolic operation
* block node returned in inline context
* schema-invalid patch produced by host code

These are host-expansion errors.

---

## 8.5 TIR Errors

Examples:

* no backend strategy for a required semantic object
* unsupported symbolic lowering class
* impossible runtime ABI mapping
* unsupported canonical feature on chosen backend profile

These are backend-lowering errors.

---

## 8.6 Engine Errors

Examples:

* TeX runtime failure
* package/runtime incompatibility
* engine-level undefined control sequence
* failed auxiliary stabilization
* backend runtime invariant violation

These are backend execution errors.

---

## 9. Earliest-Correct Error Rule

A phase MUST NOT defer an error merely because a later phase might also fail.

If NIR can determine that a field is illegal in inline position, it MUST report that there, even if the backend would also choke on the result later.

Likewise, EIR must reject an invalid host result even if it could technically stringify into something backend-readable.

The rule is:

> report errors at the earliest correct semantic boundary.

---

## 10. Information Preservation

Each phase may simplify, normalize, or lower structure.
But it must preserve the information required by later phases and tooling.

The essential preserved classes are:

* source origin,
* expansion origin,
* symbolic provenance,
* scope provenance,
* resource provenance.

No phase may erase provenance needed for meaningful downstream diagnostics.

---

## 11. Provenance Chain

Every semantically relevant artifact SHOULD carry an origin chain.

A conceptual provenance chain may contain:

* source file and span,
* enclosing directive or inline context,
* host expansion site,
* generated-from node identity,
* lowering origin,
* backend placeholder origin.

This is necessary because later phases work on objects that may no longer resemble source syntax directly.

---

## 12. Purity of Earlier Phases

Earlier phases should remain structurally pure.

This means:

* CST does not evaluate
* Surface AST does not type-check deeply
* NIR does not execute Python
* TIR does not reinterpret source syntax

Each phase may validate what belongs to it, but may not absorb another phase’s primary responsibility.

This keeps the compiler explainable.

---

## 13. Normalization Closure

NIR is the first phase in which MarkTeX becomes semantically closed with respect to source syntax.

After NIR:

* there is no unresolved `[]()` ambiguity,
* there is no untyped MOS object,
* there is no implicit scope structure,
* there is no unclassified patch lifetime.

This is one of the most important invariants in the entire language.

---

## 14. Expansion Closure

EIR is the phase in which MarkTeX becomes host-closed.

After EIR:

* there are no unexecuted host statements,
* host expressions have either reduced or become symbolic,
* host-generated nodes are already ordinary semantic nodes,
* patch and node validity is already established.

After EIR, the language is no longer “waiting for Python.”

---

## 15. Backend Closure

TIR is the phase in which MarkTeX becomes backend-closed.

After TIR:

* all backend strategies are chosen,
* symbolic placeholders are classified,
* runtime ABI calls are determined,
* unsupported backend semantics are already diagnosed.

After TIR, the backend should not need to invent semantics.

---

## 16. Multi-Pass Boundary

The engine phase may require multiple runs.

This is the only phase family in which repeated execution is expected as part of normal semantics.

The compiler-side phases:

* CST
* Surface AST
* NIR
* EIR
* TIR

are conceptually single-pass transformations, even if implemented incrementally.

The engine side is permitted to iterate until stabilization.

---

## 17. Stabilization Semantics

A backend-stable build is one in which all required backend-resolved symbolic values have converged.

Typical convergence targets:

* total page count
* reference pages
* table of contents anchors
* running marks
* bibliography ordering or numbering if backend-managed

A MarkTeX build driver SHOULD explicitly distinguish:

* compile success,
* engine success,
* stabilization success.

These are not identical notions.

---

## 18. Chosen Backend and Phase Semantics

Backend selection influences only the later phases.

Backend choice may affect:

* TIR strategy,
* runtime ABI,
* symbolic lowering support,
* engine pass behavior.

Backend choice MUST NOT affect:

* CST meaning,
* Surface AST meaning,
* NIR source normalization,
* Python host execution semantics,
* patch precedence rules.

In other words:

> backend choice may affect realization, but not the meaning of source-level language semantics.

---

## 19. Incrementality

An implementation may cache or incrementally recompute phases.

However, incremental execution must preserve phase contracts.

Examples:

* reparsing one file segment may invalidate CST and Surface AST locally,
* normalization cache may be reused only if source and schema assumptions are unchanged,
* host expansion cache may be reused only if host-visible dependencies are unchanged,
* backend stabilization data may be reused only if compatible with the emitted TIR and runtime assumptions.

Incrementality is an optimization, not a semantic shortcut.

---

## 20. Phase-Local Introspection

Implementations SHOULD expose phase-local inspection tools.

Recommended capabilities:

* dump CST
* dump Surface AST
* dump NIR
* dump EIR
* dump TIR
* inspect symbolic expressions
* inspect active scopes
* inspect effective state at a node
* inspect backend runtime requirements

A language with multiple strong phase boundaries benefits greatly from explicit visibility into each one.

---

## 21. Minimal End-to-End Example

Source:

```marktex id="yuljlr"
!# footer: center: "[$ PAGE.N ] / [$ PAGE.MAX ]"

!@ column: count: 2
Hello [world](color: blue, bold).
!!@ column
```

### CST

Recognizes:

* persistent directive line
* scoped directive open
* paragraph line
* scoped directive close

### Surface AST

Represents:

* directive `!#` with raw MOS payload
* directive `!@` with raw MOS payload
* paragraph with bracket-call
* directive `!!@`

### NIR

Produces:

* `PersistentPatch(PagePatch(...footer.center...))`
* `RegionBlock(ScopedPatch(FlowPatch(column.count = 2)), ...)`
* `StyledSpan(InlinePatch(color=blue, weight=bold), "world")`
* explicit scope structure

### EIR

Evaluates:

* embedded `PAGE.N` and `PAGE.MAX` remain symbolic
* no host statements here, so structure mostly preserved

### TIR

Lowers to:

* footer runtime slot with symbolic page placeholders
* begin/end region for two-column flow
* inline styled span runtime calls

### Engine phase

Resolves:

* actual page numbers
* total page count
* page layout and pagination

---

## 22. Phase Invariants

The following are normative.

### 22.1 CST invariant

All delimiter and source-span structure is explicit.

### 22.2 Surface AST invariant

All major source constructs are structurally identified.

### 22.3 NIR invariant

No unresolved source-level semantic ambiguity remains.

### 22.4 EIR invariant

No unresolved host-execution ambiguity remains.

### 22.5 TIR invariant

No unresolved backend-structural ambiguity remains.

### 22.6 Engine invariant

Only backend-runtime and pagination-dependent values remain to be resolved.

---

## 23. Forbidden Cross-Phase Leakage

The following are forbidden design patterns.

### 23.1 Parser-time host execution

The parser must not execute Python to decide syntax.

### 23.2 Backend-time source disambiguation

The backend must not guess whether a source form meant Markdown or MTX.

### 23.3 Host-time patch reinterpretation

The host must not bypass typed patch rules by textually forging semantics.

### 23.4 Engine-time semantic invention

The TeX runtime must not invent source semantics missing from earlier phases.

These prohibitions are essential to compiler integrity.

---

## 24. Recommended Compiler Architecture

A strong recommended architecture is:

* CST / Surface AST / NIR in a parser-centric frontend
* EIR in a host-expansion layer
* TIR in a backend-lowering layer
* engine orchestration in a build driver
* runtime support in dedicated backend runtime files

This architecture is not mandatory in implementation language, but it is strongly aligned with the phase model.

---

## 25. Final Principle

MarkTeX works only if every phase is both strong and modest:

* strong enough to fully decide what belongs to it,
* modest enough not to steal another phase’s job.

That is the phase law of the language.

Or in its shortest form:

> parse early, normalize fully, evaluate explicitly, lower late, resolve pages last.

That is the clean architecture of MarkTeX.
