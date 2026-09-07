import unittest

from app.services.query_rewriter import RuleBasedQueryRewriter


class RuleBasedQueryRewriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rewriter = RuleBasedQueryRewriter()

    def test_removes_politeness_and_normalizes_school_relationship_terms(self) -> None:
        rewritten = self.rewriter.rewrite(
            "Could you please tell me what courses do I need before the capstone course?"
        )

        self.assertEqual(rewritten, "prerequisite courses for the capstone course")

    def test_normalizes_credit_and_chinese_prerequisite_queries(self) -> None:
        cases = (
            (
                "How many credits are required to complete the analytics program?",
                "credit requirements for the analytics program",
            ),
            ("请问需要先修哪些课程？", "先修课程"),
        )

        for question, expected in cases:
            with self.subTest(question=question):
                self.assertEqual(self.rewriter.rewrite(question), expected)

    def test_uses_keyword_fallback_for_safe_shortening(self) -> None:
        rewritten = self.rewriter.rewrite(
            "What is the assessment weighting in the selected syllabus?"
        )

        self.assertEqual(rewritten, "assessment weighting selected syllabus")

    def test_returns_none_when_no_different_safe_query_exists(self) -> None:
        self.assertIsNone(self.rewriter.rewrite("prerequisite capstone"))
        self.assertIsNone(self.rewriter.rewrite("这门课"))

    def test_rejects_blank_or_non_string_questions(self) -> None:
        for value in ("  ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.rewriter.rewrite(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
