import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.providers.deepseek_llm_provider import DeepSeekLLMProvider


class _FakeResponsesResource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text="DeepSeek grounded answer [1].",
            usage=SimpleNamespace(
                input_tokens=80,
                output_tokens=20,
                input_tokens_details=SimpleNamespace(cached_tokens=8),
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesResource()


class DeepSeekLLMProviderTests(unittest.TestCase):
    def test_reuses_responses_contract_with_non_thinking_default(self) -> None:
        client = _FakeClient()
        provider = DeepSeekLLMProvider(api_key="test-key", client=client)

        result = provider.generate_answer("question", ["evidence"])

        self.assertEqual(provider.name, "deepseek")
        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(result.text, "DeepSeek grounded answer [1].")
        self.assertEqual(result.usage.input_tokens, 80)
        call = client.responses.calls[0]
        self.assertEqual(call["reasoning"], {"effort": "none"})
        self.assertEqual(call["model"], "deepseek-v4-flash")

    def test_client_receives_official_base_url(self) -> None:
        with patch("app.providers.openai_llm_provider.OpenAI") as client_class:
            provider = DeepSeekLLMProvider(api_key="test-key")

        client_class.assert_called_once_with(
            api_key="test-key",
            timeout=60.0,
            max_retries=2,
            base_url="https://api.deepseek.com",
        )
        provider.close()

    def test_responses_api_rejects_unsupported_model(self) -> None:
        with self.assertRaises(ValueError):
            DeepSeekLLMProvider(api_key="test-key", model="deepseek-v4-pro")


if __name__ == "__main__":
    unittest.main()
