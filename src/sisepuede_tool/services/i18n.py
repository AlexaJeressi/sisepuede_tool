"""UI text by language and text direction.

Text lives in resources/i18n/<lang>/*.yaml (one file per area of the app,
merged), nested keys flattened to dotted ones ("nav.pathways.label").
English is the source: a key missing from another catalog falls back to
English, then to the key itself.

Text that comes from the app's resource files (transformer names, card
titles, ...) is translated under ``data.*`` in es/ar only; English is the
resource file itself, passed as the default (``td()``).

The first language comes from ``?lang=`` (app_shell.app_ui); switching later
happens in place, without a reload, so nothing in the session is lost:

- Server code passes the session's language (``state.lang()``, reactive), so
  everything it renders re-renders in the new language.
- The page built at load (module UI functions) calls ``t()`` without a
  language inside ``use(lang, static=True)``. There ``t()``/``tn()`` return a
  ``UIText``: a str that remembers its key. ``mark()`` then tags those spots
  in the page (``data-i18n`` attributes) and the browser swaps their text
  from ``client_strings()`` when the language changes (app_shell).
"""

import contextlib
import contextvars
import dataclasses
import functools
import json
import pathlib
import string
import urllib.parse

import yaml


@dataclasses.dataclass(frozen=True)
class Language:
    code: str
    name: str  # in its own language, for the selector
    dir: str  # "ltr" | "rtl"


LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in (
        Language("en", "English", "ltr"),
        Language("es", "Español", "ltr"),
        Language("ar", "العربية", "rtl"),
    )
}
DEFAULT_LANG = "en"

_I18N_DIR = pathlib.Path(__file__).resolve().parent.parent / "resources" / "i18n"
_current = contextvars.ContextVar("sisepuede_tool_lang", default=DEFAULT_LANG)
_static = contextvars.ContextVar("sisepuede_tool_static_ui", default=False)


def normalize(code: str | None) -> str:
    """'AR', 'es-MX' -> 'ar', 'es'; anything unknown -> the default."""
    code = (code or "").strip().lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANG


def from_query(search: str | None) -> str:
    """Language from a URL query string ('?lang=ar&x=1')."""
    values = urllib.parse.parse_qs((search or "").lstrip("?")).get("lang")
    return normalize(values[0] if values else None)


def is_rtl(lang: str) -> bool:
    return LANGUAGES[normalize(lang)].dir == "rtl"


_FSI, _PDI = "\u2068", "\u2069"  # first-strong isolate ... pop directional isolate


def isolate(text: str, lang: str | None = None) -> str:
    """Under a right-to-left language, keep `text` ("590 Mt", "2015–2050", a name)
    in its own direction so it doesn't mix with the words around it."""
    lang = normalize(lang) if lang else _current.get()
    return f"{_FSI}{text}{_PDI}" if is_rtl(lang) and text else text


def plain(text: str) -> str:
    """Text without the isolate marks, for text that becomes data (a name the user can save)."""
    return text.replace(_FSI, "").replace(_PDI, "") if text else text


class _IsolatingFormatter(string.Formatter):
    def format_field(self, value, format_spec):
        return isolate(super().format_field(value, format_spec), "ar")


_ISOLATING = _IsolatingFormatter()


def _format(text: str, lang: str, fmt: dict) -> str:
    # placeholder values are isolated under RTL, so "{n} Mt" or a Latin name keeps its order
    return _ISOLATING.vformat(text, (), fmt) if is_rtl(lang) else text.format(**fmt)


@contextlib.contextmanager
def use(lang: str, static: bool = False):
    """Language for t() calls without one; static=True while building the page at load."""
    token, token_static = _current.set(normalize(lang)), _static.set(static)
    try:
        yield
    finally:
        _current.reset(token)
        _static.reset(token_static)


class UIText(str):
    """Text placed in the page at load, with what's needed to redo it in another language."""

    def __new__(cls, text: str, key: str, n: int | None = None, fmt: dict | None = None):
        out = super().__new__(cls, text)
        out.key, out.n, out.fmt = key, n, fmt or {}
        return out

    def __getnewargs__(self):  # copy / deepcopy (Shiny copies widget options)
        return str(self), self.key, self.n, self.fmt


def _marked(text: str, key: str, lang: str | None, n: int | None = None, fmt: dict | None = None) -> str:
    if _static.get() and (lang is None or normalize(lang) == _current.get()):
        return UIText(text, key, n, fmt)
    return text


def pinned() -> str | None:
    """The language while marked text is being built (page load, keep_inputs), else None.
    The session's lang() returns it so those builds don't subscribe to language changes."""
    return _current.get() if _static.get() else None


def keep_inputs(lang_fn):
    """For a @render.ui output that holds form inputs. Re-rendering on a language
    switch would reset what the user typed, so it is built in the current language
    without depending on it, its text marked, and the browser swaps that text."""
    from shiny import reactive

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            with reactive.isolate():
                lang = lang_fn()
            with use(lang, static=True):
                return mark(fn(*args, **kwargs))

        return inner

    return wrap


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


@functools.cache
def catalog(lang: str) -> dict[str, str]:
    out = {}
    for path in sorted((_I18N_DIR / lang).glob("*.yaml")):
        # BaseLoader keeps every value a string (no "No" -> False, "1.0" -> float)
        with open(path, encoding="utf-8") as f:
            entries = _flatten(yaml.load(f, Loader=yaml.BaseLoader) or {})
        clash = out.keys() & entries.keys()
        if clash:
            raise ValueError(f"{path.name} repeats keys from another {lang} file: {sorted(clash)[:5]}")
        out.update(entries)
    return out


def t(key: str, lang: str | None = None, default: str | None = None, **fmt) -> str:
    """Text for `key`; `fmt` fills its {placeholders}."""
    resolved = normalize(lang) if lang else _current.get()
    text = catalog(resolved).get(key) or catalog(DEFAULT_LANG).get(key)
    if text is None:
        return key if default is None else default
    return _marked(_format(text, resolved, fmt) if fmt else text, key, lang, fmt=fmt)


def td(kind: str, code: str, field: str, source: str | None, lang: str | None = None) -> str | None:
    """Translated resource text, e.g. td("transformers", "TFR:AGRC:DEC_CH4_RICE", "name", name, lang).

    `source` is the English text from the resource file; it is returned when
    there is no translation (always in English).
    """
    lang = normalize(lang) if lang else _current.get()
    if lang == DEFAULT_LANG or source is None:
        return source
    return catalog(lang).get(f"data.{kind}.{code}.{field}") or source


def plural_category(lang: str, n: int) -> str:
    """CLDR plural category; Arabic has six, English and Spanish two."""
    if normalize(lang) == "ar":
        if n == 0:
            return "zero"
        if n == 1:
            return "one"
        if n == 2:
            return "two"
        if 3 <= n % 100 <= 10:
            return "few"
        if 11 <= n % 100 <= 99:
            return "many"
        return "other"
    return "one" if n == 1 else "other"


def tn(key: str, n: int, lang: str | None = None, **fmt) -> str:
    """Plural text: `key.<category>`, else `key.other`; {n} is filled with `n`."""
    return _marked(_tn(key, n, normalize(lang) if lang else _current.get(), fmt), key, lang, n, fmt)


def _tn(key: str, n: int, lang: str, fmt: dict) -> str:
    entries = catalog(lang)
    text = entries.get(f"{key}.{plural_category(lang, n)}") or entries.get(f"{key}.other")
    if text is None:
        return key if lang == DEFAULT_LANG else _tn(key, n, DEFAULT_LANG, fmt)
    return _format(text, lang, {"n": n, **fmt})


# ---- language switch in the browser (app_shell) ----

# elements whose text the browser sets directly (a <span> isn't allowed inside them)
_TEXT_ONLY = {"option", "title", "textarea"}


def _mark_attrs(text: UIText, prefix: str) -> dict:
    attrs = {prefix: text.key}
    if text.n is not None:
        attrs[f"{prefix}-n"] = str(text.n)
    if text.fmt:
        attrs[f"{prefix}-args"] = json.dumps(text.fmt, default=str)
    return attrs


def mark(node):
    """Tag every UIText in a page tree so the browser can translate it in place:
    text -> data-i18n (on its element, or a <span> around it); attribute ->
    data-i18n-<attr>, listed in data-i18n-attrs; select options ->
    data-i18n-options for selectize."""
    from htmltools import Tag, TagList, tags

    def walk(node):
        if isinstance(node, TagList):
            for i, child in enumerate(node):
                node[i] = wrap(child, None)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        if not isinstance(node, Tag):
            # Shiny containers that become tags later (NavSet, NavPanel, ...) hold their tags as fields
            if hasattr(node, "tagify") and hasattr(node, "__dict__"):
                for value in vars(node).values():
                    walk(value)
            return
        translated = [attr for attr, value in node.attrs.items() if isinstance(value, UIText)]
        for attr in translated:
            node.attrs.update(_mark_attrs(node.attrs[attr], f"data-i18n-{attr}"))
        if translated:
            node.attrs["data-i18n-attrs"] = " ".join(translated)
        texts = [c for c in node.children if isinstance(c, UIText)]
        if texts and (node.name in _TEXT_ONLY or len(node.children) == 1):
            node.attrs.update(_mark_attrs(texts[0], "data-i18n"))
        else:
            for i, child in enumerate(node.children):
                node.children[i] = wrap(child, node)
        if node.name == "select":
            options = {}
            for child in node.children:
                if isinstance(child, Tag) and child.name == "option" and child.attrs.get("data-i18n"):
                    options[child.attrs.get("value")] = child.attrs["data-i18n"]
            if options:
                node.attrs["data-i18n-options"] = json.dumps(options)

    def wrap(child, parent):
        if isinstance(child, UIText):
            return tags.span(str(child), **_mark_attrs(child, "data-i18n"))
        walk(child)
        return child

    walk(node)
    return node


def client_strings(lang: str) -> dict[str, str]:
    """UI text the browser needs to translate the page in place (English where missing)."""
    lang = normalize(lang)
    english = {k: v for k, v in catalog(DEFAULT_LANG).items() if not k.startswith("data.")}
    return {**english, **{k: v for k, v in catalog(lang).items() if not k.startswith("data.")}}
