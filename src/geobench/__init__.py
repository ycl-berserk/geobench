"""geobench - a deterministic plane-geometry kernel for authoring problems.

The package is deliberately small at this stage: the construction graph, the
exact-arithmetic layer, the operator registry and the figure store. See
``docs/spec.md`` for the contract these modules implement.
"""

from __future__ import annotations

from geobench.field import FIELD, Field, SympyField
from geobench.model import Figure, Node, Relation, Style
from geobench.registry import ArgSpec, OperatorRegistry, OpSpec
from geobench.state import ApplyResult, FigureStore, OpRequest

__version__ = "0.1.0.dev0"

__all__ = [
    "FIELD",
    "ApplyResult",
    "ArgSpec",
    "Field",
    "Figure",
    "FigureStore",
    "Node",
    "OpRequest",
    "OpSpec",
    "OperatorRegistry",
    "Relation",
    "Style",
    "SympyField",
    "__version__",
]
