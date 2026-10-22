import dataclasses
from typing import List, Optional

import sisepuede.transformers as trf


@dataclasses.dataclass
class StrategyEntry:
    """A saved Strategy plus the transformation codes it was built from.

    `Strategy` itself doesn't expose the codes it was constructed with after
    the fact (only the resolved `.function_list` of bound closures), so the
    GUI has to keep this alongside it for display purposes (e.g. showing
    which transformations make up a saved strategy, and its actual
    application order via strategy_service.resolve_application_order).

    `base_year`: the pathway's last historical year. NemoMod optimizes the
    years up to it first and keeps them as the starting point of the rest
    (SISEPUEDEModels.project(time_periods_base=...)), so the pathway can't
    change the power system of years that already happened. None: sisepuede's
    default, only the first year.
    """

    strategy: trf.Strategy
    transformation_codes: List[str]
    base_year: Optional[int] = None
