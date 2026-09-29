import io
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import recall


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return json.dumps({
            "recommended_route": "recall",
            "reason": "目录发现相关历史主题。",
            "matched_nodes": ["experience"],
            "catalog_probe": {"status": "observed", "candidate_count": 3, "matched_entities": ["小黛"]},
            "catalog_hints": [{"memory_id": "m1", "topic": "小黛回复链路"}],
            "confidence": 0.8,
        }, ensure_ascii=False).encode()


class MemoryRouteProbeTest(unittest.TestCase):
    def test_prompt_receipt_contains_real_catalog_result_and_renderable_context(self):
        with tempfile.TemporaryDirectory() as root, patch.object(recall.urllib.request, "urlopen", return_value=Response()):
            value = recall.record_memory_route_probe(
                {"session_id": "s1", "turn_id": "t1"},
                "小黛空回复后来怎么处理的？",
                {"memoryRouteReceiptRoot": root, "memoryRouteStatusUrl": "http://127.0.0.1:12098"},
                "check-1",
            )

        self.assertEqual(value["recommended_route"], "recall")
        self.assertEqual(value["prompt_binding"]["hook_invocation_id"], "check-1")
        context = recall.format_memory_route_context(value)
        self.assertIn("小黛", context)
        self.assertIn("目录只用于判断", context)

    def test_route_context_preserves_catalog_overview_and_coverage(self):
        context=recall.format_memory_route_context({'check_id':'c1','recommended_route':'recall','reason':'topic found',
            'catalog_probe':{'status':'catalog_observed','candidate_count':1,'catalog_coverage':'partial_navigation_projection','matched_entities':['备份']},
            'catalog_hints':[{'topic_id':'entity:backup','title':'备份','abstract':'备份策略与恢复','overview':'本地、云镜像与清理','source_count':4,'coverage':{'sampled':3,'total':4},'pending_changes':1,'boundary':'navigation_only_not_fact_evidence'}]})
        self.assertIn('备份策略与恢复',context)
        self.assertIn('partial_navigation_projection',context)
        self.assertIn('目录未命中不等于Bank不存在',context)

    def test_short_followup_probe_reuses_guidance_active_context(self):
        seen=[]
        previous=recall.ENTRY_GUIDANCE_RECEIPT
        recall.ENTRY_GUIDANCE_RECEIPT={"request":{"task":{"context_summary":"前一项活动任务：修复链路页目录提示。","continuation":True}}}
        try:
            with tempfile.TemporaryDirectory() as root, patch.object(recall.urllib.request,"urlopen",side_effect=lambda request,timeout: seen.append(urllib.parse.unquote(request.full_url)) or Response()):
                recall.record_memory_route_probe(
                    {"session_id":"s1","turn_id":"t1"},"赶紧修正",
                    {"memoryRouteReceiptRoot":root,"memoryRouteStatusUrl":"http://127.0.0.1:12098"},"check-2",
                )
        finally:
            recall.ENTRY_GUIDANCE_RECEIPT=previous
        self.assertIn("修复链路页目录提示",seen[0])


if __name__ == "__main__":
    unittest.main()
