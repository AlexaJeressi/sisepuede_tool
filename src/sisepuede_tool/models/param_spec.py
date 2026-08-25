import dataclasses
import enum
from typing import Any, Dict, List, Optional, Tuple


class WidgetKind(str, enum.Enum):
    NUMERIC = "numeric"
    BOOL = "bool"
    CATEGORICAL_MULTI = "categorical_multi"
    TEXT = "text"
    JSON = "json"
    RAMP_VECTOR = "ramp_vector"


@dataclasses.dataclass
class ParamSpec:
    name: str
    kind: WidgetKind
    default: Any
    bounds: Optional[Tuple[float, float]] = None
    choices: Optional[List[str]] = None
    help_text: Optional[str] = None
    extra: Dict[str, Any] = dataclasses.field(default_factory=dict)
