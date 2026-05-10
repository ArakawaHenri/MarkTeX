from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import marktex
from marktex.driver import ArtifactKind, compile_file
from marktex.driver.compiler import build_document
from marktex.source import MarkTeXError


class DriverTests(unittest.TestCase):
    def test_default_compile_writes_tex(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("# Title\n\nHello [$ PAGE.CURRENT ].\n", encoding="utf-8")
            result = compile_file(source)
            output = directory / "paper.tex"
            self.assertEqual(result.written[ArtifactKind.TEX], output)
            self.assertIn("\\section{Title}", output.read_text(encoding="utf-8"))
            self.assertIn("\\thepage{}", output.read_text(encoding="utf-8"))

    def test_multiple_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            out_dir = directory / "build"
            source.write_text("Hello\n", encoding="utf-8")
            compile_file(
                source,
                emits={ArtifactKind.AST, ArtifactKind.EIR, ArtifactKind.TEX},
                out_dir=out_dir,
            )
            self.assertTrue((out_dir / "paper.ast.json").exists())
            self.assertTrue((out_dir / "paper.eir.json").exists())
            self.assertTrue((out_dir / "paper.tex").exists())

    def test_scope_close_is_not_parsed_as_scope_open(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!@ w\n!!@ w\nHello\n", encoding="utf-8")
            result = compile_file(source, emits={ArtifactKind.EIR})
            eir = json.loads(result.artifacts[ArtifactKind.EIR])
            self.assertEqual(eir["state"]["scopes"][0]["key"], "w")
            self.assertEqual(eir["state"]["scopes"][0]["close_order"], 1)

    def test_scope_open_shapes(self) -> None:
        build = build_document("!@ font=Times\n!@ w\n!@ w: font=Times\n", filename="test.mtx")
        events = [event.to_json() for event in build.document.events]
        self.assertEqual(events[0]["key"], "")
        self.assertEqual(events[0]["kwargs"]["font"]["text"], "Times")
        self.assertEqual(events[1]["key"], "w")
        self.assertEqual(events[2]["key"], "w")
        self.assertEqual(events[2]["kwargs"]["font"]["text"], "Times")

    def test_host_block_variable_visible_to_later_expression(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("$$$python\nname = 'Ada'\n$$$\nHello [$ name ].\n", encoding="utf-8")
            compile_file(source)
            tex = source.with_suffix(".tex").read_text(encoding="utf-8")
            self.assertIn("Hello Ada.", tex)

    def test_concrete_expression_is_inline_ast_part(self) -> None:
        build = build_document("Total [$ 1 + 2 ].\n", filename="test.mtx")
        paragraph = build.document.blocks[0]
        data = paragraph.to_json()
        self.assertEqual(data["children"][1]["kind"], "inline_expr")
        self.assertEqual(data["children"][1]["value"], 3)
        self.assertIn("Total 3.", build.tex)

    def test_page_placeholders_lower_to_lualatex(self) -> None:
        build = build_document("Page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ].\n", filename="test.mtx")
        self.assertIn(r"\thepage{}", build.tex)
        self.assertIn(r"\pageref{LastPage}", build.tex)

    def test_interpolated_code_block_page_placeholder_lowers_to_lualatex(self) -> None:
        build = build_document(
            "```$python\nprint('page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ]')\n```\n",
            filename="test.mtx",
        )
        self.assertIn(r"\ttfamily\obeyspaces\obeylines", build.tex)
        self.assertIn(r"\thepage{}", build.tex)
        self.assertIn(r"\pageref{LastPage}", build.tex)
        self.assertNotIn("PAGE.CURRENT", build.tex)

    def test_unsupported_symbolic_expression_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Remaining [$ PAGE.TOTAL - PAGE.CURRENT ].\n", encoding="utf-8")
            with self.assertRaises(MarkTeXError):
                compile_file(source)

    def test_interpolated_code_block_unsupported_symbolic_expression_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported symbolic expression"):
            build_document(
                "```$python\nprint([$ PAGE.TOTAL - PAGE.CURRENT ])\n```\n",
                filename="test.mtx",
            )

    def test_symbolic_bool_coercion_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("$$$python\nif PAGE.TOTAL > 10:\n    x = 1\n$$$\nHello\n", encoding="utf-8")
            with self.assertRaises(MarkTeXError):
                compile_file(source)

    def test_unknown_document_head_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!# unknown: value\n", encoding="utf-8")
            with self.assertRaises(MarkTeXError):
                compile_file(source)

    def test_symbolic_conditional_current_equals_total_lowers(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!? [$ PAGE.CURRENT == PAGE.TOTAL ]\nLast\n!!?\n", encoding="utf-8")
            compile_file(source)
            tex = source.with_suffix(".tex").read_text(encoding="utf-8")
            self.assertIn(r"\ifnum\value{page}=\getpagerefnumber{LastPage}", tex)
            self.assertIn("Last", tex)

    def test_concrete_conditional_lowers_selected_branch(self) -> None:
        build = build_document("!? [$ False ]\nNo\n!?!\nYes\n!!?\n", filename="test.mtx")
        self.assertIn("Yes", build.tex)
        self.assertNotIn("No", build.tex)

    def test_unsupported_symbolic_conditional_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!? [$ PAGE.CURRENT % 2 == 0 ]\nEven\n!!?\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "unsupported symbolic conditional"):
                compile_file(source)

    def test_unclosed_blocks_report_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("```python\nx = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "unclosed code fence"):
                compile_file(source)

            source.write_text("$$$python\nx = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "unclosed host block"):
                compile_file(source)

            source.write_text("+++ a | b\nA | B\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "unclosed rich table"):
                compile_file(source)

    def test_lualatex_backend_mvp_blocks(self) -> None:
        build = build_document(
            "!# layout: Letter, landscape\n"
            "# Title\n\n"
            "```python\nprint('hi')\n```\n\n"
            "+++ align=left | align=right\nName | Score\nAda | 98\n+++\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[letterpaper,landscape]{geometry}", build.tex)
        self.assertIn(r"\section{Title}", build.tex)
        self.assertIn(r"\begin{verbatim}", build.tex)
        self.assertIn(r"\begin{tabular}", build.tex)

    def test_basic_inline_markdown_lowers(self) -> None:
        build = build_document(
            "This is *em* and **strong** with `code` and [site](https://example.com).\n",
            filename="test.mtx",
        )
        self.assertIn(r"\emph{em}", build.tex)
        self.assertIn(r"\textbf{strong}", build.tex)
        self.assertIn(r"\texttt{code}", build.tex)
        self.assertIn(r"\href{https://example.com}{site}", build.tex)

    def test_image_markdown_lowers(self) -> None:
        build = build_document("Logo ![MarkTeX](logo.png).\n", filename="test.mtx")
        self.assertIn(r"\includegraphics{logo.png}", build.tex)

    def test_footnote_and_citation_lower(self) -> None:
        build = build_document(
            "Claim[^note] and cite [^ cite: Knuth84, pages=12-15 ].\n\n"
            "[^note]: Footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Footnote body.}", build.tex)
        self.assertIn(r"\textsuperscript{[Knuth84; pages=12-15]}", build.tex)

    def test_table_cell_footnote_is_deferred_after_tabular(self) -> None:
        build = build_document(
            "+++ A | B\nHeader | Value\nCell[^note] | ok\n+++\n\n"
            "[^note]: Table footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"Cell\footnotemark & ok \\", build.tex)
        self.assertIn(r"\addtocounter{footnote}{-1}", build.tex)
        self.assertIn(r"\stepcounter{footnote}\footnotetext{Table footnote body.}", build.tex)

    def test_multiple_table_cell_footnotes_defer_in_source_order(self) -> None:
        build = build_document(
            "+++ A | B\nHeader | Value\nFirst[^a] | Second[^b]\n+++\n\n"
            "[^a]: First note.\n"
            "[^b]: Second note.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\addtocounter{footnote}{-2}", build.tex)
        first = build.tex.index(r"\stepcounter{footnote}\footnotetext{First note.}")
        second = build.tex.index(r"\stepcounter{footnote}\footnotetext{Second note.}")
        self.assertLess(first, second)

    def test_table_cell_undefined_footnote_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "undefined footnote: missing"):
            build_document(
                "+++ A\nHeader\nCell[^missing]\n+++\n",
                filename="test.mtx",
            )

    def test_no_host_allows_literals_and_page_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Value [$ 'ok' ] page [$ PAGE.CURRENT ].\n", encoding="utf-8")
            compile_file(source, no_host=True)
            tex = source.with_suffix(".tex").read_text(encoding="utf-8")
            self.assertIn("Value ok page", tex)
            self.assertIn(r"\thepage{}", tex)

    def test_no_host_rejects_user_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("$$$python\nx = 1\n$$$\nHello\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "disabled by --no-host"):
                compile_file(source, no_host=True)
            source.write_text("Value [$ 1 + 2 ].\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "disabled by --no-host"):
                compile_file(source, no_host=True)

    def test_forbidden_host_builtins_fail(self) -> None:
        forbidden = [
            "open('x')",
            "__import__('os')",
            "eval('1')",
            "exec('x=1')",
        ]
        for expr in forbidden:
            with self.subTest(expr=expr):
                with self.assertRaises(MarkTeXError):
                    build_document(f"[$ {expr} ]\n", filename="test.mtx")

    def test_strict_rejects_legacy_interp_fence(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("```python interp\nx = 1\n```\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "legacy"):
                compile_file(source, strict=True)

    def test_version_matches_pyproject(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(marktex.__version__, pyproject["project"]["version"])

    def test_examples_compile(self) -> None:
        for source in sorted(Path("examples").glob("*.mtx")):
            with self.subTest(source=source.name):
                result = compile_file(
                    source,
                    emits={ArtifactKind.TEX, ArtifactKind.AST, ArtifactKind.EIR, ArtifactKind.BACKEND_IR},
                    out_dir=Path(tempfile.mkdtemp()),
                )
                self.assertIn(ArtifactKind.TEX, result.artifacts)

    def test_invalid_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            with self.assertRaises(MarkTeXError):
                compile_file(source, target="xelatex")  # type: ignore[arg-type]

    def test_unmatched_scope_close_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unmatched scope close"):
            build_document("!!@ w\n", filename="test.mtx")

    def test_else_if_branch_selects_correct_body(self) -> None:
        build = build_document(
            "!? [$ False ]\nA\n!?!? [$ True ]\nB\n!?!? [$ False ]\nC\n!!?\n",
            filename="test.mtx",
        )
        self.assertIn("B", build.tex)
        self.assertNotIn("A", build.tex)
        self.assertNotIn("C", build.tex)

    def test_host_block_without_language_defaults_python(self) -> None:
        build = build_document("$$$\nname = 'Ada'\n$$$\nHello [$ name ].\n", filename="test.mtx")
        self.assertIn("Hello Ada.", build.tex)

    def test_non_python_host_block_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported host block language"):
            build_document("$$$ruby\nputs 'hi'\n$$$\n", filename="test.mtx")

    def test_unclosed_conditional_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unclosed conditional"):
            build_document("!? [$ True ]\nBody\n", filename="test.mtx")

    def test_rich_table_wrong_cell_count_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "rich table row has"):
            build_document("+++ A | B\nX\n+++\n", filename="test.mtx")

    def test_heading_inline_content_is_lowered(self) -> None:
        build = build_document("# Hello *World* and `code`\n", filename="test.mtx")
        self.assertIn(r"\section{Hello \emph{World} and \texttt{code}}", build.tex)

    def test_table_cell_inline_content_is_lowered(self) -> None:
        build = build_document("+++ A | B\nHeader | Value\n*em* | **bold**\n+++\n", filename="test.mtx")
        self.assertIn(r"\emph{em}", build.tex)
        self.assertIn(r"\textbf{bold}", build.tex)

    def test_heading_inline_diagnostic_span_points_to_token(self) -> None:
        with self.assertRaises(MarkTeXError) as caught:
            build_document("# Bad [$ PAGE.TOTAL - PAGE.CURRENT ]\n", filename="test.mtx")
        span = caught.exception.diagnostic.span
        self.assertIsNotNone(span)
        self.assertEqual((span.line, span.column), (1, 7))

    def test_table_inline_diagnostic_span_points_to_cell_token(self) -> None:
        with self.assertRaises(MarkTeXError) as caught:
            build_document(
                "+++ A\nBad [$ PAGE.TOTAL - PAGE.CURRENT ]\n+++\n",
                filename="test.mtx",
            )
        span = caught.exception.diagnostic.span
        self.assertIsNotNone(span)
        self.assertEqual((span.line, span.column), (2, 5))


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        return subprocess.run(
            [sys.executable, "-m", "marktex.cli", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_emit_pdf_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "--emit", "pdf")
            self.assertEqual(result.returncode, 2)
            self.assertIn("does not build PDFs", result.stderr)

    def test_stdout_single_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "-o", "-")
            self.assertEqual(result.returncode, 0)
            self.assertIn("\\begin{document}", result.stdout)

    def test_cli_custom_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            output = Path(raw_dir) / "custom.tex"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "-o", str(output))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(output.exists())

    def test_cli_emit_all_default_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "--emit", "all")
            self.assertEqual(result.returncode, 0)
            build_dir = Path(raw_dir) / "paper.mtxbuild"
            self.assertTrue((build_dir / "paper.host.py").exists())
            self.assertTrue((build_dir / "paper.ast.json").exists())
            self.assertTrue((build_dir / "paper.eir.json").exists())
            self.assertTrue((build_dir / "paper.backend-ir.json").exists())
            self.assertTrue((build_dir / "paper.tex").exists())

    def test_json_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!# unknown: value\n", encoding="utf-8")
            result = self.run_cli(str(source), "--diagnostic-format", "json")
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stderr)
            self.assertIn("unknown call head", payload["message"])
            self.assertIsNotNone(payload["span"])

    def test_cli_no_host(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("[$ 1 + 2 ]\n", encoding="utf-8")
            result = self.run_cli(str(source), "--no-host")
            self.assertEqual(result.returncode, 2)
            self.assertIn("disabled by --no-host", result.stderr)

    def test_cli_out_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            out_dir = Path(raw_dir) / "custom_out"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "--emit", "tex", "--out-dir", str(out_dir))
            self.assertEqual(result.returncode, 0)
            self.assertTrue((out_dir / "paper.tex").exists())


if __name__ == "__main__":
    unittest.main()
