"""Inside Hermes's interpreter: tool-search recall for render_widget, two description variants, against a REALISTIC catalog.

Catalog = Hermes's own curated deferred tools (real definitions from the registry) + render_widget + 172 name-only tools shaped
like a large MCP server (the user's session has a 172-tool reverse-engineering server). Queries are of two kinds: the short keyword
queries a model writes after seeing the listing, and whole-sentence phrasings.
Usage: HERMES_HOME=<iso> python verify_discovery.py"""
import copy
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
import model_tools  # noqa: E402
from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402
from tools import tool_search as ts  # noqa: E402
from tools.tool_search_catalog import build_catalog, build_catalog_listing_with_form, search_catalog  # noqa: E402
from tools.registry import registry  # noqa: E402
from toolsets import resolve_toolset  # noqa: E402

NOISE = """address_name address_to_file_offset analyze_function analyze_javascript_application analyze_swift_types analyze_web_bundle annotate_native_function batch_decompile binary_overview binary_session build_call_path build_reconstruction_obligation_ledger capture_adb_screen capture_browser_scenario capture_electron_scenario capture_native_ui_scenario capture_process_scenario capture_web_screenshot close_binary collect_adb_bugreport comment compare_application_versions compare_artifacts compare_bundles compare_functions compare_javascript_export_shapes compare_managed_members compare_process_captures compare_source_to_bundle compare_web_captures compare_web_screenshots correlate_static_and_runtime current_address current_document current_procedure decode_android_resources decode_interface_builder decompile_jeb_item demangle_swift discover_webmcp_tools evaluate_reconstruction_coverage export_evidence_bundle export_web_scripts extract_artifact extract_firmware find_changed_behavior find_xrefs_to_name get_call_graph get_evidence_bundle get_navigation_context get_objc_classes get_objc_protocols get_prompt goto_address import_evidence_bundle import_managed_reconstruction inline_comment inspect_adb_client inspect_adb_device inspect_adb_display inspect_adb_package inspect_adb_window inspect_address_context inspect_analysis_view inspect_android_class inspect_android_method inspect_android_package inspect_apktool_client inspect_artifact inspect_asset_catalog inspect_binary_layout inspect_electron_page inspect_evm_interface inspect_firmware_regions inspect_jeb_client inspect_keyed_archive inspect_macho inspect_managed_artifact inspect_managed_members inspect_managed_native_boundaries inspect_native_api inspect_native_data_type inspect_native_dispatch_metadata inspect_native_instruction inspect_native_load_image inspect_pe_resources inspect_plist inspect_recorded_crash inspect_signature inspect_web_event_listeners inspect_web_network_capture inspect_web_page install_adb_package list_adb_devices list_adb_directory list_adb_features list_adb_packages list_adb_processes list_adb_services list_architectures list_bookmarks list_browser_targets list_documents list_electron_targets list_javascript_runtime_targets list_jeb_units list_names list_procedures list_prompts list_segments list_strings list_unknowns next_address observe_javascript_runtime observe_native_calls observe_native_ui observe_web_execution observe_web_session open_binary open_jeb_project prev_address procedure_address procedure_assembly procedure_callees procedure_callers procedure_info procedure_pseudo_code procedure_references project_android_application_graph project_apple_application_graph project_managed_application_graph pull_adb_file pull_adb_package push_adb_file read_adb_logcat read_adb_setting read_bytes read_function_instructions reconcile_javascript_runtime record_unknown recover_javascript_sources resolve_adb_packages resolve_containing_procedure resolve_native_call_targets search_android_classes search_procedures search_strings set_address_name set_addresses_names set_bookmark set_comment set_inline_comment start_adb_activity start_adb_app stop_adb_app trace_android_references trace_application_feature trace_call_path trace_dylib_resolution trace_feature trace_javascript_semantics trace_native_ui_action trace_native_values trace_web_module_imports trace_web_source_location uninstall_adb_package unset_bookmark update_unknown verify_managed_native_boundaries verify_reconstruction verify_unknown_resolution xrefs""".split()

V1 = (
    "Draw charts, DAG/ER diagrams, maps and dashboards in chat. "
    "Renders a rich interactive inline widget in the Hermes desktop app from OpenUI Lang: metric tiles, tables, tabs, cards, "
    "line/area/pie/radar/bar charts, DAG pipelines, ER diagrams, offline maps, code, markdown, FAQs and clickable Choice questions. "
    "Pass the OpenUI Lang as `source`; the tool validates it and returns a one-line directive to put ALONE on its own line in your reply. "
    "Call it once with reference=true first to get the exact component signatures. "
    "Desktop app only. For a single value or a short answer, reply in plain text instead."
)
_UNUSED = (
    "Draw charts, graphs, DAG/ER diagrams, maps and dashboards. "
    "Show data visually in the Hermes desktop chat as an interactive inline widget written in OpenUI Lang: KPI metric tiles, tables, tabs, cards, "
    "bar/line/area/pie/radar charts and plots, flowcharts, DAG pipelines, ER database schemas, network topology, offline maps, code blocks, markdown, "
    "FAQs and clickable Choice questions. "
    "Pass the OpenUI Lang as `source`; the tool validates it and returns a one-line directive to put ALONE on its own line in your reply. "
    "Call it once with reference=true first to get the exact component signatures. "
    "Desktop app only. For a single value or a short answer, reply in plain text instead."
)

enabled = sorted(_get_platform_tools(load_config(), "cli", include_default_mcp_servers=True))
names = {n for t in enabled for n in resolve_toolset(t)}
defs = [d for d in registry.get_definitions(names, quiet=True)]
effective = ts.ToolSearchConfig.from_raw((load_config().get("tools") or {}).get("tool_search")).effective_defer_tools
core_deferred = [d for d in defs if d["function"]["name"] != "render_widget" and ts.is_deferrable_tool_name(d["function"]["name"], effective)]
rw = next(d for d in defs if d["function"]["name"] == "render_widget")
noise = [{"type": "function", "function": {"name": "mcp__rea__" + n, "description": "", "parameters": {"type": "object", "properties": {}}}} for n in NOISE]
print("catalog: %d curated core tools deferred + %d MCP-style noise tools + render_widget" % (len(core_deferred), len(noise)))

KEYWORD = ["dag", "dag diagram", "chart", "bar chart", "pie chart", "line chart", "graph", "plot", "diagram", "flowchart", "dashboard", "table", "map",
           "er diagram", "database schema", "network topology", "visualize data", "inline widget", "kpi tiles", "pipeline",
           "infrastructure map", "infrastructure diagram", "architecture diagram", "network diagram", "server map"]
SENTENCE = ["draw a dag", "draw a DAG of my build pipeline", "make a bar chart of these numbers", "show a pie chart of the results",
            "visualize the database schema as an ER diagram", "put these sites on a map", "build a dashboard with KPIs", "network topology diagram",
            "line chart of tokens per second over time", "show a flowchart of the process",
            "map out my infrastructure", "draw my server architecture", "diagram my office network"]
UNRELATED = ["send an email", "take a screenshot of the screen", "create a calendar event", "restart the service"]


def variant(desc):
    d = copy.deepcopy(rw)
    if desc:
        d["function"]["description"] = desc
    return build_catalog(core_deferred + noise + [d])


def score(cat, queries):
    found, ranks = 0, []
    for q in queries:
        top = [e.name for e in search_catalog(cat, q, limit=5)]
        r = top.index("render_widget") + 1 if "render_widget" in top else None
        found += 1 if r else 0
        ranks.append((q, r))
    return found, ranks


for label, desc in (("first draft (before tuning)", V1), ("SHIPPED description", None)):
    cat = variant(desc)
    print("\n=== %s (%d chars)" % (label, len(desc or rw["function"]["description"])))
    for kind, qs in (("keyword", KEYWORD), ("sentence", SENTENCE)):
        f, ranks = score(cat, qs)
        miss = [q for q, r in ranks if not r]
        print("  %-8s queries: found %2d of %2d | misses: %s" % (kind, f, len(qs), miss if miss else "none"))
    false_pos = [q for q in UNRELATED if any(e.name == "render_widget" for e in search_catalog(cat, q, limit=5))]
    print("  false positives on unrelated requests:", false_pos if false_pos else "none")
    listing, form = build_catalog_listing_with_form([d for d in core_deferred + [copy.deepcopy(rw)]], max_tokens=4000)
    if desc is None and listing:
        line = [l for l in listing.splitlines() if "render_widget" in l]
        print("  always-visible listing line:", line[0] if line else "n/a")


# --- Both tools together: adding export_widgets must not cost render_widget its recall, and export queries must find export_widgets.
ex = next((d for d in defs if d["function"]["name"] == "export_widgets"), None)
if ex is None:
    print("\n(export_widgets is not registered in this home: skipping the combined check)")
else:
    EXPORT = ["export html", "save as html", "export dashboard", "standalone page", "offline report", "share a report", "download chart"]
    base = [d for d in core_deferred if d["function"]["name"] != "export_widgets"]  # core_deferred already holds it (it is a deferrable plugin tool)
    combined = build_catalog(base + noise + [copy.deepcopy(rw), copy.deepcopy(ex)])
    print("\n=== BOTH TOOLS in one catalog (%d chars export description)" % len(ex["function"]["description"]))
    for label, qs, target in (("render keyword", KEYWORD, "render_widget"), ("render sentence", SENTENCE, "render_widget"), ("export", EXPORT, "export_widgets")):
        ranks = []
        for q in qs:
            top = [e.name for e in search_catalog(combined, q, limit=5)]
            ranks.append((q, top.index(target) + 1 if target in top else None))
        miss = [q for q, r in ranks if not r]
        first = sum(1 for q, r in ranks if r == 1)
        print("  %-16s found %2d of %2d (rank 1: %2d) | misses: %s" % (label, len(qs) - len(miss), len(qs), first, miss if miss else "none"))
    wrong = [q for q in EXPORT if [e.name for e in search_catalog(combined, q, limit=5)][:1] != ["export_widgets"]]
    print("  export queries where export_widgets is NOT first:", wrong if wrong else "none")
    fp = [q for q in UNRELATED if {e.name for e in search_catalog(combined, q, limit=5)} & {"render_widget", "export_widgets"}]
    print("  false positives on unrelated requests:", fp if fp else "none")
    line = [l for l in build_catalog_listing_with_form(base + [copy.deepcopy(rw), copy.deepcopy(ex)], max_tokens=4000)[0].splitlines() if "_widget" in l]
    print("  always-visible listing lines:", *line, sep="\n    ")
