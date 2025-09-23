import os
import sys
import runpy
import traceback
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ENTRY = PROJECT_ROOT / "run.py"

EXCLUDE_DIRS = {"venv", ".venv", "__pycache__", "tests", "docs", "static", "templates"}
EXCLUDE_FILES = {"scan_imports.py"}


def iter_python_files(root: Path):
    for p in root.rglob("*.py"):
        rel = p.relative_to(PROJECT_ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        yield p


def main():
    sys.path.insert(0, str(PROJECT_ROOT))

    imported_files = set()

    # Run app entry to let Flask import modules (without starting the server)
    try:
        # Use a non-__main__ run_name to avoid triggering app.run
        runpy.run_path(str(APP_ENTRY), run_name="__scan_entry__")
    except SystemExit:
        # Some apps call sys.exit; ignore to proceed
        pass
    except Exception:
        # Even if run.py fails to start server, we still record what got imported so far
        traceback.print_exc()

    # Walk sys.modules to collect file paths
    for _, module in list(sys.modules.items()):
        try:
            file = getattr(module, "__file__", None)
            if not file:
                continue
            file_path = Path(file).resolve()
            if PROJECT_ROOT in file_path.parents:
                imported_files.add(file_path)
        except Exception:
            continue

    # All project python files
    all_files = set(map(lambda p: p.resolve(), iter_python_files(PROJECT_ROOT)))

    # Candidates = all project files - imported files - obvious non-runtime files
    candidates = []
    for p in sorted(all_files):
        if p in imported_files:
            continue
        rel = p.relative_to(PROJECT_ROOT)
        # Keep operational scripts but mark separate
        category = "runtime"
        if rel.parts and rel.parts[0] == "scripts":
            category = "script"
        candidates.append((str(rel).replace("\\", "/"), category))

    # Print report
    print("=== Imported files (project scope) ===")
    for p in sorted({str(Path(f).relative_to(PROJECT_ROOT)).replace("\\", "/") for f in imported_files if PROJECT_ROOT in Path(f).parents}):
        print(p)

    print("\n=== Unimported candidates ===")
    for rel, category in candidates:
        print(f"{rel}\t[{category}]")


if __name__ == "__main__":
    main()
