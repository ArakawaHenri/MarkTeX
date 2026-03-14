# MarkTeX v0.1

## Core IR, Evaluation Model, and Frontend/Backend Contract

## 1. Scope

This document defines the semantic core of MarkTeX.

It does **not** define the entire surface syntax of `.mtx`. Instead, it defines:

* the compilation phases,
* the normalized and expanded intermediate representations,
* the state model,
* the evaluation model for Python-hosted expressions,
* the `[]()` fallback rule,
* and the contract by which MarkTeX lowers to TeX.

The purpose of this specification is to make MarkTeX a language rather than a collection of ad hoc syntactic conveniences.

---

## 2. Design Position

MarkTeX is:

* a **document programming language**,
* with a **Markdown-like authoring surface**,
* a **typed object language** for document state and layout,
* a **Python compile-time host**,
* and a **TeX-targeting compiler**.

MarkTeX is **not** defined by Markdown compatibility.
Markdown is a source-level inheritance and fallback layer, not the semantic core.
Where MarkTeX and Markdown surface forms overlap, MarkTeX has priority and Markdown only interprets the residual structure left after MarkTeX resolution.

TeX is **not** the semantic authority of the language.
TeX is the primary backend.

The semantic authority of MarkTeX is the IR defined here.

---

## 3. Compilation Pipeline

The canonical internal pipeline is:

```text
.mtx
-> CST
-> Surface AST
-> NIR   (Normalized IR)
-> EIR   (Expanded IR)
-> TIR   (TeX IR)
-> .tex
-> TeX engine
-> PDF
```

### 3.1 CST

Concrete syntax tree. Preserves:

* source spans,
* token boundaries,
* original delimiters,
* trivia when needed for formatting or diagnostics.

### 3.2 Surface AST

Represents parsed source constructs before semantic normalization. It may still contain:

* `!#`, `!@`, `!!@`, `!$`,
* bracket-call nodes,
* raw MOS fragments,
* ambiguous Markdown/MTX inline forms.

### 3.3 NIR

Normalized IR. This is the first semantic IR.

NIR MUST:

* resolve `[]()` into either MTX inline control or Markdown inline structure,
* parse MOS into typed objects,
* normalize directives into explicit patches and regions,
* classify state mutations by lifetime,
* preserve unresolved expressions as expression nodes.

NIR MUST NOT execute Python.

### 3.4 EIR

Expanded IR. This is NIR after compile-time evaluation.

EIR MUST:

* execute `!$` statements,
* evaluate `[$ ... ]` where possible,
* expand macros and generated content,
* materialize Python-produced document nodes,
* materialize host-origin intrinsic mutations into typed semantic state effects,
* preserve symbolic expressions that cannot yet be concretized.

EIR is the authoritative semantic form for backend lowering.

### 3.5 TIR

TeX IR. Backend-oriented lowering form.

TIR MUST:

* encode layout and style decisions in backend-friendly form,
* preserve symbolic page/runtime expressions where TeX must resolve them,
* separate content flow from backend support code,
* lower document semantics into runtime calls rather than raw ad hoc TeX whenever possible.

---

## 4. Semantic Layers

MarkTeX has four distinct semantic layers:

1. **Surface layer**: author-facing source syntax.
2. **Core IR layer**: normalized semantic objects and patches.
3. **Compile-time host layer**: Python evaluation and expansion.
4. **Backend layer**: TeX-oriented lowering and runtime support.

A feature is properly designed only if its meaning is clear at all four layers.

---

## 5. Core IR Overview

The core IR is object-based and typed.
It is not a string-rewriting system.

The minimal semantic categories are:

* document nodes,
* block nodes,
* inline nodes,
* control nodes,
* state patches,
* expressions,
* values,
* symbolic values,
* resources,
* source origins.

---

## 6. Core Types

The following notation is schematic rather than implementation-bound.

## 6.1 Root

```text
Document {
  meta: MetaState,
  body: BlockSeq,
  resources: ResourceTable,
  origin: Origin
}
```

```text
BlockSeq = [Block]
InlineSeq = [Inline]
```

---

## 6.2 Block Nodes

```text
Block =
    Paragraph
  | Heading
  | PageBreak
  | ListBlock
  | QuoteBlock
  | CodeBlock
  | InterpolatedCodeBlock
  | MathBlock
  | TableBlock
  | RegionBlock
  | RawMarkdownBlock
  | RawTeXBlock
  | GeneratedBlock
```

### Paragraph

```text
Paragraph {
  content: InlineSeq,
  origin: Origin
}
```

### Heading

```text
Heading {
  level: Int,         // 1..6 in the common case
  content: InlineSeq,
  attrs: AttrMap,
  origin: Origin
}
```

### PageBreak

```text
PageBreak {
  cause: PageBreakCause,
  origin: Origin
}
```

This is an explicit semantic page boundary.
It is distinct from engine-emergent pagination.
One common cause is a page-bound state transition such as a mid-flow change to layout, margins, columns, header, or footer.

### CodeBlock

```text
CodeBlock {
  info_string: CodeFenceInfo?,
  body: String,
  origin: Origin
}
```

This is the normalized form of an ordinary fenced code block.
Its body is literal text.

### InterpolatedCodeBlock

```text
InterpolatedCodeBlock {
  info_string: CodeFenceInfo?,
  body: [LiteralChunk | ExprChunk],
  origin: Origin
}
```

This is the normalized form of a fenced code block whose info string contains the reserved flag `interp`.

### MathBlock

```text
MathBlock {
  payload: MathPayload,
  origin: Origin
}
```

This is the normalized form of delegated display math such as `$$ ... $$`.

### RegionBlock

A region is an explicitly scoped semantic block.

```text
RegionBlock {
  patch: ScopedPatch,
  body: BlockSeq,
  origin: Origin
}
```

This is the normalized form of constructs such as scoped `!@ ... !!@`.

---

## 6.3 Inline Nodes

```text
Inline =
    Text
  | SoftBreak
  | HardBreak
  | Span
  | StyledSpan
  | Link
  | Image
  | MathInline
  | InlineExpr
  | Citation
  | CrossRef
  | RawMarkdownInline
  | RawTeXInline
  | GeneratedInline
```

### StyledSpan

```text
StyledSpan {
  patch: InlinePatch,
  content: InlineSeq,
  origin: Origin
}
```

This is the normalized form of MTX-style `[]()` inline control.

### Image

```text
Image {
  alt: InlineSeq,
  resource: ResourceRef?,
  patch: ObjectPatch?,
  origin: Origin
}
```

This is the normalized form of either:

* Markdown image fallback,
* or MTX rich image control from `![alt](payload)`.

The exact image schema determines whether the source, local image patch, or both are present explicitly on the node.

### MathInline

```text
MathInline {
  payload: MathPayload,
  origin: Origin
}
```

This is the normalized form of delegated inline math such as `$ ... $`.

### InlineExpr

```text
InlineExpr {
  expr: Expr,
  origin: Origin
}
```

---

## 6.4 Control Nodes

Control is normalized into explicit objects.

```text
Control =
    PersistentPatch
  | ScopedPatch
  | EvalStmt
  | ResourceDecl
  | BibDecl
  | IncludeDecl
```

### PersistentPatch

A persistent patch mutates document state from its point of appearance onward until overridden.

```text
PersistentPatch {
  patch: StatePatch,
  origin: Origin
}
```

This is the normalized form of `!#`.

### ScopedPatch

A scoped patch applies only to a lexical region.

```text
ScopedPatch {
  patch: StatePatch,
  scope_kind: ScopeKind,
  origin: Origin
}
```

This is the normalized form of one expanded scoped declaration from `!@ ... !!@` or an equivalent region form.
If one `!@` payload contains multiple top-level declarations separated by `;`, normalization first expands them into the same left-to-right stream that would result from multiple `!@` lines.

### EvalStmt

```text
EvalStmt {
  code: PyStmtOrExpr,
  origin: Origin
}
```

This is the normalized form of `!$`.

---

## 6.5 Expressions

```text
Expr =
    LiteralExpr
  | NameExpr
  | AttrExpr
  | UnaryExpr
  | BinaryExpr
  | CallExpr
  | IndexExpr
  | PyExpr
  | SymbolicExpr
```

`Expr` exists in both NIR and EIR, but its allowed subforms differ by phase.

### In NIR

* expressions may still be close to source form,
* Python expressions are opaque-but-parsed as expression payloads,
* no execution has occurred.

### In EIR

* expressions may be reduced to concrete values,
* or preserved as symbolic expressions if backend/runtime resolution is required.

---

## 6.6 Values

```text
Value =
    Null
  | Bool
  | Int
  | Float
  | String
  | DateTime
  | ListValue
  | MapValue
  | ObjectValue
  | NodeValue
  | SymbolicValue
```

### ObjectValue

A typed object produced by MOS or by Python host construction.

### NodeValue

A document node or sequence of nodes produced during expansion.

### SymbolicValue

A value known semantically but not yet concretely available.

Examples:

* current page number,
* total page count,
* page parity,
* current running heading,
* page of a target reference.

---

## 7. State Model

MarkTeX state is partitioned, not monolithic.

```text
State =
  MetaState
  × PageState
  × FlowState
  × TextState
  × ObjectState
  × ResourceState
  × EvalState
```

---

## 7.1 MetaState

Document metadata.

Examples:

* title,
* author,
* date,
* subject,
* keywords.

MetaState is normally document-global.

---

## 7.2 PageState

Page-level layout and page furniture.

Examples:

* layout,
* paper size,
* orientation,
* margins,
* header,
* footer,
* page numbering style,
* page style selectors.

---

## 7.3 FlowState

Block and page-flow behavior.

Examples:

* column count,
* column gap,
* block spacing,
* alignment,
* paragraph indent,
* widow/orphan policy,
* keep-with-next,
* region-local flow behavior.

---

## 7.4 TextState

Run-level and typographic behavior.

Examples:

* western font routing,
* eastern font routing,
* font family,
* size,
* weight,
* italic/emphasis,
* color,
* decoration,
* inline language or script routing.

---

## 7.5 ObjectState

Occurrence-default state for schema-defined object families.

Examples:

* image defaults such as width, fit, and align,
* figure defaults such as placement policy,
* table defaults,
* theorem/listing family defaults in later extensions.

ObjectState exists so that extensible block and inline objects can reuse the same precedence and merge model as other stateful features without being forced into unrelated text or page partitions.

---

## 7.6 ResourceState

Document resources and cross-document support.

Examples:

* bibliography set,
* labels,
* counters,
* references,
* assets,
* external files.

---

## 7.7 EvalState

Compile-time environment.

Examples:

* Python variables,
* imported modules,
* user-defined functions,
* host-side helper objects,
* compile-time configuration.

EvalState is not directly lowered to backend output.

---

## 8. Patches and Merge Semantics

MarkTeX state is mutated only through typed patches.

A patch MUST be schema-driven.
A patch MUST NOT be interpreted as an untyped free-form dictionary merge.

```text
StatePatch =
  MetaPatch
  | PagePatch
  | FlowPatch
  | TextPatch
  | ObjectPatch
  | ResourcePatch
```

### 8.1 Merge Rule Categories

Each field in the schema MUST declare one merge rule:

* `replace`
* `deep-merge`
* `append`
* `prepend`
* `union`
* `subtract`
* `slot-merge`
* `domain-specific`

Examples:

* `layout`: `replace`
* `margin.top`: `replace`
* `header.left`: `slot-merge`
* `image.width`: `replace`
* `bib`: `union` and `subtract`
* font routing tables: `domain-specific`

### 8.2 Patch Lifetimes

There are exactly three lifetimes:

1. **Persistent**

   * begins at source position,
   * remains active until overridden.

2. **Scoped**

   * applies only within a lexical region.

3. **Inline**

   * applies only to the local inline span.

These MUST remain distinct in the IR.

---

## 9. MOS

MOS is the canonical object notation of the surface language.

Its role is not mere configuration convenience.
Its role is to construct typed semantic objects.

MOS MUST compile to typed semantic objects through ordered modifier application.
It MUST NOT be treated as an unordered map literal.

Examples:

* `layout: A4, landscape` → `LayoutSpec`
* `margin: top: 20` → `MarginPatch`
* `w: font: "Times New Roman", size: 12pt` → `FontRoutePatch`
* `header: left: "...", right: "..."` → `HeaderPatch`

### 9.1 Schema Registry

MOS roots, fields, and tags are resolved against a schema registry:

* core schema,
* extension schema,
* namespaced schema.

The grammar of MOS is fixed.
Its vocabulary may be extended by schema registration.

This preserves language stability while allowing domain extension.

### 9.2 Ordered Modifier Application

The normalized meaning of MOS is an ordered modifier stream.

Within one modifier list:

* groups normalize first,
* then modifiers at the same level are applied left to right,
* later modifiers may override earlier effects according to schema.

This applies both:

* inside one object's value list,
* and across directive-level declaration streams separated by `;`.

Example:

```text
layout: A4, width: 100, landscape
```

is interpreted as:

1. apply `A4`,
2. apply `width = 100`,
3. apply `landscape`.

If `A4` expands to width and height defaults, the later explicit width overrides only the width component unless the schema defines stronger replacement semantics.

### 9.3 Binding Modes and Tags

A schema may declare accepted modifiers using binding classes analogous to Python parameter modes:

* positional-only,
* keyword-only,
* dual-use.

Dimension literals are ordinary scalar atoms.
They are not tags, but a schema may bind them positionally.

Tags are zero-value modifier applications.
They commonly correspond to keyword-only or dual-use schema parameters that permit omission of an explicit value.

Useful tag families include:

* preset tags such as `A4`, `A5`, `Letter`
* transform tags such as `landscape`, `portrait`
* enum/style tags such as `bold`, `italic`, `justify`, `contain`

A tag may expand into one or more ordinary field assignments or other schema-defined effects.

Thus `A4` may normalize into a paper preset, a width/height pair, or an equivalent typed object according to schema, after which later modifiers still apply in source order.

Transform tags may additionally declare prerequisites.
In the core layout schema, `landscape` and `portrait` require an active paper preset such as `A4`.

Their role is to transform preset-derived orientation and dimensions, not to overwrite explicit user-provided width or height fields.

Therefore:

```text
layout: A4, width: 100, landscape
```

normalizes to a layout object equivalent to:

* `orientation = landscape`
* `width = 100`
* `height = 210`

assuming `A4` begins as the portrait preset `210 × 297`.
If no compatible preset is active, a transform tag such as `landscape` is a schema-binding error.

---

## 10. `[]()` Resolution Rule

The bracket-call form is intentionally overloaded.

It MUST be normalized by a strict two-stage rule.

### 10.1 Stage 1: Parse Outer Form

Any source construct of the shape:

```text
[content](payload)
```

is first parsed as a generic `BracketCall`.

No semantic commitment is made yet.

### 10.2 Stage 2: Attempt MTX Interpretation

The `payload` is parsed as MOS.

The construct is resolved as MTX inline control iff all of the following hold:

1. the payload parses as valid MOS with full consumption,
2. the resulting object is valid in inline-style position,
3. semantic validation succeeds for that object kind.

Therefore MTX acceptance depends on full parse success plus successful schema binding and contextual legality.
Syntactic MOS success alone is not enough.

If all three hold, the result is:

```text
StyledSpan { patch: InlinePatch(...), content: ... }
```

### 10.3 Fallback

Otherwise, the entire construct falls back to Markdown interpretation.

Fallback is whole-node, not partial.

This includes cases where:

* MOS parsing succeeds,
* but binding fails,
* or the bound object is illegal in inline context.

This rule is normative.
There is no heuristic mixed mode.

---

## 10.4 `![...](...)` / Image-Call Resolution Rule

The image-call form is intentionally overloaded in the same way as `[]()`.

Any source construct of the shape:

```text
![alt](payload)
```

is first parsed as a generic `ImageCall`.

No semantic commitment is made yet.

### 10.4.1 Attempt MTX Rich-Image Interpretation

The `payload` is parsed as MOS.

The construct is resolved as MTX rich image control iff all of the following hold:

1. the payload parses as valid MOS with full consumption,
2. the resulting object is valid in image-call position,
3. semantic validation succeeds for that object kind.

Again, syntactic MOS success without successful binding/context validation is not enough.

If all three hold, the result is an `Image` node carrying the schema-defined source and local image patch semantics.

### 10.4.2 Fallback

Otherwise, the entire construct falls back to Markdown image interpretation.

Fallback is whole-node, not partial.

---

## 11. Python Host Model

Python is the compile-time host of MarkTeX.
It is not the parser, and it is not the final backend.

Python execution occurs in the transition from NIR to EIR.

### 11.1 Execution Forms

* `!$ ...` introduces executable host statements.
* `!$``` ... !$``` ` introduces executable multi-line host blocks.
* `[$ ... ]` introduces evaluable host expressions.
* host functions may return document nodes, patches, objects, or concrete values.

### 11.2 Allowed Result Categories

A Python evaluation may produce:

* a `ConcreteValue`,
* a `SymbolicValue`,
* a typed object,
* a block node,
* an inline node,
* a sequence of nodes,
* a patch object.

Results outside the allowed categories are a compile-time error.

### 11.3 Host Environment

The host environment exposes:

* intrinsic objects,
* schema-bound constructors,
* node constructors,
* patch constructors,
* helper APIs for generation.

The host environment MUST be explicit and versioned.

---

## 12. Symbolic Objects

Some values are not concretely known during NIR→EIR expansion.

These MUST be represented as symbolic objects rather than forced eagerly.

Examples:

* `PAGE.N`
* `PAGE.MAX`
* running headings,
* target page references.

### 12.1 Operator Semantics

Symbolic objects participate in expression construction.

For example:

```python
PAGE.MAX - PAGE.N
```

does not necessarily reduce to an integer in EIR.
It may instead construct:

```text
BinaryExpr(Sub, AttrExpr(PAGE, "MAX"), AttrExpr(PAGE, "N"))
```

or an equivalent symbolic expression form.

### 12.2 Reduction Policy

Expression reduction is phase-sensitive:

* if all operands are concrete, reduce eagerly;
* if any operand is symbolic and the operation is representable, preserve symbolically;
* otherwise emit a compile-time error.

This gives MarkTeX partial symbolic evaluation rather than all-or-nothing evaluation.

---

## 13. Intrinsic Objects

Intrinsic objects are part of the host environment and the symbolic model.

Examples include:

* `PAGE`
* `TIME`
* `LAYOUT`
* `MARGIN`
* `COLUMN`
* `HEADER`
* `FOOTER`
* `BIB`

These are not required to be ordinary Python objects in the naive sense.
They are semantic objects with operator and attribute behavior defined by the compiler.

### 13.1 Categories

Intrinsic objects may be:

* live compiler-owned state objects,
* read-only symbolic engine-owned objects,
* read-only symbolic stabilization-owned objects,
* smart collections,
* frozen concrete views,
* derived semantic views.

Their behavior MUST be specified per object kind.

### 13.2 Example

`BIB + "extra.bib"` should construct a valid `ResourcePatch` or equivalent typed object, not merely a raw string concatenation.

If the host API exposes direct mutation, then:

```python
LAYOUT.width = 100
```

is a real host-time mutation of a compiler-owned intrinsic object.
The compiler must still canonicalize its semantic effect into the IR-owned state record used for lowering and diagnostics.

---

## 14. Resource Semantics

Bibliography, assets, references, and labels are resources.

They are modeled in `ResourceState`, not as ad hoc text insertion.

Key resource operations include:

* declaration,
* addition,
* subtraction,
* lookup,
* symbolic reference,
* backend emission.

Resource manipulations MUST remain typed through EIR.

---

## 15. Backend Contract

The backend MUST lower from EIR, not from raw source.

TeX output SHOULD target a stable runtime layer rather than directly inlining every implementation detail.

### 15.1 Backend Preference

The canonical backend is LuaLaTeX.

Other TeX engines may support subsets or alternate lowering strategies, but LuaLaTeX defines the reference behavior.

### 15.2 Runtime Contract

Lowering SHOULD produce calls into a MarkTeX runtime layer, such as:

* style-setting primitives,
* region begin/end primitives,
* symbolic page/runtime placeholders,
* bibliography and reference support.

This creates a stable backend ABI and prevents semantic leakage into arbitrary TeX fragments.

---

## 16. Origins and Diagnostics

Every IR node SHOULD carry origin information.

```text
Origin {
  file_id,
  span_start,
  span_end,
  expansion_chain
}
```

`expansion_chain` tracks provenance across generated content and Python expansion.

This is necessary for:

* meaningful diagnostics,
* source mapping,
* formatting,
* incremental rebuilds,
* debugger-style inspection of generated nodes.

---

## 17. Phase Invariants

The following invariants are normative.

### 17.1 Surface AST

May contain unresolved surface constructs.

### 17.2 NIR

Must contain no unresolved `[]()` ambiguity.
Must contain typed MOS objects.
Must not contain executed Python results.

### 17.3 EIR

Must contain no unevaluated host statements.
May contain symbolic expressions.
Must contain only semantically valid node/value/patch objects.

### 17.4 TIR

Must be backend-oriented.
Must not reintroduce source-level ambiguity.
Must preserve enough origin information for backend diagnostics.

---

## 18. Minimal Example

Source:

```marktex
!# layout: A4, landscape; margin: top: 20

!@ column: count: 2, gap: 5

Hello [world](color: blue, bold).
Page: [$ PAGE.N ] / [$ PAGE.MAX ]

!!@ column
```

### NIR sketch

```text
PersistentPatch(PagePatch(LayoutSpec(A4, landscape), MarginPatch(top=20)))
RegionBlock(
  patch = ScopedPatch(FlowPatch(ColumnSpec(count=2, gap=5))),
  body = [
    Paragraph(
      Text("Hello "),
      StyledSpan(
        patch = InlinePatch(color=blue, weight=bold),
        content = [Text("world")]
      ),
      Text(".")
    ),
    Paragraph(
      Text("Page: "),
      InlineExpr(AttrExpr(PAGE, "N")),
      Text(" / "),
      InlineExpr(AttrExpr(PAGE, "MAX"))
    )
  ]
)
```

### EIR sketch

Same as above, except:

* any concrete expressions are reduced,
* `PAGE.N` and `PAGE.MAX` remain symbolic.

### TIR sketch

Lowered to backend calls and symbolic runtime placeholders.

---

## 19. What This Spec Intentionally Does Not Decide Yet

This document leaves the following open for later specification:

* the exact token-level grammar of MOS,
* the exact class API of host-side constructors,
* detailed bibliography backend strategy,
* TeX runtime ABI details,
* packaging and module/import system,
* incremental compilation cache format.

Those belong to separate documents.

---

## 20. Final Principle

The essential design law of MarkTeX is:

> Surface freedom, core rigidity.

The source language may be expressive, inherited, overloaded, and ergonomic.
But the core IR must be typed, phase-separated, and semantically exact.

That is the only way for MarkTeX to remain elegant at the surface without becoming soft at the core.
