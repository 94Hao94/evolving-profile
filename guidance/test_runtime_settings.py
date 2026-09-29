import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_settings import DEFAULT_SETTINGS, load_runtime_settings, module_enabled, route_policy


class RuntimeSettingsTest(unittest.TestCase):
    def test_defaults_keep_ep_modules_on_and_external_rag_off(self):
        with tempfile.TemporaryDirectory() as root, patch("runtime_settings.SETTINGS_PATH", Path(root) / "settings.json"):
            value = load_runtime_settings()
        self.assertTrue(value["modules"]["facts"]["retrieve"])
        self.assertTrue(value["modules"]["scenario_summary"]["retrieve"])
        self.assertFalse(value["rag"]["enabled"])
        self.assertEqual(value["routing"]["mode"], "auto")

    def test_disabled_module_is_reported_without_mutating_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "settings.json"
            path.write_text(json.dumps({"modules": {"preferences": {"retrieve": False}}}), encoding="utf-8")
            with patch("runtime_settings.SETTINGS_PATH", path):
                value = load_runtime_settings()
        self.assertFalse(module_enabled(value, "preferences", "retrieve"))
        self.assertTrue(module_enabled(value, "facts", "retrieve"))

    def test_route_policy_never_enables_rag_when_disabled(self):
        value = dict(DEFAULT_SETTINGS)
        value["rag"] = {**DEFAULT_SETTINGS["rag"], "enabled": False}
        value["routing"] = {**DEFAULT_SETTINGS["routing"], "mode": "both_isolated"}
        policy = route_policy(value, request_source="auto")
        self.assertEqual(policy["sources"], ["ep"])
        self.assertFalse(policy["rag_enabled"])

    def test_provider_profiles_keep_fallbacks_out_of_ep_module_switches(self):
        value = load_runtime_settings()
        value["providers"]["fallbacks"] = [{"name": "backup", "api_key": "secret"}]
        self.assertTrue(module_enabled(value, "preferences", "retrieve"))
        self.assertEqual(value["providers"]["fallbacks"][0]["name"], "backup")


if __name__ == "__main__":
    unittest.main()
