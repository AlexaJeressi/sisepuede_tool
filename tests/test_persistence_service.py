import io
import pathlib

import pandas as pd
import pytest

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import catalog_service, persistence_service, strategy_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def transformers_catalog():
    df = pd.read_csv(FIXTURE_CSV)
    return catalog_service.build_transformers_catalog(df)


def _build_session(transformers_catalog):
    transformations_obj = transformation_service.create_transformations_collection(transformers_catalog)
    transformation = transformation_service.build_transformation(
        transformation_code="TX:AGRC:DEC_EXPORTS_TEST",
        transformation_name="Decrease exports test",
        transformer_code="TFR:AGRC:DEC_EXPORTS",
        parameters={"magnitude": 0.35},
        transformers_catalog=transformers_catalog,
        description="a round-trip test transformation",
    )
    transformation_service.add_transformation(transformations_obj, transformation)

    strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:DEC_EXPORTS_TEST"], transformations_obj, name="Export test strategy", description="desc"
    )
    baseline_strategy = strategy_service.build_baseline_strategy(transformations_obj)
    strategies_map = {
        0: StrategyEntry(strategy=baseline_strategy, transformation_codes=[transformations_obj.code_baseline]),
        1000: StrategyEntry(strategy=strategy, transformation_codes=["TX:AGRC:DEC_EXPORTS_TEST"]),
    }
    return transformations_obj, strategies_map


def test_export_zip_contains_expected_files(transformers_catalog):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    zip_bytes = persistence_service.export_session_zip(transformations_obj, strategies_map)

    import zipfile

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "config_general.yaml" in names
        assert "strategy_definitions.csv" in names
        assert "transformation_tx_agrc_dec_exports_test.yaml" in names

        strategy_csv = pd.read_csv(io.BytesIO(zf.read("strategy_definitions.csv")))
        assert set(strategy_csv["strategy_id"]) == {0, 1000}
        row = strategy_csv[strategy_csv["strategy_id"] == 1000].iloc[0]
        assert row["transformation_specification"] == "TX:AGRC:DEC_EXPORTS_TEST"
        assert row["strategy"] == "Export test strategy"


def test_export_then_import_round_trips(transformers_catalog, tmp_path):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    zip_bytes = persistence_service.export_session_zip(transformations_obj, strategies_map)

    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(zip_bytes)

    imported_transformations, imported_strategies = persistence_service.import_session_zip(
        zip_path, transformers_catalog
    )

    assert "TX:AGRC:DEC_EXPORTS_TEST" in imported_transformations.dict_transformations
    imported_t = imported_transformations.get_transformation("TX:AGRC:DEC_EXPORTS_TEST")
    assert imported_t.dict_parameters["magnitude"] == 0.35
    assert imported_t.transformer_code == "TFR:AGRC:DEC_EXPORTS"

    assert set(imported_strategies.keys()) == {0, 1000}
    assert imported_strategies[1000].transformation_codes == ["TX:AGRC:DEC_EXPORTS_TEST"]
    assert imported_strategies[1000].strategy.name == "Export test strategy"

    df = pd.read_csv(FIXTURE_CSV)
    df_out = imported_strategies[1000].strategy(df_input=df)
    assert df_out.shape[0] == df.shape[0]


def test_export_transformations_dir_writes_expected_files(transformers_catalog, tmp_path):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    out_dir = tmp_path / "my_transformations"

    persistence_service.export_transformations_dir(transformations_obj, strategies_map, out_dir)

    assert (out_dir / "config_general.yaml").exists()
    assert (out_dir / "strategy_definitions.csv").exists()
    assert (out_dir / "citations.bib").exists()
    assert (out_dir / "transformation_tx_agrc_dec_exports_test.yaml").exists()
    # baseline (TX:BASE) must not get its own transformation_*.yaml file
    assert not (out_dir / "transformation_tx_base.yaml").exists()


def test_export_then_import_directory_round_trips(transformers_catalog, tmp_path):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    out_dir = tmp_path / "my_transformations"
    persistence_service.export_transformations_dir(transformations_obj, strategies_map, out_dir)

    imported_transformations, imported_strategies = persistence_service.import_transformations_dir(
        out_dir, transformers_catalog
    )

    imported_t = imported_transformations.get_transformation("TX:AGRC:DEC_EXPORTS_TEST")
    assert imported_t.dict_parameters["magnitude"] == 0.35
    assert set(imported_strategies.keys()) == {0, 1000}

    df = pd.read_csv(FIXTURE_CSV)
    df_out = imported_strategies[1000].strategy(df_input=df)
    assert df_out.shape[0] == df.shape[0]


def test_import_transformations_dir_rejects_non_directory(transformers_catalog, tmp_path):
    not_a_dir = tmp_path / "not_a_dir.txt"
    not_a_dir.write_text("hello")
    with pytest.raises(FileNotFoundError):
        persistence_service.import_transformations_dir(not_a_dir, transformers_catalog)


def test_import_transformations_dir_rejects_missing_config(transformers_catalog, tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="config_general.yaml"):
        persistence_service.import_transformations_dir(empty_dir, transformers_catalog)


def test_export_transformations_dir_reuses_existing_citations(transformers_catalog, tmp_path):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    out_dir = tmp_path / "my_transformations"
    out_dir.mkdir()
    (out_dir / "citations.bib").write_text("@misc{example, title={x}}")

    persistence_service.export_transformations_dir(transformations_obj, strategies_map, out_dir)

    assert (out_dir / "citations.bib").read_text() == "@misc{example, title={x}}"


def test_empty_pathway_and_library_transformation_round_trip(transformers_catalog):
    from sisepuede_tool.services import library_service, pathway_service

    transformations_obj, strategies_map = _build_session(transformers_catalog)
    library_service.add_library_to_collection(transformations_obj, transformers_catalog)
    strategies_map, empty_id = pathway_service.create_pathway(strategies_map, transformations_obj, "Empty for now")
    strategies_map, lib_id = pathway_service.create_pathway(strategies_map, transformations_obj, "With NDC")
    strategies_map = pathway_service.add_to_pathway(
        strategies_map, transformations_obj, lib_id, "TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC"
    )

    blob = persistence_service.export_session_zip(transformations_obj, strategies_map)
    tx2, strategies2 = persistence_service.import_session_zip(io.BytesIO(blob), transformers_catalog)

    assert strategies2[empty_id].transformation_codes == []
    assert strategies2[empty_id].strategy.name == "Empty for now"
    assert strategies2[lib_id].transformation_codes == ["TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC"]
    assert "TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC" in tx2.dict_transformations


def test_extra_tables_round_trip(transformers_catalog):
    transformations_obj, strategies_map = _build_session(transformers_catalog)
    links = pd.DataFrame({"project": ["A"], "transformation_code": ["TX:AGRC:DEC_EXPORTS_TEST"], "in_scope": [True]})
    blob = persistence_service.export_session_zip(transformations_obj, strategies_map, {"project_links.csv": links})
    tables = persistence_service.read_extra_tables(io.BytesIO(blob), ["project_links.csv", "custom_projects.csv"])
    assert list(tables) == ["project_links.csv"]
    assert tables["project_links.csv"]["transformation_code"].tolist() == ["TX:AGRC:DEC_EXPORTS_TEST"]
    # still a plain sisepuede directory for import
    tx2, _ = persistence_service.import_session_zip(io.BytesIO(blob), transformers_catalog)
    assert "TX:AGRC:DEC_EXPORTS_TEST" in tx2.dict_transformations
