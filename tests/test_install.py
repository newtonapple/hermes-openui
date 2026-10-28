"""scripts/install.sh must copy every runtime module. A hard-coded file list once left a new module behind and the installed plugin failed to load."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

ROOT = helpers.ROOT


@unittest.skipUnless(shutil.which("sh") and shutil.which("cp"), "needs sh and cp")
class InstallScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name)
        r = subprocess.run(["sh", str(ROOT / "scripts" / "install.sh"), "--home", str(cls.home), "--no-enable"], capture_output=True, text=True, timeout=120)
        cls.result = r
        cls.dest = cls.home / "plugins" / "hermes-openui"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_script_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)

    def test_every_top_level_python_module_is_installed(self):
        source = {p.name for p in ROOT.glob("*.py")}
        installed = {p.name for p in self.dest.glob("*.py")}
        self.assertEqual(sorted(source - installed), [], "install.sh left these runtime modules behind")

    def test_the_examples_folder_is_installed(self):
        for name in ("dashboard.oui", "reports/platform-status.json"):
            with self.subTest(example=name):
                self.assertTrue((self.dest / "examples" / name).is_file())

    def test_the_installed_copy_imports_cleanly(self):
        code = (
            "import importlib.util, sys; "
            "spec = importlib.util.spec_from_file_location('hermes_plugins_probe', %r, submodule_search_locations=[%r]); "
            "m = importlib.util.module_from_spec(spec); sys.modules['hermes_plugins_probe'] = m; spec.loader.exec_module(m); "
            "print('imported', sorted(n for n in dir(m) if n in ('cli', 'export', 'packs', 'tools', 'page')))"
        ) % (str(self.dest / "__init__.py"), str(self.dest))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("'cli'", r.stdout)
        self.assertIn("'export'", r.stdout)
        self.assertIn("'packs'", r.stdout)


if __name__ == "__main__":
    unittest.main()
