import json, subprocess, sys, tempfile, unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
SCRIPT = KIT / "install_cli_hooks.py"
USER_HOOK = {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "echo mine"}]}


def run(settings, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), "--settings", str(settings), "--ep-home", "/tmp/ep-test-home", *extra],
                          capture_output=True, text=True)


class InstallCliHooks(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.p = Path(self.d.name) / "settings.json"
        self.addCleanup(self.d.cleanup)

    def load(self):
        return json.loads(self.p.read_text())

    def test_creates_file_when_missing_and_registers_six_events(self):
        r = run(self.p)
        self.assertEqual(r.returncode, 0, r.stderr)
        hooks = self.load()["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop"})
        self.assertEqual(len(hooks["PreToolUse"]), 2)

    def test_keeps_foreign_keys_and_foreign_hooks_and_is_idempotent(self):
        self.p.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Read"]}, "hooks": {"PreToolUse": [USER_HOOK]}}))
        run(self.p)
        first = self.load()
        run(self.p)
        self.assertEqual(self.load(), first, "second run must not change anything")
        self.assertEqual(first["model"], "x")
        self.assertEqual(first["permissions"], {"allow": ["Read"]})
        self.assertIn(USER_HOOK, first["hooks"]["PreToolUse"])
        self.assertEqual(len(first["hooks"]["PreToolUse"]), 3)

    def test_uninstall_removes_only_ours(self):
        self.p.write_text(json.dumps({"hooks": {"PreToolUse": [USER_HOOK]}}))
        run(self.p)
        run(self.p, "--uninstall")
        self.assertEqual(self.load(), {"hooks": {"PreToolUse": [USER_HOOK]}})

    def test_dry_run_changes_nothing_and_backup_is_made_on_change(self):
        self.p.write_text("{}")
        run(self.p, "--dry-run")
        self.assertEqual(self.p.read_text(), "{}")
        run(self.p)
        self.assertTrue(list(Path(self.d.name).glob("settings.json.pre-ep-*")))

    def test_unparseable_settings_are_never_overwritten(self):
        self.p.write_text("{not json")
        r = run(self.p)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.p.read_text(), "{not json")


if __name__ == "__main__":
    unittest.main()
