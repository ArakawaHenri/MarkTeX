<div align="center"><img src=logo.svg width=45% /></div>

# MarkTeX

MarkTeX is a programmable document language with Markdown-derived surface
spellings. LuaLaTeX-oriented `.tex` output is the current backend target, not
the language definition.

The current package milestone is `0.1`: installable Python package, `mtxc` CLI,
MOS call syntax, Python host runtime, self-contained pipeline artifacts, a private
MarkTeX fallback parser for Markdown-derived spellings, a BibTeX-backed
citation style layer, and a thin LuaLaTeX backend. `mtxc` does not run
LuaLaTeX and does not build PDFs.

The core contract is MarkTeX syntax, MOS, canonical document objects, and the
state model. Future backends can target Typst, Microsoft Office XML, or other
renderers without changing what `.mtx` means.

The single canonical documentation entry is
[`docs/marktex-0.1.md`](docs/marktex-0.1.md).

## CLI

```bash
uv tool install .
mtxc paper.mtx
```

By default this reads from the `mtx` stage and writes `paper.tex`. Pipeline
artifacts are available with `--emit`, and any emitted stage can be used as a
later input with explicit `--from`:

```bash
mtxc paper.mtx -o output.tex
mtxc paper.mtx --emit all
mtxc paper.mtx --emit ast --emit eir --emit target --out-dir build/
mtxc --from host build/paper.host.py --emit ast --emit target --out-dir build2/
mtxc --from backend-ir build/paper.backend-ir.json --emit target
mtxc paper.mtx --no-host
mtxc paper.mtx --diagnostic-format json
```

Developer runs without installation can use:

```bash
uv sync --extra dev
uv run mtxc paper.mtx
```

This repository uses `uv` as its only Python package manager. Use `uv run`,
`uv sync`, and `uv build` for project workflows.

Because `.mtx` files may contain Python host blocks, treat them as scripts.
Use `--no-host` for untrusted input. See the canonical documentation for the
exact supported syntax and release checklist.
