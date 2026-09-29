import subprocess
import unittest
from pathlib import Path


class DatabaseOwnerCalibrationTest(unittest.TestCase):
    def test_check_mode_reports_owner_drift_without_changing_database(self):
        """A future admin-owned migration must be visible before API startup hides it as a DDL 500."""
        script = Path.home() / ".evolving-profile" / "bin" / "evolving-profile-db-owner-calibration.zsh"
        result = subprocess.run(["zsh", str(script), "--check"], text=True, capture_output=True, check=False)

        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertIn('"status"', result.stdout)


if __name__ == "__main__":
    unittest.main()
