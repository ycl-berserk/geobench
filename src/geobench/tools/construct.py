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
from geobench.evaluate import evaluate_figure
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
                # The construction is legal; the geometry is not (yet)
                # computable. The figure stays as it was built, and the
                # reason is reported rather than swallowed.
                errors.append(to_error_info(exc))
                warnings.append(
                    f"the figure was constructed but could not be evaluated: {exc}"
                )
                status = "degraded"
            else:
                if not dry_run:
                    store.set_figure(fid, evaluated)

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
