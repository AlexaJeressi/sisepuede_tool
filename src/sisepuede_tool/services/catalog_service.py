"""Construction of the session-wide ModelAttributes / Transformers catalog.

Both are safe to build once and reuse: `ModelAttributes` is independent of
any user-uploaded data, and `Transformers` was empirically confirmed
(see tests/test_catalog_service.py) to produce an identical catalog (same
codes, names, descriptions) regardless of which baseline DataFrame's
*values* it's built from -- only the input's shape matters. Note this shape
dependency is real, not just column names: some `_trfunc_*` implementations
(e.g. `transformation_entc_renewable_target`) index ramp vectors sized to
the full time-period range, so `df_input` must cover every time period in
`attribute_dim_time_period.csv` (confirmed: a row-trimmed baseline raises a
`ValueError` on broadcast shape mismatch during construction). Every
baseline this app accepts is validated via `input_service` against that
same full time-period range before being usable, so this holds in practice
-- the catalog only needs to be built once, from whichever baseline was
loaded first.
"""

import pandas as pd
import sisepuede.transformers as trf
from sisepuede.core.model_attributes import ModelAttributes

from sisepuede_tool import config


def build_model_attributes() -> ModelAttributes:
    return ModelAttributes(
        dir_attributes=str(config.ATTRIBUTES_DIR),
        fp_config=str(config.DEFAULT_CONFIG_PATH),
    )


def build_transformers_catalog(df_reference_baseline: pd.DataFrame) -> trf.Transformers:
    return trf.Transformers({}, df_input=df_reference_baseline)
