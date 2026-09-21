"""Sidebar/topbar navigation config for the custom app shell (app_shell.py).

One place both the sidebar renderer and the topbar renderer read from --
adding, renaming, or reordering pages is a change here, not a change to the
rendering logic itself.
"""

import dataclasses
from typing import List


@dataclasses.dataclass(frozen=True)
class NavItem:
    id: str  # matches the module id used in app_shell's ui.nav_panel(..., value=id)
    label: str
    group: str
    icon_svg: str
    description: str


_ICON_BASELINE = '<path d="M4 4h16v4H4z"/><path d="M4 12h16v8H4z"/><path d="M9 16h6"/>'
_ICON_PROJECTS = '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'
_ICON_TRANSFORMATIONS = '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2.2"/><circle cx="8" cy="17" r="2.2"/>'
_ICON_STRATEGIES = '<circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="12" r="2.4"/><path d="M6 8.4V15.6M8.2 6.9 15.8 10.9M8.2 17.1 15.8 13.1"/>'
_ICON_RUN = '<path d="M7 4.5v15l13-7.5z"/>'
_ICON_EXPLORER = '<path d="M4 20V10M12 20V4M20 20v-7"/>'
_ICON_MONITORING = '<path d="M3 12h4l2.5-7L13 19l2.5-7H21"/>'
_ICON_PERSISTENCE = '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/>'
_ICON_COST_BENEFITS = '<path d="M12 3v18M5 8l-3 6a3 3 0 0 0 6 0zM19 8l-3 6a3 3 0 0 0 6 0zM5 8h14M9 3h6"/>'
_ICON_MACRO_IMPACTS = '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>'
_ICON_ARTICLE_6 = '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 2.5 15.5 0 18M12 3c-2.5 2.5-2.5 15.5 0 18"/>'


def _svg(inner: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
    )


NAV_ITEMS: List[NavItem] = [
    NavItem(
        id="data_input",
        label="Baseline Data",
        group="Setup",
        icon_svg=_svg(_ICON_BASELINE),
        description="Load and validate the emissions baseline that every scenario in this project builds from.",
    ),
    NavItem(
        id="projects",
        label="Define Projects",
        group="Define Pathways",
        icon_svg=_svg(_ICON_PROJECTS),
        description="Browse candidate NDC/LTS projects and mark which ones are in scope.",
    ),
    NavItem(
        id="transformations",
        label="Transformations",
        group="Define Pathways",
        icon_svg=_svg(_ICON_TRANSFORMATIONS),
        description="Configure a SISEPUEDE Transformer's parameters and save it as a named Transformation.",
    ),
    NavItem(
        id="strategies",
        label="Strategies",
        group="Define Pathways",
        icon_svg=_svg(_ICON_STRATEGIES),
        description="Combine saved Transformations into a Strategy to run against a baseline.",
    ),
    NavItem(
        id="run",
        label="Run",
        group="Execute",
        icon_svg=_svg(_ICON_RUN),
        description="Run selected Strategies against selected baselines and review the results.",
    ),
    NavItem(
        id="output_explorer",
        label="Emissions and Drivers",
        group="Review",
        icon_svg=_svg(_ICON_EXPLORER),
        description="Explore model output variables across strategies and baselines.",
    ),
    NavItem(
        id="cost_benefits",
        label="Cost and Benefits",
        group="Review",
        icon_svg=_svg(_ICON_COST_BENEFITS),
        description="Review the costs and benefits of run Strategies.",
    ),
    NavItem(
        id="macroeconomic_impacts",
        label="Macroeconomic Impacts",
        group="Review",
        icon_svg=_svg(_ICON_MACRO_IMPACTS),
        description="Review the macroeconomic impacts of run Strategies.",
    ),
    NavItem(
        id="article_6",
        label="Article 6",
        group="Review",
        icon_svg=_svg(_ICON_ARTICLE_6),
        description="Review Article 6 (cooperative approaches) accounting for run Strategies.",
    ),
    NavItem(
        id="validation",
        label="Monitoring",
        group="Monitoring and Verification",
        icon_svg=_svg(_ICON_MONITORING),
        description="Compare model output against observed data via a crosswalk.",
    ),
    NavItem(
        id="persistence",
        label="Save/Load",
        group="System",
        icon_svg=_svg(_ICON_PERSISTENCE),
        description="Export the session's Transformations and Strategies, or import a previous project.",
    ),
]

NAV_ITEMS_BY_ID = {item.id: item for item in NAV_ITEMS}

# Group order as they appear in the sidebar (dict preserves insertion order).
NAV_GROUPS: List[str] = list(dict.fromkeys(item.group for item in NAV_ITEMS))

DEFAULT_NAV_ID = NAV_ITEMS[0].id

        