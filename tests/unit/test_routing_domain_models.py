import unittest

from app.domain.models import (
    AnswerRoute,
    RoutedAnswerResult,
    RouteReason,
    RoutingDecision,
    RoutingStopReason,
)


class RoutingDomainModelTests(unittest.TestCase):
    def test_routing_decision_rejects_mismatched_reason(self) -> None:
        invalid = (
            (AnswerRoute.DIRECT_ANSWER, RouteReason.RETRIEVE_DEFAULT),
            (AnswerRoute.REFUSE, RouteReason.GREETING),
            (AnswerRoute.RETRIEVE, RouteReason.USAGE_HELP),
        )

        for route, reason in invalid:
            with self.subTest(route=route, reason=reason):
                with self.assertRaises(ValueError):
                    RoutingDecision(route, reason)

    def test_routed_result_rejects_non_retrieval_data_and_invalid_rewrite(self) -> None:
        with self.assertRaises(ValueError):
            RoutedAnswerResult(
                answer="direct",
                citations=(),
                retrieval_count=1,
                route=AnswerRoute.DIRECT_ANSWER,
                route_reason=RouteReason.GREETING,
                retrieval_attempts=1,
                stop_reason=RoutingStopReason.DIRECT_ANSWER,
            )
        with self.assertRaises(ValueError):
            RoutedAnswerResult(
                answer="answer",
                citations=(),
                retrieval_count=0,
                route=AnswerRoute.RETRIEVE,
                route_reason=RouteReason.RETRIEVE_DEFAULT,
                retrieval_attempts=1,
                rewritten_query="changed",
                stop_reason=RoutingStopReason.NO_SAFE_REWRITE,
            )

    def test_routed_result_rejects_blank_answer_and_bad_attempt_count(self) -> None:
        base = {
            "citations": (),
            "retrieval_count": 0,
            "route": AnswerRoute.RETRIEVE,
            "route_reason": RouteReason.RETRIEVE_DEFAULT,
            "stop_reason": RoutingStopReason.NO_DOCUMENT_SCOPE,
        }
        with self.assertRaises(ValueError):
            RoutedAnswerResult(answer=" ", retrieval_attempts=0, **base)
        with self.assertRaises(ValueError):
            RoutedAnswerResult(answer="answer", retrieval_attempts=3, **base)
        with self.assertRaises(ValueError):
            RoutedAnswerResult(
                answer="answer",
                retrieval_attempts=2,
                rewritten_query=" ",
                **base,
            )


if __name__ == "__main__":
    unittest.main()
