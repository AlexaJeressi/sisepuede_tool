"""Ready-made transformations shipped with the app ("library").

The library is Egypt's NDC set (resources/library/egypt_ndc): the
transformations activated by the NDC strategy (6003 PFLO:NDC) in the
ssp_egypt repo, branch btr_invent, e.g. `TX:IPPU:DEC_CLINKER_STRATEGY_NDC`.
One transformation per NDC lever; the news-reported projects that map to it
are linked by transformer (see projects_service.default_links).

Files are loaded one at a time so that one bad file (e.g. a transformer that
no longer exists in sisepuede) is reported instead of blocking the rest.
"""

import dataclasses
import logging
import pathlib
from typing import Dict, List, Optional

import sisepuede.transformers as trf
import yaml

from sisepuede_tool.services import transformation_service

logger = logging.getLogger(__name__)

SOURCE_USER = "user"
SOURCE_NDC = "ndc"


def default_library_dir() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "library" / "egypt_ndc"


@dataclasses.dataclass
class LibraryItem:
    code: str
    name: str
    transformer_code: str
    config: dict
    path: pathlib.Path
    source: str = SOURCE_NDC
    citations: List[str] = dataclasses.field(default_factory=list)
    error: Optional[str] = None  # set when it can't be used with the installed sisepuede

    @property
    def ok(self) -> bool:
        return self.error is None


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
        items.append(
            LibraryItem(
                code=code,
                name=ident.get("transformation_name") or code,
                transformer_code=config.get("transformer"),
                config=config,
                path=fp,
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
