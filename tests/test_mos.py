from __future__ import annotations

import unittest

from marktex.mos import CallUnit, RawString, parse_mos
from marktex.schema import ContextSpec, SchemaRegistry, builtin_registry
from marktex.source import MarkTeXError


class MosParserTests(unittest.TestCase):
    def test_raw_value_preserves_leading_space(self) -> None:
        call = parse_mos("a: b")[0]
        self.assertEqual(call.head, "a")
        self.assertIsInstance(call.args[0], RawString)
        self.assertEqual(call.args[0].text, " b")

    def test_semicolon_closes_one_frame(self) -> None:
        calls = parse_mos("a: b: c;; d")
        self.assertEqual([call.head for call in calls], ["a", "d"])
        nested = calls[0].args[0]
        self.assertIsInstance(nested, CallUnit)
        self.assertEqual(nested.head, "b")

    def test_raw_literal_disables_structure(self) -> None:
        call = parse_mos("a: `,;:=()`")[0]
        value = call.args[0]
        self.assertIsInstance(value, RawString)
        self.assertTrue(value.force_raw)
        self.assertEqual(value.text, ",;:=()")

    def test_backslash_newline_continues_without_space(self) -> None:
        call = parse_mos("a: hello\\\nworld")[0]
        value = call.args[0]
        self.assertIsInstance(value, RawString)
        self.assertEqual(value.text, " helloworld")

    def test_escaped_mos_head_and_key_are_not_syntax(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "escaped MOS call head"):
            parse_mos(r"\layout: A4", context="document")
        with self.assertRaisesRegex(MarkTeXError, "escaped MOS named argument"):
            parse_mos(r"layout: \width=210mm", context="document")

    def test_escaped_mos_value_is_still_a_value(self) -> None:
        call = parse_mos(r"layout: width=\210mm, orientation=\landscape", context="document")[0]
        width = call.kwargs["width"]
        orientation = call.kwargs["orientation"]
        self.assertIsInstance(width, RawString)
        self.assertIsInstance(orientation, RawString)
        self.assertEqual(width.text, "210mm")
        self.assertEqual(orientation.text, "landscape")

    def test_tuple_value_allows_leading_space(self) -> None:
        call = parse_mos("a: (x, y)")[0]
        value = call.args[0]
        self.assertEqual(value.to_json()["kind"], "tuple")

    def test_tuple_rejects_bare_named_argument(self) -> None:
        with self.assertRaisesRegex(MarkTeXError, "expected ','"):
            parse_mos("a: (font=Times)")


class SchemaTests(unittest.TestCase):
    def test_layout_shading_is_schema_driven(self) -> None:
        registry = builtin_registry()
        call = parse_mos("layout: A4, landscape", context="document")[0]
        resolved = registry.resolve_call(call)
        self.assertEqual(resolved.head, "layout")
        self.assertEqual([arg.head for arg in resolved.args if isinstance(arg, CallUnit)], ["A4", "landscape"])
        preset = resolved.args[0]
        self.assertIsInstance(preset, CallUnit)
        self.assertEqual(set(preset.kwargs), {"width", "height"})

    def test_removed_shorthand_changes_resolution_not_parse(self) -> None:
        call = parse_mos("layout: A4", context="document")[0]
        registry = SchemaRegistry({"layout.value": ContextSpec("layout.value")})
        resolved = registry.resolve_call(call)
        self.assertIsInstance(resolved.args[0], RawString)
        self.assertEqual(resolved.args[0].text, " A4")

    def test_forced_raw_prevents_shading(self) -> None:
        registry = builtin_registry()
        call = parse_mos("layout: `A4`", context="document")[0]
        resolved = registry.resolve_call(call)
        self.assertIsInstance(resolved.args[0], RawString)
        self.assertEqual(resolved.args[0].text, "A4")


if __name__ == "__main__":
    unittest.main()
