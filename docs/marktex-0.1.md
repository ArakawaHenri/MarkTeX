# MarkTeX 0.1 Documentation

This is the single normative documentation entry for the current repository.
The root `README.md` is only a landing page. Older root-level design notes were
folded into this document and should not be used as implementation authority.

MarkTeX 0.1 is a publishable Python package milestone, not the complete
language 1.0. It provides the `marktex` package and the `mtxc` command. The
compiler reads `.mtx` files and emits LuaLaTeX-oriented `.tex` files plus
optional debug artifacts. It does not run LuaLaTeX and it does not build PDFs.

## 1. Design Laws

1. MarkTeX is a superset of base Markdown. V0 does not adopt Markdown extension
   syntax as language law.
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
8. Add, remove, or rename shorthand behavior through schema data. Do not modify
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
| Default `.tex` output | Supported |
| Target `lualatex` | Only accepted target |
| PDF generation | Out of scope |
| `--emit host|ast|eir|backend-ir|tex|all` | Supported |
| `--diagnostic-format text|json` | Supported |
| `--schema` | Reserved hook; file existence is validated |
| `--strict` | Rejects known legacy forms implemented by 0.1 |
| `--no-host` | Supported restricted mode |
| MOS raw strings, frames, tuples, escapes, raw literals | Supported |
| Schema-driven value shading | Supported |
| `!#` document events | Supported; backend lowers layout only |
| `!@` and `!!@` scope events | Supported in state/EIR |
| Python `$$$` host blocks | Supported for trusted input |
| Inline `[$ ... ]` expressions | Supported |
| `PAGE.CURRENT` and `PAGE.TOTAL` placeholders | Supported inline and in `$` code fences |
| Complex symbolic inline math | Diagnostic in LuaLaTeX backend |
| Headings and paragraphs | Supported |
| Basic inline Markdown | Supported subset |
| Ordinary and `$`-interpolated code fences | Supported subset |
| Rich `+++` tables | Supported |
| Markdown pipe tables | Planned |
| Footnotes | Supported single-line definitions |
| Explicit citation references | Supported through citation styles |
| Bibliography backend | Supported BibTeX subset with `.mtxcs`/`.mtxbs` styles |
| Conditionals | Concrete bool and `PAGE.CURRENT == PAGE.TOTAL` supported |
| Full Markdown dialect compatibility | Planned |

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
mtxc paper.mtx --emit ast --emit eir --emit tex --out-dir build/
mtxc paper.mtx --emit all
mtxc paper.mtx --no-host
mtxc paper.mtx --diagnostic-format json
```

`-o -` writes a single text artifact to stdout. It is invalid with multiple
artifacts. `--emit pdf` is invalid because `mtxc` is not a PDF build driver.
Any target other than `lualatex` is invalid in 0.1.

Artifact names are deterministic:

```text
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
from marktex.driver import ArtifactKind, compile_file

compile_file(
    Path("paper.mtx"),
    emits={ArtifactKind.TEX},
    output_path=None,
    out_dir=None,
    target="lualatex",
    schema_paths=(),
    strict=False,
    no_host=False,
)
```

## 4. Compiler Pipeline

The V0 architecture is:

```text
.mtx source
-> SurfaceDocument
-> MOS CallUnit objects
-> Python host environment
-> canonical Document
-> EIR debug view
-> LuaLaTeX backend IR
-> .tex
```

The long-term architecture also treats the generated host script as the
explicit construction artifact:

```text
.mtx -> CST -> Surface AST / CallUnit -> generated host script
     -> canonical AST/EIR -> backend IR -> .tex
```

The 0.1 driver executes an equivalent Python host environment directly while
building the document, and emits a deterministic `host` artifact for inspection.

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
controls at column zero of a physical line. Leading spaces make the line
ordinary Markdown/prose for 0.1.

Recognition order:

1. Backtick code fences beginning with `` ``` ``.
2. Host blocks beginning with `$$$`.
3. Footnote definitions.
4. Rich tables beginning with `+++`.
5. Conditional controls.
6. Scope close `!!@`.
7. Document directive `!#`.
8. Scope open `!@`.
9. Markdown heading.
10. Blank line.
11. Paragraph text.

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
- `\x` produces literal `x`.
- `\` followed by a physical newline produces one literal space.
- `` `...` `` creates a forced raw literal. Structural characters and keyword
  matches inside it are inactive.
- Only call heads and parameter names are trimmed for matching.
- Values are not trimmed by the parser.

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

### Value Shading

Schema may shade a raw value into a no-argument nested call unit.

Rule:

1. Keep the raw value text.
2. Trim only a lookup copy.
3. If the current value context has a matching `ShadeSpec`, replace the value
   with that no-argument call unit.
4. Otherwise preserve the original raw string.

Built-in examples:

```marktex
!# layout: A4, landscape
```

resolves through schema data into layout value calls with payloads such as
`paper="a4paper"` and `orientation="landscape"`. Removing `A4` from schema data
does not change MOS parsing; it only changes resolution.

Forced raw literals disable shading:

```marktex
!# layout: `A4`
```

passes the raw string `A4`.

## 7. Document Directives

`!#` parses its payload as document-context MOS:

```marktex
!# layout: A4, landscape
!# margin: top=20pt, bottom=24pt
!# bib: main.bib
!# bib+: appendix.bib
!# bib-: old.bib
```

Each top-level call becomes a document-level event:

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

Built-in document heads in 0.1:

```text
layout
margin
bib
bib+
bib-
bibstyle
citestyle
```

The LuaLaTeX backend currently lowers `layout` to `geometry` options for
`A4`, `A5`, `Letter`, `landscape`, and `portrait`. Other document events remain
visible in AST/EIR for future backend work.

## 8. Scopes

`!@` parses its payload as scope-context MOS. Each top-level call becomes:

```python
scope_push(key, *args, scope="DEFAULT", **kwargs)
```

0.1 stores this as a `ScopePush` object.

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

Names such as `w`, `e`, and `h1` are scope keys. They can change how the
default scope is interpreted by schema and backend rules, but they are still
data in the scope event.

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

is valid V0 directionally, but unsupported by the 0.1 LuaLaTeX backend.

## 11. Markdown Subset

0.1 supports a small, explicit Markdown subset:

- ATX headings `#` through `######`;
- paragraphs separated by blank lines;
- ordinary backtick code fences;
- inline emphasis `*text*`;
- inline strong `**text**`;
- inline code `` `text` ``;
- links `[label](url)`;
- images `![alt](src)`;
- footnote references `[^label]`;
- single-line footnote definitions `[^label]: body`.

Not supported in 0.1:

- Markdown lists as typed list nodes;
- block quotes as typed quote nodes;
- Markdown pipe tables;
- nested or escaped delimiter behavior beyond the simple subset above;
- full CommonMark conformance.

Unsupported Markdown usually remains paragraph text unless it collides with a
recognized MarkTeX form that has to be diagnosed.

## 12. Code Blocks

Ordinary code fence:

````marktex
```python
print("hello")
```
````

emits a verbatim block.

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

In strict mode, the legacy `interp` info-string flag is rejected. Use `` ```$ ``
instead.

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

The 0.1 LuaLaTeX backend emits a simple `tabular` with left-aligned columns.
Column MOS is preserved in AST/EIR but only minimally lowered in 0.1.

Markdown pipe tables are planned separately. They are not the rich table
syntax.

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
Footnote references inside rich table cells lower to a table-safe
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

Markdown footnotes and bibliography citations are deliberately separate:

- `[^note]` always lowers as a Markdown-style footnote;
- `[^ cite: Key ]` always lowers through the active citation style, even when
  that style is footnote-based.

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
InlineCode
Link
Image
FootnoteRef
Citation
Paragraph
Heading
CodeText
CodeExpression
CodeBlock
Table
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

The EIR debug artifact contains:

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

`mtxc` emits a self-contained `.tex` file oriented to LuaLaTeX. The 0.1
preamble uses:

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
- inline code -> `\texttt`;
- links -> `\href`;
- images -> `\includegraphics`;
- ordinary footnotes -> `\footnote`;
- rich table cell footnotes -> `\footnotemark` plus deferred `\footnotetext`
  after the `tabular`;
- citations -> active `.mtxcs` citation style;
- references -> active `.mtxbs` bibliography style, appended when non-empty;
- ordinary code blocks -> `verbatim`;
- `$`-interpolated code blocks -> escaped `\ttfamily` text with live lowered
  page placeholders;
- rich tables -> simple `tabular`;
- `PAGE.CURRENT` -> `\thepage{}`;
- `PAGE.TOTAL` -> `\pageref{LastPage}`;
- `PAGE.CURRENT == PAGE.TOTAL` conditionals -> a page/last-page test.

Unsupported backend objects must raise diagnostics. They must not be silently
dropped and must not be emitted as raw TeX by convenience fallback.

## 18. Schema Strategy

The parser is schema-agnostic. Schema owns:

- known call heads per context;
- shorthand/no-argument value shading;
- validation of explicit MarkTeX heads;
- semantic lowerer identifiers.

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
data and golden outputs only. It must not require a MOS parser change.

Adding an entirely new semantic family may add a lowerer and backend support,
but it still must not add tag logic to the parser.

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
- unclosed rich table;
- rich table row with wrong cell count;
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
lualatex -interaction=nonstopmode -halt-on-error -output-directory=/tmp/marktex-comprehensive /tmp/marktex-comprehensive/comprehensive.tex
lualatex -interaction=nonstopmode -halt-on-error -output-directory=/tmp/marktex-comprehensive /tmp/marktex-comprehensive/comprehensive.tex
```

0.1 changelog:

- Add the `marktex` Python package and `mtxc` CLI.
- Generate LuaLaTeX-oriented `.tex` output by default.
- Add debug artifact emission for host script, AST, EIR, backend IR, and TeX.
- Implement schema-driven MOS value shading.
- Support headings, paragraphs, code fences, rich tables, basic inline
  Markdown, footnotes, citation placeholders, simple conditionals, and page
  placeholders.
- Add `--no-host` and JSON diagnostics.

## 22. Roadmap

Planned V0 work after 0.1:

- external additive schema loading;
- fuller Markdown block support through a proper Markdown parser boundary;
- Markdown pipe table fallback;
- backend lowering for scope-driven typography;
- fuller APA/MLA/Chicago bibliography rule coverage;
- symbolic inline arithmetic such as `PAGE.TOTAL - PAGE.CURRENT`;
- richer symbolic conditionals;
- generated host script as the exact replayable construction path;
- optional PDF build driver outside `mtxc`, if a separate tool is desired.

The core philosophy should not change: keep syntax thin, keep parser mechanics
mathematical, and move complexity into schema, host objects, and backend
lowerers where it belongs.
