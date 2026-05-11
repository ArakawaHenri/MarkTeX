from __future__ import annotations

import inspect
import os
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import marktex
import marktex.runtime as runtime
from marktex.bibliography import parse_bibtex_file, parse_bibliography_style, parse_citation_style
from marktex.core import Document
from marktex.driver import ArtifactKind, compile_file
from marktex.driver.compiler import build_document
from marktex.source import MarkTeXError


class DriverTests(unittest.TestCase):
    def test_default_compile_writes_lualatex_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("# Title\n\nHello [$ PAGE.CURRENT ].\n", encoding="utf-8")
            result = compile_file(source)
            output = directory / "paper.tex"
            self.assertEqual(result.written[ArtifactKind.TARGET], output)
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
                emits={ArtifactKind.AST, ArtifactKind.EIR, ArtifactKind.TARGET},
                out_dir=out_dir,
            )
            self.assertTrue((out_dir / "paper.ast.json").exists())
            self.assertTrue((out_dir / "paper.eir.json").exists())
            self.assertTrue((out_dir / "paper.tex").exists())

    def test_emit_all_includes_self_describing_pipeline_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("# Title\n\nHello\n", encoding="utf-8")
            result = compile_file(source, emits=set(ArtifactKind), out_dir=directory / "build")
            for kind in (
                ArtifactKind.SURFACE,
                ArtifactKind.AST,
                ArtifactKind.EIR,
                ArtifactKind.BACKEND_IR,
            ):
                artifact = json.loads(result.artifacts[kind])
                self.assertEqual(artifact["kind"], kind.value)
                self.assertIn("marktex_version", artifact)
                self.assertIn("artifact_version", artifact)
                self.assertIn("payload", artifact)
            self.assertIn("document_from_surface_artifact", result.artifacts[ArtifactKind.HOST])

    def test_from_host_emits_same_ast_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("# Title\n\nHello [$ PAGE.CURRENT ].\n", encoding="utf-8")
            first = compile_file(source, emits=set(ArtifactKind), out_dir=directory / "build")
            host_path = first.written[ArtifactKind.HOST]
            second = compile_file(
                host_path,
                from_stage="host",
                emits={ArtifactKind.AST, ArtifactKind.TARGET},
                out_dir=directory / "from-host",
            )
            self.assertEqual(
                json.loads(first.artifacts[ArtifactKind.AST])["payload"],
                json.loads(second.artifacts[ArtifactKind.AST])["payload"],
            )
            self.assertEqual(first.artifacts[ArtifactKind.TARGET], second.artifacts[ArtifactKind.TARGET])

    def test_from_ast_and_backend_ir_compile_without_mtx(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("# Title\n\nHello\n", encoding="utf-8")
            first = compile_file(source, emits=set(ArtifactKind), out_dir=directory / "build")
            source.unlink()
            ast_result = compile_file(
                first.written[ArtifactKind.AST],
                from_stage="ast",
                emits={ArtifactKind.BACKEND_IR, ArtifactKind.TARGET},
                out_dir=directory / "from-ast",
            )
            backend_result = compile_file(
                first.written[ArtifactKind.BACKEND_IR],
                from_stage="backend-ir",
                emits={ArtifactKind.TARGET},
                out_dir=directory / "from-backend-ir",
            )
            self.assertEqual(first.artifacts[ArtifactKind.TARGET], ast_result.artifacts[ArtifactKind.TARGET])
            self.assertEqual(first.artifacts[ArtifactKind.TARGET], backend_result.artifacts[ArtifactKind.TARGET])

    def test_backend_ir_is_self_contained_for_bibliography(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            refs = directory / "refs.bib"
            refs.write_text(
                "@book{Knuth84, author={Donald Knuth}, title={The TeXbook}, year={1984}}\n",
                encoding="utf-8",
            )
            style = directory / "all.mtxbs"
            style.write_text(
                "style: name=all; "
                "references: title=`All Sources`, include=all, sort=key, placement=inline, label=key; "
                "template: default, author, title, year;\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n!# bibstyle: all.mtxbs\nSee [^ cite: Knuth84 ].\n",
                encoding="utf-8",
            )
            first = compile_file(source, emits=set(ArtifactKind), out_dir=directory / "build")
            refs.unlink()
            style.unlink()
            result = compile_file(
                first.written[ArtifactKind.BACKEND_IR],
                from_stage="backend-ir",
                emits={ArtifactKind.TARGET},
                out_dir=directory / "from-backend-ir",
            )
            self.assertIn("Donald Knuth", result.artifacts[ArtifactKind.TARGET])
            self.assertIn("All Sources", result.artifacts[ArtifactKind.TARGET])

    def test_from_stage_requires_matching_artifact_kind(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            first = compile_file(source, emits=set(ArtifactKind), out_dir=directory / "build")
            with self.assertRaisesRegex(MarkTeXError, "expected ast artifact, got 'backend-ir'"):
                compile_file(
                    first.written[ArtifactKind.BACKEND_IR],
                    from_stage="ast",
                    emits={ArtifactKind.TARGET},
                )

    def test_from_host_with_no_host_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = directory / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            first = compile_file(source, emits={ArtifactKind.HOST}, out_dir=directory / "build")
            with self.assertRaisesRegex(MarkTeXError, "--from host cannot be used with --no-host"):
                compile_file(
                    first.written[ArtifactKind.HOST],
                    from_stage="host",
                    no_host=True,
                )

    def test_scope_close_is_not_parsed_as_scope_open(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!@ w\n!!@ w\nHello\n", encoding="utf-8")
            result = compile_file(source, emits={ArtifactKind.EIR})
            eir = json.loads(result.artifacts[ArtifactKind.EIR])["payload"]
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

    def test_host_block_runtime_event_affects_backend(self) -> None:
        build = build_document(
            "$$$python\n"
            "marktex.invoke(marktex.document_patch(\n"
            "    'layout',\n"
            "    marktex.call('Letter', context='layout.value', paper='letterpaper'),\n"
            "))\n"
            "$$$\n"
            "Hello\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[letterpaper]{geometry}", build.target_text)
        self.assertEqual(build.document.events[0].to_json()["call"]["head"], "layout")
        self.assertEqual(build.state.to_json()["events"][0]["object"]["call"]["head"], "layout")

    def test_host_runtime_events_do_not_leak_between_builds(self) -> None:
        first = build_document(
            "$$$python\nmarktex.invoke(marktex.document_patch('bibstyle', 'numeric'))\n$$$\n",
            filename="first.mtx",
        )
        self.assertEqual(len(first.document.events), 1)
        second = build_document("Hello\n", filename="second.mtx")
        self.assertEqual(second.document.events, ())

    def test_host_artifact_replays_events(self) -> None:
        build = build_document(
            "!# layout: A4, landscape\n"
            "!@ body: font=Times\n"
            "!!@ body\n"
            "Hello\n",
            filename="test.mtx",
        )
        namespace: dict[str, object] = {}
        exec(build.host_script, namespace)
        replayed = namespace["document"]
        self.assertIsInstance(replayed, Document)
        self.assertEqual([event.__class__.__name__ for event in replayed.events], ["DocumentPatch", "ScopePush", "ScopeClose"])
        self.assertEqual(replayed.events[0].call.head, "layout")
        self.assertEqual(replayed.events[1].key, "body")
        self.assertEqual(replayed.events[2].key, "body")
        self.assertEqual(replayed.blocks[0].to_json()["children"][0]["value"], "Hello")

    def test_host_artifact_is_canonical_construction_script(self) -> None:
        build = build_document(
            "$$$python\nmarktex.invoke(marktex.document_patch('bibstyle', 'numeric'))\n$$$\n",
            filename="test.mtx",
        )
        namespace: dict[str, object] = {}
        exec(build.host_script, namespace)
        document = namespace["document"]
        self.assertIsInstance(document, Document)
        self.assertEqual(len(document.events), 1)
        self.assertEqual(document.events[0].to_json()["call"]["head"], "bibstyle")

    def test_runtime_rejects_unsupported_invoked_object(self) -> None:
        session = runtime.RuntimeSession()
        with self.assertRaisesRegex(MarkTeXError, "unsupported runtime object"):
            session.invoke("not a MarkTeX event")

    def test_concrete_expression_is_inline_ast_part(self) -> None:
        build = build_document("Total [$ 1 + 2 ].\n", filename="test.mtx")
        paragraph = build.document.blocks[0]
        data = paragraph.to_json()
        self.assertEqual(data["children"][1]["kind"], "inline_expr")
        self.assertEqual(data["children"][1]["value"], 3)
        self.assertIn("Total 3.", build.target_text)

    def test_page_placeholders_lower_to_lualatex(self) -> None:
        build = build_document("Page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ].\n", filename="test.mtx")
        self.assertIn(r"\thepage{}", build.target_text)
        self.assertIn(r"\pageref{LastPage}", build.target_text)

    def test_interpolated_code_block_page_placeholder_lowers_to_lualatex(self) -> None:
        build = build_document(
            "```$python\nprint('page [$ PAGE.CURRENT ] of [$ PAGE.TOTAL ]')\n```\n",
            filename="test.mtx",
        )
        self.assertIn(r"\ttfamily\obeyspaces\obeylines", build.target_text)
        self.assertIn(r"\thepage{}", build.target_text)
        self.assertIn(r"\pageref{LastPage}", build.target_text)
        self.assertNotIn("PAGE.CURRENT", build.target_text)

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
        self.assertIn("Yes", build.target_text)
        self.assertNotIn("No", build.target_text)

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

    def test_lualatex_backend_supported_blocks(self) -> None:
        build = build_document(
            "!# layout: Letter, landscape\n"
            "# Title\n\n"
            "```python\nprint('hi')\n```\n\n"
            "+++ align=left | align=right\nName | Score\nAda | 98\n+++\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[letterpaper,landscape]{geometry}", build.target_text)
        self.assertIn(r"\section{Title}", build.target_text)
        self.assertIn(r"\begin{verbatim}", build.target_text)
        self.assertIn(r"\begin{tabular}", build.target_text)

    def test_basic_inline_fallback_lowers(self) -> None:
        build = build_document(
            "This is *em* and **strong** with `code` and [site](https://example.com).\n",
            filename="test.mtx",
        )
        self.assertIn(r"\emph{em}", build.target_text)
        self.assertIn(r"\textbf{strong}", build.target_text)
        self.assertIn(r"\texttt{code}", build.target_text)
        self.assertIn(r"\href{https://example.com}{site}", build.target_text)

    def test_image_fallback_lowers(self) -> None:
        build = build_document("Logo ![MarkTeX](logo.png).\n", filename="test.mtx")
        self.assertIn(r"\includegraphics{logo.png}", build.target_text)

    def test_markdown_derived_marktex_block_shapes_lower(self) -> None:
        build = build_document(
            "Setext Title\n"
            "============\n\n"
            "3. third\n"
            "4. fourth\n\n"
            "- [x] done\n"
            "- [ ] todo\n"
            "  - nested [$ PAGE.CURRENT ]\n\n"
            "> Quote with ~~strike~~.\n\n"
            "---\n",
            filename="test.mtx",
        )
        self.assertIn(r"\section{Setext Title}", build.target_text)
        self.assertIn(r"\begin{enumerate}", build.target_text)
        self.assertIn(r"\setcounter{enumi}{2}", build.target_text)
        self.assertIn(r"\item[{[x]}] done", build.target_text)
        self.assertIn(r"\item[{[ ]}] todo", build.target_text)
        self.assertIn(r"\thepage{}", build.target_text)
        self.assertIn(r"\begin{quote}", build.target_text)
        self.assertIn(r"\sout{strike}", build.target_text)
        self.assertIn(r"\usepackage[normalem]{ulem}", build.target_text)
        self.assertIn(r"\rule{\linewidth}{0.4pt}", build.target_text)

    def test_nested_ordered_list_uses_matching_latex_counter(self) -> None:
        build = build_document(
            "1. outer\n"
            "   3. inner\n",
            filename="test.mtx",
        )
        self.assertIn(r"\setcounter{enumii}{2}", build.target_text)
        self.assertNotIn(r"\setcounter{enumi}{2}", build.target_text)

    def test_ordered_list_beyond_lualatex_native_depth_fails(self) -> None:
        with self.assertRaisesRegex(
            MarkTeXError,
            "ordered list nesting deeper than LuaLaTeX backend supports",
        ):
            build_document(
                "1. a\n"
                "   1. b\n"
                "      1. c\n"
                "         1. d\n"
                "            1. e\n",
                filename="test.mtx",
            )

    def test_pipe_table_alignment_and_inline_marktex_lower(self) -> None:
        build = build_document(
            "| Left | Center | Right |\n"
            "| :--- | :----: | ----: |\n"
            "| [$ PAGE.CURRENT ] | two [^note] | ~~gone~~ |\n\n"
            "[^note]: Table note.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\begin{tabular}{l|c|r}", build.target_text)
        self.assertIn(r"\thepage{}", build.target_text)
        self.assertIn(r"two \footnotemark", build.target_text)
        self.assertIn(r"\stepcounter{footnote}\footnotetext{Table note.}", build.target_text)
        self.assertIn(r"\sout{gone}", build.target_text)

    def test_pipe_table_wrong_cell_count_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, r"pipe table row has 1 cells; expected 2"):
            build_document("| A | B |\n| - | - |\n| only |\n", filename="test.mtx")
        with self.assertRaisesRegex(MarkTeXError, r"pipe table row has 3 cells; expected 2"):
            build_document("| A | B |\n| - | - |\n| one | two | three |\n", filename="test.mtx")

    def test_fallback_fenced_code_unclosed_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unclosed code fence"):
            build_document("~~~python\nx = 1\n", filename="test.mtx")

    def test_reference_style_links_and_images_lower(self) -> None:
        build = build_document(
            "See [site][ref], [shortcut], and ![Logo][logo].\n\n"
            "[ref]: https://example.com\n"
            "[shortcut]: https://shortcut.example\n"
            "[logo]: assets/logo.pdf\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://example.com}{site}", build.target_text)
        self.assertIn(r"\href{https://shortcut.example}{shortcut}", build.target_text)
        self.assertIn(r"\includegraphics{assets/logo.pdf}", build.target_text)

    def test_conditional_link_reference_definition_does_not_leak(self) -> None:
        build = build_document(
            "!? [$ False ]\n"
            "[ref]: https://branch.example\n"
            "!!?\n"
            "Outside [x][ref].\n",
            filename="test.mtx",
        )
        self.assertNotIn(r"\href{https://branch.example}", build.target_text)
        self.assertIn("Outside [x][ref].", build.target_text)

    def test_root_link_reference_is_visible_in_child_containers(self) -> None:
        build = build_document(
            "[ref]: https://root.example\n\n"
            "- [item][ref]\n\n"
            "> [quote][ref]\n\n"
            "!? [$ True ]\n"
            "Branch [branch][ref].\n"
            "!!?\n",
            filename="test.mtx",
        )
        self.assertEqual(build.target_text.count(r"\href{https://root.example}"), 3)

    def test_conditional_link_reference_shadows_parent_inside_branch(self) -> None:
        build = build_document(
            "[ref]: https://root.example\n\n"
            "!? [$ True ]\n"
            "[ref]: https://branch.example\n"
            "Inside [x][ref].\n"
            "!!?\n"
            "Outside [x][ref].\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://branch.example}{x}", build.target_text)
        self.assertIn(r"\href{https://root.example}{x}", build.target_text)

    def test_reference_style_image_uses_scoped_definitions(self) -> None:
        build = build_document(
            "[logo]: root.pdf\n\n"
            "!? [$ True ]\n"
            "[logo]: branch.pdf\n"
            "![Local][logo]\n"
            "!!?\n"
            "![Root][logo]\n",
            filename="test.mtx",
        )
        self.assertIn(r"\includegraphics{branch.pdf}", build.target_text)
        self.assertIn(r"\includegraphics{root.pdf}", build.target_text)

    def test_line_breaks_and_backslash_escapes_lower(self) -> None:
        build = build_document(
            "line\n"
            "break\n"
            "space  \n"
            "break\n"
            "slash\\\n"
            "break\n"
            r"\aliteral"
            "\n"
            r"\*literal\*"
            "\n",
            filename="test.mtx",
        )
        paragraph = build.document.blocks[0].to_json()
        breaks = [child for child in paragraph["children"] if child["kind"] == "line_break"]
        self.assertEqual([item["hard"] for item in breaks], [True, True, True, True, True, True])
        self.assertIn(r"line\\break", build.target_text)
        self.assertIn(r"space  \\", build.target_text)
        self.assertIn("slashbreak", build.target_text)
        self.assertIn("aliteral", build.target_text)
        self.assertIn("*literal*", build.target_text)

    def test_autolink_and_raw_html_are_plain_text(self) -> None:
        build = build_document("<https://example.com>\n<div>raw</div>\n", filename="test.mtx")
        self.assertNotIn(r"\href{https://example.com}", build.target_text)
        self.assertIn("<https://example.com>", build.target_text)
        self.assertIn("<div>raw</div>", build.target_text)

    def test_footnote_and_citation_lower(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@book{Knuth84,\n"
                "  author = {Donald Knuth},\n"
                "  title = {The TeXbook},\n"
                "  year = {1984},\n"
                "  publisher = {Addison-Wesley}\n"
                "}\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n"
                "Claim[^note] and cite [^ cite: Knuth84, pages=12-15 ].\n\n"
                "[^note]: Footnote body.\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\footnote{Footnote body.}", build.target_text)
        self.assertIn("[1]", build.target_text)
        self.assertIn(r"\section*{References}", build.target_text)
        self.assertIn("Donald Knuth", build.target_text)

    def test_marktex_fallback_footnote_and_note_citation_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{Turing36,\n"
                "  author = {Alan Turing},\n"
                "  title = {On Computable Numbers},\n"
                "  journal = {Proceedings of the London Mathematical Society},\n"
                "  year = {1936}\n"
                "}\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n"
                "!# citestyle: chicago-notes\n"
                "Footnote[^note] and citation [^ cite: Turing36 ].\n\n"
                "[^note]: MarkTeX fallback footnote body.\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\footnote{MarkTeX fallback footnote body.}", build.target_text)
        self.assertIn(r"\footnote{Alan Turing. On Computable Numbers. 1936.}", build.target_text)

    def test_table_cell_note_citation_is_deferred_after_tabular(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{Turing36, author={Alan Turing}, title={On Computable Numbers}, year={1936}}\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n"
                "!# citestyle: chicago-notes\n"
                "+++ A | B\n"
                "Ref | Status\n"
                "[^ cite: Turing36 ] | ok\n"
                "+++\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\footnotemark & ok \\", build.target_text)
        self.assertIn(r"\stepcounter{footnote}\footnotetext{Alan Turing. On Computable Numbers. 1936.}", build.target_text)

    def test_citation_missing_bibliography_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text("", encoding="utf-8")
            source = directory / "paper.mtx"
            source.write_text("!# bib: refs.bib\nSee [^ cite: Missing ].\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "undefined bibliography entry: Missing"):
                build_document(source.read_text(encoding="utf-8"), filename=str(source))

    def test_at_reference_payload_is_unsupported(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported reference payload: @Knuth84"):
            build_document("See [^@Knuth84].\n", filename="test.mtx")

    def test_valid_footnote_label_still_lowers(self) -> None:
        build = build_document(
            "Claim[^note-1].\n\n[^note-1]: Footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Footnote body.}", build.target_text)

    def test_custom_bibliography_style_can_include_uncited_entries(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@book{Knuth84, author={Donald Knuth}, title={The TeXbook}, year={1984}}\n",
                encoding="utf-8",
            )
            (directory / "all.mtxbs").write_text(
                "style: name=all; "
                "references: title=`All Sources`, include=all, sort=key, placement=inline, label=key; "
                "template: default, author, title, year;\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text("!# bib: refs.bib\n!# bibstyle: all.mtxbs\nNo cite.\n", encoding="utf-8")
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\section*{All Sources}", build.target_text)
        self.assertIn("[Knuth84]", build.target_text)

    def test_bibtex_parser_reads_common_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                "@article{Turing36,\n"
                "  author = {Alan Turing},\n"
                "  title = {On {Computable} Numbers},\n"
                "  year = \"1936\"\n"
                "}\n",
                encoding="utf-8",
            )
            entry = parse_bibtex_file(path)[0]
        self.assertEqual(entry.key, "Turing36")
        self.assertEqual(entry.entry_type, "article")
        self.assertEqual(entry.fields["title"], "On Computable Numbers")

    def test_style_parsers_read_mos_style_files(self) -> None:
        citation = parse_citation_style(
            "style: name=custom; citation: mode=author-page, form=paren, locator-prefix=` `;",
            "custom.mtxcs",
        )
        bibliography = parse_bibliography_style(
            "style: name=custom; "
            "references: title=Sources, include=all, sort=key, placement=inline, label=key; "
            "template: default, author, title;",
            "custom.mtxbs",
        )
        self.assertEqual(citation.mode, "author-page")
        self.assertEqual(citation.locator_prefix, " ")
        self.assertEqual(bibliography.include, "all")
        self.assertEqual(bibliography.templates["default"], ("author", "title"))

    def test_table_cell_footnote_is_deferred_after_tabular(self) -> None:
        build = build_document(
            "+++ A | B\nHeader | Value\nCell[^note] | ok\n+++\n\n"
            "[^note]: Table footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"Cell\footnotemark & ok \\", build.target_text)
        self.assertIn(r"\addtocounter{footnote}{-1}", build.target_text)
        self.assertIn(r"\stepcounter{footnote}\footnotetext{Table footnote body.}", build.target_text)

    def test_multiple_table_cell_footnotes_defer_in_source_order(self) -> None:
        build = build_document(
            "+++ A | B\nHeader | Value\nFirst[^a] | Second[^b]\n+++\n\n"
            "[^a]: First note.\n"
            "[^b]: Second note.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\addtocounter{footnote}{-2}", build.target_text)
        first = build.target_text.index(r"\stepcounter{footnote}\footnotetext{First note.}")
        second = build.target_text.index(r"\stepcounter{footnote}\footnotetext{Second note.}")
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

    def test_interp_info_string_is_plain_code_language(self) -> None:
        build = build_document(
            "```python interp\nprint('[$ PAGE.CURRENT ]')\n```\n",
            filename="test.mtx",
        )
        self.assertIn(r"\begin{verbatim}", build.target_text)
        self.assertIn("[$ PAGE.CURRENT ]", build.target_text)
        self.assertNotIn(r"\ttfamily\obeyspaces\obeylines", build.target_text)

    def test_compile_file_has_no_strict_or_schema_parameters(self) -> None:
        parameters = inspect.signature(compile_file).parameters
        self.assertNotIn("strict", parameters)
        self.assertNotIn("schema_paths", parameters)

    def test_version_matches_pyproject(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(marktex.__version__, pyproject["project"]["version"])

    def test_examples_compile(self) -> None:
        for source in sorted(Path("examples").glob("*.mtx")):
            with self.subTest(source=source.name):
                result = compile_file(
                    source,
                    emits={
                        ArtifactKind.TARGET,
                        ArtifactKind.AST,
                        ArtifactKind.EIR,
                        ArtifactKind.BACKEND_IR,
                    },
                    out_dir=Path(tempfile.mkdtemp()),
                )
                self.assertIn(ArtifactKind.TARGET, result.artifacts)

    def test_invalid_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            target = "xelatex"
            with self.assertRaises(MarkTeXError):
                compile_file(source, target=target)

    def test_unmatched_scope_close_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unmatched scope close"):
            build_document("!!@ w\n", filename="test.mtx")

    def test_else_if_branch_selects_correct_body(self) -> None:
        build = build_document(
            "!? [$ False ]\nA\n!?!? [$ True ]\nB\n!?!? [$ False ]\nC\n!!?\n",
            filename="test.mtx",
        )
        self.assertIn("B", build.target_text)
        self.assertNotIn("A", build.target_text)
        self.assertNotIn("C", build.target_text)

    def test_host_block_without_language_defaults_python(self) -> None:
        build = build_document("$$$\nname = 'Ada'\n$$$\nHello [$ name ].\n", filename="test.mtx")
        self.assertIn("Hello Ada.", build.target_text)

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
        self.assertIn(r"\section{Hello \emph{World} and \texttt{code}}", build.target_text)

    def test_table_cell_inline_content_is_lowered(self) -> None:
        build = build_document("+++ A | B\nHeader | Value\n*em* | **bold**\n+++\n", filename="test.mtx")
        self.assertIn(r"\emph{em}", build.target_text)
        self.assertIn(r"\textbf{bold}", build.target_text)

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
            self.assertTrue((build_dir / "paper.surface.json").exists())
            self.assertTrue((build_dir / "paper.host.py").exists())
            self.assertTrue((build_dir / "paper.ast.json").exists())
            self.assertTrue((build_dir / "paper.eir.json").exists())
            self.assertTrue((build_dir / "paper.backend-ir.json").exists())
            self.assertTrue((build_dir / "paper.tex").exists())

    def test_cli_from_host(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            build_dir = Path(raw_dir) / "build"
            from_dir = Path(raw_dir) / "from-host"
            source.write_text("Hello\n", encoding="utf-8")
            first = self.run_cli(str(source), "--emit", "all", "--out-dir", str(build_dir))
            self.assertEqual(first.returncode, 0)
            second = self.run_cli(
                "--from",
                "host",
                str(build_dir / "paper.host.py"),
                "--emit",
                "target",
                "--out-dir",
                str(from_dir),
            )
            self.assertEqual(second.returncode, 0)
            self.assertTrue((from_dir / "paper.host.tex").exists())

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

    def test_cli_rejects_removed_strict_and_schema_flags(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            strict_result = self.run_cli(str(source), "--strict")
            self.assertEqual(strict_result.returncode, 2)
            self.assertIn("unrecognized arguments: --strict", strict_result.stderr)
            schema_result = self.run_cli(str(source), "--schema", "custom.toml")
            self.assertEqual(schema_result.returncode, 2)
            self.assertIn("unrecognized arguments: --schema", schema_result.stderr)
            tex_result = self.run_cli(str(source), "--emit", "tex")
            self.assertEqual(tex_result.returncode, 2)
            self.assertIn("unsupported emit artifact: tex", tex_result.stderr)

    def test_cli_out_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            out_dir = Path(raw_dir) / "custom_out"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(str(source), "--emit", "target", "--out-dir", str(out_dir))
            self.assertEqual(result.returncode, 0)
            self.assertTrue((out_dir / "paper.tex").exists())


if __name__ == "__main__":
    unittest.main()
