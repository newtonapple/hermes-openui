"""Load the plugin package from its folder (the directory name has a hyphen, so it cannot be imported by name)."""
import importlib
import importlib.util
import re
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


# What a private setup leaves in a file, found without naming anyone: an address, a URL, a host name with a common
# top-level domain, a `.ts.net` host, a numbered spark host.
PRIVATE_SETUP = re.compile(
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|https?://|\.ts\.net\b|\bspark-\d|\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|ai|app|cloud)\b",
    re.I,
)
# Public product names. They are not secret, but a public fixture or skill has no reason to use them.
PRODUCT_WORDS = re.compile(r"litellm|vllm|dgx|qwen|llama|ollama", re.I)


def private_setup_hits(text):
    """The details in `text` that would identify a private setup, sorted and de-duplicated."""
    return sorted({m.group(0) for rx in (PRIVATE_SETUP, PRODUCT_WORDS) for m in rx.finditer(text)})
