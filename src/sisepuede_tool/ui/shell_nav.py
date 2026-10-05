"""Sidebar/topbar navigation config for the custom app shell (app_shell.py).

One place both the sidebar renderer and the topbar renderer read from --
adding, renaming, or reordering pages is a change here, not a change to the
rendering logic itself.
"""

import dataclasses
from typing import List, Optional


@dataclasses.dataclass(frozen=True)
class NavItem:
    id: str  # matches the module id used in app_shell's ui.nav_panel(..., value=id)
    label: str
    group: str
    icon_svg: str
    description: str
    crumb: str = ""  # topbar breadcrumb; defaults to the group name
    step: Optional[int] = None  # workflow step number shown as a badge in the sidebar
    flush: bool = False  # page manages its own padding/scrolling (e.g. the 3-column Pathways page)


_ICON_BASELINE = '<path d="M4 4h16v4H4z"/><path d="M4 12h16v8H4z"/><path d="M9 16h6"/>'
_ICON_PROJECTS = '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'
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


_ICON_PATHWAYS = _ICON_STRATEGIES

NAV_ITEMS: List[NavItem] = [
    NavItem(
        id="data_input",
        label="Baseline data",
        group="Workflow",
        icon_svg=_svg(_ICON_BASELINE),
        description="The emissions baseline every scenario builds from.",
        crumb="Setup / 1",
        step=1,
    ),
    NavItem(
        id="pathways",
        label="Pathways",
        group="Workflow",
        icon_svg=_svg(_ICON_PATHWAYS),
        description="Open a transformer, reuse or create transformations, and add them to a pathway.",
        crumb="Build / 2",
        step=2,
        flush=True,
    ),
    NavItem(
        id="run",
        label="Run",
        group="Workflow",
        icon_svg=_svg(_ICON_RUN),
        description="Pick baselines and pathways, then run.",
        crumb="Execute / 3",
        step=3,
    ),
    NavItem(
        id="output_explorer",
        label="Emissions & drivers",
        group="Results",
        icon_svg=_svg(_ICON_EXPLORER),
        description="Model outputs by pathway and baseline.",
    ),
    NavItem(
        id="cost_benefits",
        label="Costs & benefits",
        group="Results",
        icon_svg=_svg(_ICON_COST_BENEFITS),
        description="Relative to business as usual.",
    ),
    NavItem(
        id="macroeconomic_impacts",
        label="Macroeconomic impacts",
        group="Results",
        icon_svg=_svg(_ICON_MACRO_IMPACTS),
        description="GDP and jobs relative to business as usual.",
    ),
    NavItem(
        id="article_6",
        label="Article 6",
        group="Results",
        icon_svg=_svg(_ICON_ARTICLE_6),
        description="Mitigation beyond the NDC target that could be transferred.",
    ),
    NavItem(
        id="validation",
        label="Monitoring",
        group="MRV",
        icon_svg=_svg(_ICON_MONITORING),
        description="Compare model output with observed inventory data.",
    ),
    NavItem(
        id="projects",
        label="Projects",
        group="Portfolio · optional",
        icon_svg=_svg(_ICON_PROJECTS),
        description="Consult announced projects and link each one to a transformation.",
    ),
    NavItem(
        id="persistence",
        label="Project files",
        group="System",
        icon_svg=_svg(_ICON_PERSISTENCE),
        description="Export the project as sisepuede files, or import one.",
    ),
]

NAV_ITEMS_BY_ID = {item.id: item for item in NAV_ITEMS}

# Group order as they appear in the sidebar (dict preserves insertion order).
NAV_GROUPS: List[str] = list(dict.fromkeys(item.group for item in NAV_ITEMS))

DEFAULT_NAV_ID = NAV_ITEMS[0].id

        