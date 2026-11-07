"""``geo_construct`` -- apply a batch of constructions.

Two properties matter here and both are load-bearing:

- **Atomicity.** A batch that contains a bad operation changes nothing. An
  agent that sends five constructions and gets one wrong must not have to
  work out which four landed.
- **Honest degradation.** A construction can be legal and still have no
  geometric answer -- three collinear points have no circumcircle. That is
  reported as ``degraded`` with the reason, not as an error (the request
  was fine) and not as success (the geometry is incomplete).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, undefined_nodes
from geobench.registry import OperatorRegistry
from geobench.state import FigureStore, OpRequest
from geobench.tools.errors import to_error_info
from geobench.tools.models import ConstructOp, ConstructResponse
from geobench.tools.spec import TOOL_SPECS_BY_NAME
from geobench.tools.state import DEFAULT_FIGURE_ID


def make_construct_tool(
    store: FigureStore, registry: OperatorRegistry
) -> Callable[..., Any]:
    """Build the ``geo_construct`` tool bound to ``store`` and ``registry``."""

    def geo_construct(
        ops: list[ConstructOp],
        figure_id: str | None = None,
        mode: Literal["apply", "dry-run"] = "apply",
    ) -> ConstructResponse:
        fid = figure_id or DEFAULT_FIGURE_ID
        dry_run = mode == "dry-run"
        requests = [
            OpRequest(op=item.op, args=list(item.args), id=item.id) for item in ops
        ]

        result = store.apply(fid, requests, dry_run=dry_run)
        errors = [to_error_info(exc) for exc in result.exceptions]
        warnings = list(result.warnings)

        if not result.ok:
            return ConstructResponse(
                status="error",
                figure_id=fid,
                mode=mode,
                created=result.created,
                updated=result.updated,
                removed=result.removed,
                errors=errors,
                warnings=warnings,
            )

        status: Literal["ok", "degraded"] = "ok"
        working = result.figure
        if working is not None:
            evaluated = working.copy()
            try:
                evaluate_figure(evaluated, registry)
            except GeobenchError as exc:
                # The construction is illegal: the operator refused it.
                errors.append(to_error_info(exc))
                warnings.append(f"the figure was constructed but could not be evaluated: {exc}")
                status = "degraded"
            else:
                if not dry_run:
                    store.set_figure(fid, evaluated)
                # An object that has no value at this placement is
                # *undefined*, not an error: the figure is still a figure
                # (decision D19), but the caller has to know that part of
                # it could not be computed.
                undefined = undefined_nodes(evaluated)
                if undefined:
                    status = "degraded"
                    listed = ", ".join(
                        f"{node_id} ({reason})" for node_id, reason in undefined
                    )
                    warnings.append(
                        "these objects have no value at the current placement: " + listed
                    )

        return ConstructResponse(
            status=status,
            figure_id=fid,
            mode=mode,
            created=result.created,
            updated=result.updated,
            removed=result.removed,
            errors=errors,
            warnings=warnings,
        )

    geo_construct.__name__ = "geo_construct"
    geo_construct.__doc__ = TOOL_SPECS_BY_NAME["geo_construct"].description
    return geo_construct
