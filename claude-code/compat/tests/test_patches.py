import contextlib, io, os, stat, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_compat_patches as P

# syntactically valid stand-ins that contain exactly the anchors EP's real files contain
PRISTINE = {
    "retain.py": "import os\nf(\n            metadata={'source':'codex-hook-token-batch', 'session_id':session_id, 'z':1},\n)\n",
    "retention_worker.py": ("def f(batch, chosen):\n"
                            "    item={'content':batch['content'],'document_id':'codex-batch-'+batch['batch_id'],\n"
                            "          'metadata':{'source':'codex-hook-token-batch','project':batch['project'],'x':1}}\n"
                            "    return item\n"),
    "recall.py": 'import os\nrow = {\n            "host_id": "codex",\n}\n',
    "lib/session_paths.py": ("def session_roots(root):\n    roots=[root]\n"
                             "    if root.name=='sessions':roots.append(root.parent/'archived_sessions')\n"
                             "    return list(dict.fromkeys(roots))\n"),
}


def build(root, overrides=None):
    for rel, text in {**PRISTINE, **(overrides or {})}.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        os.chmod(p, 0o640)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = P.main(list(argv))
    return rc, out.getvalue()


class PatcherTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.t.name))
        build(self.root)

    def tearDown(self):
        self.t.cleanup()

    def snapshot(self):
        return {rel: (self.root / rel).read_bytes() for rel in PRISTINE}

    def test_pristine_files_are_classified_pristine_and_check_fails(self):
        self.assertEqual(set(P.states(self.root).values()), {"pristine"})
        self.assertEqual(run("check", "--adapter", str(self.root))[0], 1)

    def test_apply_patches_every_file_and_check_then_passes(self):
        rc, out = run("apply", "--adapter", str(self.root))
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(P.states(self.root).values()), {"applied"})
        self.assertEqual(run("check", "--adapter", str(self.root))[0], 0)
        self.assertIn("origin_agent", (self.root / "retain.py").read_text())
        self.assertIn("_origin", (self.root / "retention_worker.py").read_text())
        self.assertIn('os.environ.get("HINDSIGHT_AGENT_NAME")', (self.root / "recall.py").read_text())
        self.assertIn("rollouts", (self.root / "lib/session_paths.py").read_text())

    def test_apply_is_idempotent_and_touches_nothing_the_second_time(self):
        run("apply", "--adapter", str(self.root))
        before = self.snapshot(); backups = sorted(p.name for p in self.root.rglob("*.pre-reapply-*"))
        rc, out = run("apply", "--adapter", str(self.root))
        self.assertEqual(rc, 0); self.assertEqual(out.count("[skip]"), 4)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(p.name for p in self.root.rglob("*.pre-reapply-*")), backups)   # no new backups either

    def test_backup_equals_original_and_mode_is_preserved(self):
        originals = self.snapshot()
        run("apply", "--adapter", str(self.root))
        for rel, data in originals.items():
            p = self.root / rel
            backup = next(p.parent.glob(p.name + ".pre-reapply-*"))
            self.assertEqual(backup.read_bytes(), data)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o640)

    def test_dry_run_changes_nothing_and_makes_no_backup(self):
        before = self.snapshot()
        rc, out = run("apply", "--adapter", str(self.root), "--dry-run")
        self.assertEqual(rc, 0); self.assertEqual(out.count("[dry]"), 4)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.root.rglob("*.pre-reapply-*")))

    def test_half_applied_group_is_refused_and_left_untouched(self):
        # first edit of the two-edit retention_worker group is present, second is not -> would NameError at runtime
        a_old, a_new = P.GROUPS["retention_worker.py"][0]
        broken = PRISTINE["retention_worker.py"].replace(a_old, a_new)
        build(self.root, {"retention_worker.py": broken})
        self.assertEqual(P.states(self.root)["retention_worker.py"], "partial")
        rc, out = run("apply", "--adapter", str(self.root))
        self.assertEqual(rc, 1); self.assertIn("[REFUSE] retention_worker.py", out)
        self.assertEqual((self.root / "retention_worker.py").read_text(), broken)
        self.assertFalse(list(self.root.glob("retention_worker.py.pre-reapply-*")))
        self.assertEqual(P.states(self.root)["retain.py"], "applied")       # healthy files are still repaired

    def test_changed_upstream_anchor_is_refused(self):
        build(self.root, {"recall.py": 'import os\nrow = {\n            "host_id": "codex-2",\n}\n'})
        self.assertEqual(P.states(self.root)["recall.py"], "anchor_missing")
        before = (self.root / "recall.py").read_bytes()
        rc, out = run("apply", "--adapter", str(self.root))
        self.assertEqual(rc, 1); self.assertIn("[REFUSE] recall.py", out)
        self.assertEqual((self.root / "recall.py").read_bytes(), before)

    def test_missing_file_is_reported_not_crashed(self):
        (self.root / "lib/session_paths.py").unlink()
        self.assertEqual(P.states(self.root)["lib/session_paths.py"], "file_missing")
        rc, _ = run("check", "--adapter", str(self.root)); self.assertEqual(rc, 1)

    def test_result_that_would_not_compile_is_never_installed(self):
        # an upstream file where the anchor sits inside a construct that breaks once patched
        bad = "x = (\n            \"host_id\": \"codex\",\n"        # already not valid python, patched stays invalid
        build(self.root, {"recall.py": bad})
        original = (self.root / "recall.py").read_bytes()
        with self.assertRaises(Exception):
            P.cmd_apply(self.root, False)
        self.assertEqual((self.root / "recall.py").read_bytes(), original)
        self.assertFalse(list(self.root.glob("recall.py.pre-reapply-*")))
        self.assertFalse(list(self.root.glob("recall.py.new-*")), "stray temp file left behind")

    def test_anchor_appearing_twice_is_rejected(self):
        twice = PRISTINE["recall.py"] + 'row2 = {\n            "host_id": "codex",\n}\n'
        with self.assertRaises(ValueError):
            P.apply_edits(twice, P.GROUPS["recall.py"])


if __name__ == "__main__":
    unittest.main()
