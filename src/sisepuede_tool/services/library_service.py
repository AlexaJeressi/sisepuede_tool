"""Ready-made transformations shipped with the app ("library").

The first library is Egypt's NDC news set (resources/library/egypt_ndc_news,
copied from info/ndc_news): one sisepuede transformation YAML per announced
project, e.g. `TX:ENTC:TARGET_RENEWABLE_ELEC_NEWS_17`. Each file's
`description` packs the project facts into lines ("PROJECT: ...",
"Status: ...", "Investment: ...", "Start: ..."); `parse_project_description`
splits them out for display.

Files are loaded one at a time so that one bad file (e.g. a transformer that
no longer exists in sisepuede) is reported instead of blocking the rest.
"""

import dataclasses
import logging
import pathlib
import re
from typing import Dict, List, Optional

import sisepuede.transformers as trf
import yaml

from sisepuede_tool.services import transformation_service

logger = logging.getLogger(__name__)

SOURCE_USER = "user"
SOURCE_NDC_NEWS = "ndc_news"

_RE_NEWS_NUMBER = re.compile(r"_NEWS_(\d+)$")
_DESCRIPTION_KEYS = {"project": "PROJECT", "status": "Status", "investment": "Investment", "start": "Start"}


def default_library_dir() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "library" / "egypt_ndc_news"


@dataclasses.dataclass
class LibraryItem:
    code: str
    name: str
    transformer_code: str
    config: dict
    path: pathlib.Path
    source: str = SOURCE_NDC_NEWS
    news_number: Optional[int] = None
    project: Dict[str, str] = dataclasses.field(default_factory=dict)
    citations: List[str] = dataclasses.field(default_factory=list)
    error: Optional[str] = None  # set when it can't be used with the installed sisepuede

    @property
    def ok(self) -> bool:
        return self.error is None


def parse_project_description(description: Optional[str]) -> Dict[str, str]:
    """'PROJECT: X\\nStatus: Y\\n...' -> {'project': 'X', 'status': 'Y', ...}."""
    out: Dict[str, str] = {}
    for line in (description or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        for field, label in _DESCRIPTION_KEYS.items():
            if key.strip().lower() == label.lower():
                out[field] = value.strip()
    return out


def parse_citations(citations) -> List[str]:
    if not citations:
        return []
    if isinstance(citations, list):
        return [str(c).strip() for c in citations if str(c).strip()]
    return [c.strip() for c in str(citations).split("|") if c.strip()]


def load_library(dir_path=None) -> List[LibraryItem]:
    """Read every transformation_*.yaml in `dir_path`, without sisepuede."""
    dir_path = pathlib.Path(dir_path or default_library_dir())
    items = []
    for fp in sorted(dir_path.glob("transformation_*.yaml")):
        try:
            config = yaml.safe_load(fp.read_text()) or {}
            ident = config.get("identifiers") or {}
            code = ident["transformation_code"]
        except Exception as e:
            logger.warning("library file %s unreadable: %s", fp.name, e)
            continue
        m = _RE_NEWS_NUMBER.search(code)
        items.append(
            LibraryItem(
                code=code,
                name=ident.get("transformation_name") or code,
                transformer_code=config.get("transformer"),
                config=config,
                path=fp,
                news_number=int(m.group(1)) if m else None,
                project=parse_project_description(config.get("description")),
                citations=parse_citations(config.get("citations")),
            )
        )
    return items


def build_library_transformations(
    items: List[LibraryItem], transformers_catalog: trf.TransformerKernels
) -> Dict[str, trf.Transformation]:
    """Build a sisepuede Transformation per usable item. Items whose
    transformer is missing or fails on construction get `error` set and are
    left out of the result."""
    available = set(transformers_catalog.all_tkernels)
    out = {}
    for item in items:
        if item.transformer_code not in available:
            item.error = f"transformer {item.transformer_code} is not in the installed sisepuede"
            continue
        try:
            out[item.code] = trf.Transformation(item.config, transformers_catalog)
        except Exception as e:
            item.error = f"{type(e).__name__}: {e}"
            logger.warning("library transformation %s failed: %s", item.code, e)
    return out


def add_library_to_collection(
    transformations_obj: trf.Transformations,
    transformers_catalog: trf.TransformerKernels,
    items: Optional[List[LibraryItem]] = None,
) -> List[LibraryItem]:
    """Load the library into `transformations_obj` (once; existing codes are
    not overwritten). Returns all items, with `error` set on unusable ones."""
    items = load_library() if items is None else items
    built = build_library_transformations(items, transformers_catalog)
    for code, transformation in built.items():
        if code not in transformations_obj.dict_transformations:
            transformations_obj.dict_transformations[code] = transformation
    transformation_service.rebuild_attribute_table(transformations_obj)
    return items
