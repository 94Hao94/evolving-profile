"""Malformed model tool arguments must fail before identity/repository work."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from context_binding import bind_preference_request
from runtime_recovery import refresh_runtime_guidance
from test_runtime_recovery import Repo


class GuidanceInputValidationTests(unittest.TestCase):
    def test_task_shape_is_rejected_at_shared_binding_boundary(self):
        for task in ('a task', '', [], 0, False, None):
            with self.subTest(task=task), self.assertRaisesRegex(ValueError, 'task.*object'):
                bind_preference_request({'task': task})

    def test_non_object_request_is_not_treated_as_a_mapping(self):
        for request in ('request', [], None):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, 'arguments.*object'):
                bind_preference_request(request)

    def test_wrong_task_field_types_cannot_reach_selector(self):
        for field, value in [('objective', []), ('current_user_message', {}),
                             ('domains', 'npm'), ('current_constraints', [3]),
                             ('previous_user_messages', [False]), ('runtime_events', ['failure'])]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                bind_preference_request({'task': {field: value}})

    def test_original_call_shape_produces_actionable_validation_not_attribute_error(self):
        request = {'task': 'Render a short video', 'runtime_events': [
            {'event': 'dependency_install_failure', 'details': 'npm failed'}]}
        original = copy.deepcopy(request)
        with self.assertRaisesRegex(ValueError, 'task.*object'):
            refresh_runtime_guidance(object(), request)
        self.assertEqual(request, original)

    def test_runtime_event_array_is_not_silently_discarded_or_reinterpreted(self):
        with self.assertRaisesRegex(ValueError, 'runtime_event_required.*runtime_events'):
            refresh_runtime_guidance(object(), {'task': {'objective': 'render'},
                'runtime_events': [{'event': 'npm_failure', 'details': 'observed failure'}]})

    def test_runtime_fields_are_validated_before_repository_access(self):
        base = {'task': {'objective': 'render'}, 'runtime_event': {'failure': 'npm failed'}}
        cases = [('task', {'objective': 123}, 'objective'),
                 ('task', {'objective': '  '}, 'objective'),
                 ('task', {'objective': 'render', 'phase': 'unknown'}, 'phase'),
                 ('runtime_event', {'failure': {}}, 'failure'),
                 ('runtime_event', {'failure': '  '}, 'failure'),
                 ('runtime_event', {'failure': 'x', 'occurrence': True}, 'occurrence'),
                 ('runtime_event', {'failure': 'x', 'occurrence': 21}, 'occurrence'),
                 ('runtime_event', {'failure': 'x', 'tool': []}, 'tool'),
                 ('runtime_event', {'failure': 'x', 'details': 'extra'}, 'runtime_event'),
                 ('loaded', ['bad'], 'loaded'), ('max_tokens', True, 'max_tokens'),
                 ('max_tokens', 9000, 'max_tokens'), ('memory_policy', 'anything', 'memory_policy')]
        for field, value, expected in cases:
            request = {**base, field: value}
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, expected):
                refresh_runtime_guidance(object(), request)

    def test_unknown_fields_are_not_echoed_into_errors(self):
        secret = 'private-content-must-not-be-reflected'
        for extra in ({secret: 'x'}, {'runtime_event': {'failure': 'x', secret: 'x'}}):
            request = {'task': {'objective': 'render'}, 'runtime_event': {'failure': 'x'}, **extra}
            with self.subTest(extra=extra), self.assertRaises(ValueError) as caught:
                refresh_runtime_guidance(object(), request)
            self.assertNotIn(secret, str(caught.exception))

    def test_valid_request_stays_read_only_and_unmodified(self):
        request = {'task': {'objective': '恢复工具验收', 'phase': 'verify'},
                   'runtime_event': {'failure': 'transport unavailable', 'occurrence': 1}}
        original = copy.deepcopy(request)
        result = refresh_runtime_guidance(Repo(), request)
        self.assertEqual(result['mode'], 'runtime_guidance_refresh')
        self.assertEqual(result['persistence'], 'none_current_turn_only')
        self.assertFalse(result['long_term_model_created'])
        self.assertEqual(result['runtime_event']['failure'], 'transport unavailable')
        self.assertEqual(request, original)
