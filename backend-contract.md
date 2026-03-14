# MarkTeX v0.1

## Backend Contract Specification

## 1. Scope

This document defines the backend contract of MarkTeX.

It specifies:

* the role of **TIR**,
* the lowering boundary from semantic IR to backend IR,
* the runtime contract between generated TeX and the MarkTeX backend runtime,
* symbolic value lowering,
* page-resolution and multi-pass behavior,
* backend capability classes,
* and the canonical LuaLaTeX-first backend model.

This document is normative for the transition:

```text
EIR -> TIR -> .tex -> TeX engine -> PDF
```

---

## 2. Design Position

MarkTeX is not a TeX macro package with a friendlier syntax.
It is a language whose semantic core is resolved before backend emission.

Therefore:

* TeX is a **backend**, not the language core.
* TIR is a **backend-oriented semantic form**, not raw source replay.
* generated `.tex` is an **artifact**, not the primary semantic representation.

The central law is:

> Backend lowering must preserve MarkTeX semantics without reintroducing source-level ambiguity.

---

## 3. Backend Layering

The backend is divided into four layers:

1. **EIR** — expanded semantic IR
2. **TIR** — TeX-oriented backend IR
3. **TeX source** — emitted `.tex`
4. **TeX runtime** — the runtime support layer used by emitted code

The preferred architecture is:

```text
EIR
-> TIR
-> emitted .tex
-> marktex runtime (.sty / .lua / support files)
-> TeX engine
-> PDF
```

---

## 4. Canonical Backend

The canonical backend of MarkTeX is **LuaLaTeX**.

This is the reference backend for language semantics.

### 4.1 Rationale

LuaLaTeX is the canonical backend because MarkTeX needs:

* strong Unicode behavior,
* robust CJK support,
* runtime programmability,
* better structured interaction with engine state,
* and a realistic path for symbolic page/runtime features.

### 4.2 Secondary Backends

Other TeX engines may be supported, but they are not semantic authorities.

Typical classes:

* **Reference backend**: LuaLaTeX
* **Compatible backend**: XeLaTeX, if supported
* **Subset backend**: pdfLaTeX, only where the semantics remain meaningful

A non-canonical backend may reject features or lower them differently, but it MUST NOT silently misrepresent the semantics.

---

## 5. TIR

TIR is the backend-oriented IR of MarkTeX.

TIR is not source syntax and not a textual macro stream.
It is the final structured representation before `.tex` emission.

TIR MUST:

* preserve semantic decisions already made in EIR,
* preserve symbolic values that require backend/runtime resolution,
* classify content into backend-relevant strata,
* and avoid depending on raw textual TeX generation as the only abstraction layer.

---

## 5.1 TIR Categories

The backend MUST recognize at least the following categories in TIR:

1. document structure
2. flow regions
3. inline runs
4. page furniture
5. symbolic placeholders
6. resource and reference backend nodes
7. raw backend escape nodes

---

## 5.2 TIR Root

A schematic TIR root may be viewed as:

```text
TeXDocument {
  preamble: [TeXDecl],
  body: [TeXFlowNode],
  runtime_requirements: RuntimeSpec,
  aux_requirements: AuxSpec,
  origin: Origin
}
```

This structure is illustrative rather than prescriptive, but the backend contract requires equivalent information.

---

## 6. Lowering Boundary

Lowering from EIR to TIR is a semantic compilation step.

It MUST NOT be treated as “stringify everything into TeX.”

The lowering step is responsible for:

* mapping semantic nodes to backend-supportable forms,
* choosing runtime APIs,
* translating symbolic values into runtime placeholders,
* preparing page-furniture and flow declarations,
* and separating support declarations from document flow.

---

## 6.1 What Lowering Must Not Do

Lowering MUST NOT:

* reinterpret unresolved source syntax,
* guess semantics from raw text,
* bypass typed objects by textual reconstruction,
* silently drop unsupported semantics,
* or force all symbolic constructs into premature concrete strings.

---

## 7. Runtime Contract

Generated TeX SHOULD target a stable MarkTeX runtime layer.

This runtime layer is the backend ABI of MarkTeX.

The recommended runtime components are:

* `marktex.sty`
* `marktex.lua`
* auxiliary support files as needed

The emitted `.tex` SHOULD call runtime primitives rather than inline all backend logic ad hoc.

---

## 7.1 Runtime ABI Principle

The runtime ABI must satisfy:

1. generated code is simpler and more regular,
2. backend logic is centralized,
3. engine-specific details are isolated,
4. semantic diagnostics remain attributable,
5. the compiler and the runtime may evolve in a controlled way.

The central law is:

> emit runtime calls, not backend folklore.

---

## 7.2 Runtime Primitive Classes

The runtime SHOULD define primitives in at least the following classes:

### Document and preamble primitives

* document initialization
* package/runtime loading
* backend profile negotiation
* global metadata setup

### Page-state primitives

* paper layout setup
* margin setup
* page style selection
* header/footer slot installation
* running mark installation

### Flow primitives

* begin/end region
* column configuration
* spacing and alignment configuration
* block-flow markers

### Inline primitives

* begin/end styled span
* script/font routing
* color and weight changes
* inline symbolic insertion

### Symbolic primitives

* current page number insertion
* total page count insertion
* reference-page insertion
* running mark resolution

### Resource primitives

* bibliography registration
* label registration
* counter manipulation
* cross-reference hooks

---

## 8. Raw TeX Escape

MarkTeX may permit explicit raw backend escape nodes such as `RawTeXBlock` or `RawTeXInline`.

These are explicit escape hatches.

They are not the default lowering path.

### Rule

A raw backend node enters TIR only if it was explicitly present in EIR or explicitly constructed through an allowed host API.

The backend MUST NOT synthesize raw TeX escapes merely because a semantic feature was inconvenient to lower properly.

---

## 9. Symbolic Lowering

Some values remain symbolic after EIR.

These include values such as:

* `PAGE.N`
* `PAGE.MAX`
* page parity
* target page references
* running marks
* counters whose final value is backend-resolved

Such values MUST be lowered to symbolic backend placeholders, not flattened prematurely.

---

## 9.1 Symbolic Value Classes

The backend contract distinguishes at least:

1. **engine-local symbolic values**
   Values resolved by the TeX engine during execution.

2. **multi-pass symbolic values**
   Values requiring auxiliary file feedback or repeated compilation.

3. **compiler-side symbolic values**
   Values theoretically symbolic in EIR but fully lowerable to fixed backend expressions before TeX execution.

---

## 9.2 Example: Page Number

`PAGE.N` typically lowers to a runtime insertion primitive that resolves to the current page number at backend execution time.

`PAGE.MAX` typically lowers to a multi-pass page-count mechanism.

This distinction is normative in kind even if implementation details vary.

---

## 10. Multi-Pass Semantics

MarkTeX compilation is permitted and expected to be multi-pass.

This is not an implementation accident.
It is a consequence of page-dependent semantics.

A conforming backend MUST define a pass strategy for all multi-pass symbolic values it supports.

---

## 10.1 Pass Classes

The backend may involve:

1. **compile-time passes**

   * NIR
   * EIR
   * TIR
   * `.tex` generation

2. **engine passes**

   * one or more TeX engine runs

3. **aux reconciliation**

   * reading and writing backend-generated auxiliary data

---

## 10.2 Stabilization Principle

A MarkTeX build is considered backend-stable when all required backend-resolved symbolic values have converged under the backend’s stabilization rule.

Typical examples include:

* total page count,
* reference page numbers,
* table of contents page anchors,
* running marks.

Implementations SHOULD expose whether the document has stabilized.

---

## 10.3 Recommended Driver Behavior

The recommended build driver behavior is:

1. emit `.tex`,
2. run the backend engine,
3. inspect auxiliary outputs and runtime convergence markers,
4. rerun as needed,
5. stop when stable or when a configured pass limit is reached.

The exact pass limit is implementation-defined.

---

## 11. Page Furniture

Headers, footers, running marks, and related page furniture belong to **PageState** in EIR and to dedicated page-runtime structures in TIR.

They are not ordinary inline text.

The backend MUST lower them as page-furniture constructs, not as random text inserted into flow.

---

## 11.1 Header/Footer Slots

A header or footer field is slot-based.

Typical slots include:

* left
* center
* right

A slot may contain:

* plain text,
* inline content,
* symbolic expressions,
* backend-resolved runtime placeholders

The runtime contract MUST specify how such slot content is represented.

---

## 11.2 Running Marks

Running marks are page-dependent semantic values.

They may depend on:

* current heading,
* enclosing section,
* explicit user declarations,
* backend page-break outcomes.

The runtime contract MUST support running mark installation and retrieval in a structured way.

---

## 12. Flow Regions

Scoped flow constructs such as columns or local region layout lower to explicit region begin/end forms in TIR.

Example conceptual lowering:

```text
BeginRegion(flow_patch = ...)
...
EndRegion
```

The emitted `.tex` SHOULD preserve this region structure through runtime calls or environment-like wrappers.

The backend MUST ensure that region entry and exit semantics match scoped patch semantics.

---

## 12.1 Region Isolation

A flow region must not leak its scoped layout semantics outside its lexical TIR boundary.

In particular:

* column settings,
* alignment settings,
* region-local spacing semantics

must unwind at region exit.

This is backend-observable and therefore normative.

---

## 13. Inline Lowering

Inline lowering transforms EIR inline runs into backend-recognizable run sequences.

The backend SHOULD lower inline semantics in run order, minimizing unnecessary backend state churn.

Inline lowering responsibilities include:

* text emission,
* style span entry/exit,
* script/font routing,
* symbolic inline insertion,
* link and citation lowering,
* inline raw backend escapes.

---

## 13.1 Run Segmentation

The backend SHOULD segment inline content by effective `TextState`.

Two adjacent inline nodes with equivalent effective inline state MAY be coalesced if doing so preserves origin and diagnostics meaning.

Segmentation is an optimization, not a semantic change.

---

## 13.2 Script/Font Routing

If MarkTeX supports distinct western/eastern routing, the backend must define how this is realized.

The recommended canonical behavior under LuaLaTeX is:

* routing is handled by runtime-aware font selection behavior,
* or by compiler-prepared text run segmentation plus runtime font switches,
* or a hybrid of both.

What matters normatively is:

> script-aware font semantics must be preserved, not merely approximated.

---

## 14. Resource Lowering

ResourceState lowers through dedicated backend strategies.

Typical classes include:

* bibliography resources
* labels
* counters
* cross-references
* assets

Resource lowering MUST remain typed until the backend strategy is selected.

---

## 14.1 Bibliography

Bibliography lowering may target a TeX/BibTeX/Biber-compatible workflow or another backend-supported bibliography path.

The exact bibliography mechanism is not fixed here, but the backend contract requires:

* typed bibliography resources in EIR,
* a deterministic lowering strategy in TIR,
* and support for citation references that survive until backend resolution where necessary.

---

## 14.2 Labels and Cross-References

Labels and cross-references may require auxiliary-file participation.

The backend MUST define:

* label declaration lowering,
* label resolution lowering,
* unresolved-reference diagnostics behavior,
* and pass-stabilization behavior.

---

## 15. Origin Preservation

TIR MUST preserve sufficient origin information to map backend diagnostics back to source or expanded origin.

A TIR node SHOULD carry:

* direct source origin,
* expansion chain,
* backend-emission origin if transformed structurally,
* symbolic provenance if the node arose from symbolic lowering.

This is necessary for:

* backend error mapping,
* explainable lowering,
* debugging generated TeX,
* and tooling.

---

## 16. Backend Capability Model

Backends differ in what they can support natively.

Therefore, the backend contract SHOULD classify semantic features by capability:

1. **native**
2. **runtime-supported**
3. **multi-pass-supported**
4. **degraded**
5. **unsupported**

A backend MUST declare which class applies to each major feature family.

### Example

For a non-canonical backend:

* Unicode CJK routing: degraded or unsupported
* page count: multi-pass-supported
* running marks: runtime-supported
* symbolic footer expressions: runtime-supported

A backend MUST NOT claim support for a feature family unless the resulting semantics are faithful enough to the declared capability class.

---

## 17. Unsupported Feature Semantics

If a backend cannot support a semantic feature faithfully, it MUST do one of the following:

1. reject compilation,
2. lower with an explicit degraded-mode diagnostic,
3. require the canonical backend.

It MUST NOT silently erase the feature.

---

## 18. Preamble Contract

The generated `.tex` preamble is part of the backend ABI.

It SHOULD contain:

* runtime loading,
* backend profile setup,
* font and language initialization,
* page-style initialization,
* resource declarations that belong in preamble space,
* compiler-emitted support definitions only where required.

The preamble SHOULD be structured and reproducible.

The backend MUST NOT leak arbitrary implementation noise into the preamble unless necessary.

---

## 19. Auxiliary Files

The backend may use auxiliary files to support:

* page count,
* cross-references,
* bibliography,
* convergence checks,
* runtime state snapshots if needed.

The backend contract MUST define which aux channels are semantic and which are incidental.

The build driver SHOULD treat semantic aux channels as part of compilation state.

---

## 20. Generated `.tex` as Artifact

The emitted `.tex` is a backend artifact, not the language’s semantic source of truth.

Therefore:

* editing generated `.tex` does not define MarkTeX semantics,
* diagnostics SHOULD point back to `.mtx` or expansion origins,
* and `.tex` stability is desirable but secondary to semantic correctness.

That said, the emitted `.tex` SHOULD remain reasonably inspectable.

Readable artifacts improve trust and debuggability.

---

## 21. Minimal Lowering Sketch

Consider this EIR-like semantics:

```text
PersistentPatch(PagePatch(
  footer.center = inline.seq(sym(PAGE.N), text(" / "), sym(PAGE.MAX))
))

RegionBlock(
  patch = ScopedPatch(FlowPatch(column.count = 2)),
  body = [...]
)
```

A conceptual TIR sketch may resemble:

```text
TeXDocument(
  preamble = [
    RuntimeLoad("marktex"),
    PageFooterSet(center = SymbolicPageFraction)
  ],
  body = [
    BeginRegion(ColumnSpec(count = 2)),
    ...lowered body...
    EndRegion()
  ]
)
```

The emitted `.tex` then calls runtime primitives corresponding to:

* footer setup,
* symbolic page-number insertion,
* region begin/end.

The exact textual form is implementation-defined.
The structural contract is not.

---

## 22. Driver Contract

The MarkTeX build driver is part of backend orchestration.

It SHOULD be responsible for:

* backend profile selection,
* `.tex` emission,
* engine invocation,
* auxiliary reconciliation,
* repeated engine runs,
* convergence detection,
* backend diagnostic collection.

The driver SHOULD expose:

* which backend is active,
* whether the build stabilized,
* which symbolic features required extra passes,
* and where backend diagnostics map to source.

---

## 23. Backend Invariants

The following are normative.

1. EIR is the semantic input to backend lowering.
2. TIR is backend-oriented and unambiguous.
3. Symbolic values may survive into TIR.
4. The canonical backend is LuaLaTeX.
5. Generated `.tex` SHOULD target a stable runtime ABI.
6. Backend lowering must preserve scoped region semantics.
7. Page furniture must be lowered as page furniture, not ad hoc inline text.
8. Multi-pass behavior is part of the semantic backend model, not an accident.
9. Unsupported features must not be silently erased.
10. Origin information must remain traceable through backend lowering.

---

## 24. Recommended Runtime Structure

A strong recommended structure is:

### `marktex.sty`

Provides:

* TeX-visible frontend runtime API,
* structural commands,
* package-level coordination,
* default macro wrappers.

### `marktex.lua`

Provides:

* Lua-side runtime logic,
* symbolic helpers,
* improved Unicode/script handling,
* backend-side structured behaviors that are impractical in plain TeX macros alone.

### Compiler-generated support section

Provides only document-specific glue, not the whole runtime.

This separation is strongly recommended.

---

## 25. Final Principle

The backend contract exists to ensure that MarkTeX remains a language with a backend, rather than a surface syntax that dissolves into macro accidents.

The design law is:

> semantics are decided before backend emission; the backend realizes them, but does not invent them.

That is what makes the TeX backend powerful without letting it become the hidden language core.
