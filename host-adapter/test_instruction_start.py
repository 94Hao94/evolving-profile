import contextlib
import io
import json
import unittest
from unittest.mock import patch

import session_start
from lib.instruction_entry import CORE_TEXT


class InstructionStartTest(unittest.TestCase):
    def run_start(self, source, checkpoint='', offline=False):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(session_start, 'load_config', return_value={'autoRecall': False, 'autoRetain': False}))
            stack.enter_context(patch.object(session_start, 'ham_emit'))
            stack.enter_context(patch.object(session_start, '_record_instruction'))
            stack.enter_context(patch.object(session_start, 'record_output'))
            stack.enter_context(patch.object(session_start, 'load_checkpoint', return_value=checkpoint))
            stack.enter_context(patch.object(session_start, 'get_api_url', side_effect=RuntimeError('offline') if offline else None, return_value='http://127.0.0.1:12088'))
            stack.enter_context(patch.object(session_start, 'prestart_daemon_background'))
            stack.enter_context(patch.object(session_start.sys, 'stdin', io.StringIO(json.dumps({'session_id': 'fixture', 'source': source}))))
            stack.enter_context(contextlib.redirect_stdout(output))
            session_start.main()
        return json.loads(output.getvalue())['hookSpecificOutput']['additionalContext']

    def test_startup_offline_still_delivers_manual(self):
        self.assertIn(CORE_TEXT, self.run_start('startup', offline=True))

    def test_resume_and_compact_without_checkpoint_still_deliver_manual(self):
        for source in ('resume', 'compact'):
            with self.subTest(source=source):
                self.assertIn(CORE_TEXT, self.run_start(source))

    def test_large_checkpoint_does_not_push_manual_out(self):
        checkpoint = '<evolving_profile_checkpoint>' + '恢复状态' * 3000 + '</evolving_profile_checkpoint>'
        value = self.run_start('compact', checkpoint=checkpoint)
        self.assertIn(CORE_TEXT, value)
        self.assertIn(checkpoint, value)

if __name__ == '__main__':
    unittest.main()
