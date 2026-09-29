"""Internal guidance embedding route must reuse the initialized Bank encoder."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


class GuidanceEmbeddingsHttpTests(unittest.TestCase):
    def test_guidance_embedding_route_returns_aligned_local_vectors(self):
        from evolving_profile_api.api.http import create_app

        memory = MagicMock()
        memory._authenticate_tenant = AsyncMock()
        memory.embeddings.dimension = 2
        memory.embeddings.encode_query.return_value = [[0.2, 0.8], [0.6, 0.4]]
        client = TestClient(create_app(memory, initialize_memory=False))

        response = client.post(
            "/v1/default/banks/test-bank/internal/guidance-embeddings",
            json={"texts": ["query one", "query two"], "input_type": "query"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"vectors": [[0.2, 0.8], [0.6, 0.4]], "dimensions": 2})
        memory._authenticate_tenant.assert_awaited_once()
        memory.embeddings.encode_query.assert_called_once_with(["query one", "query two"])
