import json, unittest
from test_retention_worker import RetentionWorkerTest as Base


class OriginAgentTest(Base):
    """Reuses the fake EP API + real worker subprocess from the existing suite."""

    def cap(self, sid, project, meta, at='2020-01-01T00:00:00Z'):
        self.queue.capture(session_id=sid, message_count=1, bank_id="test-bank", project=project,
                           content="真实用户原话", metadata=meta, captured_at=at)

    def submitted_meta(self):
        self.assertEqual(self.run_worker()['status'], 'submitted')
        self.assertEqual(len(self.posts), 1)
        return self.posts[0]['items'][0]['metadata']

    def test_desktop_origin_is_carried_to_bank_metadata(self):
        self.cap('s-desktop', '/p', {"source": "codex-hook-token-batch", "origin_agent": "claude-desktop"})
        m = self.submitted_meta()
        self.assertEqual(m['origin_agent'], 'claude-desktop')
        self.assertEqual(m['source'], 'codex-hook-token-batch')           # old value unchanged
        self.assertTrue(self.posts[0]['items'][0]['document_id'].startswith('codex-batch-'))  # prefix unchanged

    def test_legacy_item_without_field_defaults_to_codex(self):
        self.cap('s-legacy', '/p', {"source": "codex-hook-token-batch"})
        self.assertEqual(self.submitted_meta()['origin_agent'], 'codex')

    def test_mixed_batch_lists_both_origins(self):
        self.cap('s-a', '/p', {"source": "codex-hook-token-batch", "origin_agent": "claude-desktop"})
        self.cap('s-b', '/p', {"source": "codex-hook-token-batch", "origin_agent": "codex"})
        self.assertEqual(self.submitted_meta()['origin_agent'], 'claude-desktop,codex')


if __name__ == '__main__':
    unittest.main()
