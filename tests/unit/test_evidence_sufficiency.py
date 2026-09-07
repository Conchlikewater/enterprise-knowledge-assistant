import unittest
from uuid import uuid4

from app.domain.models import RetrievalResult
from app.services.evidence_sufficiency import EvidenceSufficiencyPolicy


class EvidenceSufficiencyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = EvidenceSufficiencyPolicy()

    def test_requires_two_results_for_normal_top_k_and_one_for_top_one(self) -> None:
        one = [self._result(0.9)]
        two = [self._result(0.9), self._result(0.8)]

        self.assertTrue(
            self.policy.assess(one, top_k=5, score_threshold=None).should_retry
        )
        self.assertFalse(
            self.policy.assess(two, top_k=5, score_threshold=None).should_retry
        )
        self.assertFalse(
            self.policy.assess(one, top_k=1, score_threshold=None).should_retry
        )

    def test_uses_only_the_explicit_request_threshold_for_relevance(self) -> None:
        assessment = self.policy.assess(
            [self._result(0.8), self._result(0.4)],
            top_k=5,
            score_threshold=0.5,
        )

        self.assertEqual(assessment.required_result_count, 2)
        self.assertEqual(assessment.relevant_result_count, 1)
        self.assertTrue(assessment.should_retry)

    def test_without_threshold_negative_scores_still_count(self) -> None:
        assessment = self.policy.assess(
            [self._result(-0.2), self._result(-0.3)],
            top_k=5,
            score_threshold=None,
        )

        self.assertEqual(assessment.relevant_result_count, 2)
        self.assertFalse(assessment.should_retry)

    def test_rejects_invalid_policy_parameters(self) -> None:
        with self.assertRaises(ValueError):
            self.policy.assess([], top_k=0, score_threshold=None)
        for threshold in (float("inf"), -1.1, 1.1):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    self.policy.assess([], top_k=5, score_threshold=threshold)

    @staticmethod
    def _result(score: float) -> RetrievalResult:
        return RetrievalResult(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="course.txt",
            text="evidence",
            score=score,
        )


if __name__ == "__main__":
    unittest.main()
