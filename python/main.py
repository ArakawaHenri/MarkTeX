from __future__ import annotations

import argparse
from pathlib import Path

from marktex.pipeline import compile_marktex_to_latex


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile MarkTeX (.mtx) to LaTeX.")
    parser.add_argument("input", nargs="?", help="Input .mtx file path.")
    parser.add_argument("-o", "--output", help="Output .tex file path.")
    return parser


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    if args.input:
        source = Path(args.input).read_text(encoding="utf-8")
    else:
        source = "# MarkTeX Demo\n\n*(font: Times New Roman, size: 12)\nHello, [world](blue, bold)."

    latex = compile_marktex_to_latex(source)
    if args.output:
        Path(args.output).write_text(latex, encoding="utf-8")
        return
    print(latex)


if __name__ == "__main__":
    main()
