import subprocess
import sys
import unittest
from pathlib import Path


class RuntimeHamImportTest(unittest.TestCase):
    def test_hook_runtime_resolves_the_adjacent_evolving_profile_ham_source(self):
        """A fixed historical source path silently prevented deployed hooks from using current HAM fixes."""
        host_adapter = Path(__file__).resolve().parent
        program = f"""
import sys
sys.path.insert(0, {str(host_adapter)!r})
from lib.runtime_paths import ham_source_root
root = ham_source_root({str(host_adapter / 'post_tool_use.py')!r})
sys.path.insert(0, root)
import ham.adapter
print(root)
print(ham.adapter.__file__)
"""
        result = subprocess.run([sys.executable, "-c", program], text=True, capture_output=True, check=True)
        lines = result.stdout.splitlines()

        self.assertEqual(Path(lines[0]), host_adapter.parent / "ham-os")
        self.assertEqual(Path(lines[1]).resolve(), host_adapter.parent / "ham-os" / "ham" / "adapter.py")


if __name__ == "__main__":
    unittest.main()
