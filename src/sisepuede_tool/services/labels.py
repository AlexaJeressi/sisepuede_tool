"""Display labels for sisepuede variable names.

sisepuede variable names carry Sphinx math markup, e.g.
``:math:\\text{CH}_4 Anaerobic Biogas Emission Factor``. These helpers turn
them into plain text ("CH₄ Anaerobic Biogas Emission Factor") for the UI.
"""

import re

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_RE_MATH_ROLE = re.compile(r":math:`([^`]*)`")
_RE_TEXT = re.compile(r"\\text\{([^}]*)\}")
_RE_SUB_BRACED = re.compile(r"_\{([^}]*)\}")
_RE_SUB_SINGLE = re.compile(r"_(\w)")


def _subscript(s: str) -> str:
    # Digits become unicode subscripts; anything else (e.g. "1FR", "REM")
    # is kept as plain text after an underscore-free join.
    return s.translate(_SUBSCRIPT) if s.isdigit() else s


def clean_label(name: str) -> str:
    """Strip Sphinx/LaTeX markup from a sisepuede variable name."""
    if not isinstance(name, str):
        return name
    out = _RE_MATH_ROLE.sub(lambda m: m.group(1), name)  # :math:`...` in descriptions
    out = out.replace(":math:", "")
    out = _RE_TEXT.sub(lambda m: m.group(1), out)
    out = _RE_SUB_BRACED.sub(lambda m: _subscript(m.group(1)), out)
    out = _RE_SUB_SINGLE.sub(lambda m: _subscript(m.group(1)), out)
    return re.sub(r"\s+", " ", out).strip()


def strip_subsector_prefix(name: str) -> str:
    """'AGRC: Improve rice management' -> 'Improve rice management'."""
    if not isinstance(name, str):
        return name
    m = re.match(r"^[A-Z]{4}:\s*(.*)$", name)
    return m.group(1) if m else name


# Plain labels for transformer parameters that have no label in
# param_schemas.yaml or the transformer catalog. The sisepuede name is kept
# out of the label and shown only in a tooltip (see param_widget).
PARAM_LABELS = {
    "magnitude": "Size of the change",
    "magnitude_type": "How the size is applied",
    "magnitude_biogas": "Share of waste to biogas",
    "magnitude_compost": "Share of waste to compost",
    "magnitude_red_meat": "Cut in red meat consumption",
    "vec_implementation_ramp": "Implementation timing",
    "acceleration_factor": "Acceleration factor",
    "drop_frac_elec_increase_for_msp": "Ignore electricity growth for minimum shares",
    "scale_non_renewables_to_match_surplus_msp": "Scale non-renewables to fit the minimum shares",
    "frac_switchable": "Share of heat demand that can switch fuel",
    "force": "Force the reallocation",
    "min_loss": "Lowest loss rate allowed",
    "categories": "Categories",
    "cats_frst": "Forest types",
}


def param_label(name: str, label: str = None) -> str:
    """Display label for a transformer parameter: an explicit label (schema,
    override or catalog) first, then PARAM_LABELS, then the name made readable."""
    if label:
        return label
    if name in PARAM_LABELS:
        return PARAM_LABELS[name]
    return name.replace("_", " ").strip().capitalize()
