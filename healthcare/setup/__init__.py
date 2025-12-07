# empty to mark package

# Import all functions from _setup_module to maintain compatibility
try:
    from healthcare._setup_module import *  # noqa: F401, F403
except (ImportError, ModuleNotFoundError):
    # _setup_module may not be importable in non-Frappe environments
    pass
