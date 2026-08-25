import dataclasses
from typing import List

import sisepuede.transformers as trf


@dataclasses.dataclass
class StrategyEntry:
    """A saved Strategy plus the transformation codes it was built from.

    `Strategy` itself doesn't expose the codes it was constructed with after
    the fact (only the resolved `.function_list` of bound closures), so the
    GUI has to keep this alongside it for display purposes (e.g. showing
    which transformations make up a saved strategy, and its actual
    application order via strategy_service.resolve_application_order).
    """

    strategy: trf.Strategy
    transformation_codes: List[str]
