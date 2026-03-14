# MarkTeX v0.1

## Value Resolution Specification

## 1. Scope

This document defines the value-resolution model of MarkTeX.

It specifies:

* value categories,
* phase-aware evaluability,
* symbolic and deferred values,
* partial evaluation,
* mixed concrete/symbolic expressions,
* backend-resolvable and engine-resolvable values,
* and the lowering contract from semantic values to backend placeholders.

This document is normative for the transition from **NIR** through **EIR** and into **TIR**.

It complements, and is intended to be consistent with:

* the Core IR specification,
* the Python Host specification,
* the State Semantics specification,
* the Backend Contract specification,
* and the Phase Model specification.

---

## 2. Design Law

Not all values belong to the same phase.

The central law is:

> Every MarkTeX value must have both a semantic type and a resolution class.

A value is therefore not characterized only by what it is, but also by **when it can become concrete**.

This is necessary because MarkTeX contains at least three distinct evaluability domains:

1. source/normalization-time structure,
2. compile-time host computation,
3. backend and engine-time realization.

Without an explicit value-resolution model, these domains collapse into ad hoc exceptions.

---

## 3. Core Distinction

MarkTeX distinguishes between:

* **value kind**,
* **resolution phase**,
* **preservation mode**,
* and **lowering class**.

These are separate concepts.

### Value kind

What semantic thing the value is.

### Resolution phase

The earliest phase at which the value may become concrete.

### Preservation mode

What should happen if the current phase cannot fully resolve it.

### Lowering class

How the unresolved value is carried into later phases.

---

## 4. Value Kinds

The core value kinds are:

1. concrete values
2. symbolic values
3. deferred values
4. expression values
5. interpolated values
6. object values
7. node values
8. backend handles

---

## 4.1 Concrete Value

A concrete value is fully known at the current phase.

Examples:

* integers,
* floats,
* booleans,
* strings,
* frozen compile-time timestamps,
* schema-bound objects whose fields are all concrete.

Concrete values may be reduced eagerly.

---

## 4.2 Symbolic Value

A symbolic value is semantically valid but not yet concretely known.

Examples:

* current page number,
* total page count,
* target page reference,
* running mark,
* backend-resolved counter.

A symbolic value is not an error.
It is a first-class value category.

---

## 4.3 Deferred Value

A deferred value is a value whose semantic existence is established, but whose final realization is postponed to a later phase or external mechanism.

Symbolic values are one major subclass of deferred values, but not the only one.

Examples:

* a value that must be lowered to a backend placeholder,
* a value awaiting multi-pass convergence,
* a composite value containing unresolved symbolic subparts.

---

## 4.4 Expression Value

An expression value is a structured value tree representing computation over concrete or symbolic operands.

Examples:

* `PAGE.MAX - PAGE.N`
* `TIME.year + 1`
* `counter("sec") + 2`

An expression value may later reduce to:

* a concrete value,
* another symbolic value,
* or a backend-lowerable expression form.

---

## 4.5 Interpolated Value

An interpolated value is a composite textual or node-bearing value containing multiple parts, some concrete and some deferred.

Examples:

* `"Page " + PAGE.N + " / " + PAGE.MAX`
* a footer slot containing text plus symbolic page placeholders
* a string-like object with embedded inline expressions

Interpolated values are distinct because textual composition often has different lowering rules from arithmetic expressions.

---

## 4.6 Object Value

An object value is a typed semantic object.

Examples:

* a layout specification,
* a margin object,
* a header slot object,
* a resource set,
* a style descriptor.

An object value may itself contain concrete, symbolic, or deferred fields.

Thus object concreteness is recursive, not assumed.

---

## 4.7 Node Value

A node value is a document node or node sequence.

Examples:

* an inline span,
* a paragraph,
* a styled span,
* a citation node sequence.

Node values may embed symbolic expressions in their content.

---

## 4.8 Backend Handle

A backend handle is a backend-oriented value that has passed beyond ordinary semantic symbolic form and now denotes a concrete backend placeholder class.

Examples:

* current-page placeholder,
* total-pages placeholder,
* page-reference placeholder,
* backend counter handle,
* runtime running-mark handle.

Backend handles arise at TIR or later, not as primary source-level values.

---

## 5. Resolution Phases

Every value must declare or imply an **earliest resolution phase**.

The core resolution phases are:

1. `NormalizePhase`
2. `ExpandPhase`
3. `LowerPhase`
4. `EnginePhase`
5. `StabilizationPhase`

These are conceptual phase classes, not necessarily separate implementation processes.

---

## 5.1 NormalizePhase

A value resolvable at `NormalizePhase` can become semantically concrete during normalization.

Typical examples:

* MOS tags interpreted by schema,
* explicit literal objects,
* field-key resolution,
* purely structural state objects.

This phase rarely concerns user-visible arithmetic or dynamic values.

---

## 5.2 ExpandPhase

A value resolvable at `ExpandPhase` can be concretized during Python-host evaluation.

Typical examples:

* ordinary Python-computed numbers,
* frozen `TIME`,
* compile-time list manipulations,
* resource objects assembled from known values.

Most compile-time values belong here.

---

## 5.3 LowerPhase

A value resolvable at `LowerPhase` cannot be fully concretized during EIR construction, but can be translated into a backend-specific form without waiting for engine execution.

Typical examples:

* symbolic values that map directly to backend primitives,
* backend-known placeholder classes,
* some counter expressions or layout handles,
* some string-template objects that can already become TIR fragments.

These values are unresolved semantically in EIR but resolvable operationally during lowering.

---

## 5.4 EnginePhase

A value resolvable at `EnginePhase` becomes concrete only during actual backend execution.

Typical examples:

* current page number,
* running mark for the currently built page,
* current page parity.

Such values may be represented symbolically in EIR and as backend handles in TIR.

---

## 5.5 StabilizationPhase

A value resolvable at `StabilizationPhase` requires one or more backend passes and auxiliary feedback before its final value is known.

Typical examples:

* total page count,
* page of a target reference,
* table-of-contents target pages,
* some bibliography numbering systems if backend-managed.

These are the most deferred ordinary values in the language.

---

## 6. Resolution Classes

Every intrinsic, expression, or constructed semantic value SHOULD expose a resolution profile with at least the following properties:

1. semantic type,
2. earliest resolution phase,
3. partial-evaluation permission,
4. symbolic-preservation permission,
5. lowering class,
6. multi-pass requirement.

A conceptual form is:

```text id="j1eio9"
ResolutionProfile {
  value_kind: ValueKind,
  earliest_phase: ResolutionPhase,
  allow_partial_eval: Bool,
  allow_symbolic_preservation: Bool,
  lowering_class: LoweringClass,
  requires_stabilization: Bool
}
```

This object need not exist as a user-visible runtime object, but the compiler must behave as if such information were available.

---

## 7. Preservation Modes

If a value cannot yet become concrete at the current phase, the compiler must follow an explicit preservation mode.

The core preservation modes are:

1. reduce eagerly
2. preserve symbolically
3. preserve as interpolation
4. lower to backend handle
5. reject as non-representable

---

## 7.1 Reduce Eagerly

If all required inputs are concrete and reduction is valid, the compiler SHOULD reduce eagerly.

Example:

```python id="ptck8g"
TIME.year + 1
```

assuming `TIME.year` is concrete.

---

## 7.2 Preserve Symbolically

If the value contains symbolic parts and the operation is representable, it MUST be preserved as a symbolic expression or symbolic object.

Example:

```python id="whpn6f"
PAGE.MAX - PAGE.N
```

This should not be forced to string form or treated as an error merely because it is not concrete.

---

## 7.3 Preserve as Interpolation

If the value is text-like or node-like composition over concrete and symbolic parts, it SHOULD be preserved as an interpolated structure.

Example:

```python id="0mtoyt"
"Page " + PAGE.N + " / " + PAGE.MAX
```

or its node-aware equivalent.

---

## 7.4 Lower to Backend Handle

If a value has reached TIR and can no longer usefully remain in a semantic symbolic form, it SHOULD be converted to a backend handle.

Example:

* `sym(PAGE.N)` in EIR
* becomes `CurrentPageHandle` in TIR

This is not concretization; it is backend specialization.

---

## 7.5 Reject as Non-Representable

If an expression mixes values in a way that is neither reducible nor symbolically representable, compilation fails.

Example:

* an unsupported symbolic operation,
* a symbolic value used where only immediate concrete scalar semantics are valid,
* an object field declared `symbolic-forbidden` receiving a symbolic subtree.

---

## 8. Partial Evaluation

MarkTeX supports **partial evaluation**.

This is one of the language’s core semantic mechanisms.

The law is:

> evaluate as much as is valid at the current phase, and preserve the remainder in typed form.

Partial evaluation is most important during the transition from NIR to EIR.

---

## 8.1 Partial Evaluation Rules

Given an expression:

* if all operands are concrete, reduce to a concrete value,
* if some operands are concrete and some symbolic, partially reduce concrete subtrees,
* if all operands are symbolic but the operator is supported, preserve as symbolic expression,
* if representation is impossible, raise a compile-time error.

This rule is normative.

---

## 8.2 Example

Expression:

```python id="wry1z5"
(PAGE.MAX - PAGE.N) + 1
```

Partial evaluation result:

* `1` remains concrete,
* `PAGE.MAX - PAGE.N` remains symbolic,
* final result is a symbolic expression tree with a concrete subtree folded.

---

## 8.3 Canonicalization After Partial Evaluation

After partial evaluation, the compiler SHOULD canonicalize expression structure.

Examples:

* flatten associative concatenation where safe,
* fold adjacent concrete text fragments,
* remove neutral arithmetic elements where safe,
* normalize symbolic operator trees into a backend-lowerable shape.

Canonicalization improves lowering consistency and diagnostics.

---

## 9. Expression Stratification

Expression forms should be stratified by phase.

The recommended model is to distinguish at least:

1. **semantic expressions** in NIR/EIR
2. **backend expressions** in TIR

---

## 9.1 Semantic Expressions

These are phase-neutral or backend-independent forms.

Examples:

* `Add`
* `Sub`
* `Mul`
* `Concat`
* `Attr`
* `Call`
* `Index`
* `SymbolRef`
* `TemplateJoin`

These are the preferred forms during normalization and expansion.

---

## 9.2 Backend Expressions

These are backend-aware forms.

Examples:

* `CurrentPage`
* `TotalPages`
* `PageRef(label)`
* `RunningMark(kind)`
* `BackendCounter(name)`
* `TeXConcat`
* `TeXNumericExpr`

These arise during lowering.

This separation prevents backend concerns from contaminating the semantic value layer.

---

## 10. Phase-Bound Intrinsics

Intrinsic objects SHOULD be modeled as **phase-bound intrinsics**.

A phase-bound intrinsic is an intrinsic object whose value-resolution behavior is explicitly tied to one or more phases.

Examples:

* `TIME`
* `PAGE`
* `BIB`
* `HEADER`
* `FOOTER`

Each intrinsic object kind must define its resolution behavior.

---

## 10.1 `TIME`

Recommended profile:

* value kind: object value with concrete scalar subfields
* earliest resolution phase: `ExpandPhase`
* symbolic preservation: normally no
* lowering class: none once reduced
* stabilization: no

`TIME` is best modeled as a compile-start-frozen value.

---

## 10.2 `PAGE.N`

Recommended profile:

* value kind: symbolic value
* earliest resolution phase: `EnginePhase`
* partial evaluation: yes, in larger expressions
* symbolic preservation: yes
* lowering class: current-page placeholder
* stabilization: no

---

## 10.3 `PAGE.MAX`

Recommended profile:

* value kind: symbolic value
* earliest resolution phase: `StabilizationPhase`
* partial evaluation: yes
* symbolic preservation: yes
* lowering class: total-pages placeholder
* stabilization: yes

---

## 10.4 `BIB`

Recommended profile:

* value kind: object/resource value
* earliest resolution phase: mostly `ExpandPhase`
* symbolic preservation: sometimes, depending on bibliography strategy
* lowering class: resource-lowering strategy
* stabilization: backend-dependent for numbering and formatting

This illustrates that some intrinsics are mixed-phase objects, not pure compile-time scalars.

---

## 11. Object Concreteness

Object values may contain heterogeneous fields.

Therefore, object concreteness is field-recursive.

An object is:

* **fully concrete** if all relevant fields are concrete,
* **partially deferred** if some fields are symbolic or deferred,
* **backend-specialized** if some fields are already backend handles.

Example:

A footer object containing:

* left: concrete text
* center: symbolic page fraction
* right: concrete text

is not fully concrete, but it is semantically valid.

---

## 12. Symbolic Permission by Field

Not every field may accept symbolic values.

Each schema field SHOULD declare one of:

* `symbolic-allowed`
* `symbolic-allowed-with-lowering`
* `symbolic-forbidden`

Examples:

* header/footer slots: usually symbolic-allowed-with-lowering
* color field: usually symbolic-forbidden unless explicitly designed otherwise
* font size: usually symbolic-forbidden
* page counter display field: symbolic-allowed-with-lowering
* bibliography resource set: symbolic-allowed only if the backend/resource model permits it

If a symbolic value enters a symbolic-forbidden field, compilation fails at the earliest correct phase.

---

## 13. Interpolated Values

Text-bearing or node-bearing compositions often require a dedicated interpolation model.

A generic string model is not sufficient because symbolic components may not admit naive stringification.

Recommended interpolation parts include:

* concrete text segments,
* symbolic segments,
* inline node segments,
* formatting-preserving glue segments where needed.

A conceptual form is:

```text id="zkj2el"
InterpolatedValue {
  parts: [InterpPart]
}
```

where `InterpPart` may be:

* `TextPart`
* `SymbolPart`
* `NodePart`
* `ExprPart`

---

## 13.1 Why Interpolation Must Be Explicit

Naive Python stringification is not sufficient because:

* symbolic values may not have a meaningful concrete string yet,
* backend lowering may need segment boundaries,
* inline formatting must remain structured,
* diagnostics should know which segment came from where.

Therefore, symbolic text composition SHOULD become explicit interpolation structure rather than accidental Python strings.

---

## 14. Backend Lowering Classes

A deferred or symbolic value must carry or imply a backend lowering class.

The core lowering classes are:

1. no-lowering-needed
2. backend-expression
3. runtime-placeholder
4. aux-dependent-placeholder
5. raw-backend-escape
6. non-lowerable

---

## 14.1 No-Lowering-Needed

Used for values fully concrete before TIR.

Examples:

* plain strings,
* numbers,
* fully reduced compile-time objects.

---

## 14.2 Backend Expression

Used when a symbolic or mixed expression can be lowered to a backend expression form.

Example:

* a page-dependent numeric expression that becomes a TeX numeric expression tree.

---

## 14.3 Runtime Placeholder

Used when the backend runtime can directly resolve the value during one engine run.

Examples:

* current page number,
* current page parity,
* current running mark.

---

## 14.4 Aux-Dependent Placeholder

Used when backend passes and aux data are required.

Examples:

* total page count,
* page of a labeled reference,
* some cross-reference targets.

---

## 14.5 Raw-Backend-Escape

Used only for explicit escape-hatch values.

This is not the ordinary lowering path.

---

## 14.6 Non-Lowerable

If no valid lowering class exists for a deferred value in its context, compilation fails at TIR construction or earlier.

---

## 15. Resolution Engine

Implementations SHOULD provide a distinct resolution engine, even if not as a separately exposed module.

Its responsibilities include:

* evaluability analysis,
* partial evaluation,
* symbolic canonicalization,
* interpolation construction,
* lowering-class selection,
* backend-resolution analysis.

The recommended abstract operations are:

* `analyze_resolvability(value, phase)`
* `partially_evaluate(expr, phase)`
* `canonicalize_value(value, phase)`
* `select_lowering_class(value, backend_profile)`
* `lower_symbolic(value, backend_profile)`

This engine is conceptually distinct from both parsing and backend emission.

---

## 16. Earliest-Correct Resolution Rule

A value SHOULD become concrete at the earliest phase where:

1. all required information is available,
2. the operation is semantically valid,
3. and no later-phase information is needed.

But a value MUST NOT be forced earlier than this.

Thus:

* `TIME.year` should resolve during expansion,
* `PAGE.N` should not,
* `PAGE.MAX` must not be forced before stabilization.

This rule prevents both over-deferral and premature collapse.

---

## 17. Mixed Expressions

Mixed expressions combine concrete and deferred parts.

These are fully legitimate in MarkTeX.

Examples:

* `42 + PAGE.N`
* `"Page " + PAGE.N`
* `PAGE.MAX - PAGE.N + 1`
* a header slot containing text, symbolic values, and inline nodes

Mixed expressions should remain well-typed and canonicalized.

They are not second-class edge cases.

---

## 17.1 Numeric Mixed Expressions

Numeric mixed expressions SHOULD preserve arithmetic structure.

Example:

```python id="0e7e5f"
PAGE.MAX - PAGE.N + 1
```

should remain a numeric symbolic expression, not be collapsed into text unless explicitly requested in a text-bearing context.

---

## 17.2 Textual Mixed Expressions

Textual mixed expressions SHOULD preserve interpolation structure.

Example:

```python id="jszc7o"
"Page " + PAGE.N + " / " + PAGE.MAX
```

should become an interpolated value or inline node sequence, not a prematurely formatted opaque string.

---

## 18. Host Object vs IR Object

Python host objects are not the semantic source of truth.

They may serve as:

* builders,
* proxies,
* operator-overloaded constructors,
* symbolic wrappers.

But before or during EIR construction, they MUST be canonicalized into IR-level value forms.

This is a critical rule.

Without it:

* caching becomes fragile,
* diagnostics become opaque,
* lowering logic becomes tangled with Python object behavior,
* and the language semantics drift into host implementation details.

The law is:

> Python may construct values, but IR owns them.

---

## 19. Value Canonicalization

Canonicalization SHOULD occur after major value transformations.

Typical canonicalization steps include:

* folding adjacent concrete text parts,
* collapsing nested interpolation where safe,
* normalizing symbolic arithmetic trees,
* removing neutral elements,
* flattening associative concatenation,
* converting host-side proxies into canonical IR nodes.

Canonicalization is especially important at:

* post-expansion EIR construction,
* pre-lowering TIR construction.

---

## 20. Errors in Value Resolution

The main value-resolution error classes are:

1. premature concreteness requirement
2. unsupported symbolic operation
3. illegal symbolic field insertion
4. non-lowerable deferred value
5. invalid mixed-type composition
6. invalid host proxy escaping canonicalization

---

## 20.1 Premature Concreteness Requirement

Example:

A field requires an immediate integer, but receives `PAGE.N`.

If the field is symbolic-forbidden, this is an error at the earliest correct phase.

---

## 20.2 Unsupported Symbolic Operation

Example:

An operator is applied to symbolic values but no symbolic representation exists for that operation.

This is a compile-time error during expansion or earlier analysis.

---

## 20.3 Illegal Symbolic Field Insertion

Example:

A font size field receives `PAGE.MAX`.

If font size is symbolic-forbidden, the compiler must reject it.

---

## 20.4 Non-Lowerable Deferred Value

Example:

A value survives to TIR but has no backend lowering class for the selected backend.

This is a backend-lowering error.

---

## 20.5 Invalid Mixed-Type Composition

Example:

A block node is combined into a numeric symbolic expression without a valid coercion rule.

This is a type error.

---

## 21. Minimal Examples

## 21.1 Pure compile-time value

```marktex id="a5dsej"
[$ TIME.year + 1 ]
```

Semantics:

* `TIME.year` is concrete in `ExpandPhase`,
* expression reduces eagerly,
* result is a concrete scalar.

---

## 21.2 Engine-time symbolic value

```marktex id="9m5i0a"
[$ PAGE.N ]
```

Semantics:

* symbolic in EIR,
* lowered to current-page runtime placeholder in TIR,
* resolved during engine execution.

---

## 21.3 Stabilization-time symbolic value

```marktex id="pt71p8"
[$ PAGE.MAX ]
```

Semantics:

* symbolic in EIR,
* lowered to total-pages placeholder in TIR,
* resolved only after backend stabilization.

---

## 21.4 Mixed numeric expression

```marktex id="yf85x2"
[$ PAGE.MAX - PAGE.N + 1 ]
```

Semantics:

* partial evaluation folds concrete `+ 1`,
* symbolic arithmetic tree preserved,
* backend lowering chooses numeric placeholder expression strategy.

---

## 21.5 Mixed textual expression

```marktex id="hpu1se"
!# footer: center: "Page [$ PAGE.N ] / [$ PAGE.MAX ]"
```

Semantics:

* footer slot receives an interpolated value,
* symbolic parts are preserved,
* TIR lowers them to page runtime placeholders.

---

## 21.6 Resource object with compile-time resolution

```marktex id="m76p6r"
!$ extra = BIB + "appendix.bib"
!# bib: [$ extra ]
```

Semantics:

* `BIB + "appendix.bib"` resolves as a typed resource object in `ExpandPhase`,
* no engine-time symbolic behavior is required for the resource-set object itself,
* later bibliography formatting may still involve backend-dependent behavior.

---

## 22. Invariants

The following are normative.

1. Every value has a semantic kind and a resolution class.
2. Concrete values should resolve at the earliest correct phase.
3. Symbolic and deferred values are first-class, not exceptional.
4. Partial evaluation is required where valid.
5. Mixed concrete/symbolic expressions are valid if representable.
6. Backend handles arise only after backend specialization.
7. Python host proxies must be canonicalized into IR values.
8. Symbolic permission is field-specific, not global.
9. Deferred values must declare or imply a lowering class.
10. Values that cannot be reduced, preserved, or lowered must fail explicitly.

---

## 23. Recommended Implementation Modules

A strong recommended implementation split is:

### `mtx_value`

Defines:

* concrete values,
* symbolic values,
* deferred values,
* interpolated values,
* object and node value wrappers.

### `mtx_expr`

Defines:

* semantic expression trees,
* expression normalization,
* symbolic composition,
* canonicalization.

### `mtx_resolve`

Defines:

* evaluability analysis,
* partial evaluation,
* phase transition rules,
* lowering-class selection.

### `mtx_backend_symbol`

Defines:

* backend symbolic classes,
* page/current/total/reference handles,
* aux-dependent placeholder families.

### `mtx_lower`

Defines:

* EIR value lowering to TIR,
* backend handle construction,
* runtime placeholder emission classes.

This structure is strongly recommended because value resolution is neither merely “host logic” nor merely “backend logic.”

---

## 24. Final Principle

MarkTeX does not have a single notion of “value.”
It has values that live across phases.

Therefore the language must treat value resolution as a dedicated semantic system.

The shortest correct summary is:

> some values compute, some values defer, some values lower, and some values stabilize.

That is the value law of MarkTeX.
