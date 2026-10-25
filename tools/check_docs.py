#!/usr/bin/env python3
"""Mechanical quality gate for docs/ui-components/. Run it after writing or changing a page.

usage: python3 tools/check_docs.py [--only Metric,Table,...] [--no-node]

What it proves (it does not judge prose quality; read the pages for that):
  * every page has the required sections and an H1 equal to its file name
  * every signature in a page's Signature block is a line of assets/components.md, verbatim
  * every ```openui block equals an examples/<kebab-name>-*.oui file, and that file has a screenshot images/<same-name>.png
  * every example passes the structural checks and (when Node is available) the real OpenUI validator
  * every PNG is a real 2x screenshot (1344 px wide) under 300 KB
  * links between pages resolve; no machine-specific paths leak into pages or examples
  * (full run only) every component in the runtime is documented, and no example is orphaned
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import struct
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "ui-components"
REQUIRED = ["## Signature", "## When to use", "## Arguments", "## Examples", "## Tips and pitfalls"]
PNG_WIDTH = 1344  # 640 px column + 2 x 16 px padding, at 2x
PNG_MAX = 300 * 1024


def kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def load_pkg():
    spec = importlib.util.spec_from_file_location("hermes_openui", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_openui"] = mod
    spec.loader.exec_module(mod)
    return [importlib.import_module("hermes_openui." + n) for n in ("lint", "bundle", "tools")]


def load_docs_source():
    spec = importlib.util.spec_from_file_location("shoot", ROOT / "tools" / "shoot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.docs_source


def reference_signatures(text: str) -> Dict[str, str]:
    sigs: Dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Za-z0-9]*)\(", line)
        if m and " — " in line:
            sigs[m.group(1)] = line.split(" — ", 1)[0].strip()
    return sigs


def png_info(path: Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated page names (e.g. Metric,Table); skips the whole-set checks")
    ap.add_argument("--no-node", action="store_true", help="skip the Node validator")
    args = ap.parse_args()

    lint, bundle, tools = load_pkg()
    docs_source = load_docs_source()
    sigs = reference_signatures(bundle.reference_text())
    problems: List[str] = []

    pages = sorted(p for p in DOCS.glob("*.md") if p.name != "README.md")
    only: Set[str] = {n.strip() for n in args.only.split(",")} if args.only else set()
    if only:
        missing = only - {p.stem for p in pages}
        problems += ["page not found: %s.md" % n for n in sorted(missing)]
        pages = [p for p in pages if p.stem in only]
    if not pages and not problems:
        problems.append("no pages found in docs/ui-components/")

    covered: Set[str] = set()
    referenced_examples: Set[str] = set()
    examples_dir = DOCS / "examples"
    example_text = {p.name: p.read_text(encoding="utf-8") for p in examples_dir.glob("*.oui")}

    for page in pages:
        text = page.read_text(encoding="utf-8")
        tag = page.name
        lines = text.splitlines()
        if not lines or lines[0].strip() != "# %s" % page.stem:
            problems.append("%s: first line must be `# %s`" % (tag, page.stem))
        for h in REQUIRED:
            if not re.search(r"^%s\s*$" % re.escape(h), text, re.M):
                problems.append("%s: missing section `%s`" % (tag, h))
        intro = next((l for l in lines[1:] if l.strip() and not l.startswith(("#", "!", "```"))), "")
        if len(intro) < 40:
            problems.append("%s: needs a one-or-two sentence description right under the title" % tag)

        sig_block = re.search(r"^## Signature\s*\n+```[a-z]*\n(.*?)```", text, re.M | re.S)
        if not sig_block:
            problems.append("%s: the Signature section needs a fenced code block" % tag)
        else:
            sig_lines = [l.strip() for l in sig_block.group(1).splitlines() if l.strip()]
            if not sig_lines:
                problems.append("%s: empty Signature block" % tag)
            for l in sig_lines:
                name = re.match(r"^([A-Z][A-Za-z0-9]*)\(", l)
                if not name or sigs.get(name.group(1)) != l:
                    problems.append("%s: signature is not a verbatim line of assets/components.md: %s" % (tag, l[:90]))
                else:
                    covered.add(name.group(1))
            if page.stem not in {re.match(r"^([A-Z][A-Za-z0-9]*)\(", l).group(1) for l in sig_lines if re.match(r"^([A-Z][A-Za-z0-9]*)\(", l)}:
                problems.append("%s: the Signature block must include `%s(...)` itself" % (tag, page.stem))

        blocks = [b.rstrip() for b in re.findall(r"```openui\n(.*?)```", text, re.S)]
        if not blocks:
            problems.append("%s: needs at least one ```openui example" % tag)
        by_content = {v.rstrip(): k for k, v in example_text.items()}
        for b in blocks:
            name = by_content.get(b)
            if not name:
                problems.append("%s: an ```openui block does not match any file in examples/ (copy the .oui file exactly)" % tag)
                continue
            referenced_examples.add(name)
            if not name.startswith(kebab(page.stem) + "-"):
                problems.append("%s: example %s must be named %s-<variant>.oui" % (tag, name, kebab(page.stem)))
            if not (DOCS / "images" / (name[:-4] + ".png")).is_file():
                problems.append("%s: example %s has no screenshot images/%s.png" % (tag, name, name[:-4]))

        shown = re.findall(r"!\[[^\]]*\]\((images/[^)]+)\)", text)
        for img in shown:
            p = DOCS / img
            if not p.is_file():
                problems.append("%s: image not found: %s" % (tag, img))
                continue
            dims = png_info(p)
            if not dims:
                problems.append("%s: %s is not a PNG" % (tag, img))
            elif dims[0] != PNG_WIDTH:
                problems.append("%s: %s is %d px wide; screenshots must come from tools/shoot.py (%d px)" % (tag, img, dims[0], PNG_WIDTH))
            if p.stat().st_size > PNG_MAX:
                problems.append("%s: %s is %d KB; the limit is %d KB" % (tag, img, p.stat().st_size // 1024, PNG_MAX // 1024))
            if not (DOCS / "examples" / (p.stem + ".oui")).is_file():
                problems.append("%s: image %s has no matching examples/%s.oui" % (tag, img, p.stem))
        if not shown:
            problems.append("%s: needs at least one screenshot" % tag)

        for target in re.findall(r"\]\(([A-Za-z]+\.md)(?:#[^)]*)?\)", text):
            if only and target[:-3] in bundle.component_names():
                continue  # a sibling page another author is still writing
            if not (DOCS / target).is_file():
                problems.append("%s: broken link to %s" % (tag, target))
        if re.search(r"/Users/|/home/[a-z]|[A-Z]:\\\\|\.hermes/cache", text):
            problems.append("%s: contains a machine-specific path" % tag)

    check_names = list(example_text) if not only else sorted(referenced_examples)
    for name in check_names:
        src = docs_source(example_text[name])
        if re.search(r"/Users/|/home/[a-z]|[A-Z]:\\\\", example_text[name]):
            problems.append("examples/%s: contains a machine-specific path (use /path/to/sample.png for images)" % name)
        for p in lint.check(lint.strip_fences(src), bundle.component_names()):
            problems.append("examples/%s: %s" % (name, p))
        if not args.no_node:
            errs = tools._node_validate(lint.strip_fences(src))
            for e in errs or []:
                problems.append("examples/%s: validator: %s" % (name, e))

    if not only:
        for name in sorted(set(example_text) - referenced_examples):
            problems.append("examples/%s is not shown on any page" % name)
        expected = bundle.component_names()
        for c in sorted(expected - covered):
            problems.append("component %s is not documented (no page has its signature)" % c)
        for c in sorted(covered - expected):
            problems.append("page documents %s, which the runtime does not have" % c)

        index = DOCS / "README.md"
        if not index.is_file():
            problems.append("docs/ui-components/README.md (the gallery index) is missing")
        else:
            itext = index.read_text(encoding="utf-8")
            linked = set(re.findall(r"\]\(([A-Za-z]+)\.md(?:#[^)]*)?\)", itext))
            # helper components (TabItem, Series, ...) are documented on their parent's page and need no link of their own
            helpers = {c for c in expected if not (DOCS / (c + ".md")).is_file()}
            for c in sorted((expected - helpers) - linked):
                problems.append("README.md: no link to %s.md" % c)
            for t in sorted(linked - {p.stem for p in pages}):
                problems.append("README.md: links to %s.md, which does not exist" % t)
            for img in re.findall(r"(?:src=\"|\]\()(images/[^\")]+)", itext):
                if not (DOCS / img).is_file():
                    problems.append("README.md: image not found: %s" % img)
            if re.search(r"/Users/|/home/[a-z]|\.hermes/cache", itext):
                problems.append("README.md: contains a machine-specific path")

    if problems:
        print("%d problem(s):" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("docs OK: %d page(s), %d example(s) checked%s" % (len(pages), len(check_names), "" if only else ", all %d components documented" % len(bundle.component_names())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
