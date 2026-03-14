# MarkTeX v0.1

## Python Host Specification

## 1. Scope

This document defines the Python compile-time host of MarkTeX.

It specifies:

* when Python executes,
* what forms invoke host execution,
* the host environment and its visible objects,
* intrinsic and symbolic object behavior,
* allowed return categories,
* node and patch construction,
* side effects and execution order,
* and the contract between semantic IR and host evaluation.

This document is normative for the transition from **NIR** to **EIR**.

---

## 2. Design Position

Python is the **compile-time host language** of MarkTeX.

It is not:

* the source parser,
* the semantic authority of the language,
* or the final rendering backend.

Its role is to provide:

* compile-time computation,
* structural generation,
* macro-like expansion,
* typed object construction,
* and partial symbolic expression formation.

The central law is:

> Python may compute, generate, and transform, but the semantic currency of MarkTeX remains typed IR objects.

Python therefore does not replace the language core.
It operates through it.

---

## 3. Execution Phase

Python execution occurs during the transition:

```text id="hfa1p5"
NIR -> EIR
```

No Python code is executed during:

* lexical analysis,
* surface parsing,
* bracket-call disambiguation,
* MOS parsing,
* or NIR formation.

This separation is mandatory.

The parser constructs structure.
The host computes over structure.

---

## 4. Host Invocation Forms

The core host invocation forms are:

1. **evaluation statements**
2. **evaluation expressions**

---

## 4.1 Evaluation Statements

Surface form:

```text id="4mffcy"
!$ <python-code>
```

This introduces host-side executable code.

Its normalized form is:

```text id="pseajh"
EvalStmt { code: PyStmtOrExpr, origin: Origin }
```

Statement execution may:

* bind names,
* mutate host-visible compile-time objects,
* emit nodes or patches through APIs,
* register resources,
* define helper functions,
* perform arbitrary Python computation.

A statement does not directly yield inline text unless it explicitly constructs or emits nodes.

---

## 4.2 Evaluation Expressions

Surface form:

```text id="3f8nbn"
[$ <python-expression> ]
```

This introduces an evaluable host expression.

Its normalized form is:

```text id="xyjofj"
InlineExpr { expr: Expr, origin: Origin }
```

or its structured equivalent in MOS-bearing contexts.

An evaluation expression yields a value or node-like object that is then lifted into EIR.

Python expression semantics are ordinary Python expression semantics as mediated by the host bridge.
If an expression performs side effects through host-visible live objects, those effects are real.

However, statement form remains the recommended style for stateful mutation because it is clearer in source.

---

## 5. Host Execution Model

Host execution is **lexically ordered**.

The host environment is persistent across the source file unless a future module or local-host-scope system defines otherwise.

Thus:

```marktex id="w9ys0y"
!$ x = 10
Value: [$ x ]
```

is valid because the binding of `x` persists to the later evaluation point.

The default rule is:

> later host code sees the effects of earlier host code in the same compilation unit.

---

## 5.1 Statement/Expression Ordering

Given source order:

1. NIR is formed first,
2. host statements and expressions are visited in lexical order,
3. each evaluation point sees the host environment produced by prior evaluation points,
4. the result is accumulated into EIR.

This ordering is normative.

Implementations may optimize only if the behavior is observationally identical.

---

## 6. Host Environment

The host environment is an explicit compiler-provided namespace.

It MUST be versioned and documented.

It SHOULD be stable across minor language revisions.

The host environment exposes at least the following categories:

1. intrinsic objects,
2. symbolic objects,
3. typed constructors,
4. node constructors,
5. patch constructors,
6. resource constructors,
7. helper utilities,
8. current compilation context.

---

## 6.1 Required Environment Classes

The exact API names are implementation-defined, but the following semantic classes are required.

### Intrinsic objects

Examples:

* `PAGE`
* `TIME`
* `LAYOUT`
* `MARGIN`
* `COLUMN`
* `HEADER`
* `FOOTER`
* `BIB`

### Constructors

Examples:

* block constructors,
* inline constructors,
* patch constructors,
* object constructors.

### Compilation context

Examples:

* current file,
* current origin,
* backend profile,
* compilation options,
* package registry if adopted.

---

## 7. Host Result Categories

A host evaluation may return only values in the language’s accepted result domain.

Allowed result categories are:

1. concrete scalar values,
2. symbolic values,
3. typed semantic objects,
4. patches,
5. inline nodes,
6. block nodes,
7. node sequences,
8. null-like absence values where permitted by context.

Any other Python value is invalid unless explicitly lifted by a registered conversion rule.

---

## 7.1 Concrete Scalars

Concrete scalars include:

* `None`, where context allows omission,
* `bool`,
* `int`,
* `float`,
* `str`,
* datetime-like values if supported by the host bridge,
* lists and mappings only when the receiving constructor or context accepts them.

A scalar does not automatically become a node.
Context determines lifting.

---

## 7.2 Symbolic Values

A symbolic value is a host-visible proxy for a semantically valid but not yet concrete value.

Examples:

* page number,
* total page count,
* page parity,
* current running mark,
* unresolved cross-reference page.

Symbolic values may participate in host expressions and may survive into EIR and TIR.

---

## 7.3 Typed Semantic Objects

A typed semantic object is a host-side representation of a schema-bound MarkTeX object.

Examples:

* layout specification,
* margin patch,
* font routing object,
* bibliography resource set.

Typed semantic objects are the preferred bridge between Python and IR.

---

## 7.4 Patches

A host expression may produce a patch directly.

Example, schematically:

```python id="hqmqfc"
patch.text(color="red", weight="bold")
```

A returned patch is inserted or applied according to the context in which it appears.

Patch objects MUST already be typed and schema-valid before entering EIR.

---

## 7.5 Nodes and Node Sequences

A host evaluation may produce:

* one inline node,
* one block node,
* a sequence of inline nodes,
* a sequence of block nodes.

Node sequences are valid only in contexts that admit them.

Example:

```python id="sdln57"
inline.seq(text("A"), text("B"))
block.paragraph("Hello")
```

---

## 8. Contextual Lifting Rules

The same host value may be interpreted differently depending on context.

This is intentional.

### 8.1 Inline expression context

In inline position:

* `str` lifts to `Text`,
* inline node lifts directly,
* inline sequence lifts directly,
* scalar values lift to text by stringification if the context allows it,
* block nodes are invalid.

### 8.2 Block generation context

In block-emitting host APIs:

* block nodes lift directly,
* block sequences lift directly,
* plain strings MAY lift to paragraphs if the API defines that behavior,
* inline-only values are invalid unless wrapped.

### 8.3 Patch context

Where a patch is expected:

* only patch-compatible results are accepted,
* arbitrary scalars do not implicitly become patches.

Context-sensitive lifting MUST be deterministic and documented.

---

## 9. Intrinsic Objects

Intrinsic objects are compiler-provided host-visible semantic objects.

They are not merely fake placeholders for later replacement.
Depending on object kind, they may be:

* live mutable compiler-owned state objects,
* read-only symbolic engine-owned objects,
* read-only symbolic stabilization-owned objects,
* frozen concrete views,
* smart resource collections,
* operator-overloaded expression builders.

The meaning of each intrinsic object is defined by the compiler, not by naive Python intuition.

---

## 9.1 Declarative and Imperative Frontends

MarkTeX has two frontends onto one document-state system:

* `!#` introduces declarative state changes in surface syntax,
* `!$` may perform imperative state changes through live intrinsic objects.

These are not separate semantic worlds.
They are two frontends over the same typed state model.

Thus:

```marktex
!# layout: width: 100
```

and:

```marktex
!$ LAYOUT.width = 100
```

are two ways to produce the same class of semantic state effect.

When host code mutates a compiler-owned intrinsic, the mutation is real during EIR construction.
The compiler MUST still record an equivalent typed state event or canonical patch form, with origin, so that diagnostics, replay, lowering, and tooling remain coherent.

---

## 9.2 Ownership Classes

Each intrinsic object kind and each exposed intrinsic field MUST declare at least:

1. owner class,
2. host readability,
3. host writability,
4. resolution behavior,
5. lowering behavior where relevant.

The core ownership classes are:

### Compiler-owned

Examples:

* `LAYOUT`
* `MARGIN`
* `COLUMN`
* `HEADER`
* `FOOTER`
* `BIB`

These may be live mutable host objects if the schema permits.

### Engine-owned

Examples:

* `PAGE.N`
* current-page parity
* current running mark of the active page

These are readable symbolic values, not writable host state.

### Stabilization-owned

Examples:

* `PAGE.MAX`
* page of a reference target

These are readable symbolic values whose final concretization requires backend stabilization.

### Frozen concrete

Examples:

* `TIME`

These are concrete during host execution and ordinarily read-only.

---

## 9.3 Compiler-Owned Live Objects

Compiler-owned intrinsics may be exposed as live semantic objects.

If so:

* reads observe the current compile-time document state,
* writes mutate that state immediately in host evaluation order,
* later host code sees the updated value,
* the compiler records the mutation as a typed semantic state effect.

Example:

```python
LAYOUT.width = 100
MARGIN.top = 20
```

This is real mutation, not merely syntactic sugar.

However, such mutation is valid only where:

* the target field is declared writable,
* the assigned value passes schema validation,
* and the resulting state remains semantically valid.

The implementation MUST reject writes to unknown fields, illegal fields, or invalid value shapes.

---

## 9.4 `PAGE`

`PAGE` is a read-only symbolic page-state object.

Typical attributes include:

* `N`
* `MAX`
* parity or side selectors if supported,
* current page style markers.

`PAGE.N` is typically engine-owned.
`PAGE.MAX` is typically stabilization-owned.

They may be used in expressions:

```python id="3890cq"
PAGE.MAX - PAGE.N
```

This produces a symbolic expression if not concretely reducible.

Writes such as:

```python
PAGE.N = 3
```

are invalid because `PAGE` fields are not host-writable.

---

## 9.5 `TIME`

`TIME` is a compile-time temporal object.

It is usually concrete at evaluation time.

It MAY expose Python-like datetime behavior such as:

* `.year`
* `.month`
* `.day`
* `.hour`
* `.minute`
* `.strftime(...)`

The implementation MUST define whether `TIME` is:

* fixed at compilation start,
* fixed per file,
* or evaluated per host access.

The recommended rule is:

> `TIME` is frozen at compilation start for one compilation run.

This yields stable intra-run behavior.

`TIME` is ordinarily read-only.

---

## 9.6 `BIB`

`BIB` is a bibliography resource object.

It is not a string.

It behaves as a smart resource collection and may support operators such as:

* `+` for union-addition,
* `-` for subtraction,
* `+=` for live resource mutation if the host API exposes it,
* membership or iteration if exposed by the host API.

Examples:

```python id="skhzlm"
BIB + "extra.bib"
```

and, if supported by the host API:

```python
BIB += "extra.bib"
```

The former constructs a typed resource result.
The latter performs a real compiler-owned resource mutation and records the corresponding state effect.

Neither may degrade into raw string concatenation.

---

## 9.7 Layout and Style Intrinsics

Objects such as `LAYOUT`, `MARGIN`, `COLUMN`, `HEADER`, and `FOOTER` may be exposed as live compiler-owned semantic objects with field assignment, method update helpers, or both depending on implementation strategy.

Their behavior MUST be documented per object and per field.

They MUST NOT silently degrade into backend-specific text fragments.

---

## 10. Symbolic Objects and Expression Formation

MarkTeX host evaluation supports **partial symbolic evaluation**.

If an expression is fully concrete, it SHOULD be reduced eagerly.

If an expression contains symbolic operands but remains representable, it MUST be preserved symbolically.

If an expression is neither reducible nor representable, it is a compile-time error.

---

## 10.1 Symbolic Operator Support

A symbolic object may support:

* arithmetic operators,
* comparison operators,
* string-like interpolation support,
* attribute access,
* function-like combinators if explicitly defined.

Supported operations MUST be closed over symbolic expression construction.

Unsupported operations MUST fail explicitly.

---

## 10.2 Example

```python id="yjlwm0"
f"{PAGE.N} / {PAGE.MAX}"
```

may be permitted only if the host bridge supports symbolic string interpolation.

Otherwise, the preferred canonical form is:

```python id="30j6a6"
PAGE.N, PAGE.MAX
```

inside a schema-aware text field, or explicit constructors such as:

```python id="vhu4zi"
inline.seq(PAGE.N, text(" / "), PAGE.MAX)
```

The host specification MUST define how symbolic text composition works.

The recommended rule is:

> symbolic content is composed through node-aware constructors, not through arbitrary Python stringification.

---

## 11. Constructors

The host MUST expose typed constructors.

Free-form Python dictionaries and raw tuples are not the preferred semantic interface.

The constructor surface SHOULD be divided into these families:

1. node constructors,
2. patch constructors,
3. object constructors,
4. resource constructors.

---

## 11.1 Node Constructors

These construct IR node objects.

Typical constructors include:

* `text(...)`
* `span(...)`
* `paragraph(...)`
* `heading(...)`
* `link(...)`
* `cite(...)`
* `region(...)`
* `inline.seq(...)`
* `block.seq(...)`

The exact API naming is implementation-defined, but the constructors MUST be typed and phase-valid.

---

## 11.2 Patch Constructors

These construct state patches.

Typical families include:

* `patch.page(...)`
* `patch.flow(...)`
* `patch.text(...)`
* `patch.object(...)`
* `patch.resource(...)`

Example:

```python id="pkog2a"
patch.text(color="blue", weight="bold")
```

A patch constructor MUST validate field names, value types, and allowed lifetime usage when the patch is placed into context.

---

## 11.3 Object Constructors

These construct schema-bound semantic objects that are not yet attached to a particular state lifetime.

Examples:

* layout specifications,
* margin objects,
* bibliography declarations,
* counter policies.

These are useful when the host builds more complex patches or generated structures compositionally.

---

## 11.4 Resource Constructors

These construct typed resource declarations or resource sets.

Examples:

* bibliography file sets,
* asset references,
* labels,
* counters,
* cross-reference descriptors.

---

## 12. Host-Side Emission

Host code may generate document content in two general ways.

## 12.1 Return-based generation

A host expression returns a node, node sequence, or value which is then inserted into the surrounding IR context.

This is the preferred form for local generation.

## 12.2 Context-based emission

A host statement may call a compiler-provided API to emit nodes or patches into the current compilation stream.

This is useful for macro-like operations, but SHOULD be more restricted and more explicit.

The recommended rule is:

> return values are primary; side-effect emission is secondary.

This keeps the host model more compositional.

---

## 13. Side Effects

MarkTeX does not define a safety sandbox as part of the language core.

Python host code is real Python.

Therefore:

* filesystem access,
* process access,
* imports,
* mutation of host-visible objects,
* and arbitrary Python side effects

are matters of implementation policy, not language prohibition.

However, the compiler MUST still define semantic visibility.

The semantic rule is:

> only effects that are reflected through accepted MarkTeX result objects or registered compilation channels may affect EIR.

In other words, Python may do many things, but only MarkTeX-visible results alter document semantics.

---

## 13.1 Semantic vs Extra-Semantic Effects

### Semantic effects

Effects that alter the generated document through:

* returned nodes,
* returned patches,
* resource registration,
* direct mutation of compiler-owned intrinsic objects,
* compiler-recognized host bindings.

### Extra-semantic effects

Effects such as:

* writing files,
* printing diagnostics,
* external network operations,
* arbitrary process mutation.

These may occur, but are outside the semantic model unless the implementation explicitly integrates them.

---

## 14. Host Bindings and Persistence

Names bound in the host environment persist in lexical compilation order.

Example:

```marktex id="vfhubp"
!$ base_color = "blue"
Hello [$ base_color ]
```

This is valid.

Bindings may be shadowed by later bindings.

The host environment is therefore a persistent compile-time namespace.

---

## 14.1 Rebinding

Rebinding a name replaces the previous binding for subsequent evaluation points.

Example:

```marktex id="s0wk9f"
!$ x = 1
[$ x ]
!$ x = 2
[$ x ]
```

yields `1` then `2` in ordinary semantics.

---

## 14.2 Scope of Python Bindings

By default, Python bindings are compilation-global within the current source unit and its evaluation stream.

They are not coupled to document style scopes unless a later language revision explicitly introduces such coupling.

Thus:

* entering a `!@ ... !!@` document scope does not automatically push or pop Python locals,
* style scope and host scope are distinct systems.

---

## 15. Error Semantics

Host errors are compile-time errors.

The core host error classes include:

* Python syntax error in `!$` or `[$ ... ]`,
* invalid host result type,
* invalid symbolic operation,
* invalid constructor call,
* schema-invalid patch produced by host code,
* illegal write to a read-only intrinsic field,
* schema-invalid intrinsic mutation,
* context-invalid node returned into an incompatible position,
* host exception raised during evaluation.

Implementations SHOULD preserve Python traceback information, but MUST also map the error back to source origin.

---

## 15.1 Invalid Result Example

In inline expression context:

```python id="4e01tp"
paragraph("hello")
```

is invalid because a block node cannot be inserted into inline position.

This is a context error, not merely a Python error.

---

## 15.2 Invalid Symbolic Operation Example

If symbolic division of page objects is unsupported, then:

```python id="r9cvk6"
PAGE.MAX / PAGE.N
```

is a compile-time error unless the host bridge explicitly supports that symbolic expression form.

---

## 15.3 Invalid Intrinsic Mutation Example

If `PAGE.N` is read-only, then:

```python
PAGE.N = 3
```

is a compile-time host/state error, not a valid symbolic override.

Likewise, if `LAYOUT.width` exists but rejects the assigned value shape, the assignment fails as a schema-invalid intrinsic mutation.

---

## 16. Lowering Boundary

Python host evaluation ends at EIR.

The host MUST NOT directly emit raw backend code as the primary semantic path.

Host code may construct raw backend nodes if the language exposes such nodes, but this is an explicit escape hatch, not the default model.

The normal path is:

```text id="l7qmxj"
Python -> typed values / patches / nodes -> EIR -> TIR -> backend
```

This preserves semantic integrity.

---

## 17. Host/IR Bridge Contract

The host bridge MUST define conversions in both directions.

## 17.1 IR-visible to Python

The host may receive:

* intrinsic proxies,
* symbolic objects,
* typed semantic objects,
* node objects,
* patch objects,
* source origin helpers,
* compilation context objects.

## 17.2 Python-visible back to IR

The compiler may accept from Python:

* allowed concrete scalars,
* symbolic expressions,
* typed semantic objects,
* patches,
* nodes,
* node sequences,
* null-like omission values.

This bridge MUST be explicit and stable.

---

## 18. Determinism

The language does not require host evaluation to be pure.

However, the compiler SHOULD distinguish between:

* deterministic semantic expansion,
* and extra-semantic host effects.

The recommended operational principle is:

> a MarkTeX compilation is semantically determined by the source plus the observable results of host evaluation.

If the host reads external state, then compilation may vary accordingly.
This is permitted by the language model.

---

## 19. Caching and Reuse

Because host execution may be expensive, implementations MAY cache evaluation results.

However, caching is valid only if the implementation can preserve observational equivalence.

The language itself imposes no requirement that host execution be referentially transparent.

Therefore, caching is an implementation optimization, not a semantic assumption.

---

## 20. Minimal Examples

## 20.1 Simple binding

```marktex id="ggwgqi"
!$ x = 42
Answer: [$ x ]
```

Semantics:

* `!$` binds `x`,
* `[$ x ]` evaluates to concrete scalar `42`,
* inline context lifts `42` to text.

---

## 20.2 Symbolic expression

```marktex id="gqvvwb"
Pages remaining: [$ PAGE.MAX - PAGE.N ]
```

Semantics:

* both operands are symbolic,
* subtraction yields symbolic expression,
* expression survives into EIR and later lowering.

---

## 20.3 Patch construction

```marktex id="g2kr6w"
[$ patch.text(color="red", weight="bold").apply_to("Warning") ]
```

If the host API defines such a constructor pattern, this may yield a styled inline node sequence.

The important point is that Python constructs typed semantic objects rather than raw formatting strings.

---

## 20.4 Node generation

```marktex id="9jkjkw"
!$ def note(s): return paragraph(span(text("Note: "), patch.text(weight="bold")), text(s))
```

A later block-generation site may use `note(...)` if the embedding context admits block results.

---

## 20.5 Resource update

```marktex id="zt8ax1"
!$ extra = BIB + "supplement.bib"
!# bib: [$ extra ]
```

Semantics:

* `extra` is a typed bibliography resource result,
* the persistent patch consumes that object,
* resource state is updated under its declared merge law.

---

## 21. Host Invariants

The following are normative.

1. Python executes only after NIR construction.
2. Python does not participate in parsing or source disambiguation.
3. Host-visible objects are semantic objects, not naive raw strings unless documented as such.
4. Only accepted result categories may enter EIR.
5. Symbolic values may survive host evaluation.
6. Context determines lifting of values into nodes.
7. Host code may have arbitrary Python effects, but only MarkTeX-visible outputs alter document semantics.
8. Style scope and host binding scope are distinct unless later unified by explicit language design.
9. Typed constructors are the preferred bridge between Python and IR.
10. Compiler-owned intrinsic mutation, if supported, is real host-time mutation and must be recorded as typed semantic state effect.
11. Engine-owned and stabilization-owned symbolic intrinsics are readable but not writable.
12. EIR is the semantic output of host evaluation.

---

## 22. Recommended Host API Style

The host API SHOULD prefer:

* typed constructors over free-form dicts,
* node composition over string templating,
* symbolic composition over accidental stringification,
* explicit resource operations over raw path hacking,
* explicit patch construction over textual pseudo-MOS generation.

This keeps the host layer expressive without weakening the core language.

---

## 23. Final Principle

The Python host is powerful because it is real Python.
But MarkTeX remains coherent only if the host still interacts with typed semantic objects and typed semantic state.

The design law is therefore:

> Python may be unrestricted, and intrinsic mutation may be real, but the compiler must still own the typed semantic record of what happened.

That is what lets the language remain script-like at the surface while exact at the core.
