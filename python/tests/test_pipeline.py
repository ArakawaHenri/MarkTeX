from __future__ import annotations

import unittest

from marktex.lexer import lex
from marktex.model import StyledChunk
from marktex.pipeline import compile_marktex_to_latex
from marktex.resolver import resolve


def _styled_chunks(resolved) -> list[StyledChunk]:
    return [unit for unit in resolved.units if isinstance(unit, StyledChunk)]


class ResolverTestCase(unittest.TestCase):
    def test_scope_unset_only_removes_latest_patch(self) -> None:
        source = """\
*(font: Times New Roman, size: 12)
*(bold)
A
!*
B
"""
        resolved = resolve(list(lex(source)))
        chunks = [chunk for chunk in _styled_chunks(resolved) if chunk.text.strip()]
        chunk_a = next(chunk for chunk in chunks if chunk.text == "A")
        chunk_b = next(chunk for chunk in chunks if chunk.text == "B")

        self.assertTrue(chunk_a.styles.get("bold"))
        self.assertEqual(chunk_a.styles.get("font"), "Times New Roman")
        self.assertEqual(chunk_b.styles.get("font"), "Times New Roman")
        self.assertIsNone(chunk_b.styles.get("bold"))

    def test_scope_order_overrides_only_same_property(self) -> None:
        source = """\
*l(blue, italic, underline, size: 13)
*w(font: Times New Roman, size: 12)
[Link](href: https://example.com)
"""
        resolved = resolve(list(lex(source)))
        chunk = next(chunk for chunk in _styled_chunks(resolved) if chunk.text == "Link")
        self.assertEqual(chunk.styles.get("size"), 12.0)
        self.assertEqual(chunk.styles.get("color"), "blue")
        self.assertTrue(chunk.styles.get("italic"))
        self.assertTrue(chunk.styles.get("underline"))

    def test_nested_inline_overrides_outer_scope(self) -> None:
        source = """\
*(font: Times New Roman, size: 12)
[outer [inner](size: 20)](color: red)
"""
        resolved = resolve(list(lex(source)))
        chunks = [chunk for chunk in _styled_chunks(resolved) if chunk.text.strip()]
        outer = next(chunk for chunk in chunks if "outer " in chunk.text)
        inner = next(chunk for chunk in chunks if chunk.text == "inner")
        self.assertEqual(outer.styles.get("size"), 12.0)
        self.assertEqual(outer.styles.get("color"), "red")
        self.assertEqual(inner.styles.get("size"), 20.0)
        self.assertEqual(inner.styles.get("color"), "red")
        self.assertEqual(inner.styles.get("font"), "Times New Roman")

    def test_western_and_eastern_are_split(self) -> None:
        source = """\
*w(font: Times New Roman)
*e(font: SimSun)
Hello世界
"""
        resolved = resolve(list(lex(source)))
        chunks = [chunk for chunk in _styled_chunks(resolved) if chunk.text.strip()]
        self.assertEqual(chunks[0].text, "Hello")
        self.assertEqual(chunks[0].styles.get("font"), "Times New Roman")
        self.assertEqual(chunks[1].text, "世界")
        self.assertEqual(chunks[1].styles.get("font"), "SimSun")

    def test_heading_scope_applies_to_heading_line(self) -> None:
        source = """\
*h(bold)
# Title
"""
        resolved = resolve(list(lex(source)))
        chunk = next(chunk for chunk in _styled_chunks(resolved) if chunk.text == "Title")
        self.assertTrue(chunk.styles.get("bold"))
        self.assertEqual(chunk.block.kind, "heading")
        self.assertEqual(chunk.block.heading_level, 1)

    def test_unset_all_scopes(self) -> None:
        source = """\
*w(font: Times New Roman)
*e(font: SimSun)
!**
Hello世界
"""
        resolved = resolve(list(lex(source)))
        chunks = [chunk for chunk in _styled_chunks(resolved) if chunk.text.strip()]
        self.assertGreaterEqual(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.styles, {})

    def test_directive_layout_and_margin(self) -> None:
        source = """\
!# layout: A4, landscape
!# margin: top: 10, bottom: 20, left: 30, right: 40
Body
"""
        resolved = resolve(list(lex(source)))
        self.assertEqual(resolved.config.layout_name, "a4")
        self.assertEqual(resolved.config.orientation, "landscape")
        self.assertEqual(resolved.config.margins_mm["top"], 10.0)
        self.assertEqual(resolved.config.margins_mm["bottom"], 20.0)

    def test_citation_is_emitted_as_latex(self) -> None:
        source = "See [#Doe2024](pages: 12-13)."
        latex = compile_marktex_to_latex(source)
        self.assertIn(r"\cite[p.~12-13]{Doe2024}", latex)

    def test_header_footer_expression_compiles(self) -> None:
        source = """\
!# -. Still <M-N> pages to go
Body
"""
        latex = compile_marktex_to_latex(source)
        self.assertIn(r"\newcommand{\MarkTeXEval}[1]{\fpeval{round(#1,0)}}", latex)
        self.assertIn(
            r"\fancyfoot[R]{Still \MarkTeXEval{(\getpagerefnumber{LastPage})-(\value{page})} pages to go}",
            latex,
        )

    def test_column_rules_apply_initial_multicol(self) -> None:
        source = """\
!# column: 2, 1
!# column-margin: 10, 20g
Line one.
Line two.
"""
        latex = compile_marktex_to_latex(source)
        self.assertIn(r"\usepackage{multicol}", latex)
        self.assertIn(r"\setlength{\columnsep}{10.0mm}", latex)
        self.assertIn(r"\begin{multicols}{2}", latex)


if __name__ == "__main__":
    unittest.main()
