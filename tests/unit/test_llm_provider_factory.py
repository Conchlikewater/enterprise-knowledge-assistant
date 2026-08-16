import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.providers.llm_provider_factory import create_llm_provider


class LLMProviderFactoryTests(unittest.TestCase):
    def test_missing_selected_provider_key_returns_none(self) -> None:
        self.assertIsNone(create_llm_provider(Settings()))
        self.assertIsNone(
            create_llm_provider(
                Settings(
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-flash",
                    llm_reasoning_effort="none",
                )
            )
        )

    def test_openai_selection_preserves_existing_backend(self) -> None:
        with patch(
            "app.providers.llm_provider_factory.OpenAILLMProvider"
        ) as provider_class:
            provider = create_llm_provider(Settings(openai_api_key="openai-test"))

        self.assertIs(provider, provider_class.return_value)
        provider_class.assert_called_once()
        self.assertEqual(provider_class.call_args.kwargs["model"], "gpt-5.6-sol")

    def test_deepseek_selection_uses_separate_key_and_base_url(self) -> None:
        settings = Settings.from_env(
            {
                "RAG_LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "deepseek-test",
            }
        )
        with patch(
            "app.providers.llm_provider_factory.DeepSeekLLMProvider"
        ) as provider_class:
            provider = create_llm_provider(settings)

        self.assertIs(provider, provider_class.return_value)
        provider_class.assert_called_once()
        self.assertEqual(provider_class.call_args.kwargs["api_key"], "deepseek-test")
        self.assertEqual(
            provider_class.call_args.kwargs["base_url"],
            "https://api.deepseek.com",
        )


if __name__ == "__main__":
    unittest.main()
