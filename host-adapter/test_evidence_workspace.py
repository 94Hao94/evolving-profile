import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_workspace import read_page, explicit_anchor_terms


class EvidenceWorkspaceTest(unittest.TestCase):
    def test_open_profile_inventory_does_not_use_entire_question_as_anchor(self):
        query = '用户问“现在写方案你都有什么对我的了解”。请盘点用户写高校/政企方案时的长期偏好。'
        self.assertEqual(explicit_anchor_terms(query), [])

    def test_relationship_question_extracts_entity_instead_of_full_sentence(self):
        self.assertEqual(explicit_anchor_terms('用户问“我和PPT有什么关系”。查相关历史记录。'), ['ppt'])
        self.assertEqual(explicit_anchor_terms('用户问“我跟具身智能什么关系”。查相关历史记录。'), ['具身智能'])

    def test_read_page_returns_bounded_preview_and_source_locator(self):
        """A one-page candidate response must not put an entire long source into model context."""
        research_id = str(uuid.uuid4())
        memory_id = str(uuid.uuid4())
        long_text = "历史证据" * 2000
        with tempfile.TemporaryDirectory() as root:
            Path(root, f"{research_id}.json").write_text(
                json.dumps(
                    {
                        "research_id": research_id,
                        "bank": "bank",
                        "created_at": 9_999_999_999,
                        "status": "discovered_not_verified",
                        "memory_ids": [memory_id],
                        "invalid_reference_ids": [],
                        "query": "测试",
                        "seconds": 0.1,
                        "tool_call_count": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def api(path, timeout=8):
                return {
                    "id": memory_id,
                    "state": "valid",
                    "text": long_text,
                    "document_id": "document-1",
                    "chunk_id": "chunk-1",
                    "metadata": {},
                }

            page = read_page("bank", research_id, 0, api, root, page_size=1)

        item = page["memories"][0]
        self.assertLess(len(item["text"]), len(long_text))
        self.assertTrue(item["text_truncated"])
        self.assertEqual(item["source_locator"], {"memory_id": memory_id, "document_id": "document-1", "chunk_id": "chunk-1"})

    def test_explicit_entity_query_rejects_semantically_unrelated_candidates(self):
        research_id = str(uuid.uuid4())
        mismatch_id, direct_id = str(uuid.uuid4()), str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            Path(root, f"{research_id}.json").write_text(json.dumps({
                "research_id": research_id, "bank": "bank", "created_at": 9_999_999_999,
                "status": "discovered_not_verified", "memory_ids": [mismatch_id, direct_id],
                "invalid_reference_ids": [], "query": "鹏飞学校有没有历史记录",
                "explicit_anchor_terms": ["鹏飞学校"], "seconds": 0.1, "tool_call_count": 1,
            }, ensure_ascii=False), encoding="utf-8")
            def api(path, timeout=8):
                mid=path.rsplit('/',1)[-1]
                return {"id":mid,"state":"valid","text":"系统架构和检索机制记录" if mid==mismatch_id else "鹏飞学校方案记录",
                        "document_id":"document-1","chunk_id":"chunk-1","metadata":{}}
            page=read_page("bank",research_id,0,api,root,page_size=2)
        self.assertEqual([row["id"] for row in page["memories"]],[direct_id])
        self.assertEqual(page["scope_filter"]["rejected_count"],1)
