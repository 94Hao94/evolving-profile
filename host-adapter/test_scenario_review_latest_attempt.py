import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lib.scenario_model import validate_session_state, fingerprint_draft
from lib.scenario_source import read_session_source


class LatestReviewTest(unittest.TestCase):
    def test_failed_current_review_replaces_old_approval_and_dry_run_is_read_only(self):
        sid = '01a0c6a2-8e59-7e23-b595-15917157a2ca'
        spec = importlib.util.spec_from_file_location('review_pilot', Path(__file__).with_name('context-review-pilot.py'))
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            transcript = root / ('rollout-test-' + sid + '.jsonl')
            transcript.write_text('\n'.join(json.dumps(row) for row in [
                {'type': 'session_meta', 'payload': {'id': sid}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                 'content': [{'type': 'input_text', 'text': '只做材料分析'}]}}]) + '\n')
            source = read_session_source(sid, root)
            draft = validate_session_state(source, {'source_revision': source['source_revision'], 'events': [
                {'kind': 'user_goal', 'message_id': 'm1', 'quote': '只做材料分析'}]}, model='test')
            index = root / 'index.json'
            index.write_text(json.dumps({'schema': 'evolving-profile.context-index.v1', 'sessions': [{'session_id': sid}]}))
            drafts = root / 'drafts';drafts.mkdir()
            (drafts / (sid + '.json')).write_text(json.dumps(draft))
            reviews = root / 'reviews';reviews.mkdir()
            old = {'status': 'model_review_passed', 'source_revision': source['source_revision'],
                   'issues': [], 'draft_sha256': fingerprint_draft(draft)}
            review_path = reviews / (sid + '.json');review_path.write_text(json.dumps(old))
            argv = ['review', '--session-id', sid, '--session-root', str(root), '--index', str(index),
                    '--draft-dir', str(drafts), '--output-dir', str(reviews)]
            config = {'EVOLVING_PROFILE_API_LLM_BASE_URL': 'https://example.invalid',
                      'EVOLVING_PROFILE_API_LLM_API_KEY': 'test', 'EVOLVING_PROFILE_API_LLM_MODEL': 'test'}
            with patch.object(sys, 'argv', argv + ['--dry-run']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
            self.assertEqual(json.loads(review_path.read_text()), old)
            with patch.object(sys, 'argv', argv), patch.object(module, 'load_env', return_value=config), \
                    patch.object(module, 'request_session_review', side_effect=ConnectionError('unavailable')), \
                    patch('lib.context_retry.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 1)
            latest = json.loads(review_path.read_text())
            self.assertEqual(latest['status'], 'model_review_failed')
            self.assertEqual(latest['draft_sha256'], fingerprint_draft(draft))
            review_path.write_text(json.dumps(old))
            with patch.object(sys, 'argv', argv), \
                    patch.object(module, 'load_env', side_effect=FileNotFoundError('missing configuration')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 1)
            self.assertEqual(json.loads(review_path.read_text())['status'], 'model_review_failed')


if __name__ == '__main__':
    unittest.main()
