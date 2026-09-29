import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from repository import GuidanceRepository


def _published_model(model_id: str) -> dict:
    return {
        "id": model_id,
        "revision": "sha256:published",
        "model_kind": "atomic_cross_dimensional",
        "status": "active",
        "title": "Published model",
        "dimensions": ["reasoning", "delivery"],
    }


def _candidate_model(model_id: str) -> dict:
    return {
        "id": model_id,
        "revision": "sha256:candidate",
        "model_kind": "atomic_cross_dimensional_candidate",
        "status": "needs_review",
        "title": "Candidate revision",
        "dimensions": ["reasoning", "delivery"],
    }


class ModelLifecycleTests(unittest.TestCase):
    def repo(self) -> GuidanceRepository:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        return GuidanceRepository(root / "guidance.sqlite3", "bank-a")

    def test_candidate_revision_does_not_leave_superseded_published_model_selectable(self):
        repo = self.repo()
        repo.store_model(_published_model("model-a"))
        repo.store_candidate_model(_candidate_model("model-a"))

        self.assertEqual(repo.model_inventory()["counts"], {"active": 0, "candidates": 1, "archived_legacy": 0})
        self.assertEqual(repo.active_models(), [])

    def test_active_models_returns_only_the_latest_published_revision_per_model(self):
        repo = self.repo()
        repo.store_model(_published_model("model-a"))
        repo.store_model({**_published_model("model-b"), "revision": "sha256:published-b"})

        self.assertEqual([model["id"] for model in repo.active_models()], ["model-a", "model-b"])
