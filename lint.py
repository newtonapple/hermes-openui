"""Structural checks for OpenUI Lang that need no Node: the failures a model actually makes.

This is NOT a replacement for the real parser. When Node is available the bundled validator (assets/validate.cjs) runs
after these checks and also verifies argument types, parallel chart arrays and cross-references. These checks exist so
that a machine without Node still gets feedback on: truncated or unbalanced source, a missing `root`, undefined or
unreachable variables, unknown components, colon-style arguments, and constructs a widget cannot use.
"""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Set, Tuple

# Builtins the language provides that are not widget components.
BUILTIN_CALLS = {"Action"}
KEYWORDS = {"true", "false", "null", "root"}

_STMT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", re.S)
_CALL = re.compile(r"(?<![@\w$])([A-Z][A-Za-z0-9_]*)\s*\(")
_REF = re.compile(r"(?<![\w@$.])([a-z_][A-Za-z0-9_]*)\b(?!\s*[\(:])")


def strip_strings(text: str) -> str:
    """Blank out double-quoted string literals so words inside text are never mistaken for code."""
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append('""')
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def strip_fences(source: str) -> str:
    """Models often wrap source in a markdown fence even when told not to; the language has no fences."""
    s = source.strip().lstrip("\ufeff")
    m = re.match(r"^```[A-Za-z0-9_-]*\s*\n(.*?)\n?```\s*$", s, re.S)
    return (m.group(1) if m else s).strip("\n") + "\n"


def split_statements(source: str) -> Tuple[List[Tuple[int, str]], bool]:
    """(line, text) per statement, tracking brackets and strings so a statement may span lines. Second value: True when
    the source ends inside an open bracket or string (truncated)."""
    stmts: List[Tuple[int, str]] = []
    cur: List[str] = []
    start = 1
    depth = 0
    in_str = False
    for lineno, line in enumerate(source.splitlines(), 1):
        if not cur and not line.strip():
            continue
        if not cur:
            start = lineno
        cur.append(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                if ch == "\\":
                    i += 1
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            i += 1
        if depth <= 0 and not in_str:
            stmts.append((start, "\n".join(cur)))
            cur = []
            depth = 0
    truncated = bool(cur)
    if cur:
        stmts.append((start, "\n".join(cur)))
    return stmts, truncated


def _colon_args(expr: str) -> List[str]:
    """Names written as `name: value` directly inside a call's parentheses (not inside an object literal)."""
    found: List[str] = []
    stack: List[str] = []
    for m in re.finditer(r"[\(\[\{\)\]\}]|([A-Za-z_]\w*)\s*:(?!:)", expr):
        tok = m.group(0)
        if tok in "([{":
            stack.append(tok)
        elif tok in ")]}":
            if stack:
                stack.pop()
        elif stack and stack[-1] == "(":
            found.append(m.group(1))
    return found


def check(source: str, known_components: Set[str]) -> List[str]:
    """Problems found in `source` (empty list = nothing the structural checks can see)."""
    problems: List[str] = []
    if not source.strip():
        return ["Source is empty. Write `root = Stack([...])` plus one statement per component."]

    stmts, truncated = split_statements(source)
    if truncated:
        problems.append("Source looks truncated or unbalanced: a bracket or a double quote is never closed.")

    defined: Dict[str, int] = {}
    exprs: Dict[str, str] = {}
    for line, text in stmts:
        m = _STMT.match(text)
        if not m:
            first = text.strip().splitlines()[0][:70]
            problems.append("Line %d is not a statement of the form `name = Expression`: %s" % (line, first))
            continue
        name, expr = m.group(1), m.group(2)
        if name in defined:
            problems.append("`%s` is defined twice (lines %d and %d)." % (name, defined[name], line))
        defined[name] = line
        exprs[name] = expr

    if "root" not in defined:
        problems.append("No `root` statement. The entry point must be `root = Stack([...])`.")

    refs: Dict[str, Set[str]] = {}
    seen_unknown: Set[str] = set()
    for name, expr in exprs.items():
        code = strip_strings(expr)
        refs[name] = {r for r in _REF.findall(code) if r not in KEYWORDS}
        for comp in _CALL.findall(code):
            if comp in known_components or comp in BUILTIN_CALLS or comp in seen_unknown:
                continue
            seen_unknown.add(comp)
            close = difflib.get_close_matches(comp, sorted(known_components), n=2, cutoff=0.6)
            hint = " Did you mean %s?" % " or ".join("`%s`" % c for c in close) if close else ""
            problems.append("Unknown component `%s` in `%s`.%s" % (comp, name, hint))
        for bad in _colon_args(code):
            problems.append("`%s` uses colon syntax (`%s: ...`). Arguments are POSITIONAL: write the values in order, without names." % (name, bad))
        if "$" in code:
            problems.append("`%s` uses a `$variable`. Widgets are static: use literal values, no variables, queries or mutations." % name)
        if "@OpenUrl" in code:
            problems.append("`%s` uses @OpenUrl. The widget is sandboxed and cannot navigate: put the link in a Text instead." % name)

    for name, rs in sorted(refs.items()):
        for r in sorted(rs):
            if r not in defined:
                problems.append("`%s` refers to `%s`, which is never defined." % (name, r))

    if "root" in defined:
        reach: Set[str] = set()
        todo = ["root"]
        while todo:
            cur = todo.pop()
            if cur in reach or cur not in refs:
                continue
            reach.add(cur)
            todo.extend(r for r in refs[cur] if r in defined)
        for name in defined:
            if name not in reach:
                problems.append("`%s` is defined but not reachable from root, so it will not render. Add it to its parent's children." % name)

    return problems
