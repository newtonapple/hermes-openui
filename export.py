"""The `export_widgets` tool: one standalone, offline HTML report written to a place the user chose.

Sections are new OpenUI Lang (`source`, validated exactly like render_widget) or widgets already shown in this chat (`widget`: a
file name in this profile's widgets folder, whose source is read back out of the file render_widget wrote). The page itself is built
by page.build_export_page. This module owns what is specific to leaving the chat: WHERE the file may be written.

Destination policy (see check_destination): Hermes's own write guard decides when it is importable; otherwise a conservative built-in
denylist applies. Only .html/.htm files are ever written, symlinks are resolved before any check, missing folders are created only
after the checks pass, and the file is written atomically (temp file in the same folder, then os.replace).
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import bundle, lint, packs, page, tools

logger = logging.getLogger(__name__)

MAX_SECTIONS = 30
MAX_TITLE_CHARS = 120
MAX_ERRORS = 12
EXPORT_IMAGE_MAX = 1024 * 1024  # per image; render_widget keeps its 100 KB because a chat widget shares a 480 KB page budget
MAX_WIDGET_FILE = 4 * 1024 * 1024  # widget pages are under 512 KiB; anything bigger is not one
DEFAULT_TITLE = "Hermes report"
HTML_SUFFIXES = (".html", ".htm")
_WIDGET_SRC = re.compile(r'<script id="oui-src" type="application/json">(.*?)</script>', re.S)
_FIX = "Fix exactly these and call export_widgets again. Nothing was written."


class ExportError(Exception):
    """A problem the model (or user) can fix; the message is returned to it verbatim. `errors` lists several when there are several."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


# ---------------------------------------------------------------------------------------------------------------------
# Destination policy
# ---------------------------------------------------------------------------------------------------------------------

# Fallback denylist, used ONLY when Hermes's own guard (agent.file_safety) cannot be imported. Deliberately short and conservative:
# credentials the user would never want a report written into, Hermes's own secrets and code, and the system roots.
#   under the user's home:  .ssh .aws .gnupg .config/gcloud .kube .docker
#   in the Hermes home (this profile's, and the default ~/.hermes with each of its profiles/<name>):
#                           .env auth.json config.yaml (files), plugins skills sessions (folders)
#   system roots:           /etc /usr /bin /sbin /System /Library /private/etc /var/root
# Matching is on whole path components, case-insensitive (macOS volumes are), after symlinks were resolved. POSIX paths only.
_HOME_DENY = (".ssh", ".aws", ".gnupg", ".config/gcloud", ".kube", ".docker")
_HERMES_DENY = (".env", "auth.json", "config.yaml", "plugins", "skills", "sessions")
_SYSTEM_DENY = ("/etc", "/usr", "/bin", "/sbin", "/System", "/Library", "/private/etc", "/var/root")


def _norm(path: str) -> str:
    return path.replace(os.sep, "/").rstrip("/").casefold() or "/"


def _under(path: str, base: str) -> bool:
    p, b = _norm(path), _norm(base)
    return p == b or p.startswith(b.rstrip("/") + "/")


def _real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return path


def _fallback_denial(candidates: List[str]) -> Optional[str]:
    """What the built-in list refuses, as `(location)`; None when the path is fine."""
    home = os.path.expanduser("~")
    hermes = str(tools.hermes_home())
    protected: List[Tuple[str, str]] = []
    for base in {home, _real(home)}:
        protected += [(os.path.join(base, rel), "~/" + rel) for rel in _HOME_DENY]
    default_root = os.path.join(home, ".hermes")
    for base in {hermes, _real(hermes), default_root, _real(default_root)}:
        protected += [(os.path.join(base, rel), "the Hermes home's " + rel) for rel in _HERMES_DENY]
    for root in _SYSTEM_DENY:
        protected += [(root, root), (_real(root), root)]
    profiles = [os.path.join(b, "profiles") for b in {hermes, _real(hermes), default_root, _real(default_root)}]
    for cand in candidates:
        for base, label in protected:
            if _under(cand, base):
                return label
        for root in profiles:
            if _under(cand, root):
                rest = _norm(cand)[len(_norm(root)):].strip("/").split("/")
                if len(rest) >= 2 and rest[1] in {d.casefold() for d in _HERMES_DENY}:
                    return "a Hermes profile's " + rest[1]
    return None


def check_destination(path: str) -> Optional[str]:
    """An error message when `path` (the final .html file) must not be written, else None. Writes and creates nothing.

    Symlinks are resolved first (the nearest existing parent decides), and both the literal and the resolved path are checked. When
    Hermes's own guard is importable it is asked first: a denied path is refused with its text, and a path that needs the user's
    approval is refused too (this tool never routes around the approval system). The built-in list above ALWAYS applies as well:
    the real guard allows places such as ~/.hermes/plugins, skills and /etc, and an exported page has no business there."""
    literal = os.path.abspath(os.path.expanduser(str(path)))
    resolved = _real(literal)
    candidates = [literal] if literal == resolved else [literal, resolved]
    try:
        from agent.file_safety import get_write_denied_error, is_write_approval_required  # type: ignore
    except ImportError:
        get_write_denied_error = is_write_approval_required = None
    if get_write_denied_error is not None and is_write_approval_required is not None:
        try:
            for cand in candidates:
                text = get_write_denied_error(cand)
                if text:
                    return str(text)
            for cand in candidates:
                if is_write_approval_required(cand):
                    return (
                        "Writing to %s needs the user's approval in Hermes, and this tool never routes around that. Choose a normal folder "
                        "(leave `path` out for the default exports folder), or ask the user to approve saving a copy with the file tools." % cand
                    )
        except Exception:  # a guard that misbehaves must not open the gate: use the built-in list instead
            logger.debug("hermes-openui: agent.file_safety failed; using the built-in denylist", exc_info=True)
    where = _fallback_denial(candidates)
    if where:
        return (
            "Refusing to write to %s: it is inside a protected location (%s). Choose a normal folder such as ~/Documents, "
            "or leave `path` out for the default exports folder." % (literal, where)
        )
    return None


def _title_slug(title: str) -> str:
    slug = re.sub(r"\W+", "-", title.casefold()).strip("-_")[:48].strip("-_")
    return slug or "report"


def _default_dir(settings: Optional[dict]) -> str:
    configured = (settings or {}).get("export_dir")
    if isinstance(configured, str) and configured.strip():
        expanded = os.path.expanduser(configured.strip())
        if not os.path.isabs(expanded):
            raise ExportError("The plugin setting export_dir must be an absolute path (or start with ~): %s" % configured)
        return os.path.abspath(expanded)
    return str(tools.hermes_home() / "exports")


def _generated_name(folder: str, title: str) -> str:
    for _ in range(8):
        target = os.path.join(folder, "%s-%s.html" % (_title_slug(title), secrets.token_hex(3)))
        if not os.path.lexists(target):
            return target
    raise ExportError("Could not find a free file name in %s" % folder)


def plan_destination(path_param: object, title: str, settings: Optional[dict], overwrite: bool) -> str:
    """The absolute .html file to write, or ExportError. Pure: nothing is created or written here."""
    if path_param is None or (isinstance(path_param, str) and not path_param.strip()):
        target = _generated_name(_default_dir(settings), title)
    elif not isinstance(path_param, str) or "\x00" in path_param:
        raise ExportError("path must be a plain string such as ~/Documents/report.html")
    else:
        raw = path_param.strip()
        expanded = os.path.expanduser(raw)
        if not os.path.isabs(expanded):
            raise ExportError(
                "path must be absolute (or start with ~): %s. Use a full path such as ~/Documents/report.html, or leave `path` out "
                "for the default exports folder." % raw
            )
        norm = os.path.abspath(expanded)
        suffix = os.path.splitext(norm)[1].lower()
        if raw.endswith(("/", os.sep)) or os.path.isdir(norm):
            if os.path.isdir(norm) and suffix in HTML_SUFFIXES and not raw.endswith(("/", os.sep)):
                raise ExportError("%s is a folder, not a file. Give a file name ending in .html inside it, or a folder path." % norm)
            if os.path.lexists(norm) and not os.path.isdir(norm):
                raise ExportError("%s is a file, not a folder." % norm)
            target = _generated_name(norm, title)
        elif suffix in HTML_SUFFIXES:
            target = norm
            if os.path.lexists(target):
                if os.path.isdir(target):
                    raise ExportError("%s is a folder, not a file." % target)
                if not overwrite:
                    raise ExportError("%s already exists. Pass overwrite=true to replace it, or choose another file name." % target)
        elif suffix == "" and not os.path.lexists(norm):
            target = _generated_name(norm, title)  # a new folder, created below once the checks pass
        else:
            raise ExportError("Only .html or .htm files are written. Use a path ending in .html, or a folder (existing, or new without a file extension).")
    denied = check_destination(target)
    if denied:
        raise ExportError(denied)
    return target


def _write_atomic(target: str, data: bytes) -> None:
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)  # only reached after check_destination passed
    tmp = os.path.join(folder, ".%s.%s.tmp" % (os.path.basename(target), secrets.token_hex(4)))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)  # the umask decides the final mode, like any file the user makes
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------------------------------------------------
# Widgets rendered earlier in the chat
# ---------------------------------------------------------------------------------------------------------------------


def _plain_name(name: object) -> str:
    if not isinstance(name, str):
        raise ExportError("widget must be a file name string such as gpu-status-1a2b3c.html")
    raw = name.strip()
    if not raw or ".." in raw or "\x00" in raw or "/" in raw or "\\" in raw or raw.startswith("~") or raw == "." or Path(raw).name != raw:
        raise ExportError("widget must be a plain file name from an earlier render_widget directive (such as gpu-status-1a2b3c.html), not a path: %r" % name)
    return raw


def _recent_widgets(folder: Path, limit: int = 5) -> List[str]:
    try:
        files = [p for p in folder.iterdir() if p.suffix in (".html", ".oui") and p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    return [p.name for p in files[:limit]]


def widget_source(name: object) -> str:
    """The OpenUI Lang source of a widget rendered earlier. `name` is the file stem or the .html/.oui file name; only plain file names
    inside this profile's widgets folder are read. Raises ExportError."""
    raw = _plain_name(name)
    folder = tools.widgets_dir()
    low = raw.lower()
    candidates = [raw] if low.endswith((".html", ".oui")) else [raw + ".html", raw + ".oui"]
    base = os.path.realpath(str(folder))
    found = None
    for cand in candidates:
        p = folder / cand
        if p.is_file() and os.path.dirname(os.path.realpath(str(p))) == base:  # a link pointing out of the folder is not a widget
            found = p
            break
    if found is None:
        recent = _recent_widgets(folder)
        raise ExportError(
            "widget %r was not found in this profile's widgets folder.%s Use the exact file name from the earlier render_widget directive, "
            "or pass the OpenUI Lang as `source` instead." % (raw, (" Recent widgets: %s." % ", ".join(recent)) if recent else " There are no widgets yet.")
        )
    try:
        if found.stat().st_size > MAX_WIDGET_FILE:
            raise ExportError("%s is too large to be a widget file." % found.name)
        text = found.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ExportError("Could not read widget %s: %s" % (found.name, e))
    if found.suffix == ".oui":
        return text
    m = _WIDGET_SRC.search(text)
    source = None
    if m:
        try:
            source = json.loads(m.group(1))
        except ValueError:
            source = None
    if not isinstance(source, str):
        raise ExportError("%s is not a widget page written by render_widget (no embedded OpenUI source)." % found.name)
    return source


# ---------------------------------------------------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------------------------------------------------


def _fail(errors: List[str]) -> str:
    return tools._fail(errors[:MAX_ERRORS], _FIX)


def _clean_title(value: object, limit: int = MAX_TITLE_CHARS) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _label(index: int, title: str, widget: object) -> str:
    if title:
        return 'Section %d ("%s")' % (index, title[:40])
    if isinstance(widget, str) and widget.strip():
        return "Section %d (widget %s)" % (index, widget.strip()[:60])
    return "Section %d" % index


def _truthy(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in ("true", "yes", "1"))


def _read_sections(raw: object) -> List[Tuple[str, str, str]]:
    """[(label, title, source)] from the `sections` parameter, or ExportError carrying every shape problem."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    if not isinstance(raw, list) or not raw:
        raise ExportError("sections is required: a list of 1 to %d objects, each with `source` (OpenUI Lang) or `widget` (a widget shown earlier in this chat)." % MAX_SECTIONS)
    if len(raw) > MAX_SECTIONS:
        raise ExportError("sections has %d items; the limit is %d. Export two files, or merge related content into one section." % (len(raw), MAX_SECTIONS))
    out: List[Tuple[str, str, str]] = []
    errors: List[str] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            errors.append("Section %d: each section must be an object like {\"title\": ..., \"source\": ...} or {\"title\": ..., \"widget\": ...}." % i)
            continue
        title = _clean_title(item.get("title"))
        label = _label(i, title, item.get("widget"))
        if item.get("title") is not None and not isinstance(item.get("title"), str):
            errors.append("%s: title must be a string." % label)
            continue
        has_source, has_widget = item.get("source") is not None, item.get("widget") is not None
        if has_source == has_widget:
            errors.append("%s: give exactly one of `source` (OpenUI Lang) or `widget` (a widget shown earlier), %s." % (label, "not both" if has_source else "not neither"))
            continue
        if has_widget:
            try:
                source = widget_source(item.get("widget"))
            except ExportError as e:
                errors.append("%s: %s" % (label, e))
                continue
        else:
            source = item.get("source")
            if not isinstance(source, str) or not source.strip():
                errors.append("%s: source must be non-empty OpenUI Lang text." % label)
                continue
        out.append((label, title, source))
    if errors:
        raise ExportError(errors[0], errors)
    return out


def _export(params: dict, settings: Optional[dict]) -> str:
    title = _clean_title(params.get("title")) or DEFAULT_TITLE
    theme = params.get("theme")
    theme = "auto" if theme is None or theme == "" else (theme.strip().lower() if isinstance(theme, str) else theme)
    if theme not in page.THEMES:
        return _fail(["theme must be one of auto, light or dark, got %r." % (params.get("theme"),)])

    try:
        loaded = _read_sections(params.get("sections"))
    except ExportError as e:
        return _fail(e.errors)
    try:
        target = plan_destination(params.get("path"), title, settings, _truthy(params.get("overwrite")))
    except ExportError as e:
        return _fail([str(e)])

    custom, pack_problems = tools.load_custom(settings)
    known = bundle.component_names() | set(packs.by_component(custom))
    sections: List[Dict[str, Optional[str]]] = []
    labels: List[str] = []
    errors: List[str] = []
    for label, sec_title, source in loaded:
        source = lint.strip_fences(source)
        if len(source) > tools.MAX_SOURCE_CHARS:
            errors.append("%s: source is %d characters; the limit is %d. Use fewer rows or cards." % (label, len(source), tools.MAX_SOURCE_CHARS))
            continue
        problems = lint.check(source, known)
        errors += ["%s: %s" % (label, p) for p in problems[:4]]
        sections.append({"title": sec_title or None, "source": source})
        labels.append(label)
    if errors:
        return _fail(errors)

    checked = "node"
    for label, sec in zip(labels, sections):
        node_errors = tools._node_validate(str(sec["source"]), packs.used(str(sec["source"]), custom))
        if node_errors is None:
            checked = "structural"
        else:
            errors += ["%s: %s" % (label, e) for e in node_errors[:4]]
    if errors:
        return _fail(errors)

    try:
        for label, sec in zip(labels, sections):
            try:
                sec["source"] = page.inline_images(str(sec["source"]), max_bytes=EXPORT_IMAGE_MAX)
            except page.WidgetError as e:
                errors.append("%s: %s" % (label, e))
            except OSError as e:
                errors.append("%s: could not read an image (%s)" % (label, e))
        if errors:
            return _fail(errors)
        joined = "\n".join(str(s["source"]) for s in sections)
        html, used_packs = page.build_export_page(sections, title, theme=str(theme), extra_packs=packs.used(joined, custom))  # type: ignore[arg-type]
    except page.WidgetError as e:
        return _fail([str(e)])

    data = html.encode("utf-8")
    try:
        _write_atomic(target, data)
    except OSError as e:
        return _fail(["Could not write %s: %s" % (target, e)])

    out = {
        "ok": True,
        "path": target,
        # Hermes has no artifacts folder. The Desktop's Artifacts view and the messaging gateways read what a tool result and a
        # reply carry: a strong result key (artifact_path / media_tag) and a `MEDIA:` line in the reply. With both, the export
        # is a file card with Download and Preview in the app, and a native attachment on messaging platforms.
        "artifact_path": target,
        "media_tag": "MEDIA:" + target,
        "bytes": len(data),
        "sections": len(sections),
        "packs": used_packs,
        "checked": checked,
        "next": "Put media_tag alone on its own line in your reply (no backticks, no bold), after at most one sentence naming what was saved. Hermes shows it as "
        "a file card the user can preview or download, and messaging platforms attach it. It is a single offline HTML file; do not paste the HTML.",
    }
    if pack_problems:
        out["pack_warnings"] = pack_problems[:5]
    return json.dumps(out, ensure_ascii=False)


def export_widgets(params: object, settings: Optional[dict] = None, **_kwargs: object) -> str:
    """Tool handler. Returns a JSON string (the registry contract) and never raises. `settings` is the plugin config
    (`export_dir`, `components`)."""
    try:
        return _export(params if isinstance(params, dict) else {}, settings if isinstance(settings, dict) else None)
    except Exception as e:  # a tool must answer, not crash the turn
        logger.debug("hermes-openui: export_widgets failed", exc_info=True)
        return _fail(["Unexpected error while exporting: %s: %s" % (type(e).__name__, e)])
