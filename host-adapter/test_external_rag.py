import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.external_rag import search_external_rag


class ExternalRagTest(unittest.TestCase):
    def test_disabled_rag_never_reads_ep_or_files(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "note.md").write_text("外部资料", encoding="utf-8")
            settings = {"rag": {"enabled": False, "root_path": root}, "routing": {"external_rag_enabled": False}}
            with patch("lib.external_rag.load_runtime_settings", return_value=settings):
                value = search_external_rag("外部资料")
        self.assertEqual(value["status"], "disabled_by_runtime_settings")
        self.assertFalse(value["ep_accessed"])

    def test_enabled_rag_returns_only_external_file_sources(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "policy.md").write_text("外部政策文件的预算条款", encoding="utf-8")
            settings = {"rag": {"enabled": True, "root_path": root, "rerank_enabled": True}, "routing": {"external_rag_enabled": True}}
            with patch("lib.external_rag.load_runtime_settings", return_value=settings):
                value = search_external_rag("预算条款")
        self.assertEqual(value["status"], "ok")
        self.assertTrue(value["items"])
        self.assertTrue(all(item["source"] == "external_rag" for item in value["items"]))
        self.assertFalse(value["ep_accessed"])

    def test_rag_uses_bound_retrieval_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "policy.md").write_text("外部政策文件的预算条款", encoding="utf-8")
            settings = {
                "rag": {"enabled": True, "root_path": root, "vector_enabled": True,
                        "rerank_enabled": True, "embedding_profile_id": "embedding-default",
                        "reranker_profile_id": "reranker-default"},
                "routing": {"external_rag_enabled": True},
                "retrieval_models": {
                    "embedding": {"enabled": True, "profile_id": "embedding-default", "model": "local-embedding"},
                    "reranker": {"enabled": True, "profile_id": "reranker-default", "model": "local-reranker"},
                },
            }
            with patch("lib.external_rag.load_runtime_settings", return_value=settings), \
                 patch("lib.external_rag._vector_scores", return_value=([0.9], "test-vector")) as vectors, \
                 patch("lib.external_rag._rerank", side_effect=lambda query, items, model: (items, model)) as rerank:
                value = search_external_rag("预算条款")
        self.assertEqual(vectors.call_args.args[2], "local-embedding")
        self.assertEqual(rerank.call_args.args[2], "local-reranker")
        self.assertEqual(value["retrieval"]["embedding_profile_id"], "embedding-default")
        self.assertEqual(value["retrieval"]["reranker_profile_id"], "reranker-default")

    def test_rag_resolves_non_active_profile_by_id(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "policy.md").write_text("外部政策文件的预算条款", encoding="utf-8")
            settings = {
                "rag": {"enabled": True, "root_path": root, "vector_enabled": True,
                        "rerank_enabled": True, "embedding_profile_id": "embedding-bge",
                        "reranker_profile_id": "rerank-mini"},
                "routing": {"external_rag_enabled": True},
                "retrieval_models": {
                    "embedding": {"enabled": True, "profile_id": "embedding-default", "model": "active"},
                    "reranker": {"enabled": True, "profile_id": "reranker-default", "model": "active-rerank"},
                    "embedding_profiles": [{"enabled": True, "profile_id": "embedding-bge", "model": "bge-m3"}],
                    "reranker_profiles": [{"enabled": True, "profile_id": "rerank-mini", "model": "mini-reranker"}],
                },
            }
            with patch("lib.external_rag.load_runtime_settings", return_value=settings), \
                 patch("lib.external_rag._vector_scores", return_value=([0.9], "test-vector")) as vectors, \
                 patch("lib.external_rag._rerank", side_effect=lambda query, items, model: (items, model)) as rerank:
                search_external_rag("预算条款")
        self.assertEqual(vectors.call_args.args[2], "bge-m3")
        self.assertEqual(rerank.call_args.args[2], "mini-reranker")


if __name__ == "__main__":
    unittest.main()
