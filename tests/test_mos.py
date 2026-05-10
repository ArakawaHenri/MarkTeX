from __future__ import annotations

import unittest

from marktex.mos import CallUnit, RawString, parse_mos
from marktex.schema import ContextSpec, SchemaRegistry, builtin_registry


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

    def test_backslash_newline_becomes_space(self) -> None:
        call = parse_mos("a: hello\\\nworld")[0]
        value = call.args[0]
        self.assertIsInstance(value, RawString)
        self.assertEqual(value.text, " hello world")


class SchemaTests(unittest.TestCase):
    def test_layout_shading_is_schema_driven(self) -> None:
        registry = builtin_registry()
        call = parse_mos("layout: A4, landscape", context="document")[0]
        resolved = registry.resolve_call(call)
        self.assertEqual(resolved.head, "layout")
        self.assertEqual([arg.head for arg in resolved.args if isinstance(arg, CallUnit)], ["A4", "landscape"])

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
