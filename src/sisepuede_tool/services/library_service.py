"""Ready-made transformations shipped with the app ("library").

The library is Egypt's NDC set (resources/library/egypt_ndc): the
transformations activated by the NDC strategy (6003 PFLO:NDC) in the
ssp_egypt repo, branch btr_invent, e.g. `TX:IPPU:DEC_CLINKER_STRATEGY_NDC`.
One transformation per NDC lever; the news-reported projects that map to it
are linked by transformer (see projects_service.default_links).

A second set, Egypt's LEP transformations (resources/library/egypt_lep),
is the higher-ambition pathway used to demonstrate Article 6 opportunities:
the `*_LEP.yaml` files from the same branch (commit 802be90, jcsyme), e.g.
`TX:TRNS:SHIFT_MODE_PASSENGER_LEP`. The LEP strategy (6005 PFLO:LEP) is 13
NDC transformations plus these 9; its list is in egypt_lep/pathway_LEP.txt.
Their names were changed from "Scaled Default Max Parameters by 1.0 - ..." /
"Default Value - ..." to "LEP · ...". Projects are linked to the NDC set only.

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
SOURCE_LEP = "lep"
SOURCE_LABELS = {SOURCE_NDC: "NDC", SOURCE_LEP: "LEP"}


def default_library_dir() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "library" / "egypt_ndc"


def lep_library_dir() -> pathlib.Path:
    return default_library_dir().parent / "egypt_lep"


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


def load_library(dir_path=None, source: str = SOURCE_NDC) -> List[LibraryItem]:
    """Read every transformation_*.yaml in `dir_path` (default: the NDC set), without sisepuede."""
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
                source=source,
                citations=parse_citations(config.get("citations")),
            )
        )
    return items


def load_lep_library() -> List[LibraryItem]:
    return load_library(lep_library_dir(), source=SOURCE_LEP)


def load_all_libraries() -> List[LibraryItem]:
    """The NDC set, then the LEP set."""
    return load_library() + load_lep_library()


def lep_pathway_codes() -> List[str]:
    """Transformation codes of the LEP strategy (6005 PFLO:LEP): NDC and LEP items."""
    lines = (lep_library_dir() / "pathway_LEP.txt").read_text().splitlines()
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


def strip_set_prefix(name: str) -> str:
    """'NDC · ENTC: Clean hydrogen' -> 'ENTC: Clean hydrogen' (same for 'LEP · ')."""
    for label in SOURCE_LABELS.values():
        prefix = f"{label} · "
        if name and name.startswith(prefix):
            return name[len(prefix) :]
    return name


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
    """Load the library (default: NDC + LEP sets) into `transformations_obj`
    (once; existing codes are not overwritten). Returns all items, with `error`
    set on unusable ones."""
    items = load_all_libraries() if items is None else items
    built = build_library_transformations(items, transformers_catalog)
    for code, transformation in built.items():
        if code not in transformations_obj.dict_transformations:
            transformations_obj.dict_transformations[code] = transformation
    transformation_service.rebuild_attribute_table(transformations_obj)
    return items
