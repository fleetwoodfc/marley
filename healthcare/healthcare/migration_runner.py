import importlib.util
import frappe


def run_convert_requested_proc():
    """Load and run the convert_requested_proc_to_links migration script by path."""
    # Path to the patch file (app-level patches folder)
    path = "/workspace/development/frappe-bench/apps/healthcare/patches/convert_requested_proc_to_links.py"
    spec = importlib.util.spec_from_file_location("convert_req", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.migrate()


def run_merge_requested_proc_records():
    """Run the merge patch that consolidates Requested Procedure Record docs."""
    path = "/workspace/development/frappe-bench/apps/healthcare/healthcare/patches/merge_requested_proc_records.py"
    spec = importlib.util.spec_from_file_location("merge_req", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.migrate()
