import pathlib
import re
import string

import pytest
import yaml

from sisepuede_tool.services import i18n

_PLURAL_CATEGORIES = {"zero", "one", "two", "few", "many", "other"}
_PKG = pathlib.Path(i18n.__file__).resolve().parent.parent
_TRANSLATIONS = [code for code in i18n.LANGUAGES if code != i18n.DEFAULT_LANG]


def _message_keys(lang):
    """UI keys (not data.*) with plural entries folded to their base key."""
    keys = set()
    for key in i18n.catalog(lang):
        if key.startswith("data."):
            continue
        base, _, last = key.rpartition(".")
        keys.add(base if last in _PLURAL_CATEGORIES else key)
    return keys


def _data_keys(lang):
    return {key for key in i18n.catalog(lang) if key.startswith("data.")}


def _placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.mark.parametrize("lang", _TRANSLATIONS)
def test_catalog_has_every_english_key(lang):
    assert _message_keys(lang) == _message_keys(i18n.DEFAULT_LANG)


def test_resource_translations():
    # English resource text is the resource file itself; es and ar translate the same entries
    assert not _data_keys(i18n.DEFAULT_LANG)
    assert _data_keys("es") == _data_keys("ar")


def test_resource_translations_point_at_real_entries():
    with open(_PKG / "resources" / "transformer_catalog.yaml", encoding="utf-8") as f:
        transformers = set(yaml.safe_load(f)["transformers"])
    with open(_PKG / "resources" / "param_schemas.yaml", encoding="utf-8") as f:
        params = {f"{tf}.{p}" for tf, ps in yaml.safe_load(f).items() if not tf.startswith("_") for p in ps}
    with open(_PKG / "resources" / "results_groups.yaml", encoding="utf-8") as f:
        cards = set(re.findall(r"^\s*-?\s*key: (\S+)", f.read(), flags=re.MULTILINE))
    for key in _data_keys("es"):
        _, kind, rest = key.split(".", 2)
        code = rest.rsplit(".", 1)[0]
        if kind == "transformers":
            assert code in transformers, key
        elif kind == "params":
            assert code in params, key
        elif kind == "results_groups":
            assert code in cards, key


def _used_keys():
    """Keys the UI code looks up with literal strings: i18n.t("a.b"), and _t("b") /
    _tn("b") in files whose _t prefixes with i18n.t(f"<area>.{key}", ...)."""
    used = set()
    for path in (_PKG / "ui").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        used |= {(k, path.name) for k in re.findall(r'i18n\.tn?\(\s*"([\w.]+)"', src)}
        prefixes = set(re.findall(r'i18n\.tn?\(f"([\w.]+)\.\{key\}"', src))
        assert len(prefixes) <= 1, f"{path.name}: one _t prefix per file"
        for prefix in prefixes:
            used |= {(f"{prefix}.{k}", path.name) for k in re.findall(r'\b_tn?\(\s*"([\w.]+)"', src)}
    return used


def test_keys_used_in_code_exist():
    english = _message_keys(i18n.DEFAULT_LANG)
    missing = sorted(f"{name}: {key}" for key, name in _used_keys() if key not in english)
    assert not missing, missing


@pytest.mark.parametrize("lang", _TRANSLATIONS)
def test_placeholders_match_english(lang):
    english = i18n.catalog(i18n.DEFAULT_LANG)
    for key, text in i18n.catalog(lang).items():
        if key.startswith("data."):
            continue
        base, _, last = key.rpartition(".")
        if last in _PLURAL_CATEGORIES:
            # a plural form may spell out its number ("one" -> "واحد") and leave {n} out
            source = english.get(f"{base}.other", "")
            assert _placeholders(text) - {"n"} <= _placeholders(source), key
            assert f"{base}.other" in i18n.catalog(lang), f"{base} needs an 'other' form"
        else:
            assert _placeholders(text) == _placeholders(english[key]), key


def test_every_catalog_formats():
    for lang in i18n.LANGUAGES:
        for text in i18n.catalog(lang).values():
            names = _placeholders(text)
            text.format(**{name: 1234 for name in names})  # raises on a bad placeholder


def test_resource_text():
    assert i18n.td("transformers", "NO:SUCH", "name", "Source name", "ar") == "Source name"
    assert i18n.td("transformers", "NO:SUCH", "name", "Source name", "en") == "Source name"
    assert i18n.td("transformers", "NO:SUCH", "name", None, "es") is None


def test_fallback_to_english_then_key():
    assert i18n.t("nav.pathways.label", "ar") == "المسارات"
    assert i18n.t("nav.pathways.label", "xx") == "Pathways"
    assert i18n.t("no.such.key", "es") == "no.such.key"
    assert i18n.t("no.such.key", "es", default="") == ""


def test_language_set_while_building_ui():
    with i18n.use("es"):
        assert i18n.t("nav.run.label") == "Ejecutar"
    assert i18n.t("nav.run.label") == "Run"


@pytest.mark.parametrize(
    "n, category",
    [(0, "zero"), (1, "one"), (2, "two"), (3, "few"), (10, "few"), (11, "many"), (99, "many"), (100, "other"), (103, "few")],
)
def test_arabic_plural_categories(n, category):
    assert i18n.plural_category("ar", n) == category


def test_plurals():
    assert i18n.tn("shell.baselines_loaded", 1, "en") == "1 baseline loaded"
    assert i18n.tn("shell.baselines_loaded", 3, "es") == "3 líneas base cargadas"
    assert i18n.tn("shell.baselines_loaded", 2, "ar") == "تم تحميل خطَّي أساس"
    # Arabic entry with only an 'other' form; values are isolated under RTL
    assert i18n.tn("data_input.n_fields", 1, "ar") == "عدد حقول المتغيرات: \u20681\u2069."


def test_values_isolated_only_for_rtl():
    assert i18n.t("data_input.region", "en", region="egypt") == "Region: egypt"
    assert i18n.t("data_input.region", "ar", region="egypt") == "المنطقة: \u2068egypt\u2069"
    assert i18n.isolate("590 Mt", "es") == "590 Mt"
    assert i18n.isolate("590 Mt", "ar") == "\u2068590 Mt\u2069"
    assert i18n.plain(i18n.t("data_input.region", "ar", region="egypt")) == "المنطقة: egypt"


@pytest.mark.parametrize(
    "search, lang", [("", "en"), ("?lang=ar", "ar"), ("lang=ES&x=1", "es"), ("?lang=fr", "en"), ("?lang=es-MX", "es")]
)
def test_language_from_query(search, lang):
    assert i18n.from_query(search) == lang


def test_rtl():
    assert i18n.is_rtl("ar") and not i18n.is_rtl("es")
    assert re.fullmatch(r"[a-z]{2}", i18n.DEFAULT_LANG)


def test_text_marked_only_while_building_the_page():
    assert not isinstance(i18n.t("nav.run.label", "es"), i18n.UIText)
    with i18n.use("es"):
        assert not isinstance(i18n.t("nav.run.label"), i18n.UIText)
    with i18n.use("es", static=True):
        text = i18n.t("nav.run.label")
        assert isinstance(text, i18n.UIText) and text == "Ejecutar" and text.key == "nav.run.label"
        assert isinstance(i18n.t("nav.run.label", "es"), i18n.UIText)  # same language (i18n.keep_inputs)
        assert not isinstance(i18n.t("nav.run.label", "ar"), i18n.UIText)
        assert i18n.pinned() == "es"
    assert i18n.pinned() is None


def test_mark_tags_text_attributes_and_options():
    from shiny import ui

    with i18n.use("es", static=True):
        tree = ui.div(
            ui.tags.h2(i18n.t("nav.run.label")),
            ui.tags.p(i18n.t("nav.run.label"), ui.tags.b("x")),
            ui.input_text("x", None, placeholder=i18n.t("data_input.search_placeholder")),
            ui.input_select("s", None, choices={"all": i18n.t("data_input.all")}),
            ui.tags.span(i18n.tn("shell.baselines_loaded", 2)),
        )
    html = str(i18n.mark(tree))
    assert '<h2 data-i18n="nav.run.label">Ejecutar</h2>' in html
    assert '<span data-i18n="nav.run.label">Ejecutar</span>' in html  # next to other children
    assert 'data-i18n-placeholder="data_input.search_placeholder"' in html and 'data-i18n-attrs="placeholder"' in html
    assert 'data-i18n="data_input.all"' in html and "data-i18n-options" in html
    assert 'data-i18n="shell.baselines_loaded" data-i18n-n="2"' in html


def test_client_strings_fall_back_to_english():
    strings = i18n.client_strings("ar")
    assert strings["nav.run.label"] == "التشغيل"
    assert not any(k.startswith("data.") for k in strings)
    assert set(i18n.client_strings("en")) <= set(strings)
