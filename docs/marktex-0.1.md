# MarkTeX 0.1 Documentation

This is the single normative documentation entry for the current repository.
The root `README.md` is only a landing page. Older root-level design notes were
folded into this document and should not be used as implementation authority.

MarkTeX 0.1 is a publishable Python package milestone, not the complete
language 1.0. It provides the `marktex` package and the `mtxc` command. The
compiler reads explicit pipeline-stage inputs and emits LuaLaTeX-oriented
`.tex` files plus optional self-contained stage artifacts. It does not run
LuaLaTeX and it does not build PDFs.
LuaLaTeX is the current backend, not the definition of MarkTeX. The language
contract is the MarkTeX surface syntax, MOS, canonical core objects, and state
model; a backend is one possible lowering target.

## 1. Design Laws

1. MarkTeX owns its surface language. It includes Markdown-inspired spellings,
   but those spellings are MarkTeX syntax, not delegated Markdown
   compatibility.
2. `.mtx` is a script-shaped document. With host execution enabled, source
   files are trusted code.
3. MOS, the MarkTeX Object Syntax, is the smallest call syntax needed to build
   MarkTeX objects.
4. A MOS head is a call head. It is not a tag, not a type marker, and not
   necessarily a host function name.
5. MOS values are raw strings unless MOS explicitly creates structure.
6. The host runtime constructs MarkTeX objects, invoke events, and symbolic
   values. It is not the LaTeX backend.
7. The backend receives canonical document objects and emits target text. It
   never reparses `.mtx` source and never executes host code.
8. LuaLaTeX is the first 0.1 target, not the language's identity. Future
   targets such as Typst or Microsoft Office XML should lower the same
   canonical MarkTeX document model, just as Rust is not defined by LLVM or
   libc even though it commonly targets them.
9. Add, remove, or rename shorthand behavior through schema data. Do not modify
   parser logic for tag-like surface changes.

The central call model is:

```text
CallUnit(context, head, args, kwargs, origin)
lower(context, head, args, kwargs) -> MarkTeXObject
```

In an ordinary context, `font: Times` may lower to a host package call. In a
scope context, `!@ w: font=Times` lowers to a scope event with key `w`; `w` is
not a global function.

## 2. Conformance Table

| Area | 0.1 status |
| --- | --- |
| Python package `marktex` | Supported |
| CLI `mtxc` | Supported |
| Default target artifact | Supported: `.tex` for `lualatex` |
| Target `lualatex` | Only accepted target |
| PDF generation | Out of scope |
| `--from mtx\|surface\|host\|ast\|eir\|backend-ir` | Supported: default `mtx`, no extension inference |
| `--emit surface\|host\|ast\|eir\|backend-ir\|target\|all` | Supported |
| `--diagnostic-format text\|json` | Supported |
| `--no-host` | Supported restricted mode |
| MOS raw strings, frames, tuples, escapes, raw literals | Supported |
| Schema-driven value shading | Supported |
| `!#` document/page directives | Supported: backend lowers layout, margins, and body page setup |
| `!@` and `!!@` scope events | Supported in state/EIR |
| Python `$$$` host blocks | Supported for trusted input |
| Inline `[$ ... ]` expressions | Supported |
| Inline `$...$` math | Supported as MarkTeX inline syntax |
| Display `$$` math blocks | Supported as MarkTeX block syntax |
| `PAGE.CURRENT` and `PAGE.TOTAL` placeholders | Supported inline and in `$` code fences |
| Complex symbolic inline expressions | Diagnostic in LuaLaTeX backend |
| Headings and paragraphs | Supported |
| Markdown-inspired MarkTeX fallback syntax | Supported practical subset |
| Ordinary and `$`-interpolated code fences | Supported subset |
| Rich `+++` tables | Supported |
| Pipe tables with familiar pipe spelling | Supported fallback syntax |
| Footnotes | Supported single-line definitions |
| Explicit citation references | Supported through citation styles |
| Bibliography backend | Supported BibTeX subset with `.mtxcs`/`.mtxbs` styles |
| Conditionals | Concrete bool and `PAGE.CURRENT == PAGE.TOTAL` supported |
| Direct Markdown dialect compatibility | Out of scope: autolink and raw HTML semantics are not supported |

## 3. Package And CLI

Install from the repository:

```bash
uv tool install .
```

Run from source without installation:

```bash
uv sync --extra dev
uv run mtxc examples/hello.mtx
```

This repository uses `uv` as its only Python package manager. Project workflows
must use `uv sync`, `uv run`, and `uv build`; do not introduce parallel
pip/build/venv instructions.

The installed command is:

```bash
mtxc input.mtx
```

Default behavior:

```text
mtxc paper.mtx -> paper.tex
```

Common forms:

```bash
mtxc paper.mtx -o output.tex
mtxc paper.mtx -o -
mtxc paper.mtx --target lualatex
mtxc paper.mtx --emit surface --emit ast --emit eir --emit target --out-dir build/
mtxc paper.mtx --emit all
mtxc --from host build/paper.host.py --emit ast --emit target --out-dir build2/
mtxc --from ast build/paper.ast.json --emit backend-ir --emit target
mtxc --from backend-ir build/paper.backend-ir.json --emit target
mtxc paper.mtx --no-host
mtxc paper.mtx --diagnostic-format json
```

`-o -` writes a single text artifact to stdout. It is invalid with multiple
artifacts. `--emit pdf` is invalid because `mtxc` is not a PDF build driver.
Any target other than `lualatex` is invalid in 0.1. CLI finite options are
trimmed before enum validation. `--from` is a required semantic label when input
is not `.mtx`; `mtxc` does not infer a stage from the file extension. For
example, `--from ast paper.backend-ir.json` fails because the artifact envelope
kind is `backend-ir`, not `ast`.

Artifact names are deterministic. For the `lualatex` target, the target
artifact uses `.tex`:

```text
paper.surface.json
paper.host.py
paper.ast.json
paper.eir.json
paper.backend-ir.json
paper.tex
```

When multiple artifacts are requested without `--out-dir`, `mtxc` writes them
to `<stem>.mtxbuild/`.

Public driver API:

```python
from pathlib import Path
from marktex.driver import ArtifactKind, InputStage, compile_file

compile_file(
    Path("paper.mtx"),
    emits={ArtifactKind.TARGET},
    output_path=None,
    out_dir=None,
    target="lualatex",
    from_stage=InputStage.MTX,
    no_host=False,
)
```

## 4. Compiler Pipeline

The 0.1 architecture is an explicit, forward-only compiler pipeline:

```text
.mtx source
-> surface artifact
-> host.py construction artifact
-> canonical AST artifact
-> EIR artifact
-> backend IR artifact
-> target artifact
```

Every JSON artifact has the same envelope:

```text
{
  "kind": "surface|ast|eir|backend-ir",
  "marktex_version": "...",
  "artifact_version": 1,
  "payload": { ... }
}
```

The `surface` artifact contains recognized MarkTeX surface nodes, source spans,
and the original source text needed for accurate inline lowering. The `host.py`
artifact is an executable construction script; from `.mtx` input, the compiler
generates this script and executes it to obtain the canonical `Document`. It is
trusted Python, and `--from host` is therefore equivalent to executing that
artifact. `--from host --no-host` is invalid.

The `ast` artifact stores the canonical `Document`. The `eir` artifact stores
that document plus state log/scope state. The `backend-ir` artifact stores the
target, lowered document snapshot, and bibliography/style snapshot; target
emission from backend IR does not read the original `.mtx`, `.bib`, `.mtxcs`,
or `.mtxbs` files.

The only implemented 0.1 target is LuaLaTeX, but the boundary is intentionally
backend-shaped: a future Typst backend, Office Open XML backend, or other
renderer should consume the canonical document objects rather than redefining
the source language.

Implementation modules:

```text
src/marktex/cli.py                 CLI
src/marktex/driver/                compile_file and artifact writing
src/marktex/surface/               line-oriented surface parser
src/marktex/mos/                   schema-agnostic MOS parser
src/marktex/schema/                built-in call specs and shorthand data
src/marktex/core/                  immutable document objects
src/marktex/state/                 invoke log and scope stack
src/marktex/host/python/           Python host profile and symbolic values
src/marktex/bibliography/          BibTeX parsing and citation style loading
src/marktex/backend/lualatex/      LuaLaTeX lowering
```

## 5. Surface Recognition

The 0.1 parser is deliberately thin and line oriented. It recognizes MarkTeX
controls at column zero of a physical line. Chunks not claimed by those
controls are parsed by MarkTeX's private fallback parser and immediately
lowered to ordinary MarkTeX AST nodes. This is analogous to C++ owning syntax
that originated in C: the spelling may be familiar, but the language contract
is MarkTeX's.

Recognition order:

1. Backtick code fences beginning with `` ``` ``.
2. Host blocks beginning with `$$$`.
3. Display math blocks delimited by column-one `$$` lines.
4. Footnote definitions.
5. Rich tables beginning with `+++`.
6. Conditional controls.
7. Scope close `!!@`.
8. Document directive `!#`.
9. Scope open `!@`.
10. MarkTeX fallback blocks and inline content.

`!!@` must be checked before `!@`, and `!?!?` before `!?`, because these forms
share prefixes.

Line-start controls:

```text
!#    document directive
!@    scope push
!!@   scope close
!?    conditional if
!?!?  conditional else-if
!?!   conditional else
!!?   conditional end
$$$   host block fence
$$    display math fence, only when the whole physical line is exactly $$
+++   rich table fence if length is at least 3 plus signs
```

The actual rich table opener may be any fence of three or more `+` characters.
Examples use `+++`.

## 6. MOS

MOS is raw by default. The parser does not infer booleans, numbers, dimensions,
quoted strings, or tags.

```marktex
font: Times New Roman
margin: top=10pt, bottom=12pt
layout: A4, landscape
```

Structural characters:

```text
: , ; = ( )
```

Rules:

- `:` opens a call frame.
- `,` separates arguments in the current frame.
- `;` closes exactly one open call frame; at root it ends the current unit.
- `=` binds one named parameter.
- `(...)` creates a tuple-like structured value.
- `\x` produces literal `x` for any following character `x`.
- `\` followed by a physical newline produces nothing; it is line
  continuation, not a space.
- `` `...` `` creates a forced raw literal. Structural characters and keyword
  matches inside it are inactive.
- Only call heads and parameter names are trimmed for matching.
- Values are not trimmed by the parser.

For line-start `!#` and `!@` controls, the surface parser collects physical
continuation lines before passing the payload to MOS. For example,
`!# layout: \` followed by `A4` is equivalent to `!# layout: A4`.
Conditions remain line-local because their payload is a `[$ ... ]` host
expression, not a MOS value.

Examples:

```text
a: b
-> CallUnit("root", "a", args=[" b"], kwargs={})

a: b; c
-> CallUnit("root", "a", args=[" b"], kwargs={})
-> CallUnit("root", "c", args=[], kwargs={})

a: b: c;; d
-> CallUnit("root", "a", args=[CallUnit("root", "b", [" c"], {})], kwargs={})
-> CallUnit("root", "d", args=[], kwargs={})

a: enabled=True, size=10pt
-> CallUnit("root", "a", args=[], kwargs={"enabled": "True", "size": "10pt"})

a: (x, y, z)
-> CallUnit("root", "a", args=[TupleValue(["x", " y", " z"])], kwargs={})

a: `,;:=()`
-> CallUnit("root", "a", args=[RawString(",;:=()", force_raw=True)], kwargs={})
```

Root-level named arguments form an empty-head call unit. This is used by scope
syntax:

```marktex
!@ font=Times
```

becomes a scope push with key `""` and kwarg `font="Times"`.

### Finite Values And Value Shading

MOS itself still passes values as raw strings. Finite option domains are checked
by the semantic function that consumes the call. That consumer trims and
normalizes a lookup copy, then accepts only its declared values.

Schema may also shade a raw value into a no-argument nested call unit before
semantic execution.

Rule:

1. Keep the raw value text.
2. Trim only a lookup copy.
3. If the current value context has a matching `ShadeSpec`, replace the value
   with that no-argument call unit.
4. Otherwise preserve the original raw string and let the semantic consumer
   decide whether it is valid.

Built-in examples:

```marktex
!# layout: A4, landscape
```

resolves through schema data into layout value calls with payloads such as
`paper="a4paper"` and `orientation="landscape"`. Removing `A4` from schema data
does not change MOS parsing; it only changes resolution.

Forced raw literals disable schema shading, not semantic validation:

```marktex
!# layout: `A4`
```

passes the raw string `A4`. The `layout` semantic function may still accept that
literal because it owns paper-name normalization.

## 7. Document Directives

`!#` parses its payload as document-context MOS:

```marktex
!# layout: A4, landscape
!# margin: top=20pt, bottom=24pt
!# bib: main.bib
!# bib+: appendix.bib
!# bib-: old.bib
!# newpage
```

Before the first body block, stateful top-level calls become document-level
events:

```text
DocumentPatch(CallUnit(...))
```

`!#` never opens a scope. Active scopes override document-level state where a
backend implements that state field.

Multiple root calls are allowed:

```marktex
!# layout: A4; margin: top=20pt;
```

This is equivalent to two document directive events.

After body content has begun, `!#` is planned by each directive head:

- page-model directives such as `layout` and `margin` create a pending
  `PageSetup` before the next emitted block;
- state/config directives such as `bib`, `bib+`, `bib-`, `bibstyle`, and
  `citestyle` update document state and do not create a page break;
- `newpage` creates an immediate `PageBreak`.

Consecutive page-model directives coalesce into one pending page setup. A
trailing page-model directive does not create a blank page. `newpage` is the
only exception: it is effective at the beginning, middle, or end of a document,
even when no body content follows it. `newpage` merges with a previous empty
page transition, such as a pending `PageSetup` or a consecutive `newpage`
without intervening content, but later page-model directives do not merge
backward into that `newpage`.

Built-in document heads in 0.1:

```text
layout
margin
bib
bib+
bib-
bibstyle
citestyle
newpage
```

`layout` accepts paper aliases (`A4`, `A5`, `Letter`, or
`paper=a4paper|a5paper|letterpaper`), explicit `width=` / `height=`, optional
`orientation=portrait|landscape`, and margin keys `top`, `bottom`, `left`, and
`right`. In one call, size is applied first, then orientation, then margins:

```marktex
!# layout: paper=A4, orientation=landscape, top=20mm
!# layout: width=100mm, height=200mm, orientation=landscape
```

Paper aliases set width and height with portrait defaults. Orientation is an
atomic transform on the current page size: if the current width/height already
match the requested orientation it does nothing; otherwise it transposes width
and height. All canonical layout events store explicit `width` and `height`,
not backend-specific paper names.

The LuaLaTeX backend lowers initial layout events to `geometry` package options
and body `PageSetup` blocks to `\clearpage` plus `\newgeometry{...}`. `newpage`
lowers to `\clearpage` and is not a document event. Other document events
remain visible in AST/EIR for future backend work.

## 8. Scopes

`!@` parses its payload as scope-context MOS. Each top-level call becomes:

```python
scope_push(key, *args, scope="DEFAULT", **kwargs)
```

0.1 stores this as a `ScopePush` object. The call head is the frame key used by
`!!@` matching. The optional `scope` kwarg is a semantic target selector for
schema/backend interpretation; it is not the close key.

Examples:

```marktex
!@ font=Times
```

means:

```text
ScopePush(key="", kwargs={"font": "Times"})
```

```marktex
!@ w
!@ w:
!@ w: font=Times
```

mean:

```text
ScopePush(key="w", args=[], kwargs={})
ScopePush(key="w", args=[], kwargs={})
ScopePush(key="w", args=[], kwargs={"font": "Times"})
```

Frame keys are ordinary data and close by exact key match. Scope target values
are defined separately. Built-in 0.1 target values are:

```text
DEFAULT
w e
h1 h2 h3 h4 h5 h6
```

When `scope` is omitted, the target is `DEFAULT`. Explicit `scope=DEFAULT` is
canonicalized away in the stored event, while EIR state records the target as
`DEFAULT`.

```marktex
!@ w: font=Times, scope=e
```

means:

```text
ScopePush(key="w", args=[], kwargs={"font": "Times", "scope": "e"})
```

This opens a frame closed by `!!@ w`, while marking the event as targeting
scope `e`. Unknown target values are compile errors.

`!!@` closes the nearest active scope frame with a matching key:

```marktex
!!@       # closes key ""
!!@ w     # closes key "w"
```

Same-key scopes stack naturally. An unmatched close is a compile error. Scope
events are visible in the EIR state log even when the 0.1 LuaLaTeX backend does
not yet lower a specific style effect.

## 9. Host Runtime

The only host profile in 0.1 is Python.

Host blocks:

```marktex
$$$python
name = "Ada"
$$$

Hello [$ name ].
```

The language marker defaults to `python` if omitted. Any non-Python host block
language is a compile error in 0.1.

`.mtx` files are trusted scripts when host execution is enabled. The Python host
uses a small builtins mapping and does not expose `open`, `import`,
`__import__`, `eval`, or `exec` as builtins, but this is not a sandbox. Use
`--no-host` for untrusted input.

`--no-host` behavior:

- `$$$` host blocks are rejected.
- `[$ PAGE.CURRENT ]` is allowed.
- `[$ PAGE.TOTAL ]` is allowed.
- Python literal expressions accepted by `ast.literal_eval` are allowed.
- Host computation such as `[$ 1 + 2 ]` is rejected.

Required host intrinsics:

```text
PAGE.CURRENT
PAGE.TOTAL
TIME
BIB
marktex
```

The `marktex` intrinsic is a per-build runtime session. It exposes:

```text
marktex.raw(text, force_raw=False)
marktex.tuple_value(*items)
marktex.call(head, *args, context="document", **kwargs)
marktex.document_patch(head, *args, **kwargs)
marktex.scope_push(key, *args, scope="DEFAULT", **kwargs)
marktex.scope_close(key="")
marktex.invoke(event)
marktex.finish()
marktex.document(events=(), blocks=(), footnotes=())
marktex.paragraph(*children)
marktex.heading(level, *children)
marktex.table(columns, header, rows=())
marktex.footnote_definition(label, *children)
```

`marktex.invoke()` accepts only `DocumentPatch`, `ScopePush`, and `ScopeClose`
objects in 0.1. Runtime constructors normalize Python values into MOS values:
strings become raw MOS strings, tuples and lists become MOS tuples, and nested
calls must be written with `marktex.call(...)`. `scope_push(..., scope=...)`
accepts the same built-in scope targets as surface `scope=`. Construction
helpers return canonical core objects and are used by executable host
artifacts.

`PAGE.CURRENT` and `PAGE.TOTAL` are symbolic values. They are never concrete
during host execution.

Supported symbolic proxy operators in the Python profile:

```text
+  -
%
== != < <= > >=
```

Reverse operations such as `1 + PAGE.TOTAL` also produce symbolic expressions.
Implicit boolean conversion of any symbolic value is invalid:

```python
if PAGE.TOTAL > 10:
    ...
```

Use a MarkTeX conditional instead.

## 10. Inline Expressions

Inline expressions use:

```marktex
[$ ... ]
```

They are parsed as inline objects, not backend string replacement.

Examples:

```marktex
Hello [$ name ].
Page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ].
```

Concrete values are stringified by the receiving inline text context and then
escaped by the LuaLaTeX backend. Individual page placeholders lower to:

```text
PAGE.CURRENT -> \thepage{}
PAGE.TOTAL   -> \pageref{LastPage}
```

Complex symbolic inline expressions are preserved as symbolic objects, but the
0.1 LuaLaTeX backend rejects most of them with diagnostics. For example:

```marktex
Remaining [$ PAGE.TOTAL - PAGE.CURRENT ] pages.
```

is valid 0.1 directionally, but unsupported by the 0.1 LuaLaTeX backend.

## 11. MarkTeX Fallback Syntax

0.1 supports practical Markdown-inspired spellings as MarkTeX fallback syntax.
This is not a public Markdown adapter layer and it is not a direct promise of
Markdown dialect compatibility: MarkTeX controls are recognized first, then
unclaimed text chunks are parsed and converted directly to MarkTeX AST.

- ATX headings `#` through `######`;
- setext headings;
- paragraphs separated by blank lines;
- fenced code blocks;
- unordered, ordered, nested, loose, and tight lists;
- task list markers `- [ ]` and `- [x]`;
- block quotes;
- thematic breaks;
- pipe tables with an alignment row;
- inline emphasis `*text*` and `_text_`;
- inline strong `**text**` and `__text__`;
- inline code `` `text` ``;
- inline math `$x+y$`;
- strikethrough `~~text~~`;
- links `[label](url)`;
- images `![alt](src)`;
- reference-style links and images;
- backslash escapes;
- physical line breaks;
- backslash line continuation;
- footnote references `[^label]`;
- single-line footnote definitions `[^label]: body`.

Not supported in 0.1:

- autolink semantics such as `<https://example.com>`;
- raw/block/inline HTML semantics;
- HTML entity decoding as HTML behavior;
- CommonMark whitespace, indentation, softbreak, or HTML behavior.

Autolinks and raw HTML remain escaped document text. Unsupported
Markdown-inspired spelling usually remains paragraph text unless it collides
with a recognized MarkTeX form that has to be diagnosed.

Fallback block syntax uses a control-sequence consumption model: each form
consumes only its explicit control prefix, and every character after that
prefix is document content. Fallback control prefixes are recognized only at
the current container column; MarkTeX does not inherit Markdown's `0..3`
leading-space tolerance. For example, `- x` consumes the list opener `- ` and
uses `x` as content, while `-  x` keeps one leading content space. `# Title`
is a heading, but ` # Title` and `#Title` are ordinary paragraph text.

A physical newline inside a paragraph is a MarkTeX hard line break. A backslash
immediately followed by a physical newline is line continuation and contributes
nothing. This intentionally differs from Markdown's soft/hard break rules:
spaces are ordinary text characters in MarkTeX.

Lists derive their nesting unit from the current contiguous nonblank list run.
The first item must start at the current container column. If nested items
exist, MarkTeX uses the greatest common divisor of positive opener indents as
the indent unit. Blank lines end the current list run. Tabs and spaces cannot
be mixed in structural indentation, and nesting cannot skip levels. Ordered
list markers in the same ordered block must be sequential; switching between
ordered and unordered at the same level creates a sibling list block.

Inline MarkTeX delimiter forms are physical-line local. `[$ ... ]` host
expressions and `$...$` inline math must open and close on the same physical
line. A failed form is ordinary text; line continuation in that ordinary text
does not trigger a second inline parse pass. Therefore `[$ x\` followed by
`y ]` and `$x\` followed by `y$` are text, not expressions or math. Inside
math, the body is raw target math text and MarkTeX inline parsing is inactive.
Inline code, emphasis, strong, and strikethrough delimiters are mechanical
same-line pairs; unclosed or cross-line pairs remain text.

Display math uses column-one fence lines:

```marktex
$$
a^2 + b^2 = c^2
$$
```

The opening and closing lines must be exactly `$$`. Indented `$$`, `$$ x $$`,
or a line with trailing spaces is ordinary fallback text. Display math body is
owned by the math language, so MarkTeX backslash continuation and inline
parsing do not apply inside it.

Reference-style link and image definitions are MarkTeX fallback declarations,
not a Markdown global pre-scan. Root definitions are visible to root content
and child containers such as lists, block quotes, and conditional branches.
Definitions inside a conditional branch are visible only inside that branch and
may shadow root definitions there. Definitions inside child containers are
local to that container and may shadow inherited definitions for their own
children.

## 12. Code Blocks

Ordinary code fence:

````marktex
```python
print("hello")
```
````

emits a LuaLaTeX code block with explicit typewriter spacing.

Interpolated code fence:

````marktex
```$python
print("[$ name ]")
```
````

enables `[$ ... ]` interpolation inside the code body. Concrete expressions are
inserted as escaped code text. `PAGE.CURRENT` and `PAGE.TOTAL` remain symbolic
until backend lowering, so the LuaLaTeX backend can render them as live page
placeholders inside the displayed code block.

Only a `$` prefix enables code interpolation. An info string such as
`` ```python interp `` is just an ordinary code-fence language string.
Both top-level backtick fences and fallback fences report `unclosed code fence`
when the closing fence is missing.

Indented code blocks are not MarkTeX syntax. Leading spaces at the current
container column are ordinary paragraph text; fenced code is the canonical code
block form.

## 13. Rich Tables

Rich table syntax:

```marktex
+++ align=left | align=right
Name | Score
Ada | 98
Grace | 99
+++
```

Examples normally use `+++`; the closing fence must match the opener length.

Rules:

- The opener payload is split by unescaped `|` into column specs.
- Each column spec is parsed as table-column MOS.
- The first body row is the header.
- Later rows are body rows.
- Blank lines are errors.
- Multiline cells are not supported.
- Every row must have the same number of cells as there are column specs.
- Literal `|` is written as `\|`.

The 0.1 LuaLaTeX backend emits a simple `tabular`. Column MOS alignment lowers
to `l`, `c`, or `r` when the column spec provides `align=left|center|right`.
Unknown alignment values are diagnostics; omitted alignment defaults to `left`.

Pipe tables use familiar pipe spelling as MarkTeX fallback syntax and lower to
the same `Table` core object. Rows must start and end with `|`. A cell consumes
at most one delimiter-adjacent ASCII padding space on each side: `| x |`
contains `x`, while `|  x  |` contains ` x `. Only `\|` is interpreted by the
table splitter as a literal pipe; other backslash escapes are left for the
inline parser. The alignment row is converted into table-column metadata
before backend lowering. Header and body rows must have exactly the same
number of cells as the alignment row; MarkTeX does not silently pad or
truncate pipe table rows. Pipe tables are not rich table syntax, even though
both become the same core `Table` object.

## 14. References, Footnotes, And Citations

Footnotes:

```marktex
Claim[^note].

[^note]: This is the footnote body.
```

Footnote labels may contain letters, numbers, `_`, `.`, `:`, and `-`.
Definitions are single-line in 0.1. An undefined footnote reference is a
backend diagnostic.

In LuaLaTeX output, ordinary inline footnote references lower to `\footnote`.
Footnote references inside table cells lower to a table-safe
`\footnotemark`, with matching `\footnotetext` emitted immediately after the
`tabular`.

Explicit citations:

```marktex
!# bib: main.bib
!# citestyle: apa
!# bibstyle: apa

See [^ cite: Knuth84, pages=12-15 ].
```

Citation payloads reuse MOS in reference context. The call head is `cite`; raw
positional args become citation keys, and raw kwargs become citation options.
The backend resolves each key against active BibTeX resources and renders the
in-text citation through the active `.mtxcs` citation style.

MarkTeX footnotes using familiar bracket spelling and bibliography citations are
deliberately separate:

- `[^note]` always lowers as a MarkTeX footnote using familiar bracket spelling;
- `[^ cite: Key ]` always lowers through the active citation style, even when
  that style is footnote-based.

There is no `[^@key]` citation shorthand. A reference payload containing `@`
does not match the footnote-label grammar and fails as an unsupported reference
payload.

Bibliography resource declarations should use MOS document directives:

```marktex
!# bib: main.bib
!# bib+: appendix.bib
!# bib-: old.bib
```

`bib` replaces the active resource list, `bib+` appends, and `bib-` removes.
Paths are resolved relative to the current `.mtx` file. The first bibliography
backend supports a common BibTeX subset: `@article`, `@book`,
`@inproceedings`, `@thesis`, `@misc`, and `@online`, with field names treated
case-insensitively.

Citation and bibliography styles are selected independently:

```marktex
!# citestyle: chicago-notes
!# bibstyle: chicago-notes-bibliography
```

Built-in citation styles are `numeric`, `superscript`, `apa`, `mla`,
`chicago-notes`, and `chicago-author-date`. Built-in bibliography styles are
`numeric`, `apa`, `mla`, `chicago-notes-bibliography`, and
`chicago-author-date`. If the style value looks like a path or ends with
`.mtxcs` / `.mtxbs`, it is loaded as a custom MOS style file relative to the
document.

Minimal `.mtxcs`:

```marktex
style: name=custom;
citation: mode=author-page, form=paren, locator-prefix=` `;
```

Minimal `.mtxbs`:

```marktex
style: name=custom;
references: title=Sources, include=cited, sort=author-title, placement=new-page, label=none;
template: default, author, title, container, year, url;
```

`include=cited` and `include=all` are style-level choices. MarkTeX does not
hard-code whether uncited BibTeX entries appear in references.

## 15. Conditionals

Conditional controls:

```marktex
!? [$ condition ]
if body
!?!? [$ other_condition ]
else-if body
!?!
else body
!!?
```

The condition payload must be a `[$ ... ]` host expression. Conditions produce
either a concrete boolean or a symbolic condition.

Supported in 0.1:

```marktex
!? [$ True ]
Visible.
!!?
```

```marktex
!? [$ PAGE.CURRENT == PAGE.TOTAL ]
Last page text.
!!?
```

Unsupported symbolic conditionals are diagnostics:

```marktex
!? [$ PAGE.CURRENT % 2 == 0 ]
Even page text.
!!?
```

The symbolic object can be represented in AST/EIR, but the 0.1 LuaLaTeX backend
does not lower this condition yet.

## 16. Core Objects And EIR

Core objects are immutable semantic values.

Current object families:

```text
Text
InlineExpression
Emphasis
Strong
Strikethrough
InlineCode
InlineMath
LineBreak
Link
Image
FootnoteRef
Citation
Paragraph
Heading
CodeText
CodeExpression
CodeBlock
MathBlock
Table
ListBlock
ListItem
BlockQuote
ThematicBreak
PageBreak
PageSetup
Conditional
FootnoteDefinition
DocumentPatch
ScopePush
ScopeClose
Document
```

State-changing objects enter the state engine as invoke events:

```text
DocumentPatch
ScopePush
ScopeClose
```

The EIR artifact payload contains:

```json
{
  "kind": "eir",
  "document": "... canonical document JSON ...",
  "state": "... invoke events and scope frames ..."
}
```

The state engine closes scopes by key:

```text
!!@ key -> find nearest active frame whose key == key, then close it
```

The document event log is authoritative. Bucket-style effective state views are
an implementation strategy for future backend work, not a separate source
language feature.

## 17. LuaLaTeX Backend

LuaLaTeX is the first concrete backend and the only accepted 0.1 `--target`.
It is an implementation target, not MarkTeX's semantic core. `mtxc` emits a
self-contained `.tex` file oriented to LuaLaTeX. The 0.1 preamble uses:

```latex
\documentclass{article}
\usepackage{fontspec}
\usepackage{luatexja}
\usepackage{hyperref}
\usepackage{array}
\usepackage{lastpage}
\usepackage{graphicx}
\usepackage{refcount}
\usepackage{geometry}
```

Lowering support:

- headings -> `\section`, `\subsection`, and related article commands;
- paragraphs -> escaped LaTeX text;
- emphasis -> `\emph`;
- strong -> `\textbf`;
- strikethrough -> `\sout` with `ulem` loaded only when needed;
- inline code -> `\texttt`;
- inline math -> `\(...\)` with raw math body;
- display math -> `\[...\]` with raw math body;
- physical line breaks -> `\\`;
- links -> `\href`;
- images -> `\includegraphics`;
- ordinary footnotes -> `\footnote`;
- table cell footnotes -> `\footnotemark` plus deferred `\footnotetext`
  after the `tabular`;
- citations -> active `.mtxcs` citation style;
- references -> active `.mtxbs` bibliography style, appended when non-empty;
- ordinary code blocks -> escaped typewriter text with explicit spacing;
- `$`-interpolated code blocks -> the same code block renderer with live
  lowered page placeholders;
- rich and pipe tables -> simple `tabular`;
- lists -> `itemize` or `enumerate`;
- task list items -> explicit `[ ]` or `[x]` item labels;
- block quotes -> `quote`;
- thematic breaks -> horizontal rules;
- page breaks -> `\clearpage`;
- page setup blocks -> `\clearpage` plus `\newgeometry{paperwidth=...,paperheight=...}`;
- `PAGE.CURRENT` -> `\thepage{}`;
- `PAGE.TOTAL` -> `\pageref{LastPage}`;
- `PAGE.CURRENT == PAGE.TOTAL` conditionals -> a page/last-page test.

The `tight` flag on list AST nodes is preserved, but the 0.1 LuaLaTeX backend
maps tight and loose lists to the same `itemize` / `enumerate` spacing. Ordered
list starts lower by setting the active LaTeX enumerate counter
(`enumi`, `enumii`, `enumiii`, or `enumiv`). List nesting deeper than LaTeX's
four native list levels is a backend diagnostic.

Unsupported backend objects must raise diagnostics. They must not be silently
dropped and must not be emitted as raw TeX by convenience fallback.

## 18. Schema Strategy

The parser is schema-agnostic. Schema owns:

- known call heads per context;
- shorthand/no-argument value shading;
- validation of explicit MarkTeX heads.

Semantic modules own finite domains, canonical core construction, and backend
independent meaning. MOS and schema do not decide whether a string such as
`A4`, `a4paper`, or `landscape` is valid for layout; the layout semantic
function does that after explicit normalization.

Built-in shorthand data lives in constants such as:

```python
LAYOUT_VALUE_SHADES = {
    "A4": ShadeSpec("A4", lowerer="paper_preset", payload={"paper": "a4paper"}),
    "landscape": ShadeSpec(
        "landscape",
        lowerer="orientation",
        payload={"orientation": "landscape"},
    ),
}
```

Adding `Legal` paper, renaming `A4`, or removing `landscape` changes schema
data, semantic constants, and golden outputs only. It must not require a MOS
parser change.

Adding an entirely new semantic family may add semantic validation and backend
support, but it still must not add tag logic to the parser.

## 19. Error Policy

Diagnostics should be precise and origin-aware.

Examples that must fail:

- unknown document call head;
- unsupported target;
- `--emit pdf`;
- multiple artifacts with `-o`;
- non-Python host block;
- host block under `--no-host`;
- unsafe or unavailable host builtins;
- symbolic value coerced to host boolean;
- unclosed code fence;
- unclosed host block;
- unclosed math block;
- unclosed rich table;
- rich table row with wrong cell count;
- pipe table row with wrong cell count;
- unmatched scope close;
- unclosed conditional;
- unsupported symbolic inline expression in LuaLaTeX backend;
- unsupported symbolic conditional in LuaLaTeX backend.

JSON diagnostics use:

```json
{
  "message": "...",
  "span": {
    "filename": "...",
    "start": 0,
    "end": 0,
    "line": 1,
    "column": 1
  }
}
```

## 20. Examples

Minimal document:

```marktex
!# layout: A4, portrait

# Hello

This is *MarkTeX* page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ].
Inline math is MarkTeX syntax too: $E = mc^2$.

$$
a^2 + b^2 = c^2
$$
```

Scoped event log:

```marktex
!@ w: font=Times New Roman
Western scoped text.
!!@ w
```

Trusted host:

```marktex
$$$python
name = "Ada"
$$$

Hello [$ name ].
```

No-host compatible expression:

```marktex
Page [$ PAGE.CURRENT ].
Literal [$ "ok" ].
```

Rich table:

```marktex
+++ align=left | align=right
Name | Score
Ada | 98
Grace | 99
+++
```

Citation placeholder:

```marktex
!# bib: references.bib

See [^ cite: Knuth84, pages=12-15 ].
```

## 21. Release Checklist

Before a 0.1 release:

```bash
uv sync --locked --extra dev
uv run python -m unittest tests.test_driver_cli.DriverTests.test_version_matches_pyproject
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
uv run ruff check .
uv run mypy src
git diff --check
```

Build distributions:

```bash
uv build
```

Smoke test from source:

```bash
uv run mtxc examples/hello.mtx --emit all
```

Smoke test an installed wheel:

```bash
uv tool install --force dist/*.whl
mtxc examples/hello.mtx
```

Optional LuaLaTeX smoke when available:

```bash
uv run mtxc examples/comprehensive.mtx --emit all --out-dir /tmp/marktex-comprehensive
cp -R examples/assets /tmp/marktex-comprehensive/assets
lualatex -interaction=nonstopmode -halt-on-error -output-directory=/tmp/marktex-comprehensive /tmp/marktex-comprehensive/comprehensive.tex
lualatex -interaction=nonstopmode -halt-on-error -output-directory=/tmp/marktex-comprehensive /tmp/marktex-comprehensive/comprehensive.tex
```

0.1 changelog:

- Add the `marktex` Python package and `mtxc` CLI.
- Generate the selected backend target artifact by default.
- Add self-contained pipeline artifact emission for surface, host script, AST,
  EIR, backend IR, and target output.
- Implement schema-driven MOS value shading.
- Support headings, paragraphs, code fences, lists, block quotes, thematic
  breaks, rich tables, pipe tables, practical inline Markdown-inspired MarkTeX
  syntax, inline/display math, footnotes, citation placeholders, simple
  conditionals, and page placeholders.
- Add `--no-host` and JSON diagnostics.

## 22. Roadmap

Planned work after 0.1:

- external additive schema loading;
- hardening rare MarkTeX fallback delimiter and container edge cases in the
  private fallback parser;
- backend lowering for scope-driven typography;
- fuller APA/MLA/Chicago bibliography rule coverage;
- symbolic inline arithmetic such as `PAGE.TOTAL - PAGE.CURRENT`;
- richer symbolic conditionals;
- optional PDF build driver outside `mtxc`, if a separate tool is desired.

The core philosophy should not change: keep syntax thin, keep parser mechanics
mathematical, and move complexity into schema, host objects, and backend
lowerers where it belongs.
