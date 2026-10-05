import dataclasses
import enum
from typing import Any, Dict, List, Optional, Tuple, Union


TIER_BASIC = "basic"
TIER_ADVANCED = "advanced"
TIERS = (TIER_BASIC, TIER_ADVANCED)


class WidgetKind(str, enum.Enum):
    NUMERIC = "numeric"
    BOOL = "bool"
    CATEGORICAL_MULTI = "categorical_multi"
    TEXT = "text"
    JSON = "json"
    RAMP_VECTOR = "ramp_vector"
    # guided widgets from resources/param_schemas.yaml (see param_schema_service)
    DICT_TABLE = "dict_table"
    SELECT = "select"
    NOTE = "note"


@dataclasses.dataclass
class ParamSpec:
    """One transformer parameter as a form widget.

    `tier` decides visibility: "basic" parameters are always shown,
    "advanced" ones only when the global Advanced options switch is on.
    """

    name: str
    kind: WidgetKind
    default: Any
    bounds: Optional[Tuple[float, float]] = None
    # a list of keys, or {key: display name}
    choices: Optional[Union[List[str], Dict[str, str]]] = None
    help_text: Optional[str] = None
    extra: Dict[str, Any] = dataclasses.field(default_factory=dict)
    tier: str = "advanced"
    label: Optional[str] = None
    # param_schemas.yaml entry, with resolved `keys` / `labels` (DICT_TABLE)
    schema: Optional[Dict[str, Any]] = None
