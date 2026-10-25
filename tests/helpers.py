"""Load the plugin package from its folder (the directory name has a hyphen, so it cannot be imported by name)."""
import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "hermes_openui"


def load():
    if PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[PKG] = mod
        spec.loader.exec_module(mod)
    return sys.modules[PKG]


def sub(name):
    load()
    return importlib.import_module("%s.%s" % (PKG, name))


def examples():
    return sorted((ROOT / "examples").glob("*.oui"))
