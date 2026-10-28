"""The `render_widget` tool: validate OpenUI Lang, write the widget file, return the directive the model puts in its reply."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from . import bundle, lint, packs, page

MAX_SOURCE_CHARS = 200_000
NODE_TIMEOUT_S = 20
_ERR_LINE = re.compile(r"^- (.+)$", re.M)
# A plugin skill is not in the system prompt's skill index, so the tool's own text has to point to it.
CUSTOM_SKILL_HINT = "To add your own component, see skill_view('hermes-openui:custom-components')."


def hermes_home() -> Path:
    """Profile-aware Hermes home (never hard-code ~/.hermes: one process serves several profiles)."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def widgets_dir() -> Path:
    d = hermes_home() / "widgets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: object) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", name if isinstance(name, str) else "").strip("-.")[:48] or "widget"
    # A fresh suffix every time: reusing a name must not silently rewrite widgets that older messages already show.
    return "%s-%s" % (base, secrets.token_hex(3))


def _node_validate(source: str, extra_packs: Optional[list] = None) -> Optional[List[str]]:
    """Errors from the bundled Node validator; [] = valid; None = not run (no Node, validator missing, timeout)."""
    node = shutil.which("node")
    if not node or not bundle.VALIDATOR.is_file():
        return None
    env = {k: v for k, v in os.environ.items() if k != "OPENUI_RUNTIME_TELEMETRY_ENABLED"}
    env.update({"DO_NOT_TRACK": "1", "OPENUI_TELEMETRY_DISABLED": "1"})
    fd, tmp = tempfile.mkstemp(suffix=".oui")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source)
        cmd = [node, str(bundle.VALIDATOR)]
        for pack in extra_packs or []:
            cmd += ["--pack", str(pack.path)]
        proc = subprocess.run(cmd + [tmp], capture_output=True, text=True, timeout=NODE_TIMEOUT_S, env=env)
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if proc.returncode == 0:
        return []
    out = (proc.stdout + proc.stderr).strip()
    errs = _ERR_LINE.findall(out) or [out[:400] or "validation failed"]
    return [e[:320] for e in errs[:12]]


def _fail(errors: List[str], hint: str = "Fix exactly these and call render_widget again. Nothing was written.") -> str:
    return json.dumps({"ok": False, "errors": errors, "fix": hint}, ensure_ascii=False)


def _point_unknown_component_to_skill(problems: List[str]) -> List[str]:
    """Add the hint to the first `Unknown component` error only; the others and the Node validator's wording stay as they are."""
    for i, text in enumerate(problems):
        if text.startswith("Unknown component `"):
            problems[i] = "%s %s" % (text, CUSTOM_SKILL_HINT)
            break
    return problems


def load_custom(settings: Optional[dict]):
    """(packs, problems) for the `components` setting. A broken pack is reported, never fatal."""
    return packs.load((settings or {}).get("components") or [], bundle.component_names())


def render_widget(params: dict, mode: str = "preview", settings: Optional[dict] = None, **_kwargs) -> str:
    """Tool handler. Returns a JSON string (the registry contract). `settings` is the plugin's config (`components`)."""
    params = params if isinstance(params, dict) else {}
    source = params.get("source")
    custom, pack_problems = load_custom(settings)

    if params.get("reference") or not (isinstance(source, str) and source.strip()):
        out = {
            "ok": True,
            "reference": bundle.reference_text() + packs.reference(custom),
            "next": "Call render_widget with source=<OpenUI Lang>. One statement per line, root first, positional arguments. "
            "Patterns and pitfalls: skill_view('hermes-openui:openui-render'). " + CUSTOM_SKILL_HINT,
        }
        if pack_problems:
            out["pack_warnings"] = pack_problems[:5]
        return json.dumps(out, ensure_ascii=False)

    source = lint.strip_fences(source)
    if len(source) > MAX_SOURCE_CHARS:
        return _fail(["Source is %d characters; the limit is %d. Use fewer rows or cards." % (len(source), MAX_SOURCE_CHARS)])

    problems = lint.check(source, bundle.component_names() | set(packs.by_component(custom)))
    if problems:
        return _fail(_point_unknown_component_to_skill(problems)[:12])
    used = packs.used(source, custom)
    if used and mode == "native":
        names = packs.called_components(source, used)
        return _fail(["Custom components (%s) only work in preview mode: native mode renders in the app itself and does not run user scripts. "
                      "Set the plugin's mode to preview." % ", ".join(names)], "Nothing was written.")
    node_errors = _node_validate(source, used)
    if node_errors:
        return _fail(node_errors)
    checked = "node" if node_errors == [] else "structural"

    try:
        source = page.inline_images(source)
        slug = _slug(params.get("name"))
        out_dir = widgets_dir()
        if mode == "native":
            if len(source.encode("utf-8")) > page.SAFE_BUDGET:
                raise page.WidgetError("The widget source is %d KB; the desktop reads at most %d KB. Use fewer rows or smaller images." % (len(source) // 1024, page.SAFE_BUDGET // 1024))
            path = out_dir / (slug + ".oui")
            path.write_text(source, encoding="utf-8")
            directive, packs_used, size = '::openui{file="%s"}' % path, [], path.stat().st_size
        else:
            html, used_packs = page.build_page(source, title="Hermes widget", extra_packs=used)
            path = out_dir / (slug + ".html")
            path.write_text(html, encoding="utf-8")
            directive, packs_used, size = '::preview{file="%s"}' % path, used_packs, path.stat().st_size
    except page.WidgetError as e:
        return _fail([str(e)], "Nothing was written. Adjust and call render_widget again.")
    except OSError as e:
        return _fail(["Could not write the widget file: %s" % e], "Nothing was written.")

    out = (
        {
            "ok": True,
            "directive": directive,
            "mode": mode,
            "packs": packs_used,
            "bytes": size,
            "checked": checked,
            "next": "Put the directive ALONE on its own line in your reply, after at most one sentence of context. Do not repeat the widget's data in prose.",
        }
    )
    if pack_problems:
        out["pack_warnings"] = pack_problems[:5]
    return json.dumps(out, ensure_ascii=False)
