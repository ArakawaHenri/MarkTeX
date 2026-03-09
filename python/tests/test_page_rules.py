from __future__ import annotations

import unittest

from marktex.page_rules import (
    evaluate_page_rule_spec,
    parse_column_value,
    parse_page_rule_spec,
)
from marktex.tags import parse_mm_number


class PageRuleSpecTestCase(unittest.TestCase):
    def test_simple_prefix_and_default(self) -> None:
        spec = parse_page_rule_spec("2, 1", parse_column_value)
        resolved = evaluate_page_rule_spec(spec, total_pages=4)
        self.assertEqual(resolved, {1: 2, 2: 1, 3: 1, 4: 1})

    def test_first_and_last_pages(self) -> None:
        spec = parse_page_rule_spec("2, 1g, 2", parse_column_value)
        resolved = evaluate_page_rule_spec(spec, total_pages=6)
        self.assertEqual(resolved, {1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2})

    def test_explicit_positive_and_negative_pages(self) -> None:
        spec = parse_page_rule_spec("1: 2, 1g, -1: 2", parse_column_value)
        resolved = evaluate_page_rule_spec(spec, total_pages=5)
        self.assertEqual(resolved, {1: 2, 2: 1, 3: 1, 4: 1, 5: 2})

    def test_tail_tokens_are_trimmed_when_page_count_is_small(self) -> None:
        spec = parse_page_rule_spec("1, 1, 4, 19g, 5, 1, 4", parse_column_value)
        resolved = evaluate_page_rule_spec(spec, total_pages=5)
        self.assertEqual(resolved, {1: 1, 2: 1, 3: 4, 4: 5, 5: 1})

    def test_column_margin_uses_mm_parser(self) -> None:
        spec = parse_page_rule_spec("10, 20g, 30", parse_mm_number)
        resolved = evaluate_page_rule_spec(spec, total_pages=6)
        self.assertEqual(resolved[1], 10.0)
        self.assertEqual(resolved[6], 30.0)


if __name__ == "__main__":
    unittest.main()
