from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from marktex import __version__
from marktex.driver import ArtifactKind, compile_file
from marktex.driver.compiler import ALL_ARTIFACTS
from marktex.source import MarkTeXError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        emits = parse_emits(args.emit)
        output_path = Path(args.output) if args.output else None
        result = compile_file(
            Path(args.input),
            emits=emits,
            output_path=output_path,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            target=args.target,
            schema_paths=tuple(Path(path) for path in args.schema),
            strict=args.strict,
            no_host=args.no_host,
        )
        if output_path is not None and str(output_path) == "-":
            if len(result.artifacts) != 1:
                raise MarkTeXError("--output - can only be used with a single emitted artifact")
            sys.stdout.write(next(iter(result.artifacts.values())))
        return 0
    except MarkTeXError as error:
        print_diagnostic(error, args.diagnostic_format)
        return 2
    except OSError as error:
        if args.diagnostic_format == "json":
            print(json.dumps({"message": str(error), "span": None}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"mtxc: error: {error}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mtxc",
        description="Compile MarkTeX .mtx files to LuaLaTeX-oriented artifacts.",
    )
    parser.add_argument("input", help=".mtx source file")
    parser.add_argument("-o", "--output", help="output path for one emitted artifact; use '-' for stdout")
    parser.add_argument("--out-dir", help="output directory for multiple artifacts")
    parser.add_argument(
        "--emit",
        action="append",
        default=[],
        metavar="KIND",
        help="artifact to emit: tex, host, ast, eir, backend-ir, all",
    )
    parser.add_argument(
        "--target",
        default="lualatex",
        help="output target; V0 only accepts lualatex",
    )
    parser.add_argument(
        "--schema",
        action="append",
        default=[],
        help="additional schema config path (reserved hook)",
    )
    parser.add_argument("--strict", action="store_true", help="reject legacy/non-normative syntax")
    parser.add_argument(
        "--no-host",
        action="store_true",
        help="disable user host code; only literal values and PAGE placeholders are allowed in expressions",
    )
    parser.add_argument(
        "--diagnostic-format",
        choices=("text", "json"),
        default="text",
        help="diagnostic output format",
    )
    parser.add_argument("--version", action="version", version=f"mtxc {__version__}")
    return parser


def parse_emits(raw_emits: list[str]) -> set[ArtifactKind]:
    if not raw_emits:
        return {ArtifactKind.TEX}
    emits: set[ArtifactKind] = set()
    for raw in raw_emits:
        if raw == "all":
            emits.update(ALL_ARTIFACTS)
            continue
        if raw == "pdf":
            raise MarkTeXError("--emit pdf is not supported; mtxc does not build PDFs")
        try:
            emits.add(ArtifactKind(raw))
        except ValueError as exc:
            allowed = ", ".join([kind.value for kind in ArtifactKind] + ["all"])
            raise MarkTeXError(f"unsupported emit artifact: {raw}; expected one of {allowed}") from exc
    return emits


def print_diagnostic(error: MarkTeXError, diagnostic_format: str) -> None:
    if diagnostic_format == "json":
        print(json.dumps(error.diagnostic.to_json(), ensure_ascii=False), file=sys.stderr)
    else:
        print(f"mtxc: error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
