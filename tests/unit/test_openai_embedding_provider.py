import unittest
from types import SimpleNamespace

from app.core.exceptions import EmbeddingProviderError
from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider


class _FakeEmbeddingsResource:
    def __init__(self, dimensions: int = 3) -> None:
        self.dimensions = dimensions
        self.calls: list[dict[str, object]] = []
        self.raise_error = False
        self.malformed_dimensions = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_error:
            raise RuntimeError("sensitive upstream detail")

        items = []
        for index, text in enumerate(kwargs["input"]):
            dimensions = (
                self.dimensions - 1 if self.malformed_dimensions else self.dimensions
            )
            vector = [float(len(text))] + [0.0] * (dimensions - 1)
            items.append(SimpleNamespace(index=index, embedding=vector))
        return SimpleNamespace(data=list(reversed(items)))


class _FakeClient:
    def __init__(self, dimensions: int = 3) -> None:
        self.embeddings = _FakeEmbeddingsResource(dimensions)


class OpenAIEmbeddingProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _FakeClient()
        self.provider = OpenAIEmbeddingProvider(
            api_key="test-key",
            dimensions=3,
            batch_size=2,
            client=self.client,
        )

    def test_documents_are_batched_and_returned_in_input_order(self) -> None:
        vectors = self.provider.embed_documents(["a", "four", "several"])

        self.assertEqual([vector[0] for vector in vectors], [1.0, 4.0, 7.0])
        self.assertEqual(len(self.client.embeddings.calls), 2)
        for call in self.client.embeddings.calls:
            self.assertEqual(call["model"], "text-embedding-3-small")
            self.assertEqual(call["dimensions"], 3)
            self.assertEqual(call["encoding_format"], "float")

    def test_query_returns_one_embedding(self) -> None:
        vector = self.provider.embed_query("question")

        self.assertEqual(vector, [8.0, 0.0, 0.0])

    def test_empty_sequence_does_not_call_api(self) -> None:
        self.assertEqual(self.provider.embed_documents([]), [])
        self.assertEqual(self.client.embeddings.calls, [])

    def test_blank_input_is_rejected_locally(self) -> None:
        with self.assertRaises(ValueError):
            self.provider.embed_documents(["valid", "  "])
        self.assertEqual(self.client.embeddings.calls, [])

    def test_upstream_errors_are_mapped_without_raw_details(self) -> None:
        self.client.embeddings.raise_error = True

        with self.assertRaises(EmbeddingProviderError) as raised:
            self.provider.embed_query("question")

        self.assertNotIn("sensitive upstream detail", str(raised.exception))

    def test_malformed_vector_dimensions_are_mapped(self) -> None:
        self.client.embeddings.malformed_dimensions = True

        with self.assertRaises(EmbeddingProviderError):
            self.provider.embed_query("question")


if __name__ == "__main__":
    unittest.main()
