"""Building `Transformation` objects from user-supplied parameter values.

A Transformation is just a Transformer code + a parameters dict wrapped in
sisepuede's plain-dict config schema -- fully in-memory constructible, no
file I/O required (see sisepuede.transformers.transformations.Transformation).
Note: constructing a Transformation never executes its transformer function
(that only happens when it's later called against a baseline via a
Strategy), so building one here cannot itself fail due to sisepuede-side
bugs in a particular transformer's math -- only bad parameter values (e.g.
unparseable JSON) can fail at this stage.
"""

import pathlib
import tempfile
from typing import Any, Dict

import yaml
import sisepuede.transformers as trf
from sisepuede.transformers.lib import _operations


def create_transformations_collection(transformers_catalog: trf.Transformers) -> trf.Transformations:
    """Build an (initially baseline-only) Transformations collection.

    `Transformations.__init__` requires `dir_init` to contain a real
    `config_general.yaml` file on disk (it errors otherwise) and scans that
    directory for `transformation_*.yaml` files -- there's no purely
    in-memory constructor. So this writes sisepuede's own computed defaults
    (via `_operations.build_default_general_config_dict`) into a fresh temp
    directory with zero transformation files, giving a collection that
    starts with only the baseline transformation -- matching the
    requirement that the Strategy Builder must not start with any of the
    shipped default strategies/transformations. A blank config file was
    tried first and doesn't work: `Transformations.get_transformation_baseline`
    fails to resolve `code_baseline` against an empty config.
    """
    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="sisepuede_tool_"))
    config = _operations.build_default_general_config_dict(transformers_catalog)
    (tmp_dir / "config_general.yaml").write_text(yaml.safe_dump(config))
    return trf.Transformations(tmp_dir, transformers=transformers_catalog)


def _rebuild_attribute_table(transformations_obj: trf.Transformations) -> None:
    fp_map = {code: None for code in transformations_obj.dict_transformations}
    attribute_transformation, _fields = transformations_obj.build_attribute_table(
        transformations_obj.code_baseline,
        transformations_obj.dict_transformations,
        fp_map,
        baseline_id=0,
    )
    transformations_obj.attribute_transformation = attribute_transformation
    transformations_obj.all_transformation_codes = attribute_transformation.key_values


def add_transformation(transformations_obj: trf.Transformations, transformation: trf.Transformation) -> None:
    transformations_obj.dict_transformations[transformation.code] = transformation
    _rebuild_attribute_table(transformations_obj)


def remove_transformation(transformations_obj: trf.Transformations, code: str) -> None:
    if code == transformations_obj.code_baseline:
        raise ValueError("Cannot remove the baseline transformation.")
    transformations_obj.dict_transformations.pop(code, None)
    _rebuild_attribute_table(transformations_obj)


def build_transformation_config(
    transformation_code: str,
    transformation_name: str,
    transformer_code: str,
    parameters: Dict[str, Any],
    description: str = "",
) -> dict:
    return {
        "citations": None,
        "description": description,
        "identifiers": {
            "transformation_code": transformation_code,
            "transformation_name": transformation_name,
        },
        "parameters": parameters,
        "transformer": transformer_code,
    }


def build_transformation(
    transformation_code: str,
    transformation_name: str,
    transformer_code: str,
    parameters: Dict[str, Any],
    transformers_catalog: trf.Transformers,
    description: str = "",
) -> trf.Transformation:
    config = build_transformation_config(
        transformation_code, transformation_name, transformer_code, parameters, description
    )
    return trf.Transformation(config, transformers_catalog)


def suggest_transformation_code(transformer_code: str, existing_codes) -> str:
    base = transformer_code.replace("TFR:", "TX:", 1)
    if base not in existing_codes:
        return base
    i = 2
    while f"{base}_{i}" in existing_codes:
        i += 1
    return f"{base}_{i}"
