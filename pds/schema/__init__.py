"""지식 엔티티 스키마 (KNOWLEDGE-SPEC §3). pydantic 모델이 원본이고 schemas/*.schema.json은 export 결과."""
from pds.schema.common import GROUNDED, Claim, Evidence
from pds.schema.dataset import Dataset
from pds.schema.graph import Context, Edge, Gap, Issuer, Key, Law, Mapping, Recipe, Target

MODELS = {"dataset": Dataset, "key": Key, "mapping": Mapping, "edge": Edge, "context": Context, "recipe": Recipe,
          "gap": Gap, "law": Law, "issuer": Issuer, "target": Target, "claim": Claim}

__all__ = ["MODELS", "GROUNDED", "Claim", "Evidence", "Dataset", "Key", "Mapping", "Edge", "Context", "Recipe", "Gap",
           "Law", "Issuer", "Target"]
