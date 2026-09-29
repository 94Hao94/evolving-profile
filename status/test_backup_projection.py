import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BackupProjectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('backup_projection_status',Path(__file__).with_name('evolving_profile_status_server.py'))
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    def test_groups_current_managed_backup_artifacts_by_timestamp(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)
            for name,size in (
                ('evolving-profile-db-20260919-032508.dump',10),
                ('evolving-profile-config-20260919-032508.tar.gz.enc',5),
                ('evolving-profile-capture-20260919-032508.sqlite.gz.enc',3),
                ('SHA256SUMS-20260919-032508',1),
            ):
                target=path/name;target.write_bytes(b'x'*size);os.utime(target,(100,100))
            with patch.object(self.module,'BACKUP_DIR',path):value=self.module.backup()
        self.assertTrue(value['present'])
        self.assertEqual(value['set_count'],1)
        self.assertEqual(value['total_bytes'],19)
        self.assertEqual(value['latest_set'],'20260919-032508')
        self.assertTrue(value['verified_complete'])

if __name__=='__main__':unittest.main()
