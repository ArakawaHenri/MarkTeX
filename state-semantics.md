# MarkTeX v0.1

## State Semantics Specification

## 1. Scope

This document defines the semantics of state in MarkTeX.

It specifies:

* the partition of document state,
* patch typing and patch application,
* precedence and lifetime rules,
* lexical scope entry and exit,
* persistent vs scoped vs inline behavior,
* symbolic state and deferred resolution,
* and the invariants required for deterministic normalization and expansion.

This document is normative for NIR and EIR.

---

## 2. Design Law

MarkTeX state is not an implementation convenience.
It is part of the language.

The central law is:

> State is modified only by typed patches, and every patch has a declared lifetime.

MarkTeX therefore rejects:

* untyped global mutable settings,
* ad hoc dictionary merging,
* backend-dependent accidental state semantics,
* and implicit precedence by parser order alone.

All state transitions MUST be representable in the IR.

---

## 3. State Partition

The complete MarkTeX state is:

```text id="41qcc1"
State =
  MetaState
  × PageState
  × FlowState
  × TextState
  × ResourceState
  × EvalState
```

Each partition has its own schema and merge rules.

No field belongs to more than one partition.

---

## 3.1 MetaState

MetaState contains document metadata.

Typical fields include:

* title,
* author,
* date,
* subject,
* keywords,
* language defaults,
* document class profile if adopted.

MetaState is normally document-global and persistent.

MetaState fields are generally not meaningful in inline scope.

---

## 3.2 PageState

PageState contains page-level layout and page furniture.

Typical fields include:

* paper layout,
* orientation,
* page size,
* margins,
* page numbering mode,
* page style,
* header content,
* footer content,
* running marks,
* page parity selectors.

PageState affects page construction rather than immediate inline rendering.

---

## 3.3 FlowState

FlowState contains block-flow and region-flow behavior.

Typical fields include:

* column count,
* column gap,
* alignment,
* block spacing,
* paragraph indentation,
* keep-with-next,
* keep-together,
* widow/orphan controls,
* section start behavior,
* float behavior if supported.

FlowState applies to block layout regions.

---

## 3.4 TextState

TextState contains run-level typographic behavior.

Typical fields include:

* western font routing,
* eastern font routing,
* font family,
* font size,
* weight,
* italic or emphasis,
* color,
* decoration,
* script-sensitive text routing,
* inline language hints.

TextState is the primary domain for inline patches.

---

## 3.5 ResourceState

ResourceState contains document resources and reference-support state.

Typical fields include:

* bibliography sets,
* labels,
* counters,
* cross-reference tables,
* asset declarations,
* imported resource bundles.

ResourceState may influence both expansion and backend lowering.

---

## 3.6 EvalState

EvalState contains compile-time host environment state.

Typical fields include:

* Python variables,
* host-side helper functions,
* imported modules,
* macro tables,
* generation options,
* compile-time switches.

EvalState is visible during expansion, but is not itself lowered to output semantics except through produced nodes, patches, or values.

---

## 4. State Carriers

State appears in three distinct roles.

## 4.1 Ambient State

The currently active semantic state at a source position or region position.

## 4.2 Declared Patch

A typed modification to one or more partitions of state.

## 4.3 Resolved Effective State

The state after all applicable patches of all lifetimes are combined according to precedence rules.

Only effective state governs rendering and lowering.

---

## 5. Patch Model

A patch is a typed, partial modification of one state partition or a composition of such modifications.

```text id="mg42yp"
StatePatch =
  MetaPatch
  | PagePatch
  | FlowPatch
  | TextPatch
  | ResourcePatch
  | CompositePatch
```

```text id="7cu1eh"
CompositePatch {
  parts: [StatePatch]
}
```

A patch MUST be schema-valid before it may enter NIR.

A patch MUST identify its target partition and field set explicitly, whether directly or by schema-bound object construction.

---

## 5.1 Patch Totality

Patches are always partial.

A patch never stands for “replace the whole partition” unless the target field’s merge law explicitly defines such behavior.

Example:

```text id="tqrzs9"
margin: top: 20
```

does not replace the entire margin object unless the schema says otherwise.
It replaces only the `top` subfield of the page margin structure.

---

## 5.2 Patch Origin

Every patch MUST carry origin information.

This is necessary for:

* deterministic diagnostics,
* scope tracing,
* precedence inspection,
* tooling and explanation.

---

## 6. Patch Lifetimes

Every patch has exactly one lifetime.

## 6.1 Persistent Patch

A persistent patch begins at its declaration point and remains active until overridden.

Persistent patches are introduced by constructs such as `!#`.

Persistent patches affect subsequent source in lexical order.

They are not automatically reverted by region exit.

---

## 6.2 Scoped Patch

A scoped patch applies only within a lexical region.

Scoped patches are introduced by constructs such as `!@ ... !!@`, or by normalized region blocks.

Scoped patches are pushed when the region begins and popped when the region ends.

They do not survive scope exit.

---

## 6.3 Inline Patch

An inline patch applies only to one inline span.

Inline patches are introduced by MTX inline control such as:

```marktex id="shjahl"
[text](color: red, bold)
```

Inline patches do not affect surrounding text outside that span.

They are never promoted to ambient persistent or scoped state.

---

## 7. Precedence

The effective state at any point is determined by a fixed precedence order.

For any field, precedence is:

```text id="ez6mqs"
inline > scoped > persistent > default
```

This rule is normative.

### Meaning

* An inline patch overrides any scoped or persistent setting for the duration of its span.
* A scoped patch overrides any persistent setting inside its lexical region.
* A persistent patch overrides the document default from its declaration point onward.
* Defaults apply only where no explicit patch applies.

---

## 7.1 Same-Lifetime Resolution

If multiple patches of the same lifetime apply to the same field, the later one in lexical order or the inner one in scope order takes precedence, subject to the field’s merge law.

This yields:

* persistent: later overrides earlier,
* scoped: inner overrides outer,
* inline: inner span overrides outer span where nesting is legal.

---

## 7.2 Fieldwise Resolution

Precedence is applied per field, not per entire patch object.

Thus, if a persistent patch defines:

```text id="bpvh61"
margin.top = 20
```

and a scoped patch defines:

```text id="w4vcow"
margin.bottom = 10
```

then inside the scope the effective margin is a fieldwise combination, not a winner-takes-all object replacement, unless the schema explicitly defines the field as indivisible.

---

## 8. Merge Laws

Each state field MUST declare a merge law.

The core merge law classes are:

* `replace`
* `deep-merge`
* `append`
* `prepend`
* `union`
* `subtract`
* `slot-merge`
* `domain-specific`

A field without a declared merge law is ill-specified.

---

## 8.1 Replace

The later or higher-precedence value replaces the earlier one completely.

Typical examples:

* paper layout,
* orientation,
* column count,
* font size,
* alignment mode.

---

## 8.2 Deep-Merge

A structured field is merged by subfield.

Typical examples:

* margin records,
* page style records,
* some routing tables.

Deep-merge itself is schema-guided, not recursive-by-default.
Subfields must still have declared merge laws.

---

## 8.3 Append / Prepend

Ordered collections may use append or prepend semantics.

Typical examples:

* ordered style pipelines,
* hook lists,
* extension-provided processing chains.

These SHOULD be used sparingly in the core language.

---

## 8.4 Union / Subtract

Set-like resource collections use union and subtract.

Typical examples:

* bibliography resource sets,
* enabled feature sets,
* label visibility sets if adopted.

Example:

```text id="vbpj8n"
BIB + "extra.bib"
BIB - "legacy.bib"
```

These are not string operations; they are resource-set operations.

---

## 8.5 Slot-Merge

Named slot objects merge by slot.

Typical examples:

* header.left
* header.center
* header.right
* footer.left
* footer.center
* footer.right

A slot-merge affects only addressed slots.

---

## 8.6 Domain-Specific

Some fields require semantic merging not captured by generic laws.

Typical examples:

* western/eastern font routing,
* page numbering schemes with restart policy,
* counter policies,
* running-mark selection.

Domain-specific merge behavior MUST be explicitly documented per field.

---

## 9. Defaults

Every state partition has a default value.

Defaults may arise from:

* language-defined defaults,
* implementation defaults,
* document profile defaults,
* backend profile defaults,
* package-defined defaults, if package semantics are adopted.

Defaults are the lowest-precedence layer.

Defaults MUST be materializable in NIR or EIR.
They MUST NOT remain purely implicit backend behavior.

---

## 10. Persistent State Semantics

A persistent patch is activated at its lexical point of declaration.

Its effect begins immediately after declaration in source order.

It remains in effect until a later persistent patch or stronger lifetime overrides the same field.

Example:

```marktex id="9itjcr"
!# column: count: 2
```

All subsequent block flow is two-column unless:

* another persistent patch changes `column.count`,
* or a scoped patch temporarily overrides it.

Persistent state is not transactional and is not automatically unwound.

---

## 10.1 Persistent Order

Persistent patches form an ordered stream.

For each field, the effective persistent value at a source point is the result of folding all earlier persistent patches affecting that field under the field’s merge law.

Persistent state is therefore monotone in source position, though not necessarily monotone in value.

---

## 11. Scoped State Semantics

A scoped patch is activated upon entry to its region and deactivated upon exit.

This is lexical, not dynamic.

The effect of a scoped patch is visible only to content structurally inside the region.

Example:

```marktex id="twuina"
!@ column: count: 2
...
!!@ column
```

Inside the region:

* scoped `column.count = 2` is active,
* outer persistent `column.count` is shadowed,
* other unrelated fields remain inherited from outer effective state.

At scope exit, only the scoped layer is removed.
Persistent state remains unchanged.

---

## 11.1 Scope Stack

Scoped patches are maintained as a stack of active scope frames.

Each frame contains:

* scope key,
* patch,
* origin,
* optional metadata for tooling.

Effective scoped state is computed by folding active frames from outermost to innermost, then applying precedence.

---

## 11.2 Scope Matching and Unwinding

A close directive unwinds exactly one matching scope frame: the most recent active frame with that scope key.

Unwinding removes that frame and all of its active effect.

If an implementation permits structured region blocks directly in AST or IR, explicit close directives may be lowered away after normalization.

---

## 12. Inline State Semantics

An inline patch applies only to one inline subtree.

It does not mutate ambient state.

Conceptually, it produces a locally modified effective `TextState` and any other inline-legal fields for that subtree only.

Example:

```marktex id="dlwltm"
Hello [world](color: blue, bold).
```

Here:

* `color = blue` and `weight = bold` apply to `world`,
* the surrounding paragraph inherits ambient state unchanged.

---

## 12.1 Inline-Legal Fields

Not every field is valid as an inline patch.

Inline patches may affect only fields whose schema declares them inline-legal.

Typical inline-legal fields:

* font family,
* font size,
* weight,
* emphasis,
* color,
* decoration,
* some script-routing hints.

Typical non-inline-legal fields:

* page margins,
* columns,
* page layout,
* bibliography set,
* header/footer definitions.

A syntactically valid MOS object that targets non-inline-legal fields fails contextual validation in inline position.

---

## 13. Effective State Construction

At any semantic point, effective state is constructed by layered composition.

A conceptual formulation is:

```text id="u8tt8j"
EffectiveState(point) =
  apply_inline(
    apply_scoped(
      apply_persistent(
        defaults,
        persistent_patches_before(point)
      ),
      active_scoped_patches_at(point)
    ),
    active_inline_patches_at(point)
  )
```

This formulation is normative in meaning, though implementations may optimize it.

---

## 13.1 Block vs Inline Points

State may be queried at different semantic points:

* block entry,
* paragraph entry,
* inline run entry,
* region entry,
* backend runtime points for symbolic values.

An implementation MUST define each query point consistently.

PageState and FlowState are usually queried at block or region entry.
TextState is commonly queried at inline run entry.

---

## 14. Partition Validity by Lifetime

Not every partition is equally meaningful under every lifetime.

The schema MUST declare, per field or field family:

* whether the field is persistent-legal,
* whether the field is scoped-legal,
* whether the field is inline-legal.

Typical examples:

| Field        | Persistent |          Scoped | Inline |
| ------------ | ---------: | --------------: | -----: |
| layout       |        yes |      usually no |     no |
| margin.top   |        yes |    possibly yes |     no |
| column.count |        yes |             yes |     no |
| font.size    |        yes |             yes |    yes |
| color        |        yes |             yes |    yes |
| bib set      |        yes | yes, if allowed |     no |
| header.right |        yes |    possibly yes |     no |

If a patch targets a field in an illegal lifetime context, normalization or validation MUST reject it.

---

## 15. Symbolic State

Some state-dependent values cannot be concretized at NIR or EIR time.

These values are symbolic.

Typical examples:

* current page number,
* total page count,
* page parity,
* page of a labeled target,
* current running heading mark.

Symbolic values participate in expressions and state-bearing strings without immediate collapse.

---

## 15.1 Symbolic vs Concrete Fields

A field may be:

* concretely known during expansion,
* symbolically known but backend-resolved later,
* or invalid to access at a given phase.

Example:

* `TIME.year` is typically concrete during EIR.
* `PAGE.MAX` is symbolic until page resolution.
* an unresolved counter defined later may be symbolic or invalid depending on language policy.

---

## 15.2 Symbolic Expressions

When an expression mixes concrete and symbolic operands, the compiler MUST attempt symbolic preservation if the operation is representable.

Example:

```python id="mjlwm2"
PAGE.MAX - PAGE.N
```

should become a symbolic expression tree rather than a hard error, provided subtraction is supported symbolically for those object classes.

If symbolic preservation is not representable for an operation, the expression is a compile-time error.

---

## 15.3 Symbolic State in Page Furniture

Headers, footers, running marks, and some page-style fields commonly carry symbolic expressions.

This is expected.

Such fields MUST therefore accept symbolic content into EIR and TIR.

They MUST NOT require full concretization during normalization.

---

## 16. EvalState Interaction

EvalState is ambient during expansion but does not participate in rendering precedence in the same way as PageState, FlowState, TextState, or ResourceState.

EvalState is not layered into effective render state.
It is a host-side environment.

However, EvalState may produce patches or nodes that modify other partitions.

Thus, the correct rule is:

> EvalState influences compilation, not rendering directly.

---

## 16.1 EvalState Lifetime

EvalState is ordinarily persistent in lexical compilation order unless the language later introduces explicit local host scopes.

A value bound by:

```marktex id="e77x4i"
!$ x = 10
```

remains visible to later host evaluations unless shadowed by later host bindings or host-scope rules.

If local host scopes are later introduced, they must be specified separately and MUST NOT be conflated with document style scope unless explicitly designed so.

---

## 17. Region Entry and Exit

A region is entered when its scoped patch becomes active and exited when that patch is popped.

Entry and exit are semantic events, not mere parse events.

On entry:

1. validate scope applicability,
2. push scope frame,
3. recompute effective state lazily or eagerly.

On exit:

1. pop scope frame,
2. discard its scoped effect,
3. recompute effective state lazily or eagerly.

No persistent mutation occurs merely because a scope was entered.

---

## 18. Strings, Templates, and State-Carried Content

Some state fields carry textual or node-like content rather than scalar values.

Examples:

* header slots,
* footer slots,
* running marks,
* generated labels,
* captions.

Such fields may contain:

* plain strings,
* inline node sequences,
* symbolic expressions embedded in strings,
* backend-runtime placeholders after lowering.

The field schema MUST specify whether its payload is:

* plain text,
* formatted inline content,
* expression-capable text,
* or a full inline node sequence.

This is essential for deterministic lowering.

---

## 19. State Snapshots

Implementations MAY materialize snapshots of effective state for optimization, debugging, or tooling.

A state snapshot is a derived artifact, not a semantic source of truth.

The semantic truth remains:

* defaults,
* plus persistent patch stream,
* plus active scope stack,
* plus local inline patch context.

Snapshots MUST NOT alter semantics.

---

## 20. Conflict Semantics

A conflict occurs when two applicable patches assign incompatible meanings to the same field in the same effective context and the merge law does not define a legal result.

Conflicts are compile-time errors.

Typical examples:

* two mutually exclusive layout modes in one indivisible field,
* an inline patch attempting to assign a non-inline-legal page-layout field,
* incompatible resource operations in a field without a union/subtract law.

Conflict detection SHOULD occur as early as the necessary information becomes available.

---

## 21. Field Schema Requirements

Every state field in the language or an extension MUST declare at least:

1. partition,
2. value type,
3. allowed lifetimes,
4. merge law,
5. symbolic-allowed or not,
6. backend-lowering strategy class.

A field lacking any of these is not fully specified.

This requirement is the core mechanism by which MarkTeX remains extensible without becoming soft.

---

## 22. Worked Examples

## 22.1 Persistent then scoped then inline

Source:

```marktex id="j4v04s"
!# color: black
!@ color: blue
Hello [world](color: red).
!!@ color
```

Effective semantics:

* outside scope: `color = black`
* inside scope: `color = blue`
* on `world`: `color = red`

This follows:

```text id="dj09rb"
inline > scoped > persistent > default
```

---

## 22.2 Fieldwise merge

Source:

```marktex id="hbjlwm"
!# margin: top: 20, bottom: 20
!@ margin: top: 10
...
!!@ margin
```

Inside the scope, effective margin is:

```text id="0jgi1p"
top = 10
bottom = 20
```

assuming `margin` uses deep-merge by subfield.

---

## 22.3 Resource union and subtract

Source:

```marktex id="6d4jzu"
!# bib: "main.bib"
!# bib: [$ BIB + "extra.bib" ]
!# bib: [$ BIB - "legacy.bib" ]
```

Semantics:

* bibliography resources are treated as a typed set,
* `+` is union-addition,
* `-` is subtraction,
* the resulting persistent resource state is folded in lexical order.

---

## 22.4 Scoped columns over persistent columns

Source:

```marktex id="5ob1ub"
!# column: count: 1
!@ column: count: 2
...
!!@ column
```

Semantics:

* outer effective `column.count = 1`
* inside scope `column.count = 2`
* after scope exit `column.count = 1`

No mutation rollback is required because persistent state was never overwritten by the scoped layer.

---

## 22.5 Symbolic footer

Source:

```marktex id="n9jxsp"
!# footer: center: "[$ PAGE.N ] / [$ PAGE.MAX ]"
```

Semantics:

* footer content is valid persistent `PageState`,
* `PAGE.N` and `PAGE.MAX` remain symbolic through EIR,
* TIR lowers them to backend-resolved runtime placeholders.

---

## 23. Normalization Requirements

By the end of normalization:

1. all patches MUST be typed,
2. all patches MUST have a declared lifetime,
3. all fields referenced by patches MUST have schema entries,
4. all inline patches MUST have passed inline-position validation,
5. all active scope structure MUST be explicit in the IR.

Normalization MUST eliminate any ambiguity about where and how state changes.

---

## 24. Expansion Requirements

By the end of expansion:

1. compile-time host code MUST have executed or failed,
2. all host-produced patches MUST be schema-valid,
3. all remaining expressions MUST be either concrete or explicitly symbolic,
4. no unevaluated host statements may remain,
5. state semantics MUST remain phase-preserving.

Expansion may reduce state-bearing expressions, but MUST NOT silently alter patch precedence or merge laws.

---

## 25. Tooling Recommendations

Implementations SHOULD expose state diagnostics and introspection tools.

Recommended capabilities include:

* show effective state at source position,
* show active scope stack,
* explain why a field has its current value,
* show patch provenance chain,
* inspect symbolic vs concrete field status.

MarkTeX is powerful enough that state debugging is not optional in serious tooling.

---

## 26. Final Principle

MarkTeX state is deliberately rich, layered, and programmable.
Therefore its semantics must be more rigid, not less.

The language remains tractable only if three facts are always true:

1. every modification is typed,
2. every modification has a lifetime,
3. every effective value is derivable by explicit precedence and merge laws.

That is the semantic backbone of the language.
