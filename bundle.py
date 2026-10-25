"""Bundled runtime assets: the browser runtime (core + packs), the component reference, the optional Node validator."""
from __future__ import annotations

import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
VALIDATOR = ASSETS / "validate.cjs"


@lru_cache(maxsize=1)
def manifest() -> Dict:
    return json.loads((ASSETS / "packs.json").read_text(encoding="utf-8"))


def component_names() -> Set[str]:
    m = manifest()
    return set(m["core"]["components"]) | set(m["components"])


@lru_cache(maxsize=1)
def reference_text() -> str:
    """The component/syntax reference the model reads (generated from the same library the runtime is built from)."""
    return (ASSETS / "components.md").read_text(encoding="utf-8")


def verify() -> List[str]:
    """Integrity problems with the shipped bundles (empty list = every bundle matches its recorded SHA-256)."""
    problems: List[str] = []
    m = manifest()
    entries = [("core", m["core"])] + sorted(m["packs"].items())
    for name, info in entries:
        path = ASSETS / info["file"]
        if not path.is_file():
            problems.append("missing asset: %s" % info["file"])
            continue
        try:
            raw = gzip.decompress(path.read_bytes())
        except OSError as e:
            problems.append("%s is not valid gzip: %s" % (info["file"], e))
            continue
        if hashlib.sha256(raw).hexdigest() != info.get("sha256"):
            problems.append("%s does not match its recorded SHA-256 (corrupted or edited by hand)" % info["file"])
    return problems
