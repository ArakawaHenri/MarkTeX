# MarkTeX v0.1

## Surface Syntax Specification

## 1. Scope

This document defines the **surface syntax** of MarkTeX source files (`.mtx`).

It specifies:

* lexical and line-level structure,
* directive forms,
* MOS source grammar,
* inline constructs,
* block constructs,
* Markdown fallback behavior,
* and ambiguity resolution rules at the source level.

This document defines the author-facing syntax only.
Its semantic meaning is given by the Core IR specification.

---

## 2. Source Philosophy

MarkTeX source syntax follows four principles:

1. **Markdown-first appearance**
   The source should remain readable as prose.

2. **Compiler-first interpretation**
   Surface forms are resolved by formal rules, not by informal visual intuition.

3. **Unified object notation**
   MOS is the canonical surface notation for structured control payloads.

4. **Fallback by failure, not by guessing**
   When a MarkTeX-specific interpretation fails, the construct falls back in a rule-governed way.

5. **Literal islands stay literal**
   Some regions are intentionally non-prose. Inside them, only explicitly enabled sublanguage forms remain active.

---

## 3. File Model

A `.mtx` file is a Unicode text file.

The canonical source encoding is UTF-8.

A source file is parsed as a sequence of lines, then grouped into blocks and inline structures.

Line ending normalization is implementation-defined, but all standard newline conventions MUST be accepted.

---

## 4. Lexical Elements

## 4.1 Whitespace

Whitespace is significant only where explicitly stated.

Outside code spans, code blocks, raw blocks, and string literals:

* spaces and tabs may separate tokens,
* multiple spaces are not semantically distinguished unless preserved by Markdown rules,
* newlines participate in block formation.

---

## 4.2 Comments

A line whose first non-whitespace token is:

```text
--
```

is a comment line.

Comment lines are ignored by the semantic parser.

Example:

```marktex
-- this is a comment
!# margin: top: 20
```

A comment line is not a paragraph line.

Inline comments are not defined by the core syntax.

---

## 4.3 Identifiers

An identifier is a non-empty sequence beginning with a letter or underscore, followed by letters, digits, underscores, or hyphens unless the local grammar forbids hyphens.

Implementations MAY internally distinguish:

* bare identifiers,
* qualified identifiers,
* namespaced identifiers.

Examples:

```text
layout
margin
column
font_size
chem-reaction
pkg.name
```

The exact acceptance of `.` in identifiers is context-sensitive.
In MOS key position, qualified names are allowed.
In Python-hosted expressions, Python syntax governs.

---

## 4.4 Literals

The surface language recognizes at least the following literal classes:

* string literals,
* numeric literals,
* dimension literals,
* boolean literals,
* null-like literals if adopted by the implementation,
* tag literals.

### String literals

A string literal is enclosed by single or double quotes.

Examples:

```text
"Times New Roman"
'hello'
```

### Numeric literals

A numeric literal is a decimal integer or float.

Examples:

```text
12
10.5
0.75
```

### Dimension literals

A dimension literal is a numeric magnitude followed by a unit recognized by the implementation profile.

Examples:

```text
12pt
10mm
0.8em
```

Dimension literals are scalar atoms.
They are not tags.
Schemas may bind them positionally or by explicit keyed fields.

### Tag literals

A tag literal is an unkeyed atom in MOS.

A tag is not merely bare data.
It is a schema-recognized modifier with no explicit value.

Schemas may classify accepted inputs using parameter-binding classes analogous to:

* positional-only parameters,
* keyword-only parameters,
* and dual-use parameters.

A tag commonly denotes a zero-value application of a keyword-only or dual-use parameter that permits omission of an explicit value.

Useful tag families include:

* **preset tags** such as `A4`, `A5`, `Letter`, `Legal`
* **transform tags** such as `landscape`, `portrait`
* **enum/style tags** such as `bold`, `italic`, `justify`, `contain`

Tag validity is schema-local.
A tag accepted under one root may be meaningless or invalid under another.

Transform tags may depend on a previously established preset or compatible base object.
For example, in the core layout schema, `landscape` and `portrait` are valid only when a paper preset such as `A4` is active.

Examples:

```text
bold
landscape
A4
```

Tags are semantically interpreted only by schema-bound object constructors.

---

## 5. Top-Level Line Classes

At the surface level, each non-comment line begins in exactly one of the following classes:

1. **Directive line**
2. **Markdown block line**
3. **Blank line**
4. **Fenced block line**
5. **Raw block line**, if supported by the implementation profile

A directive line begins with one of:

```text
!#
!@
!!@
!$
```

A line is recognized as a directive line only if, after stripping outer whitespace, the entire remaining line is exactly one directive form.
Directive introducers do not take effect in the middle of ordinary paragraph content.

All other non-comment lines are initially eligible for Markdown block parsing.

---

## 6. Directive Forms

MarkTeX defines four directive families.

## 6.1 Persistent Directive

```text
!# <mos>
```

This introduces a **persistent patch**.

It mutates persistent document state from its point of occurrence onward until overridden.

Its payload is an ordered declaration list.
Top-level entries are applied from left to right.

Examples:

```marktex
!# layout: A4, landscape; margin: 10.5
!# margin: top: 20
!# bib: "main.bib"
```

---

## 6.2 Scoped Directive Open

```text
!@ <mos>
```

This begins one or more **scoped regions**.

Its payload defines one or more scoped declarations to be applied to subsequent source until matching closes are encountered.

The payload is parsed as MOS.
Each top-level entry in the MOS payload is treated as an independent scoped declaration after any grouped subexpressions are reduced.

Thus:

```marktex
!@ e: font: "SimSun"; w: font: "Times New Roman"; emphasis
```

is semantically equivalent to:

```marktex
!@ e: font: "SimSun"
!@ w: font: "Times New Roman"
!@ emphasis
```

This equivalence is normative.
The single-line form is only syntactic compression.

Examples:

```marktex
!@ column: count: 2, gap: 5
!@ w: font: "Times New Roman", size: 12pt; e: font: "SimSun", size: 12pt
```

---

## 6.3 Scoped Directive Close

```text
!!@ <scope-target>
```

This closes a previously opened scoped region.

A close target is not MOS.
It is a scope selector.

Examples:

```marktex
!!@ column
!!@ w
!!@ e
```

### Close Rule

The close target MUST match an active open scope according to the scope matching rules defined below.

A mismatched close is a syntax error.

---

## 6.4 Evaluation Directive

```text
!$ <python-code>
```

This introduces compile-time host code.

`!$` is line-introduced source code, not MOS.

Its body continues according to the implementation profile:

* single-line form MUST be supported,
* indented or fenced multi-line form MAY be supported by a later profile,
* the core surface grammar leaves multi-line statement blocks as an extension point.

Example:

```marktex
!$ x = 10
!$ add_bib("extra.bib")
```

---

## 7. Scoped Declaration Expansion and Matching

A scoped directive open introduces one or more lexical scopes.

For `!@ <mos>`, the compiler first parses the full MOS payload.
It then expands the payload into a left-to-right list of independent scoped declarations, one per top-level entry.

Example:

```marktex
!@ column: count: 2; image: width: 0.8; emphasis
```

is semantically equivalent to:

```marktex
!@ column: count: 2
!@ image: width: 0.8
!@ emphasis
```

This expansion happens before scope matching.

### Scope Key

Each expanded declaration opens one scope frame.
Its scope key is derived from that declaration's normalized root object kind.

Examples:

```marktex
!@ column: count: 2
```

opens scope key `column`.

```marktex
!@ w: font: "Times New Roman"
```

opens scope key `w`.

```marktex
!@ emphasis
```

opens scope key `emphasis`.

Syntactically, all `!@` roots use the same declaration language.
Semantically, schema classifies a root as a style family, an object-style family, a layout family, or another scope family.
If a root is not defined by the core schema, it is treated as a custom scope name and validated by extension or custom-scope rules.

### Matching Rule

`!!@ name` closes the most recent active scope frame whose scope key is `name`.

Matching is performed against the active scope stack by key.
The frame removed is the most recent active frame whose key matches the close target.

If no such scope exists, the source is ill-formed.

### Atomicity Rule

An open directive is atomic.
If any top-level scoped declaration in one `!@` line is invalid, the entire directive fails and no scope from that line is opened.

### Recommendation

Implementations SHOULD diagnose:

* unmatched closes,
* leaked scopes at end of file,
* suspicious cross-nesting.

---

## 8. MOS

MOS is the canonical structured payload language of MarkTeX surface syntax.

Its grammar is linear and separator-driven.

MOS source is parsed into typed object trees.
It is not a free-form map syntax.

---

## 8.1 MOS Design Roles

MOS is used in:

* `!# <mos>`
* `!@ <mos>`
* `[content](<mos>)`
* `![alt](<mos>)`
* `[^ <mos>]` in reference-definition or reference-control position
* any future schema-bound control payload position

MOS is not used for:

* `!$`
* `[$ ... ]`
* ordinary Markdown link destinations
* scope close targets

---

## 8.2 MOS Core Grammar

The following grammar is schematic and normative in structure, though implementations may refine token detail.

```ebnf
MOS          ::= TopList

TopList      ::= TopItem ( ";" TopItem )*

TopItem      ::= Entry | Group

Entry        ::= Keyed | Tag

Keyed        ::= Key ":" ValueList

ValueList    ::= ValueItem ( "," ValueItem )*

ValueItem    ::= Entry | Group | Atom

Group        ::= "(" TopList ")"

Tag          ::= Identifier

Key          ::= Identifier

Atom         ::= String
               | Number
               | Dimension
               | Identifier
               | ExprEmbed

Dimension    ::= Number Unit
```

### Informal Meaning

* `:` descends structurally,
* `,` separates sibling values within the same keyed entry,
* `;` separates top-level entries,
* `()` creates an explicit grouped subobject,
* an unkeyed identifier may be a tag,
* other unkeyed atoms remain ordinary scalar atoms whose binding is schema-defined.

---

## 8.3 MOS Modifier Semantics

MOS is interpreted as an **ordered modifier stream**, not as an unordered map.

The evaluation law is:

* grouped subexpressions are normalized first,
* then modifiers at the same level are applied from left to right,
* later modifiers may override earlier effects according to schema.

This rule applies both:

* inside a `ValueList`,
* and across top-level declaration lists separated by `;`.

Thus:

```marktex
!@ k1: v1; k2: v2; tag1
```

is semantically equivalent to:

```marktex
!@ k1: v1
!@ k2: v2
!@ tag1
```

Likewise:

```marktex
layout: A4, width: 100, landscape
```

means:

1. apply `A4`,
2. then apply `width: 100`,
3. then apply `landscape`.

Tags therefore participate in the same ordered semantics as keyed modifiers.
Their concrete effect is schema-defined.

Dimension literals remain ordinary scalar atoms in the modifier stream.
They may be bound positionally by schema, but they are not tags.

---

## 8.4 MOS Examples

```marktex
layout: A4, landscape
margin: top: 20, bottom: 15
header: left: "Draft", right: "[$ PAGE.N ] / [$ PAGE.MAX ]"
w: font: "Times New Roman", size: 12pt
```

Grouped example:

```marktex
header: (left: "A"; right: "B")
```

---

## 8.5 MOS Canonical Reading

The source:

```text
margin: top: 20, bottom: 10
```

is read as:

* top-level entry `margin`
* whose value list contains:

  * keyed entry `top: 20`
  * keyed entry `bottom: 10`

The source:

```text
layout: A4, landscape; margin: 10
```

is read as two top-level entries:

* `layout: A4, landscape`
* `margin: 10`

The source:

```text
layout: A4, width: 100
```

is read as one top-level entry `layout` whose modifier list is applied serially:

* first `A4`
* then `width: 100`

If the schema defines `A4` to imply `width = 210` and `height = 297`, the later `width: 100` overrides only width while height remains `297`.

The source:

```text
layout: A4, width: 100, landscape
```

is read as one ordered modifier stream in which:

* `A4` establishes the paper preset,
* `width: 100` establishes an explicit width override,
* `landscape` transforms only the preset-derived orientation and dimensions.

In the core layout schema, this yields:

* `orientation = landscape`
* `width = 100`
* `height = 210`

assuming `A4` contributes the portrait dimensions `210 × 297`.
The explicit width remains explicit; `landscape` rotates only the preset-derived component.

---

## 8.6 MOS Atoms and Embedded Expressions

MOS may contain embedded expression atoms through `[$ ... ]` where the local schema permits it.

Example:

```marktex
!# footer: center: "Page [$ PAGE.N ]"
```

An embedded expression atom is not evaluated during MOS parsing.
It is preserved into the IR as an expression-bearing atom.

---

## 8.7 MOS Validation

Parsing and validation are distinct.

A MOS payload is valid in context only if:

1. it parses syntactically,
2. ordered modifier binding succeeds for the relevant schema,
3. its normalized root object kind is allowed in that syntactic position,
4. schema validation succeeds.

Thus, syntactic MOS success alone does not guarantee semantic acceptance.

---

## 9. Markdown Blocks

All non-directive, non-comment text is initially parsed under Markdown block rules.

The implementation profile MUST support at least:

* paragraphs,
* ATX headings,
* block quotes,
* fenced code blocks,
* ordered and unordered lists,
* thematic breaks if adopted by the Markdown profile.

MarkTeX does not redefine ordinary Markdown block parsing unless a construct is explicitly recognized as MTX syntax.

---

## 9.1 Fenced Code Blocks

Fenced code blocks are part of the core surface profile.

An ordinary fenced code block is a **literal region**.
Inside an ordinary code fence, MarkTeX syntax is disabled.

In particular, the fence body does not parse:

* `!#`, `!@`, `!!@`, `!$`
* `[$ ... ]`
* `[content](payload)`
* `![alt](payload)`
* `[^ ... ]`
* `$ ... $` or `$$ ... $$`

Only fence delimiters and the fence info string are interpreted structurally.
The body itself is preserved as literal code text.

Inline code spans are governed by the same literal-region law.

---

## 9.2 Interpolated Fenced Code Blocks

A fenced code block whose info string contains the reserved flag `interp` is an **interpolated literal region**.

The following forms are both valid:

````marktex
```interp
...
```
````

````marktex
```python interp
...
```
````

The `interp` flag enables `[$ ... ]` inside the fence body.
All other MarkTeX and Markdown syntax remains disabled.

Thus an interpolated code fence is still fundamentally literal text, but with expression holes.

The content of `[$ ... ]` inside such a fence uses the same Python-host expression grammar and evaluation model as ordinary inline expressions.

---

## 9.3 Display Math Blocks

MarkTeX recognizes display math using `$$ ... $$`.

Display math is a **delegated opaque region**:

* the outer math delimiters are recognized by MarkTeX,
* the inner payload is preserved as math content,
* ordinary Markdown and MarkTeX inline parsing do not reinterpret the interior.

The compiler is responsible only for correct delimiter matching, source-span preservation, and backend lowering of the resulting math node.

---

## 10. Inline Syntax

Within Markdown-derived text containers, MarkTeX recognizes additional inline constructs.

The core inline constructs are:

* inline expression: `[$ ... ]`
* inline math: `$ ... $`
* bracket-call: `[content](payload)`
* image-call: `![alt](payload)`
* bracket-ref: `[^ ... ]`

Everything else is initially parsed under Markdown inline rules.

---

## 10.1 Inline Expression

```text
[$ <python-expression> ]
```

This introduces an inline evaluable expression.

Examples:

```marktex
Today is [$ TIME.strftime("%Y-%m-%d") ].
[$ PAGE.N ] / [$ PAGE.MAX ]
```

### Parsing Rule

The content of `[$ ... ]` is parsed as a Python-host expression payload, not as MOS.

Nested bracket balancing for expression payloads MUST be handled by the expression parser, not by naive textual splitting.

---

## 10.2 Inline Math

```text
$ <math-payload> $
```

Inline math is a delegated opaque region.

Its payload is preserved as math content for later lowering.
It is not parsed as MOS, Python-host expression syntax, or ordinary Markdown inline structure.

MarkTeX is responsible for matching the outer delimiters and preserving origin.
The interior remains backend-oriented math payload.

---

## 10.3 Bracket-Call

```text
[<content>](<payload>)
```

This is the principal overloaded inline surface form.

It is resolved either as:

* MTX inline control,
* or Markdown inline structure.

Its formal resolution rule is given in Section 13.

Examples:

```marktex
[hello](color: blue, bold)
[OpenAI](https://openai.com)
```

The first is intended as MTX inline control.
The second is intended as Markdown link fallback.

---

## 10.4 Image-Call

```text
![<alt>](<payload>)
```

This is the principal overloaded image surface form.

It is resolved either as:

* MTX rich image control,
* or Markdown image structure.

Its formal resolution rule is given in Section 13.4.

Examples:

```marktex
![logo](logo.svg)
![arch](src: "figures/arch.pdf", width: 0.7)
```

The first is intended as Markdown image fallback.
The second is intended as MTX rich image control.

---

## 10.5 Bracket-Ref

```text
[^ <payload> ]
```

This introduces a reference-oriented form.

Its precise interpretation depends on payload class.

The core source-level classes are:

1. **Reference definition**
2. **Reference citation**
3. **Reference control object**

Examples:

```marktex
[^ Nobody06]
[^ id: Nobody06; pages: 12-15 ]
[^ @article{Nobody06, author: "Nobody Jr", title: "My Article", year: "2006"} ]
```

The exact reference object taxonomy belongs to the bibliography/resource specification, but the surface parser MUST preserve these as distinct reference forms.

---

## 11. Paragraph Formation

Paragraph formation follows Markdown-like rules.

A paragraph is formed from one or more consecutive non-blank lines that are not consumed as:

* directives,
* code fences,
* display math blocks,
* headings,
* list items,
* block quotes,
* or other recognized block starters.

Inline MarkTeX constructs inside paragraphs do not affect paragraph formation.

---

## 12. Directive/Markdown Boundary

Directive recognition occurs before Markdown block parsing.

If, after stripping outer whitespace, a line consists of exactly one directive form beginning with `!#`, `!@`, `!!@`, or `!$`, it is a directive line, not a paragraph line.

This rule is lexical, not semantic.

Therefore:

```marktex
!# margin: top: 20
```

cannot be treated as ordinary paragraph text unless escaped by an implementation-defined escape mechanism.

---

## 13. Call Resolution

This section is normative.

Any source construct of the form:

```text
[content](payload)
```

is parsed first as an abstract `BracketCall`.

It is then resolved by the following two-stage rule.

---

## 13.1 Stage A: Attempt MTX Interpretation

The `payload` is parsed as MOS.

The construct is resolved as MTX inline control iff all of the following hold:

1. the payload parses as syntactically valid MOS,
2. parsing consumes the payload completely,
3. the resulting root object is valid in inline-style position,
4. schema validation succeeds.

If so, the construct becomes an MTX inline control node.

Example:

```marktex
[world](color: blue, bold)
```

---

## 13.2 Stage B: Markdown Fallback

If Stage A fails, the entire bracket-call falls back to Markdown interpretation.

Fallback is whole-node.

There is no mixed partial interpretation.

Thus:

```marktex
[OpenAI](https://openai.com)
```

is not “almost MOS”; it is simply a Markdown link.

---

## 13.3 Consequence

MarkTeX does not attempt to reserve `[]()` exclusively.

Instead, it establishes a strict priority:

1. MTX interpretation by full MOS success,
2. otherwise Markdown.

This is deliberate and fundamental.

---

## 13.4 Image-Call Resolution

This section is normative.

Any source construct of the form:

```text
![alt](payload)
```

is parsed first as an abstract `ImageCall`.

It is then resolved by the following two-stage rule.

### Stage A: Attempt MTX Rich-Image Interpretation

The `payload` is parsed as MOS.

The construct is resolved as MTX rich image control iff all of the following hold:

1. the payload parses as syntactically valid MOS,
2. parsing consumes the payload completely,
3. the resulting root object is valid in image-call position,
4. schema validation succeeds.

If so, the construct becomes an MTX image node carrying the source, local image patch, or both according to the image schema.

Example:

```marktex
![arch](src: "figures/arch.pdf", width: 0.7)
```

### Stage B: Markdown Fallback

If Stage A fails, the entire image-call falls back to Markdown image interpretation.

Fallback is whole-node.

Thus:

```marktex
![logo](logo.svg)
```

is simply a Markdown image if `logo.svg` does not form a valid MTX image payload.

---

## 14. Reference Payload Classification

`[^ ... ]` payloads are classified by leading form.

The classifier is surface-level and deterministic.

## 14.1 Citation Form

If the payload is a simple reference key or schema-valid citation object, it is parsed as a citation.

Examples:

```marktex
[^ Nobody06]
[^ id: Nobody06; pages: 12-15 ]
```

## 14.2 Definition Form

If the payload begins with a bibliography-entry introducer such as `@article`, `@book`, or another registered bibliography declaration marker, it is parsed as a reference definition.

Example:

```marktex
[^ @article{Nobody06, author: "Nobody Jr", title: "My Article", year: "2006"} ]
```

## 14.3 Control/Object Form

If the payload parses as a schema-valid reference object but is neither a simple citation nor a bibliography entry declaration, it is preserved as a reference-control form.

The resource specification defines its meaning.

---

## 15. Embedded Expressions in Text and MOS

MarkTeX permits `[$ ... ]` both:

* directly in inline content,
* and inside string-bearing or expression-bearing MOS payload positions.
* and inside interpolated fenced code blocks whose info string contains `interp`.

These are distinct source locations but identical expression surface syntax.

Example:

```marktex
!# header: right: "[$ PAGE.N ] / [$ PAGE.MAX ]"
```

The embedded expression remains an expression node through normalization.

String interpolation behavior is defined by the string/object schema, not by the inline parser alone.
Interpolated code fences follow the same expression grammar, but their surrounding region remains literal text rather than ordinary prose.

---

## 16. Nesting Rules

## 16.1 Inline Nesting

Bracket-call content may itself contain inline constructs.

Example:

```marktex
[Nested [text](bold)](color: red)
```

The inner inline node is parsed before or as part of the outer content parse according to the implementation’s inline parser strategy, but the resulting tree MUST be structurally well-formed.

## 16.2 MOS Group Nesting

MOS grouping uses `()`.

Example:

```marktex
header: (left: "A"; right: "B")
```

Parentheses inside string literals or expression payloads do not affect MOS grouping.

## 16.3 Expression Nesting

`[$ ... ]` content is governed by expression parsing, not by MOS separator rules.

---

## 17. Error Classes

Surface syntax errors include:

* malformed directive introducer,
* invalid MOS syntax,
* modifier-binding failure such as a transform tag without its required preset,
* invalid scope close,
* unclosed scope at end of file,
* malformed fence structure,
* malformed inline expression delimiter,
* malformed math delimiter structure,
* malformed bracket-call outer structure,
* malformed image-call outer structure,
* malformed reference payload,
* context-invalid but syntactically valid MTX payload.

Implementations SHOULD distinguish:

* syntax errors,
* contextual validity errors,
* fallback-triggered non-errors,
* host-expression parse errors.

---

## 18. Recommended Diagnostics

Diagnostics SHOULD be phrased in source-level terms.

Examples:

* “`!!@ column` closes no active `column` scope”
* “payload parses as MOS, but not as an inline patch”
* “`landscape` requires an active paper preset such as `A4` in this layout object”
* “this `[]()` form falls back to Markdown because MOS parsing failed at `https:`”
* “this `![...](...)` form falls back to Markdown image because the payload is not a valid image object”
* “`interp` fences enable `[$ ... ]`, but other MarkTeX syntax remains literal here”
* “`[$ ... ]` contains invalid Python expression syntax”

Good diagnostics are essential because MarkTeX deliberately overloads familiar surface forms.

---

## 19. Canonical Formatting Recommendations

The following are style recommendations, not grammar rules.

### 19.1 Persistent patches

Prefer one logical patch per line:

```marktex
!# layout: A4, landscape; margin: 10.5
```

### 19.2 Scoped patches

Prefer visible paired open/close:

```marktex
!@ column: count: 2, gap: 5
...
!!@ column
```

If several scopes are opened on one line, prefer making that compression visually obvious:

```marktex
!@ e: font: "SimSun"; w: font: "Times New Roman"
```

### 19.3 Inline control

Prefer MTX inline payloads that are visually unmistakable as style/control payloads.

### 19.4 Grouping

Use explicit `()` in MOS when nesting depth would otherwise be visually ambiguous.

### 19.5 Interpolated fences

Reserve `interp` fences for literal templates that truly need expression holes:

````marktex
```python interp
answer = [$ VALUE ]
```
````

---

## 20. Minimal Surface Examples

## 20.1 Persistent patch

```marktex
!# layout: A4, landscape; margin: top: 20, bottom: 15
```

## 20.2 Scoped region

```marktex
!@ column: count: 2, gap: 5

This text is in two columns.

!!@ column
```

## 20.3 Multi-declaration scoped open

```marktex
!@ e: font: "SimSun"; w: font: "Times New Roman"
```

is equivalent to:

```marktex
!@ e: font: "SimSun"
!@ w: font: "Times New Roman"
```

## 20.4 Inline control vs Markdown fallback

```marktex
[world](color: blue, bold)
[OpenAI](https://openai.com)
```

## 20.5 Rich image vs Markdown fallback

```marktex
![logo](logo.svg)
![arch](src: "figures/arch.pdf", width: 0.7)
```

## 20.6 Inline expression

```marktex
Page [$ PAGE.N ] of [$ PAGE.MAX ].
```

## 20.7 Math

```marktex
Euler wrote $e^{i\pi} + 1 = 0$.

$$
\int_0^1 x^2 \, dx
$$
```

## 20.8 Interpolated fence

````marktex
```python interp
today = "[$ TIME.strftime(\"%Y-%m-%d\") ]"
```
````

## 20.9 Reference forms

```marktex
[^ Nobody06]
[^ id: Nobody06; pages: 12-15 ]
[^ @article{Nobody06, author: "Nobody Jr", title: "My Article", year: "2006"} ]
```

---

## 21. Surface Invariants

The following are normative surface-level invariants.

1. Directive lines are recognized before Markdown block parsing.
2. `!#` and `!@` payloads are MOS.
3. Directive introducers take effect only when a stripped line is exactly one directive form.
4. In `!@ <mos>`, top-level entries expand left-to-right into the same scoped declaration stream as separate `!@` lines.
5. Tags are zero-value schema modifiers, not mere loose atoms.
6. Dimension literals are scalar atoms, not tags.
7. Transform tags may declare schema prerequisites, such as a required preset basis.
8. `!!@` payloads are scope selectors, not MOS.
9. `!$` payloads are Python-host code, not MOS.
10. `[$ ... ]` is expression syntax, not MOS.
11. `[content](payload)` is first parsed as a generic bracket-call.
12. Bracket-call resolution prefers MTX iff full MOS and contextual validation succeed.
13. `![alt](payload)` is first parsed as a generic image-call.
14. Image-call resolution prefers MTX iff full MOS and contextual validation succeed.
15. Otherwise bracket-call and image-call each fall back entirely to Markdown.
16. Ordinary fenced code blocks are literal regions.
17. Fenced code blocks whose info string contains `interp` enable only `[$ ... ]` in the fence body.
18. `$ ... $` and `$$ ... $$` are delegated math regions, not MOS or Python-host syntax.
19. MOS parsing and MOS validation are separate phases.
20. Surface syntax is allowed to be expressive; semantic rigidity begins at normalization.

---

## 22. Final Principle

The surface syntax of MarkTeX is intentionally inherited, overloaded, and compact.

Its job is not to be semantically self-sufficient.
Its job is to serve as a disciplined front-end language whose ambiguity is resolved by explicit compiler rules.

In MarkTeX, readability is desirable, but **resolvability is mandatory**.
