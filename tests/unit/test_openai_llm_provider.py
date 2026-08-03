import unittest
from types import SimpleNamespace

from app.core.exceptions import AnswerProviderError
from app.providers.openai_llm_provider import OpenAILLMProvider


class _FakeResponsesResource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.output_text = "Grounded answer [1]."
        self.raise_error = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_error:
            raise RuntimeError("sensitive upstream response")
        return SimpleNamespace(output_text=self.output_text)


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesResource()


class OpenAILLMProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _FakeClient()
        self.provider = OpenAILLMProvider(
            api_key="test-key",
            model="gpt-5.6-sol",
            reasoning_effort="low",
            verbosity="low",
            max_output_tokens=500,
            client=self.client,
        )

    def test_responses_api_receives_grounded_privacy_safe_configuration(self) -> None:
        answer = self.provider.generate_answer(
            "What is the control?",
            ['<source id="1">\nApproved evidence.\n</source>'],
        )

        self.assertEqual(answer, "Grounded answer [1].")
        call = self.client.responses.calls[0]
        self.assertEqual(call["model"], "gpt-5.6-sol")
        self.assertEqual(call["reasoning"], {"effort": "low"})
        self.assertEqual(call["text"], {"verbosity": "low"})
        self.assertEqual(call["max_output_tokens"], 500)
        self.assertFalse(call["store"])
        self.assertIn("using only the supplied evidence", call["instructions"])
        self.assertIn("What is the control?", call["input"])
        self.assertIn("Approved evidence.", call["input"])

    def test_blank_inputs_are_rejected_without_api_call(self) -> None:
        with self.assertRaises(ValueError):
            self.provider.generate_answer(" ", ["evidence"])
        with self.assertRaises(ValueError):
            self.provider.generate_answer("question", [])

        self.assertEqual(self.client.responses.calls, [])

    def test_upstream_and_empty_outputs_are_safe_provider_errors(self) -> None:
        self.client.responses.raise_error = True
        with self.assertRaises(AnswerProviderError) as raised:
            self.provider.generate_answer("question", ["evidence"])
        self.assertNotIn("sensitive upstream response", str(raised.exception))

        self.client.responses.raise_error = False
        self.client.responses.output_text = "   "
        with self.assertRaises(AnswerProviderError):
            self.provider.generate_answer("question", ["evidence"])

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OpenAILLMProvider(api_key="test", reasoning_effort="extreme")
        with self.assertRaises(ValueError):
            OpenAILLMProvider(api_key="test", verbosity="verbose")
        with self.assertRaises(ValueError):
            OpenAILLMProvider(api_key="test", max_output_tokens=0)


if __name__ == "__main__":
    unittest.main()
