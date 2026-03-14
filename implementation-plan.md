# MarkTeX v0.1

## Preliminary Implementation Plan

## 1. Scope

This document proposes an initial implementation architecture for MarkTeX.

It is guided by four goals:

* modularity,
* extensibility,
* implementation tractability,
* and semantic clarity.

The intended architectural style is closer to a layered compiler toolkit than to a monolithic macro processor.

---

## 2. Design Goals

The implementation should satisfy the following laws.

### 2.1 Frontend/IR/Backend Separation

The system should be split so that:

* parsing does not decide backend behavior,
* host execution does not own final semantic form,
* backend lowering does not reinterpret source syntax.

This is the MarkTeX analogue of a frontend/IR/backend architecture.

### 2.2 Schema-Driven Extensibility

New keywords, tags, object families, and scope roots should be added primarily by schema registration rather than parser rewrites.

The parser should understand:

* surface forms,
* delimiters,
* lists,
* tags,
* keyed modifiers,
* and grouped modifiers.

It should not need custom branches for each new language feature.

### 2.3 Live Host, IR-Owned Semantics

Python host execution may operate on real live intrinsic objects.

However:

* every semantically visible mutation must be recorded,
* every recorded mutation must canonicalize into typed semantic state effects,
* and IR remains the semantic source of truth for later phases.

### 2.4 Backend Independence of the Core

The semantic core should remain backend-neutral until TIR.

The TeX backend is the canonical first backend, but the architecture should not hard-code TeX decisions into NIR or EIR.

---

## 3. Recommended Module Split

The recommended module split for an initial implementation is:

### `mtx_surface`

Responsibilities:

* tokenization,
* delimiter matching,
* directive-line recognition,
* Markdown-core block parsing,
* inline shell capture,
* fenced block classification,
* math shell capture,
* generic bracket-call and image-call capture.

Primary outputs:

* CST,
* Surface AST.

### `mtx_collect`

Responsibilities:

* document-wide weak-order declaration collection,
* footnote-definition indexing,
* future label/ref pre-collection,
* bibliography-source indexing,
* and other global indices that should not depend on lexical declaration order.

This pass should run after surface capture but before semantic validation that depends on globally visible declarations.

### `mtx_schema`

Responsibilities:

* root registration,
* field registration,
* tag registration,
* binding-mode rules,
* allowed-lifetime rules,
* merge law declarations,
* ownership and host-writability declarations,
* object constructor lookup.

This is the main extensibility module.

### `mtx_ir`

Responsibilities:

* NIR/EIR/TIR data types,
* origin tracking types,
* node/value/patch/state-effect definitions,
* canonical serialization helpers for testing.

This module should remain deliberately stable.

### `mtx_state`

Responsibilities:

* state partitions,
* patch application,
* effective-state construction,
* live compiler-owned intrinsic objects,
* mutation log / state-effect log,
* snapshots and tooling views.

This is the runtime state engine for normalization and expansion.

### `mtx_host`

Responsibilities:

* Python execution environment,
* intrinsic object exposure,
* constructor exposure,
* host context object,
* host error capture,
* mutation interception and validation.

This module bridges Python to `mtx_state`, `mtx_ir`, and `mtx_schema`.

### `mtx_resolve`

Responsibilities:

* symbolic value construction,
* partial evaluation,
* interpolated value construction,
* owner-class checks,
* resolution-profile queries,
* lowering-class selection.

This module should not parse source and should not emit backend text.

### `mtx_lower_tex`

Responsibilities:

* EIR to TIR lowering,
* symbolic placeholder lowering,
* runtime primitive selection,
* resource lowering,
* page-furniture lowering,
* math lowering,
* `.tex` emission.

### `mtx_driver`

Responsibilities:

* orchestrating all phases,
* engine invocation,
* auxiliary-file reconciliation,
* multi-pass stabilization checks,
* diagnostics presentation.

### `runtime/marktex.sty` and `runtime/marktex.lua`

Responsibilities:

* backend ABI,
* symbolic runtime support,
* page/runtime helpers,
* structured flow and furniture primitives.

---

## 4. Core Semantic Runtime

The implementation should expose one central semantic runtime object during compilation.

A conceptual initial shape is:

```text
CompilerRuntime {
  schema_registry,
  nir_document,
  state_store,
  host_environment,
  mutation_log,
  resolver,
  backend_profile,
  diagnostics
}
```

This object need not be public API, but the architecture should behave as if such a runtime exists.

---

## 5. State and Host Strategy

## 5.1 Unified State System

MarkTeX should implement one state system with two frontends:

* declarative updates from `!#`,
* imperative updates from `!$` through live intrinsic objects.

The implementation strategy should be:

1. `!#` normalizes directly into typed patches/state effects.
2. `!$` executes against live intrinsic objects.
3. each host mutation is intercepted,
4. validated against schema,
5. applied to the live state store,
6. and appended to a typed mutation/state-effect log.

This yields Python-like ergonomics without losing compiler discipline.

## 5.2 Intrinsic Ownership Classes

The runtime should model intrinsic fields with ownership classes:

* `compiler`
* `engine`
* `stabilization`
* `frozen`

Examples:

* `LAYOUT.width`: compiler-owned, writable
* `BIB`: compiler-owned, writable if the host API exposes mutation
* `PAGE.N`: engine-owned, readable symbolic, not writable
* `PAGE.MAX`: stabilization-owned, readable symbolic, not writable
* `TIME`: frozen, readable concrete, not writable

## 5.3 Mutation Log

Every semantically visible mutation should be recorded as:

```text
StateEffect {
  target,
  operation,
  typed_value,
  lifetime,
  origin,
  host_order_index
}
```

The state store uses this for:

* diagnostics,
* replay,
* incremental rebuild decisions,
* state inspection tooling,
* and canonical EIR construction.

---

## 6. Schema-Driven Feature Addition

Adding a new keyword or feature should normally require changes in schema and lowering, not in parsing.

The recommended checklist for adding a new feature root such as `figure`, `table`, or `theorem` is:

1. register the root in `mtx_schema`,
2. register its fields,
3. register accepted tags,
4. declare binding modes,
5. declare allowed lifetimes,
6. declare merge laws,
7. declare ownership and host-writability where relevant,
8. declare symbolic permissions,
9. define host constructors if needed,
10. define TIR/backend lowering.

This is the main mechanism that gives MarkTeX LLVM-like extensibility rather than GCC-style entanglement.

---

## 7. Initial MVP Scope

The first implementation should be intentionally narrow.

Recommended MVP:

* core Markdown blocks and inline text,
* directives: `!#`, `!@`, `!!@`, `!$`,
* dedicated multi-line `!$` host blocks,
* `[$ ... ]`,
* bracket-call fallback,
* image-call fallback and rich-image mode,
* `$...$` and `$$...$$`,
* ordinary and `interp` fenced code blocks,
* state roots:
  * `layout`
  * `margin`
  * `column`
  * `header`
  * `footer`
  * basic text style fields
  * `image`
  * `bib`
* intrinsic objects:
  * `LAYOUT`
  * `MARGIN`
  * `COLUMN`
  * `HEADER`
  * `FOOTER`
  * `BIB`
  * `TIME`
  * `PAGE`
* LuaLaTeX backend only.

Do not attempt in the first implementation:

* generalized package systems,
* all bibliography styles,
* all theorem/float/listing families,
* multi-backend support,
* full incremental cache,
* editor tooling beyond simple diagnostics.

---

## 8. Suggested Implementation Order

### Milestone 1: Core Data and Schema

Build:

* schema registry,
* core IR types,
* state partitions,
* origin model,
* live intrinsic class interfaces.

Exit condition:

* hand-constructed patches and state effects can be applied and inspected.

### Milestone 2: Surface Frontend

Build:

* CST,
* Surface AST,
* directive recognition,
* MOS parser,
* bracket-call/image-call shell capture,
* math and fence capture.

Exit condition:

* parser golden tests pass on docs examples.

### Milestone 3: NIR

Build:

* modifier binding,
* schema validation,
* declaration expansion,
* scope matching,
* patch typing,
* image/math/interp fence normalization.

Exit condition:

* source-level ambiguity is removed,
* NIR snapshots are stable.

### Milestone 4: Python Host and EIR

Build:

* host environment,
* live compiler-owned intrinsic mutation,
* single-line and block-form host execution,
* read-only symbolic intrinsic values,
* mutation logging,
* return-value lifting,
* EIR canonicalization.

Exit condition:

* `!$ LAYOUT.width = 100`
* `[$ PAGE.MAX - PAGE.N ]`
* `!$ BIB += "extra.bib"`

all behave correctly under tests.

### Milestone 5: TIR and TeX Lowering

Build:

* page and text lowering,
* image lowering,
* math lowering,
* symbolic placeholder lowering,
* page furniture lowering,
* `.tex` emission.

Exit condition:

* representative documents compile under LuaLaTeX.

### Milestone 6: Driver and Multi-Pass Stabilization

Build:

* engine invocation,
* auxiliary analysis,
* stabilization loop,
* source-mapped backend diagnostics.

Exit condition:

* `PAGE.MAX`, `pageref`, and similar features converge.

---

## 9. Testing Strategy

The first implementation should rely heavily on golden and structural tests.

Recommended test classes:

### Surface tests

* directive whole-line recognition,
* tag vs dimension binding,
* `!@` multi-entry expansion,
* code fence literal behavior,
* `interp` fence behavior,
* math delimiter capture.

### Schema tests

* allowed roots,
* tag prerequisites,
* transform tags requiring presets,
* host-writable vs read-only fields,
* merge laws.

### Host tests

* live mutation ordering,
* symbolic reads of `PAGE`,
* rejection of illegal writes,
* mutation logging,
* patch/object return lifting.

### IR tests

* NIR canonical snapshots,
* EIR symbolic expression snapshots,
* TIR symbolic placeholder selection.

### Integration tests

* compile `.mtx` to `.tex`,
* run LuaLaTeX,
* verify stabilization-sensitive outputs.

---

## 10. Extensibility Rule of Thumb

When a new feature request appears, implementation should ask:

1. can this be expressed by schema only?
2. if not, does it require a new node kind?
3. if not, does it require a new lowering rule only?
4. only after those fail should the parser gain a new surface construct.

This rule is critical.

If followed consistently, MarkTeX stays small at the surface and rich in semantics.

---

## 11. Initial Recommendation

For the first code implementation, Python is a pragmatic implementation language for:

* the schema system,
* the host bridge,
* the state engine,
* and the first compiler driver.

This aligns with the host language and lowers iteration cost.

Performance-sensitive components such as parsing, caching, and future alternative backends can be optimized later without changing the semantic architecture.

---

## 12. Final Principle

The initial implementation should behave like a compiler toolkit, not like a pile of special cases.

The shortest summary is:

> parse little, bind by schema, mutate live state carefully, record every semantic effect, lower late, and keep the backend replaceable.

That is the recommended implementation architecture for MarkTeX v0.1.
