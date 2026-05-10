<div align="center"><img src=logo.svg width=45% /></div>

# MarkTeX

MarkTeX is a base Markdown superset for programmable documents that compile to
LuaLaTeX-oriented `.tex` files.

The current package milestone is `0.1`: installable Python package, `mtxc` CLI,
MOS call syntax, Python host runtime, canonical debug artifacts, and a thin
LuaLaTeX backend. `mtxc` does not run LuaLaTeX and does not build PDFs.

The single canonical documentation entry is
[`docs/marktex-0.1.md`](docs/marktex-0.1.md).

## CLI

```bash
python -m pip install .
mtxc paper.mtx
```

By default this writes `paper.tex`. Debug artifacts are available with
`--emit`:

```bash
mtxc paper.mtx -o output.tex
mtxc paper.mtx --emit all
mtxc paper.mtx --emit ast --emit eir --emit tex --out-dir build/
mtxc paper.mtx --no-host
mtxc paper.mtx --diagnostic-format json
```

Developer runs without installation can use:

```bash
PYTHONPATH=src python3 -m marktex.cli paper.mtx
```

Because `.mtx` files may contain Python host blocks, treat them as scripts.
Use `--no-host` for untrusted input. See the canonical documentation for the
exact supported syntax and release checklist.
