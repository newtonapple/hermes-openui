"""Custom component packs: JS files the user links from config that add components to the widget runtime.

A pack is a plain script. Its first comment is a JSON header so Python can learn the pack's components without running
JavaScript; the script registers them with the runtime that every widget page already carries (`window.__HM.register`).

    /* hermes-openui-pack
    {"api": 1, "name": "infra", "components": {"InfraMap": "InfraMap(zones: InfraZone[], title?: string) \u2014 what it draws."}}
    */
    (function () { var M = window.__HM.mods; ... window.__HM.register({ name: "infra", components: [ ... ] }); })();

A pack is embedded in a page only when the source calls one of its components. Packs run inside the same sandboxed frame as the
built-in runtime; the lint below is a guard against obvious mistakes, not a security boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from .lint import strip_strings

API = 1
MAX_PACK_BYTES = 200 * 1024
_HEADER = re.compile(r"/\*\s*hermes-openui-pack\b(.*?)\*/", re.S)
_PACK_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_COMPONENT = re.compile(r"^[A-Z][A-Za-z0-9]{0,47}$")
_CALL = re.compile(r"(?<![@\w$])([A-Z][A-Za-z0-9_]*)\s*\(")
# Code a pack must not contain: network access and dynamic code. Matched on the script with strings and comments blanked.
_BANNED = re.compile(
    r"\b(fetch|XMLHttpRequest|sendBeacon|WebSocket|EventSource|importScripts)\b|\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(|\bimport\s*\("
)


class PackError(Exception):
    """A problem with one pack, worded for the person who wrote it."""


class Pack:
    def __init__(self, name: str, path: Path, components: Dict[str, str], source: str):
        self.name = name
        self.path = path
        self.components = components
        self.source = source
        self.sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return "Pack(%r, %s)" % (self.name, sorted(self.components))


def parse_header(text: str) -> Dict:
    m = _HEADER.search(text)
    if not m:
        raise PackError("no `/* hermes-openui-pack {...} */` header comment")
    try:
        header = json.loads(m.group(1))
    except ValueError as e:
        raise PackError("the header is not valid JSON (%s)" % e)
    if not isinstance(header, dict):
        raise PackError("the header must be a JSON object")
    if header.get("api") != API:
        raise PackError("header `api` must be %d (this plugin speaks pack API %d)" % (API, API))
    name = header.get("name")
    if not isinstance(name, str) or not _PACK_NAME.match(name):
        raise PackError("header `name` must be a short lowercase slug such as `infra` (letters, digits, hyphens)")
    comps = header.get("components")
    if not isinstance(comps, dict) or not comps:
        raise PackError("header `components` must list at least one component: {\"Name\": \"Name(args) \u2014 what it does\"}")
    for cname, ref in comps.items():
        if not _COMPONENT.match(str(cname)):
            raise PackError("component name %r must be PascalCase (letters and digits, starting with a capital)" % cname)
        if not isinstance(ref, str) or not ref.strip():
            raise PackError("component %s needs a reference line, e.g. \"%s(args) \u2014 what it does\"" % (cname, cname))
    return header


def strip_js(text: str) -> str:
    """Blank comments and string/template literals so words inside them are not mistaken for code."""
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c in "\"'`":
            quote = c
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append(quote + quote)
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _files(entry: str) -> Tuple[List[Path], List[str]]:
    p = Path(os.path.expanduser(entry))
    if p.is_dir():
        found = sorted(f for f in p.glob("*.js") if f.is_file() and not f.name.startswith("."))
        return found, ([] if found else ["%s: the folder has no .js files" % p])
    if p.is_file():
        return [p], []
    return [], ["%s: no such file or folder" % p]


def load(paths: object, builtin_names: Set[str]) -> Tuple[List[Pack], List[str]]:
    """(packs, problems) for the config entries. A broken pack is skipped and reported; it never stops the others."""
    entries: Iterable = [paths] if isinstance(paths, str) else (paths if isinstance(paths, (list, tuple)) else [])
    found: List[Pack] = []
    problems: List[str] = []
    claimed: Dict[str, str] = {}
    names: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            continue
        files, errs = _files(entry.strip())
        problems.extend(errs)
        for f in files:
            try:
                size = f.stat().st_size
                if size > MAX_PACK_BYTES:
                    raise PackError("%d KB is over the %d KB limit" % (size // 1024, MAX_PACK_BYTES // 1024))
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    raise PackError("cannot read it as UTF-8 text (%s)" % e)
                header = parse_header(text)
                hit = _BANNED.search(strip_js(text))
                if hit:
                    raise PackError("uses `%s`, which packs may not use (no network access or dynamic code)" % hit.group(0).strip())
                if header["name"] in names:
                    raise PackError("pack name `%s` is already used by another linked pack" % header["name"])
                for cname in header["components"]:
                    if cname in builtin_names:
                        raise PackError("component `%s` shadows a built-in component; pick another name" % cname)
                    if cname in claimed:
                        raise PackError("component `%s` is already defined by %s" % (cname, claimed[cname]))
            except PackError as e:
                problems.append("%s: %s" % (f, e))
                continue
            names.add(header["name"])
            for cname in header["components"]:
                claimed[cname] = f.name
            found.append(Pack(header["name"], f, dict(header["components"]), text))
    return found, problems


def by_component(found: Iterable[Pack]) -> Dict[str, Pack]:
    return {c: p for p in found for c in p.components}


def used(source: str, found: Iterable[Pack]) -> List[Pack]:
    """Packs whose components `source` calls (text inside strings is ignored), in link order."""
    called = set(_CALL.findall(strip_strings(source)))
    return [p for p in found if called & set(p.components)]


def called_components(source: str, found: Iterable[Pack]) -> List[str]:
    """The custom component names `source` calls, sorted."""
    called = set(_CALL.findall(strip_strings(source)))
    return sorted(called & {c for p in found for c in p.components})


def reference(found: Iterable[Pack]) -> str:
    """Reference text for the linked packs, appended after the built-in component reference. Empty when none are linked."""
    found = list(found)
    if not found:
        return ""
    lines = ["", "## Custom components (linked by the user)", "", "These work like the components above, in preview mode only."]
    for p in found:
        lines += ["", "### %s" % p.name] + [p.components[c] for c in p.components]
    return "\n".join(lines) + "\n"
