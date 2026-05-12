from __future__ import annotations

import contextvars
import inspect
import json
import os
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
from marktex.driver.artifacts import ARTIFACT_VERSION
from marktex.driver.compiler import build_document
from marktex.source import MarkTeXError


class DriverTests(unittest.TestCase):
    def test_default_compile_writes_lualatex_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source_dir = directory / "source"
            output_dir = directory / "output"
            source_dir.mkdir()
            output_dir.mkdir()
            output_dir = output_dir.resolve()
            source = source_dir / "paper.mtx"
            source.write_text("# Title\n\nHello [$ PAGE.CURRENT ].\n", encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(output_dir)
                result = compile_file(source)
            finally:
                os.chdir(previous)
            output = output_dir / "paper.tex"
            self.assertEqual(result.written[ArtifactKind.TARGET], output)
            self.assertFalse((source_dir / "paper.tex").exists())
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

    def test_ast_artifact_rejects_string_bool(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            artifact = {
                "kind": "ast",
                "marktex_version": marktex.__version__,
                "artifact_version": ARTIFACT_VERSION,
                "payload": {
                    "kind": "document",
                    "events": [],
                    "blocks": [
                        {
                            "kind": "paragraph",
                            "children": [{"kind": "line_break", "hard": "false", "origin": None}],
                            "origin": None,
                        }
                    ],
                    "footnotes": [],
                },
            }
            path = Path(raw_dir) / "bad.ast.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaisesRegex(MarkTeXError, "line break hard must be a boolean"):
                compile_file(path, from_stage="ast")

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
                    out_dir=directory / "no-host",
                )

    def test_scope_close_is_not_parsed_as_scope_open(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("!@ w\n!!@ w\nHello\n", encoding="utf-8")
            result = compile_file(source, emits={ArtifactKind.EIR}, out_dir=Path(raw_dir) / "build")
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

    def test_scope_target_parameter_is_validated_and_recorded(self) -> None:
        build = build_document("!@ w: theme: body;, scope=e\n!!@ w\n", filename="test.mtx")
        event = build.document.events[0].to_json()
        self.assertEqual(event["key"], "w")
        self.assertEqual(event["kwargs"]["scope"]["text"], "e")
        self.assertEqual(event["args"][0]["head"], "theme")
        self.assertEqual(build.state.to_json()["scopes"][0]["target"], "e")

    def test_scope_target_default_is_canonicalized(self) -> None:
        build = build_document("!@ w: scope=DEFAULT\n!!@ w\n", filename="test.mtx")
        event = build.document.events[0].to_json()
        self.assertNotIn("scope", event["kwargs"])
        self.assertEqual(build.state.to_json()["scopes"][0]["target"], "DEFAULT")

    def test_unknown_scope_target_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported scope target: aside"):
            build_document("!@ w: scope=aside\n", filename="test.mtx")

    def test_host_block_variable_visible_to_later_expression(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("$$$python\nname = 'Ada'\n$$$\nHello [$ name ].\n", encoding="utf-8")
            result = compile_file(source, out_dir=Path(raw_dir) / "build")
            tex = result.written[ArtifactKind.TARGET].read_text(encoding="utf-8")
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
        self.assertIn(r"\usepackage[paperwidth=8.5in,paperheight=11in]{geometry}", build.target_text)
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
        self.assertIn(r"\par\begingroup\ttfamily", build.target_text)
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
            result = compile_file(source, out_dir=Path(raw_dir) / "build")
            tex = result.written[ArtifactKind.TARGET].read_text(encoding="utf-8")
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
        self.assertIn(r"\usepackage[paperwidth=11in,paperheight=8.5in]{geometry}", build.target_text)
        self.assertIn(r"\section{Title}", build.target_text)
        self.assertIn(r"\par\begingroup\ttfamily", build.target_text)
        self.assertIn(r"\begin{tabular}", build.target_text)

    def test_layout_aliases_canonicalize_to_dimensions(self) -> None:
        shorthand = build_document("!# layout: A4\nHello\n", filename="test.mtx")
        explicit = build_document("!# layout: paper=a4paper\nHello\n", filename="test.mtx")
        keyword_alias = build_document("!# layout: paper=A4\nHello\n", filename="test.mtx")
        expected = r"\usepackage[paperwidth=210mm,paperheight=297mm]{geometry}"
        self.assertIn(expected, shorthand.target_text)
        self.assertIn(expected, explicit.target_text)
        self.assertIn(expected, keyword_alias.target_text)

    def test_escape_provenance_on_document_directive_keys_and_values(self) -> None:
        escaped_opener = build_document(r"\!# layout: A4" "\n", filename="test.mtx")
        self.assertEqual(escaped_opener.document.to_json()["blocks"][0]["kind"], "paragraph")
        self.assertIn(r"!\# layout: A4", escaped_opener.target_text)

        with self.assertRaisesRegex(MarkTeXError, "escaped MOS call head"):
            build_document(r"!# \layout: A4" "\n", filename="test.mtx")

        value = build_document(
            r"!# layout: paper=\A4, orientation=\landscape" "\nHello\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[paperwidth=297mm,paperheight=210mm]{geometry}", value.target_text)

    def test_layout_applies_size_before_orientation(self) -> None:
        build = build_document(
            "!# layout: width=100mm, height=200mm, orientation=landscape\nHello\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[paperwidth=200mm,paperheight=100mm]{geometry}", build.target_text)

    def test_layout_orientation_is_atomic_noop_when_already_matching(self) -> None:
        build = build_document(
            "!# layout: width=200mm, height=100mm, orientation=landscape\nHello\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[paperwidth=200mm,paperheight=100mm]{geometry}", build.target_text)

    def test_layout_orientation_compares_physical_units(self) -> None:
        build = build_document(
            "!# layout: width=8in, height=200mm, orientation=portrait\nHello\n",
            filename="test.mtx",
        )
        self.assertIn(r"\usepackage[paperwidth=200mm,paperheight=8in]{geometry}", build.target_text)
        with self.assertRaisesRegex(MarkTeXError, "cannot compare dimensions for orientation"):
            build_document("!# layout: width=10em, height=2in, orientation=landscape\nHello\n", filename="test.mtx")

    def test_margin_directive_lowers_to_geometry(self) -> None:
        build = build_document("!# margin: top=20pt, bottom=24pt\nHello\n", filename="test.mtx")
        self.assertIn("top=20pt", build.target_text)
        self.assertIn("bottom=24pt", build.target_text)

    def test_body_document_directive_delays_single_page_setup_until_next_content(self) -> None:
        build = build_document(
            "First\n"
            "!# layout: A5\n"
            "!# margin: top=20pt\n"
            "Second\n",
            filename="test.mtx",
        )
        self.assertEqual([block.to_json()["kind"] for block in build.document.blocks], ["paragraph", "page_setup", "paragraph"])
        self.assertEqual(build.target_text.count(r"\clearpage"), 1)
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm,top=20pt}", build.target_text)

    def test_body_config_document_directives_do_not_page_break(self) -> None:
        build = build_document(
            "First\n"
            "!# bibstyle: numeric\n"
            "!# citestyle: numeric\n"
            "Second\n",
            filename="test.mtx",
        )
        self.assertEqual([block.to_json()["kind"] for block in build.document.blocks], ["paragraph", "paragraph"])
        self.assertEqual([event.to_json()["call"]["head"] for event in build.document.events], ["bibstyle", "citestyle"])
        self.assertNotIn(r"\clearpage", build.target_text)

    def test_body_bibliography_resource_directive_does_not_page_break(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            (Path(raw_dir) / "refs.bib").write_text(
                "@book{Knuth84, author={Donald Knuth}, title={TeXbook}, year={1984}}\n",
                encoding="utf-8",
            )
            source.write_text("First\n!# bib: refs.bib\nSecond\n", encoding="utf-8")
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertEqual([block.to_json()["kind"] for block in build.document.blocks], ["paragraph", "paragraph"])
        self.assertEqual([event.to_json()["call"]["head"] for event in build.document.events], ["bib"])
        self.assertNotIn(r"\clearpage", build.target_text)

    def test_newpage_is_explicit_page_break_everywhere(self) -> None:
        head = build_document("!# newpage\nHello\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in head.document.blocks], ["page_break", "paragraph"])
        self.assertEqual(head.document.events, ())
        self.assertIn(r"\clearpage", head.target_text)

        tail = build_document("Hello\n!# newpage\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in tail.document.blocks], ["paragraph", "page_break"])
        self.assertIn(r"\clearpage", tail.target_text)

        only = build_document("!# newpage\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in only.document.blocks], ["page_break"])
        self.assertIn(r"\clearpage", only.target_text)

    def test_newpage_flushes_pending_page_setup(self) -> None:
        build = build_document("First\n!# layout: A5\n!# newpage\nSecond\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in build.document.blocks], ["paragraph", "page_setup", "paragraph"])
        self.assertEqual(build.target_text.count(r"\clearpage"), 1)
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm}", build.target_text)

    def test_newpage_merges_with_previous_empty_page_transition_only(self) -> None:
        repeated = build_document("First\n!# newpage\n!# newpage\nSecond\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in repeated.document.blocks], ["paragraph", "page_break", "paragraph"])
        self.assertEqual(repeated.target_text.count(r"\clearpage"), 1)

        following_setup = build_document(
            "First\n"
            "!# layout: A5\n"
            "!# newpage\n"
            "!# layout: Letter\n"
            "Second\n",
            filename="test.mtx",
        )
        self.assertEqual(
            [block.to_json()["kind"] for block in following_setup.document.blocks],
            ["paragraph", "page_setup", "page_setup", "paragraph"],
        )
        self.assertEqual(following_setup.target_text.count(r"\clearpage"), 2)
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm}", following_setup.target_text)
        self.assertIn(r"\newgeometry{paperwidth=8.5in,paperheight=11in}", following_setup.target_text)

    def test_newpage_is_not_a_document_event(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "newpage' is not a document event"):
            build_document(
                "$$$python\nmarktex.invoke(marktex.document_patch('newpage'))\n$$$\n",
                filename="test.mtx",
            )

    def test_branch_document_directive_creates_body_page_setup(self) -> None:
        build = build_document(
            "First\n"
            "!? [$ True ]\n"
            "!# layout: A5\n"
            "Second\n"
            "!!?\n",
            filename="test.mtx",
        )
        conditional = build.document.blocks[1].to_json()
        self.assertEqual([block["kind"] for block in conditional["branches"][0]["body"]], ["page_setup", "paragraph"])
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm}", build.target_text)

    def test_root_conditional_flushes_pending_page_setup(self) -> None:
        build = build_document(
            "First\n"
            "!# layout: A5\n"
            "!? [$ True ]\n"
            "Second\n"
            "!!?\n",
            filename="test.mtx",
        )
        self.assertEqual(
            [block.to_json()["kind"] for block in build.document.blocks],
            ["paragraph", "page_setup", "conditional"],
        )
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm}", build.target_text)

    def test_root_conditional_counts_as_content_before_later_page_setup(self) -> None:
        build = build_document(
            "!? [$ True ]\n"
            "First\n"
            "!!?\n"
            "!# layout: A5\n"
            "Second\n",
            filename="test.mtx",
        )
        self.assertEqual(
            [block.to_json()["kind"] for block in build.document.blocks],
            ["conditional", "page_setup", "paragraph"],
        )
        self.assertEqual(build.document.events, ())
        self.assertIn(r"\newgeometry{paperwidth=148mm,paperheight=210mm}", build.target_text)

    def test_branch_newpage_is_kept_even_without_following_content(self) -> None:
        build = build_document("!? [$ True ]\n!# newpage\n!!?\n", filename="test.mtx")
        conditional = build.document.blocks[0].to_json()
        self.assertEqual([block["kind"] for block in conditional["branches"][0]["body"]], ["page_break"])
        self.assertIn(r"\clearpage", build.target_text)

    def test_state_document_directives_inside_branch_are_diagnostics(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "document directive 'bibstyle' is not supported"):
            build_document("!? [$ True ]\n!# bibstyle: numeric\n!!?\n", filename="test.mtx")

    def test_root_only_nodes_inside_branch_are_diagnostics(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "host blocks are only supported at document root"):
            build_document(
                "!? [$ True ]\n"
                "$$$python\n"
                "value = 1\n"
                "$$$\n"
                "!!?\n",
                filename="test.mtx",
            )
        with self.assertRaisesRegex(MarkTeXError, "scope directives are only supported at document root"):
            build_document("!? [$ True ]\n!@ w\n!!?\n", filename="test.mtx")

    def test_fallback_footnote_definition_can_appear_inside_branch(self) -> None:
        build = build_document(
            "!? [$ True ]\n"
            "Branch[^note]\n"
            "[^note]: Branch note.\n"
            "!!?\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Branch note.}", build.target_text)

    def test_branch_page_setup_inherits_current_layout(self) -> None:
        build = build_document(
            "!# layout: Letter\n"
            "First\n"
            "!? [$ True ]\n"
            "!# margin: top=20pt\n"
            "Second\n"
            "!!?\n",
            filename="test.mtx",
        )
        self.assertIn(r"\newgeometry{paperwidth=8.5in,paperheight=11in,top=20pt}", build.target_text)

    def test_trailing_body_document_directive_does_not_emit_blank_page(self) -> None:
        build = build_document("First\n!# layout: A5\n", filename="test.mtx")
        self.assertEqual([block.to_json()["kind"] for block in build.document.blocks], ["paragraph"])
        self.assertNotIn(r"\clearpage", build.target_text)

    def test_invalid_layout_and_margin_values_fail(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported paper"):
            build_document("!# layout: paper=foo\nHello\n", filename="test.mtx")
        with self.assertRaisesRegex(MarkTeXError, "unsupported orientation"):
            build_document("!# layout: orientation=diagonal\nHello\n", filename="test.mtx")
        with self.assertRaisesRegex(MarkTeXError, "invalid top dimension"):
            build_document("!# margin: top=wide\nHello\n", filename="test.mtx")
        with self.assertRaisesRegex(MarkTeXError, "does not accept"):
            build_document("!# newpage: now\nHello\n", filename="test.mtx")

    def test_invalid_table_alignment_fails(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported table column alignment"):
            build_document("+++ align=middle\nHeader\nCell\n+++\n", filename="test.mtx")

    def test_basic_inline_fallback_lowers(self) -> None:
        build = build_document(
            "This is *em* and **strong** with `code` and [site](https://example.com).\n",
            filename="test.mtx",
        )
        self.assertIn(r"\emph{em}", build.target_text)
        self.assertIn(r"\textbf{strong}", build.target_text)
        self.assertIn(r"\texttt{code}", build.target_text)
        self.assertIn(r"\href{https://example.com}{site}", build.target_text)

    def test_inline_math_lowers_after_marktex_inline_syntax(self) -> None:
        build = build_document(
            'Value $x+y$ and host [$ "$" ] with code `$z$`.\n',
            filename="test.mtx",
        )
        paragraph = build.document.blocks[0].to_json()
        kinds = [child["kind"] for child in paragraph["children"]]
        self.assertIn("inline_math", kinds)
        self.assertIn("inline_expr", kinds)
        self.assertIn("inline_code", kinds)
        self.assertIn(r"\(x+y\)", build.target_text)
        self.assertIn(r"\$", build.target_text)
        self.assertIn(r"\texttt{\$z\$}", build.target_text)

    def test_unclosed_and_escaped_inline_math_are_plain_text(self) -> None:
        build = build_document(r"Price \$5 and $open." "\n", filename="test.mtx")
        paragraph = build.document.blocks[0].to_json()
        self.assertNotIn("inline_math", [child["kind"] for child in paragraph["children"]])
        self.assertIn(r"Price \$5 and \$open.", build.target_text)

    def test_inline_math_dollar_delimiter_edge_cases(self) -> None:
        build = build_document(
            r"Math $a \$ b$ and double $$ stays text."
            "\n",
            filename="test.mtx",
        )
        paragraph = build.document.blocks[0].to_json()
        math_nodes = [child for child in paragraph["children"] if child["kind"] == "inline_math"]
        self.assertEqual([node["body"] for node in math_nodes], [r"a \$ b"])
        self.assertIn(r"Math \(a \$ b\) and double \$\$ stays text.", build.target_text)

    def test_inline_math_does_not_reparse_host_expression_result(self) -> None:
        build = build_document('Host [$ "$x$" ] and math $x$.\n', filename="test.mtx")
        paragraph = build.document.blocks[0].to_json()
        kinds = [child["kind"] for child in paragraph["children"]]
        self.assertEqual(kinds.count("inline_expr"), 1)
        self.assertEqual(kinds.count("inline_math"), 1)
        self.assertIn(r"Host \$x\$ and math \(x\).", build.target_text)

    def test_inline_host_and_math_do_not_cross_physical_lines(self) -> None:
        build = build_document(
            "[$ 'hel\\\n"
            "lo' ]\n"
            "$hel\\\n"
            "lo$\n",
            filename="test.mtx",
        )
        paragraph = build.document.blocks[0].to_json()
        kinds = [child["kind"] for child in paragraph["children"]]
        self.assertNotIn("inline_expr", kinds)
        self.assertNotIn("inline_math", kinds)
        self.assertIn(r"[\$ 'hello' ]", build.target_text)
        self.assertIn(r"\$hello\$", build.target_text)

    def test_reference_delimiter_does_not_cross_physical_line(self) -> None:
        build = build_document(
            "[^note\\\n"
            "]\n\n"
            "[^note]: Real note.\n",
            filename="test.mtx",
        )
        paragraph = build.document.blocks[0].to_json()
        self.assertNotIn("footnote_ref", [child["kind"] for child in paragraph["children"]])
        self.assertIn(r"[\textasciicircum{}note]", build.target_text)
        self.assertNotIn(r"\footnote{Real note.}", build.target_text)

    def test_display_math_block_lowers_raw_body(self) -> None:
        build = build_document(
            "$$\n"
            "some_\\\n"
            "latex\n"
            "$$\n",
            filename="test.mtx",
        )
        self.assertEqual(build.document.blocks[0].to_json()["kind"], "math_block")
        self.assertIn("\\[\nsome_\\\nlatex\n\\]", build.target_text)

    def test_display_math_body_keeps_owned_language_text_raw(self) -> None:
        build = build_document(
            "$$\n"
            "[$ PAGE.CURRENT ]\n"
            "x\\\n"
            "y\n"
            "$$\n",
            filename="test.mtx",
        )
        block = build.document.blocks[0].to_json()
        self.assertEqual(block["kind"], "math_block")
        self.assertEqual(block["body"], "[$ PAGE.CURRENT ]\nx\\\ny\n")
        self.assertIn("[$ PAGE.CURRENT ]\nx\\\ny", build.target_text)
        self.assertNotIn(r"\thepage{}", build.target_text)

    def test_display_math_requires_exact_column_one_marker(self) -> None:
        indented = build_document("  $$\nx\n  $$\n", filename="test.mtx")
        same_line = build_document("$$ x $$\n", filename="test.mtx")
        trailing_space = build_document("$$ \nx\n$$ \n", filename="test.mtx")
        self.assertNotEqual(indented.document.blocks[0].to_json()["kind"], "math_block")
        self.assertNotEqual(same_line.document.blocks[0].to_json()["kind"], "math_block")
        self.assertNotEqual(trailing_space.document.blocks[0].to_json()["kind"], "math_block")
        with self.assertRaisesRegex(MarkTeXError, "unclosed math block"):
            build_document("$$\nx\n", filename="test.mtx")

    def test_control_mos_payload_supports_line_continuation(self) -> None:
        build = build_document("!# layout: \\\nA4\nHello\n", filename="test.mtx")
        self.assertIn(r"\usepackage[paperwidth=210mm,paperheight=297mm]{geometry}", build.target_text)

    def test_condition_payload_does_not_use_mos_line_continuation(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, r"conditional condition must be a \[\$ \.\.\. \]"):
            build_document(
                "!? [$ True \\\n"
                "]\n"
                "Visible\n"
                "!!?\n",
                filename="test.mtx",
            )

    def test_host_fence_wins_over_display_math_prefix(self) -> None:
        build = build_document(
            "$$$python\n"
            'value = "a" \\\n'
            '    "b"\n'
            "$$$\n"
            "[$ value ]\n",
            filename="test.mtx",
        )
        self.assertEqual(build.document.blocks[0].to_json()["children"][0]["value"], "ab")
        self.assertNotIn("math_block", [block.to_json()["kind"] for block in build.document.blocks])

    def test_image_fallback_lowers(self) -> None:
        build = build_document("Logo ![MarkTeX](logo.png).\n", filename="test.mtx")
        self.assertIn(r"\includegraphics{logo.png}", build.target_text)

    def test_marktex_fallback_block_shapes_lower(self) -> None:
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

    def test_list_control_sequence_preserves_extra_content_space(self) -> None:
        build = build_document("- x\n-  y\n- \n-\n", filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual(blocks[0]["kind"], "list")
        items = blocks[0]["items"]
        self.assertEqual(items[0]["children"][0]["children"][0]["value"], "x")
        self.assertEqual(items[1]["children"][0]["children"][0]["value"], " y")
        self.assertEqual(items[2]["children"], [])
        self.assertEqual(blocks[1]["children"][0]["value"], "-")

    def test_list_indent_unit_is_derived_by_gcd(self) -> None:
        two_spaces = build_document("- parent\n  - child\n", filename="test.mtx")
        three_spaces = build_document("- parent\n   - child\n", filename="test.mtx")
        four_spaces = build_document("- parent\n    - child\n", filename="test.mtx")
        for build in (two_spaces, three_spaces, four_spaces):
            outer = build.document.to_json()["blocks"][0]
            self.assertEqual(outer["items"][0]["children"][1]["kind"], "list")
            self.assertIn(r"\begin{itemize}", build.target_text)

    def test_list_indent_cannot_skip_levels(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "list nesting cannot skip levels"):
            build_document("- parent\n  - child\n      - grandchild\n", filename="test.mtx")

    def test_invalid_list_continuation_is_not_consumed(self) -> None:
        build = build_document("- item\n continuation\n  - not nested\n", filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual([block["kind"] for block in blocks], ["list", "paragraph", "paragraph"])
        self.assertEqual(blocks[1]["children"][0]["value"], " continuation")
        self.assertEqual(blocks[2]["children"][0]["value"], "  - not nested")

    def test_list_indent_cannot_mix_tabs_and_spaces(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "list indentation cannot mix tabs and spaces"):
            build_document("- parent\n \t- child\n", filename="test.mtx")

    def test_same_ordered_block_requires_sequential_markers(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "ordered list marker must be 2"):
            build_document("1. first\n3. third\n", filename="test.mtx")

    def test_task_control_sequence_preserves_extra_content_space(self) -> None:
        build = build_document("- [x]  done\n- [ ]  todo\n", filename="test.mtx")
        items = build.document.to_json()["blocks"][0]["items"]
        self.assertEqual(items[0]["children"][0]["children"][0]["value"], " done")
        self.assertEqual(items[1]["children"][0]["children"][0]["value"], " todo")

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
            "list nesting deeper than LuaLaTeX backend supports",
        ):
            build_document(
                "1. a\n"
                "   1. b\n"
                "      1. c\n"
                "         1. d\n"
                "            1. e\n",
                filename="test.mtx",
            )

    def test_unordered_list_beyond_lualatex_native_depth_fails(self) -> None:
        with self.assertRaisesRegex(
            MarkTeXError,
            "list nesting deeper than LuaLaTeX backend supports",
        ):
            build_document(
                "- a\n"
                "  - b\n"
                "    - c\n"
                "      - d\n"
                "        - e\n",
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

    def test_pipe_table_consumes_one_padding_space_only(self) -> None:
        build = build_document("| A |\n| --- |\n| x |\n|  y  |\n", filename="test.mtx")
        table = build.document.to_json()["blocks"][0]
        self.assertEqual(table["rows"][0][0][0]["value"], "x")
        self.assertEqual(table["rows"][1][0][0]["value"], " y ")

    def test_pipe_table_only_escapes_literal_pipe_during_split(self) -> None:
        build = build_document("| A |\n| --- |\n| a\\|b |\n| \\*literal\\* |\n", filename="test.mtx")
        rows = build.document.to_json()["blocks"][0]["rows"]
        self.assertEqual(rows[0][0][0]["value"], "a|b")
        self.assertEqual([node["value"] for node in rows[1][0]], ["*", "literal", "*"])
        self.assertIn("*literal*", build.target_text)

    def test_tilde_fence_is_plain_fallback_text(self) -> None:
        build = build_document("~~~python\nx = 1\n", filename="test.mtx")
        paragraph = build.document.to_json()["blocks"][0]
        self.assertEqual(paragraph["kind"], "paragraph")
        self.assertEqual(
            "".join(child.get("value", "\n") for child in paragraph["children"]),
            "~~~python\nx = 1",
        )

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

    def test_link_titles_are_unsupported(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "unsupported link title"):
            build_document('[site](https://example.com "title")\n', filename="test.mtx")
        with self.assertRaisesRegex(MarkTeXError, "unsupported link title"):
            build_document("[ref]: https://example.com title\n\n[site][ref]\n", filename="test.mtx")

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
            "- [item][ref]\n\n"
            "> [quote][ref]\n\n"
            "!? [$ True ]\n"
            "Branch [branch][ref].\n"
            "!!?\n\n"
            "[ref]: https://root.example\n",
            filename="test.mtx",
        )
        self.assertEqual(build.target_text.count(r"\href{https://root.example}"), 3)

    def test_conditional_link_reference_shadows_parent_inside_branch(self) -> None:
        build = build_document(
            "!? [$ True ]\n"
            "Inside [x][ref].\n"
            "[ref]: https://branch.example\n"
            "!!?\n"
            "Outside [x][ref].\n\n"
            "[ref]: https://root.example\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://branch.example}{x}", build.target_text)
        self.assertIn(r"\href{https://root.example}{x}", build.target_text)

    def test_reference_style_image_uses_scoped_definitions(self) -> None:
        build = build_document(
            "!? [$ True ]\n"
            "![Local][logo]\n"
            "[logo]: branch.pdf\n"
            "!!?\n"
            "![Root][logo]\n\n"
            "[logo]: root.pdf\n",
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
                "+++ align=left | align=left\n"
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

    def test_at_reference_payload_is_plain_footnote_label(self) -> None:
        build = build_document(
            "See [^@Knuth84].\n\n[^@Knuth84]: At-sign footnote.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{At-sign footnote.}", build.target_text)

    def test_valid_footnote_label_still_lowers(self) -> None:
        build = build_document(
            "Claim[^note-1].\n\n[^note-1]: Footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Footnote body.}", build.target_text)

    def test_citation_soft_parse_falls_back_to_footnote_label(self) -> None:
        build = build_document(
            "A[^cite]. B[^ cite:]. C[^\\cite: Knuth84].\n\n"
            "[^cite]: Bare cite label.\n"
            "[^ cite:]: Missing-key cite label.\n"
            "[^\\cite: Knuth84]: Escaped cite label.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Bare cite label.}", build.target_text)
        self.assertIn(r"\footnote{Missing-key cite label.}", build.target_text)
        self.assertIn(r"\footnote{Escaped cite label.}", build.target_text)

    def test_marktex_citation_line_is_not_fallback_footnote_definition(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@book{Knuth84, author={Donald Knuth}, title={The TeXbook}, year={1984}}\n",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n"
                "[^cite: Knuth84]: This is paragraph text, not a footnote definition.\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertEqual(build.document.footnotes, ())
        paragraph = build.document.to_json()["blocks"][0]
        self.assertEqual(paragraph["children"][0]["kind"], "citation")
        self.assertEqual(paragraph["children"][1]["value"], ": This is paragraph text, not a footnote definition.")
        self.assertIn("[1]: This is paragraph text", build.target_text)

    def test_marktex_inline_island_prevents_fallback_link_definition(self) -> None:
        build = build_document('[$ "label" ]: https://example.com\n[label]\n', filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["children"][0]["kind"], "inline_expr")
        self.assertEqual(blocks[0]["children"][1]["value"], ": https://example.com")
        self.assertIn("[label]", build.target_text)
        self.assertNotIn(r"\href{https://example.com}", build.target_text)

    def test_fallback_formatting_can_contain_marktex_inline_islands(self) -> None:
        build = build_document(
            "**before $x + y$ and [$ 1 + 1 ] after**\n",
            filename="test.mtx",
        )
        strong = build.document.to_json()["blocks"][0]["children"][0]
        self.assertEqual(strong["kind"], "strong")
        self.assertEqual(
            [child["kind"] for child in strong["children"]],
            ["text", "inline_math", "text", "inline_expr", "text"],
        )

    def test_direct_link_text_can_contain_marktex_inline_islands(self) -> None:
        build = build_document("[see $x$](https://example.com)\n", filename="test.mtx")
        link = build.document.to_json()["blocks"][0]["children"][0]
        self.assertEqual(link["kind"], "link")
        self.assertEqual([child["kind"] for child in link["children"]], ["text", "inline_math"])

    def test_surface_artifact_contains_typed_inline_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "paper.mtx"
            path.write_text("**bold $x$**\n", encoding="utf-8")
            result = compile_file(path, emits={ArtifactKind.SURFACE}, out_dir=Path(raw_dir) / "build")
            artifact = json.loads(result.artifacts[ArtifactKind.SURFACE])
        paragraph = artifact["payload"]["nodes"][0]
        self.assertEqual(paragraph["kind"], "paragraph")
        self.assertEqual(paragraph["children"][0]["kind"], "strong")
        self.assertEqual(
            [child["kind"] for child in paragraph["children"][0]["children"]],
            ["text", "inline_math"],
        )

    def test_footnote_label_allows_escaped_closing_bracket(self) -> None:
        build = build_document(
            "Claim[^ a\\]b].\n\n[^ a\\]b]: Escaped bracket label.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Escaped bracket label.}", build.target_text)

    def test_footnote_definition_body_can_contain_marktex_inline_islands(self) -> None:
        build = build_document(
            "Claim[^n].\n\n[^n]: Body $x$ and [$ 1 + 1 ].\n",
            filename="test.mtx",
        )
        footnote = build.document.to_json()["footnotes"][0]
        self.assertEqual(
            [child["kind"] for child in footnote["children"]],
            ["text", "inline_math", "text", "inline_expr", "text"],
        )

    def test_escaped_citation_keyword_can_define_ordinary_footnote(self) -> None:
        build = build_document(
            "Claim[^\\cite: Knuth84].\n\n"
            "[^\\cite: Knuth84]: Escaped citation keywords fall back to ordinary footnotes.\n",
            filename="test.mtx",
        )
        self.assertIn(r"\footnote{Escaped citation keywords fall back to ordinary footnotes.}", build.target_text)

    def test_fallback_declarations_must_be_tail_of_scope(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "fallback declarations must appear after all content"):
            build_document(
                "Use [project][project].\n\n"
                "[project]: https://example.com/marktex\n"
                "More content.\n",
                filename="test.mtx",
            )
        with self.assertRaisesRegex(MarkTeXError, "fallback declarations must appear after all content"):
            build_document(
                "!? [$ True ]\n"
                "Claim[^n].\n"
                "[^n]: Branch note.\n"
                "More branch content.\n"
                "!!?\n",
                filename="test.mtx",
            )

    def test_escaped_and_indented_declarations_are_literal_text(self) -> None:
        build = build_document(
            "\\[project]: https://example.com/marktex\n"
            " [other]: https://example.com/other\n"
            "[project]\n",
            filename="test.mtx",
        )
        values = "".join(
            child["value"]
            for child in build.document.to_json()["blocks"][0]["children"]
            if child["kind"] == "text"
        )
        self.assertIn("[project]: https://example.com/marktex", values)
        self.assertIn(" [other]: https://example.com/other", values)
        self.assertIn("[project]", values)
        self.assertNotIn(r"\href{https://example.com/marktex}", build.target_text)

    def test_empty_reference_payload_is_plain_text(self) -> None:
        build = build_document("[^]\n", filename="test.mtx")
        self.assertEqual(build.document.to_json()["blocks"][0]["children"][0]["value"], "[^]")

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

    def test_citation_style_rejects_invalid_mode_form_pairs(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "requires mode note"):
            parse_citation_style("style: name=s; citation: mode=numeric, form=footnote;", "bad.mtxcs")
        with self.assertRaisesRegex(MarkTeXError, "requires form footnote"):
            parse_citation_style("style: name=s; citation: mode=note, form=square;", "bad.mtxcs")
        note = parse_citation_style("style: name=s; citation: mode=note;", "note.mtxcs")
        self.assertEqual(note.form, "footnote")

    def test_table_cell_footnote_is_deferred_after_tabular(self) -> None:
        build = build_document(
            "+++ align=left | align=left\nHeader | Value\nCell[^note] | ok\n+++\n\n"
            "[^note]: Table footnote body.\n",
            filename="test.mtx",
        )
        self.assertIn(r"Cell\footnotemark & ok \\", build.target_text)
        self.assertIn(r"\addtocounter{footnote}{-1}", build.target_text)
        self.assertIn(r"\stepcounter{footnote}\footnotetext{Table footnote body.}", build.target_text)

    def test_multiple_table_cell_footnotes_defer_in_source_order(self) -> None:
        build = build_document(
            "+++ align=left | align=left\nHeader | Value\nFirst[^a] | Second[^b]\n+++\n\n"
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
                "+++ align=left\nHeader\nCell[^missing]\n+++\n",
                filename="test.mtx",
            )

    def test_no_host_allows_literals_and_page_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Value [$ 'ok' ] page [$ PAGE.CURRENT ].\n", encoding="utf-8")
            result = compile_file(source, no_host=True, out_dir=Path(raw_dir) / "build")
            tex = result.written[ArtifactKind.TARGET].read_text(encoding="utf-8")
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
        self.assertIn(r"\par\begingroup\ttfamily", build.target_text)
        self.assertIn(r"[\$\ PAGE.CURRENT\ ]", build.target_text)
        self.assertNotIn(r"\ttfamily\obeyspaces\obeylines", build.target_text)

    def test_plain_and_interpolated_code_blocks_share_indentation_renderer(self) -> None:
        build = build_document(
            "```python\n"
            "def f():\n"
            "    return 1\n"
            "```\n\n"
            "```$python\n"
            "def f():\n"
            "    return [$ 1 ]\n"
            "```\n",
            filename="test.mtx",
        )
        self.assertNotIn(r"\begin{verbatim}", build.target_text)
        self.assertNotIn(r"\ttfamily\obeyspaces\obeylines", build.target_text)
        self.assertEqual(build.target_text.count(r"\noindent\strut \ \ \ \ return\ 1\par"), 2)

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
            build_document("+++ align=left | align=left\nX\n+++\n", filename="test.mtx")

    def test_heading_inline_content_is_lowered(self) -> None:
        build = build_document("# Hello *World* and `code`\n", filename="test.mtx")
        self.assertIn(r"\section{Hello \emph{World} and \texttt{code}}", build.target_text)

    def test_table_cell_inline_content_is_lowered(self) -> None:
        build = build_document("+++ align=left | align=left\nHeader | Value\n*em* | **bold**\n+++\n", filename="test.mtx")
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
                "+++ align=left\nBad [$ PAGE.TOTAL - PAGE.CURRENT ]\n+++\n",
                filename="test.mtx",
            )
        span = caught.exception.diagnostic.span
        self.assertIsNotNone(span)
        self.assertEqual((span.line, span.column), (2, 5))


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        repo = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo / "src")
        return subprocess.run(
            [sys.executable, "-m", "marktex.cli", *args],
            cwd=cwd or repo,
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
            result = self.run_cli(str(source), "--emit", "all", cwd=Path(raw_dir))
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

    def test_cli_finite_options_are_trimmed(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source = Path(raw_dir) / "paper.mtx"
            source.write_text("Hello\n", encoding="utf-8")
            result = self.run_cli(
                "--from",
                " mtx ",
                "--target",
                " lualatex ",
                "--emit",
                " target ",
                "--diagnostic-format",
                " text ",
                str(source),
                cwd=Path(raw_dir),
            )
            self.assertEqual(result.returncode, 0)
            self.assertTrue((Path(raw_dir) / "paper.tex").exists())


class FallbackSyntaxTests(unittest.TestCase):
    def test_setext_heading_h1_lowers(self) -> None:
        build = build_document("Title\n=====\n\nBody\n", filename="test.mtx")
        self.assertIn(r"\section{Title}", build.target_text)

    def test_setext_heading_h2_lowers(self) -> None:
        build = build_document("Subtitle\n--------\n\nBody\n", filename="test.mtx")
        self.assertIn(r"\subsection{Subtitle}", build.target_text)

    def test_thematic_break_lowers(self) -> None:
        build = build_document("Before\n\n---\n\nAfter\n", filename="test.mtx")
        self.assertIn(r"\par\noindent\rule{\linewidth}{0.4pt}\par", build.target_text)

    def test_backtick_code_fence_is_marktex_owned_language_block(self) -> None:
        build = build_document("```\n# literal\n[^note]: literal\n```\n", filename="test.mtx")
        self.assertEqual(build.document.to_json()["blocks"][0]["kind"], "code_block")
        self.assertEqual(build.document.footnotes, ())
        self.assertIn(r"\#\ literal", build.target_text)

    def test_tilde_fence_is_plain_paragraph_text(self) -> None:
        build = build_document("~~~\ncode block\n~~~\n", filename="test.mtx")
        paragraph = build.document.to_json()["blocks"][0]
        self.assertEqual(paragraph["kind"], "paragraph")
        self.assertEqual(
            "".join(child.get("value", "\n") for child in paragraph["children"]),
            "~~~\ncode block\n~~~",
        )
        self.assertNotIn(r"\par\begingroup\ttfamily", build.target_text)

    def test_indented_code_is_plain_paragraph_text(self) -> None:
        build = build_document("    indented code\n", filename="test.mtx")
        self.assertEqual(build.document.to_json()["blocks"][0]["kind"], "paragraph")
        self.assertEqual(build.document.to_json()["blocks"][0]["children"][0]["value"], "    indented code")
        self.assertNotIn(r"\par\begingroup\ttfamily", build.target_text)

    def test_blockquote_lowers(self) -> None:
        build = build_document("> Quoted text\n", filename="test.mtx")
        self.assertIn(r"\begin{quote}", build.target_text)
        self.assertIn("Quoted text", build.target_text)
        self.assertIn(r"\end{quote}", build.target_text)

    def test_blockquote_control_sequence_is_exact(self) -> None:
        build = build_document(" > not quote\n>x\n>\n", filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual(blocks[0]["kind"], "paragraph")
        self.assertEqual(
            [child.get("value") for child in blocks[0]["children"] if child["kind"] == "text"],
            [" > not quote", ">x"],
        )
        self.assertEqual(blocks[1]["kind"], "blockquote")
        self.assertEqual(blocks[1]["children"], [])

    def test_fallback_controls_are_current_column_exact(self) -> None:
        build = build_document(" # Heading\n  ```\nnot code\n  ```\n - item\n- item\n", filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual(blocks[0]["kind"], "paragraph")
        self.assertEqual(blocks[1]["kind"], "paragraph")
        self.assertEqual(blocks[1]["children"][0]["value"], " - item")
        self.assertEqual(blocks[2]["kind"], "list")
        self.assertIn(r" \# Heading", build.target_text)
        self.assertNotIn(r"\section{Heading}", build.target_text)
        self.assertNotIn(r"\par\begingroup\ttfamily", build.target_text)

    def test_escaped_fallback_control_openers_are_plain_text(self) -> None:
        build = build_document(
            r"\# Heading" "\n"
            r"\- item" "\n"
            r"\> quote" "\n"
            r"\---" "\n",
            filename="test.mtx",
        )
        blocks = build.document.to_json()["blocks"]
        self.assertEqual([block["kind"] for block in blocks], ["paragraph"])
        parts = [
            child["value"] if child["kind"] == "text" else "\n"
            for child in blocks[0]["children"]
        ]
        self.assertEqual("".join(parts), "# Heading\n- item\n> quote\n---")
        self.assertNotIn(r"\section{Heading}", build.target_text)
        self.assertNotIn(r"\begin{itemize}", build.target_text)
        self.assertNotIn(r"\begin{quote}", build.target_text)

    def test_atx_heading_consumes_only_control_space(self) -> None:
        build = build_document("#  Title ###\n#Title\n", filename="test.mtx")
        blocks = build.document.to_json()["blocks"]
        self.assertEqual(blocks[0]["kind"], "heading")
        self.assertEqual(blocks[0]["children"][0]["value"], " Title ###")
        self.assertEqual(blocks[1]["kind"], "paragraph")
        self.assertEqual(blocks[1]["children"][0]["value"], "#Title")

    def test_thematic_break_is_exact(self) -> None:
        exact = build_document("---\n", filename="test.mtx")
        spaced = build_document("-- -\n", filename="test.mtx")
        self.assertEqual(exact.document.to_json()["blocks"][0]["kind"], "thematic_break")
        self.assertEqual(spaced.document.to_json()["blocks"][0]["kind"], "paragraph")

    def test_checked_task_list_item_lowers(self) -> None:
        build = build_document("- [x] Done item\n", filename="test.mtx")
        self.assertIn(r"\item[{[x]}]", build.target_text)
        self.assertIn("Done item", build.target_text)

    def test_unchecked_task_list_item_lowers(self) -> None:
        build = build_document("- [ ] Todo item\n", filename="test.mtx")
        self.assertIn(r"\item[{[ ]}]", build.target_text)
        self.assertIn("Todo item", build.target_text)

    def test_pipe_table_center_alignment(self) -> None:
        build = build_document(
            "| A |\n| :---: |\n| x |\n",
            filename="test.mtx",
        )
        self.assertIn("{c}", build.target_text)

    def test_pipe_table_right_alignment(self) -> None:
        build = build_document(
            "| A |\n| ---: |\n| x |\n",
            filename="test.mtx",
        )
        self.assertIn("{r}", build.target_text)

    def test_pipe_table_mixed_alignments(self) -> None:
        build = build_document(
            "| L | C | R |\n| :--- | :---: | ---: |\n| a | b | c |\n",
            filename="test.mtx",
        )
        self.assertIn("l", build.target_text)
        self.assertIn("c", build.target_text)
        self.assertIn("r", build.target_text)

    def test_escaped_pipe_in_pipe_table_cell(self) -> None:
        build = build_document(
            "| A |\n| --- |\n| a\\|b |\n",
            filename="test.mtx",
        )
        self.assertIn("a|b", build.target_text)

    def test_link_reference_definition_resolves_inline_link(self) -> None:
        build = build_document(
            "[link text][myref]\n\n[myref]: https://example.com\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://example.com}", build.target_text)
        self.assertIn("link text", build.target_text)

    def test_reference_link_labels_and_targets_use_escape_provenance(self) -> None:
        build = build_document(
            "[link][a\\]b]\n\n[a\\]b]: https://example\\.com\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://example.com}{link}", build.target_text)


class InlineParserTests(unittest.TestCase):
    def test_double_underscore_strong_lowers(self) -> None:
        build = build_document("__bold text__\n", filename="test.mtx")
        self.assertIn(r"\textbf{bold text}", build.target_text)

    def test_underscore_emphasis_lowers(self) -> None:
        build = build_document("_italic text_\n", filename="test.mtx")
        self.assertIn(r"\emph{italic text}", build.target_text)

    def test_inline_image_lowers(self) -> None:
        build = build_document("![alt text](figure.pdf)\n", filename="test.mtx")
        self.assertIn(r"\includegraphics{figure.pdf}", build.target_text)

    def test_strikethrough_lowers(self) -> None:
        build = build_document("~~struck~~\n", filename="test.mtx")
        self.assertIn(r"\sout{struck}", build.target_text)
        self.assertIn(r"\usepackage[normalem]{ulem}", build.target_text)

    def test_backslash_at_end_of_paragraph_is_literal(self) -> None:
        # Trailing backslash with no following character hits the else branch
        build = build_document("text\\\n", filename="test.mtx")
        self.assertIn("text", build.target_text)

    def test_code_span_space_stripping(self) -> None:
        # A code span with a leading and trailing space and non-blank interior
        build = build_document("`` ` code ` ``\n", filename="test.mtx")
        self.assertIn(r"\texttt{` code `}", build.target_text)

    def test_code_span_is_physical_line_local(self) -> None:
        build = build_document("`a\nb`\n", filename="test.mtx")
        self.assertNotIn(r"\texttt{a b}", build.target_text)
        self.assertIn("`a", build.target_text)
        self.assertIn("b`", build.target_text)

    def test_formatting_delimiters_are_mechanical_and_line_local(self) -> None:
        build = build_document("a_b_c\n*a\nb*\n~~a\nb~~\n", filename="test.mtx")
        paragraph = build.document.to_json()["blocks"][0]
        self.assertEqual(paragraph["children"][1]["kind"], "emphasis")
        self.assertNotIn(r"\emph{a\\b}", build.target_text)
        self.assertNotIn(r"\sout{a\\b}", build.target_text)

    def test_reference_style_link_resolves(self) -> None:
        build = build_document(
            "[link text][myref]\n\n[myref]: https://example.com\n",
            filename="test.mtx",
        )
        self.assertIn(r"\href{https://example.com}", build.target_text)
        self.assertIn("link text", build.target_text)

    def test_image_reference_style_resolves(self) -> None:
        build = build_document(
            "![alt][fig]\n\n[fig]: figure.pdf\n",
            filename="test.mtx",
        )
        self.assertIn(r"\includegraphics{figure.pdf}", build.target_text)

    def test_inline_expression_in_paragraph(self) -> None:
        build = build_document("[$ 1 + 1 ]\n", filename="test.mtx")
        self.assertIn("2", build.target_text)


class BibtexEdgeCaseTests(unittest.TestCase):
    def test_duplicate_key_fails(self) -> None:
        from marktex.bibliography import load_bib_resources

        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                "@article{Same, author={A}, title={T}, year={2020}}\n"
                "@book{Same, author={B}, title={U}, year={2021}}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MarkTeXError, "duplicate bibliography key: Same"):
                load_bib_resources((path,))

    def test_file_not_found_fails(self) -> None:
        from marktex.bibliography import parse_bibtex_file

        with self.assertRaisesRegex(MarkTeXError, "bibliography file cannot be read"):
            parse_bibtex_file(Path("/nonexistent/refs.bib"))

    def test_paren_delimited_entry(self) -> None:
        from marktex.bibliography import parse_bibtex_file

        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                "@article(Paren1, author={Alice}, title={Test}, year={2020})\n",
                encoding="utf-8",
            )
            entries = parse_bibtex_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].key, "Paren1")

    def test_comment_entry_is_ignored(self) -> None:
        from marktex.bibliography import parse_bibtex_file

        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                "@comment{This is a comment}\n"
                "@article{Real, author={Alice}, title={T}, year={2020}}\n",
                encoding="utf-8",
            )
            entries = parse_bibtex_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].key, "Real")

    def test_quoted_string_value(self) -> None:
        from marktex.bibliography import parse_bibtex_file

        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                '@article{Q, author="Quoted Author", title="Test", year="2022"}\n',
                encoding="utf-8",
            )
            entries = parse_bibtex_file(path)
        self.assertEqual(entries[0].fields["author"], "Quoted Author")

    def test_numeric_field_value(self) -> None:
        from marktex.bibliography import parse_bibtex_file

        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "refs.bib"
            path.write_text(
                "@article{N, author={Alice}, title={T}, year=2023}\n",
                encoding="utf-8",
            )
            entries = parse_bibtex_file(path)
        self.assertEqual(entries[0].fields["year"], "2023")


class BibliographyCitationModeTests(unittest.TestCase):
    def _make_source(self, directory: Path, bib: str, style: str, body: str) -> Path:
        (directory / "refs.bib").write_text(bib, encoding="utf-8")
        (directory / "style.mtxcs").write_text(style, encoding="utf-8")
        source = directory / "paper.mtx"
        source.write_text(
            "!# bib: refs.bib\n!# citestyle: style.mtxcs\n" + body,
            encoding="utf-8",
        )
        return source

    def test_author_page_citation_mode(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = self._make_source(
                directory,
                "@article{A, author={Smith}, title={T}, year={2020}}\n",
                "style: name=s; citation: mode=author-page, form=paren;",
                "See [^ cite: A ].\n",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        # author-page mode: inline citation shows author only (no year)
        self.assertIn("(Smith)", build.target_text)
        # inline citation "(Smith)" should not contain the year
        citation_pos = build.target_text.index("(Smith)")
        citation_text = build.target_text[citation_pos : citation_pos + 10]
        self.assertNotIn("2020", citation_text)

    def test_author_page_citation_with_locator(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = self._make_source(
                directory,
                "@article{A, author={Smith}, title={T}, year={2020}}\n",
                "style: name=s; citation: mode=author-page, form=paren, locator-prefix=` `;",
                "See [^ cite: A, page=42 ].\n",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn("Smith", build.target_text)
        self.assertIn("42", build.target_text)

    def test_superscript_citation_form(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = self._make_source(
                directory,
                "@article{A, author={Jones}, title={T}, year={2021}}\n",
                "style: name=s; citation: mode=numeric, form=superscript;",
                "Claim [^ cite: A ].\n",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\textsuperscript{", build.target_text)

    def test_paren_citation_form(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            source = self._make_source(
                directory,
                "@article{A, author={Lee}, title={T}, year={2022}}\n",
                "style: name=s; citation: mode=numeric, form=paren;",
                "See [^ cite: A ].\n",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn("(1)", build.target_text)

    def test_sort_by_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{Zzz, author={Zeta}, title={Z}, year={2020}}\n"
                "@article{Aaa, author={Alpha}, title={A}, year={2020}}\n",
                encoding="utf-8",
            )
            (directory / "style.mtxbs").write_text(
                "style: name=s; "
                "references: title=Sources, include=all, sort=key, placement=inline, label=none; "
                "template: default, author, title;",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n!# bibstyle: style.mtxbs\n[^ cite: Zzz ]. [^ cite: Aaa ].\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        aaa_pos = build.target_text.index("Alpha")
        zzz_pos = build.target_text.index("Zeta")
        self.assertLess(aaa_pos, zzz_pos)

    def test_sort_by_author_title(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{X, author={Zzz}, title={Alpha}, year={2020}}\n"
                "@article{Y, author={Aaa}, title={Zeta}, year={2020}}\n",
                encoding="utf-8",
            )
            (directory / "style.mtxbs").write_text(
                "style: name=s; "
                "references: title=Sources, include=all, sort=author-title, placement=inline, label=none; "
                "template: default, author, title;",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n!# bibstyle: style.mtxbs\n[^ cite: X ]. [^ cite: Y ].\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        aaa_pos = build.target_text.index("Aaa")
        zzz_pos = build.target_text.index("Zzz")
        self.assertLess(aaa_pos, zzz_pos)

    def test_bibliography_label_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{MyKey, author={A}, title={T}, year={2020}}\n",
                encoding="utf-8",
            )
            (directory / "style.mtxbs").write_text(
                "style: name=s; "
                "references: title=Sources, include=all, sort=key, placement=inline, label=key; "
                "template: default, author, title;",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n!# bibstyle: style.mtxbs\nNo cite.\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn("[MyKey]", build.target_text)

    def test_doi_field_rendered_as_hyperlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            (directory / "refs.bib").write_text(
                "@article{A, author={Alice}, title={T}, year={2020}, doi={10.1234/test}}\n",
                encoding="utf-8",
            )
            (directory / "style.mtxbs").write_text(
                "style: name=s; "
                "references: title=Sources, include=all, sort=key, placement=inline, label=none; "
                "template: default, doi;",
                encoding="utf-8",
            )
            source = directory / "paper.mtx"
            source.write_text(
                "!# bib: refs.bib\n!# bibstyle: style.mtxbs\nNo cite.\n",
                encoding="utf-8",
            )
            build = build_document(source.read_text(encoding="utf-8"), filename=str(source))
        self.assertIn(r"\href{https://doi.org/10.1234/test}", build.target_text)


class RuntimeApiTests(unittest.TestCase):
    def test_session_raw_creates_raw_string(self) -> None:
        from marktex.mos import RawString

        session = runtime.RuntimeSession()
        result = session.raw("hello")
        self.assertIsInstance(result, RawString)
        self.assertEqual(result.text, "hello")

    def test_session_tuple_value_creates_tuple(self) -> None:
        from marktex.mos import TupleValue

        session = runtime.RuntimeSession()
        result = session.tuple_value("a", "b")
        self.assertIsInstance(result, TupleValue)
        self.assertEqual(len(result.items), 2)

    def test_object_to_json_serializes_mos_values(self) -> None:
        from marktex.core import object_to_json
        from marktex.mos import CallUnit, RawString, TupleValue

        raw = RawString("A4")
        tuple_value = TupleValue((raw,))
        call = CallUnit("document", "layout", args=(raw,), kwargs={"paper": tuple_value})
        self.assertEqual(object_to_json(raw), raw.to_json())
        self.assertEqual(object_to_json(tuple_value), tuple_value.to_json())
        self.assertEqual(object_to_json(call), call.to_json())

    def test_session_scope_push_and_close_appended_to_events(self) -> None:
        from marktex.core import ScopeClose, ScopePush

        session = runtime.RuntimeSession()
        push = session.scope_push("myscope", font="Times")
        close = session.scope_close("myscope")
        session.invoke(push)
        session.invoke(close)
        events = session.finish()
        self.assertIsInstance(events[0], ScopePush)
        self.assertIsInstance(events[1], ScopeClose)

    def test_session_scope_push_with_non_default_scope(self) -> None:
        session = runtime.RuntimeSession()
        push = session.scope_push("k", scope="e")
        self.assertIn("scope", push.kwargs)
        self.assertEqual(push.kwargs["scope"].text, "e")

    def test_session_rejects_unknown_scope_target(self) -> None:
        session = runtime.RuntimeSession()
        with self.assertRaisesRegex(MarkTeXError, "unsupported scope target: mycontext"):
            session.scope_push("k", scope="mycontext")

    def test_session_drain_returns_and_clears(self) -> None:
        session = runtime.RuntimeSession()
        session.invoke(session.document_patch("layout"))
        drained = session.drain()
        self.assertEqual(len(drained), 1)
        self.assertEqual(len(session.finish()), 0)

    def test_session_reset_clears_events(self) -> None:
        session = runtime.RuntimeSession()
        session.invoke(session.document_patch("layout"))
        session.reset()
        self.assertEqual(len(session.finish()), 0)

    def test_module_level_builders_return_correct_types(self) -> None:
        from marktex.core import (
            BlockQuote,
            Emphasis,
            Heading,
            Image,
            InlineCode,
            InlineMath,
            LineBreak,
            Link,
            ListBlock,
            ListItem,
            MathBlock,
            Paragraph,
            Strikethrough,
            Strong,
            Text,
            ThematicBreak,
        )

        self.assertIsInstance(runtime.text("hi"), Text)
        self.assertIsInstance(runtime.paragraph("hi"), Paragraph)
        self.assertIsInstance(runtime.heading(1, "Title"), Heading)
        self.assertIsInstance(runtime.emphasis("em"), Emphasis)
        self.assertIsInstance(runtime.strong("bold"), Strong)
        self.assertIsInstance(runtime.strikethrough("strike"), Strikethrough)
        self.assertIsInstance(runtime.inline_code("code"), InlineCode)
        self.assertIsInstance(runtime.inline_math("x+y"), InlineMath)
        self.assertIsInstance(runtime.line_break(), LineBreak)
        self.assertIsInstance(runtime.link("https://x.com", "label"), Link)
        self.assertIsInstance(runtime.image("alt", "img.pdf"), Image)
        self.assertIsInstance(runtime.thematic_break(), ThematicBreak)
        item = runtime.list_item(runtime.paragraph("item"))
        self.assertIsInstance(item, ListItem)
        lb = runtime.list_block(item)
        self.assertIsInstance(lb, ListBlock)
        bq = runtime.blockquote(runtime.paragraph("quoted"))
        self.assertIsInstance(bq, BlockQuote)
        self.assertIsInstance(runtime.math_block("x+y"), MathBlock)

    def test_session_document_method_returns_canonical_document(self) -> None:
        from marktex.core import Document

        session = runtime.RuntimeSession()
        doc = session.document(blocks=(runtime.paragraph("hello"),))
        self.assertIsInstance(doc, Document)
        self.assertEqual(len(doc.blocks), 1)

    def test_module_level_call_and_document_patch(self) -> None:
        from marktex.core import DocumentPatch
        from marktex.mos import CallUnit

        call = runtime.call("layout", context="document")
        self.assertIsInstance(call, CallUnit)
        patch = runtime.document_patch("layout")
        self.assertIsInstance(patch, DocumentPatch)

    def test_module_level_drain_and_reset_operate_on_default_session(self) -> None:
        runtime.reset()
        runtime.invoke(runtime.document_patch("layout"))
        drained = runtime.drain()
        self.assertEqual(len(drained), 1)
        self.assertEqual(len(runtime.finish()), 0)
        runtime.reset()

    def test_module_level_session_is_context_local(self) -> None:
        runtime.reset()
        runtime.invoke(runtime.document_patch("layout"))

        other_context = contextvars.Context()

        def seed_other_context() -> int:
            runtime.invoke(runtime.document_patch("margin"))
            return len(runtime.finish())

        self.assertEqual(other_context.run(seed_other_context), 1)
        self.assertEqual(len(runtime.finish()), 1)

        runtime.reset()
        self.assertEqual(len(runtime.finish()), 0)
        self.assertEqual(other_context.run(lambda: len(runtime.finish())), 1)

        other_context.run(runtime.reset)
        self.assertEqual(other_context.run(lambda: len(runtime.finish())), 0)


class SerdeRoundTripTests(unittest.TestCase):
    def _round_trip(self, source: str) -> None:
        from marktex.driver.serde import document_from_json

        build = build_document(source, filename="test.mtx")
        serialized = build.document.to_json()
        restored = document_from_json(serialized)
        self.assertEqual(restored.to_json(), serialized)

    def test_list_block_round_trip(self) -> None:
        self._round_trip("- Item one\n- Item two\n")

    def test_ordered_list_block_round_trip(self) -> None:
        self._round_trip("1. First\n2. Second\n")

    def test_blockquote_round_trip(self) -> None:
        self._round_trip("> Quoted text here\n")

    def test_thematic_break_round_trip(self) -> None:
        self._round_trip("Before\n\n---\n\nAfter\n")

    def test_scope_push_event_round_trip(self) -> None:
        from marktex.driver.serde import event_from_json

        build = build_document("!@ font=Times\nHello\n!!@\n", filename="test.mtx")
        push_events = [e for e in build.document.events if hasattr(e, "kwargs")]
        self.assertTrue(push_events)
        for event in push_events:
            serialized = event.to_json()
            restored = event_from_json(serialized)
            self.assertEqual(restored.to_json(), serialized)

    def test_scope_close_event_round_trip(self) -> None:
        from marktex.core import ScopeClose
        from marktex.driver.serde import event_from_json

        build = build_document("!@ mykey\nHello\n!!@ mykey\n", filename="test.mtx")
        close_events = [e for e in build.document.events if isinstance(e, ScopeClose)]
        self.assertTrue(close_events)
        for event in close_events:
            serialized = event.to_json()
            restored = event_from_json(serialized)
            self.assertEqual(restored.to_json(), serialized)

    def test_task_list_item_checked_round_trip(self) -> None:
        self._round_trip("- [x] Done\n- [ ] Todo\n")

    def test_math_nodes_round_trip(self) -> None:
        self._round_trip("Inline $x+y$.\n\n$$\na^2+b^2=c^2\n$$\n")


if __name__ == "__main__":
    unittest.main()
