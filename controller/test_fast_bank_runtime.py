#!/usr/bin/env python3
"""Regression tests for the runtime portion of the derived fast bank."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fast_bank import FastMemoryBank


class FastBankRuntimeRefreshTests(unittest.TestCase):
    def _write_snapshot(self, path: Path) -> None:
        path.write_text(
            json.dumps({"id": "snapshot-1", "text": "stable snapshot marker", "type": "world"}) + "\n",
            encoding="utf-8",
        )

    def _write_trace(self, path: Path, rows: list[dict]) -> None:
        path.write_text(
            json.dumps({"entries": {str(i): {"at": f"2026-09-04T00:0{i}:00Z", "selected_results": [row]}
                                       for i, row in enumerate(rows)}}),
            encoding="utf-8",
        )

    def test_new_trace_row_does_not_become_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, index, trace = root / "snapshot.jsonl", root / "index.sqlite3", root / "trace.json"
            common, policies = root / "common.json", root / "policies.json"
            self._write_snapshot(snapshot)
            self._write_trace(trace, [{"id": "old-trace", "text": "old runtime marker", "type": "world"}])
            common.write_text('{"candidates":[]}', encoding="utf-8")
            policies.write_text(json.dumps({"policies": []}), encoding="utf-8")
            bank = FastMemoryBank(snapshot, index, trace_index_path=trace, common_path=common, policies_path=policies)
            self.assertTrue(bank.ensure_ready())

            self._write_trace(trace, [
                {"id": "old-trace", "text": "old runtime marker", "type": "world"},
                {"id": "new-trace", "text": "Hindsight runtime refresh marker", "type": "world"},
            ])
            # Filesystems with coarse timestamp resolution are still handled by
            # the size component, but explicitly bump the mtime for clarity.
            now = time.time() + 2
            os.utime(trace, (now, now))
            items, receipt = bank.search("Hindsight runtime refresh marker", types=["world"])
            ids = {str(item.get("id")) for item in items}
            self.assertNotIn("trace:new-trace", ids)
            self.assertTrue(receipt.get("runtime_cache_as_of"))
            self.assertFalse(receipt.get("runtime_refresh_error"))

    def test_runtime_refresh_keeps_type_filter_and_policy_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, index, trace = root / "snapshot.jsonl", root / "index.sqlite3", root / "trace.json"
            common, policies = root / "common.json", root / "policies.json"
            self._write_snapshot(snapshot)
            self._write_trace(trace, [])
            common.write_text(
                json.dumps({"candidates": [{"id": "common-1", "text": "policy refresh marker", "type": "direct_policy"}]}),
                encoding="utf-8",
            )
            policies.write_text(json.dumps({"policies": []}), encoding="utf-8")
            bank = FastMemoryBank(snapshot, index, trace_index_path=trace, common_path=common, policies_path=policies)
            self.assertTrue(bank.ensure_ready())
            items, _ = bank.search("policy refresh marker", types=["direct_policy"])
            self.assertIn("candidate:common-1", {str(item.get("id")) for item in items})

    def test_common_candidate_lifecycle_filter_excludes_retired_and_discarded_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, index, trace = root / "snapshot.jsonl", root / "index.sqlite3", root / "trace.json"
            common, policies = root / "common.json", root / "policies.json"
            self._write_snapshot(snapshot)
            self._write_trace(trace, [])
            common.write_text(json.dumps({"candidates": [
                {"candidate_id": "keep", "text": "active common marker", "status": "processed", "decision": "add"},
                {"candidate_id": "discard", "text": "discarded common marker", "status": "processed", "decision": "discard"},
                {"candidate_id": "retired", "text": "retired common marker", "status": "retired-source-bank"},
            ]}), encoding="utf-8")
            policies.write_text(json.dumps({"policies": []}), encoding="utf-8")
            bank = FastMemoryBank(snapshot, index, trace_index_path=trace, common_path=common, policies_path=policies)
            self.assertTrue(bank.ensure_ready())
            items, _ = bank.search("active common marker", types=["world"])
            ids = {str(item.get("id")) for item in items}
            self.assertIn("candidate:keep", ids)
            self.assertNotIn("candidate:discard", ids)
            self.assertNotIn("candidate:retired", ids)

    def test_runtime_refresh_removes_a_candidate_newly_marked_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, index, trace = root / "snapshot.jsonl", root / "index.sqlite3", root / "trace.json"
            common, policies = root / "common.json", root / "policies.json"
            self._write_snapshot(snapshot)
            self._write_trace(trace, [])
            common.write_text(json.dumps({"candidates": [
                {"candidate_id": "flip", "text": "flip lifecycle marker", "status": "processed", "decision": "add"},
            ]}), encoding="utf-8")
            policies.write_text(json.dumps({"policies": []}), encoding="utf-8")
            bank = FastMemoryBank(snapshot, index, trace_index_path=trace, common_path=common, policies_path=policies)
            self.assertTrue(bank.ensure_ready())
            before, _ = bank.search("flip lifecycle marker", types=["world"])
            self.assertIn("candidate:flip", {str(item.get("id")) for item in before})
            common.write_text(json.dumps({"candidates": [
                {"candidate_id": "flip", "text": "flip lifecycle marker", "status": "processed", "decision": "discard"},
            ]}), encoding="utf-8")
            now = time.time() + 2
            os.utime(common, (now, now))
            after, _ = bank.search("flip lifecycle marker", types=["world"])
            self.assertNotIn("candidate:flip", {str(item.get("id")) for item in after})


if __name__ == "__main__":
    unittest.main()
