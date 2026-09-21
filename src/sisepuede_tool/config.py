"""Paths derived from the installed `sisepuede` package.

Resolved relative to wherever `sisepuede` is actually installed (editable or
not) rather than hardcoded to a specific environment, so the app works the
same in any conda/venv that has `sisepuede` installed.
"""

import pathlib

import sisepuede

SISEPUEDE_PACKAGE_DIR = pathlib.Path(sisepuede.__file__).resolve().parent
SISEPUEDE_TOOL_PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SISEPUEDE_TOOL_PACKAGE_DIR.parent.parent

ATTRIBUTES_DIR = SISEPUEDE_PACKAGE_DIR / "attributes"
DEFAULT_CONFIG_PATH = SISEPUEDE_PACKAGE_DIR / "sisepuede_config.yaml"
JULIA_DIR = SISEPUEDE_PACKAGE_DIR / "julia"
NEMOMOD_REFERENCE_DIR = SISEPUEDE_PACKAGE_DIR / "ref" / "nemo_mod"

PROJECTS_XLSX_PATH = SISEPUEDE_TOOL_PACKAGE_DIR / "ref" / "Egypt_Projects_SISEPUEDE_NDC_LTS.xlsx"
CB_CONFIG_XLSX_PATH = REPO_ROOT / "tests" / "fixtures" / "cb_config_params.xlsx"
