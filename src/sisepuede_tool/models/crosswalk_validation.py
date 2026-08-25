import dataclasses
from typing import List


@dataclasses.dataclass
class CrosswalkValidation:
    ok: bool
    errors: List[str] = dataclasses.field(default_factory=list)
    comparison_ids: List[str] = dataclasses.field(default_factory=list)
