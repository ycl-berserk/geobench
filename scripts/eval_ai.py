"""Run the evaluation set against a real model service.

This is the **manual** runner: it talks to the network, so it is not
part of CI (CI uses a fake provider -- see ``tests/eval``).  Run it
when the skill changes, to see the pass rate move:

    python scripts/eval_ai.py                 # every case
    python scripts/eval_ai.py 锐角             # only the cases whose name matches
    python scripts/eval_ai.py --show          # also print the figures

The service is the one the studio would use: the environment first,
then the key file, then the app's own settings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from evals.cases import CASES  # noqa: E402
from evals.harness import run_case  # noqa: E402

from geobench.ai_settings import resolve_provider  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pattern", nargs="?", default="", help="only the cases whose name matches")
    parser.add_argument("--show", action="store_true", help="print the figures too")
    parser.add_argument("--retries", type=int, default=2, help="how many tries the model gets")
    args = parser.parse_args()

    resolution = resolve_provider()
    if not resolution.ok:
        print(f"没有可用的模型服务：{resolution.reason}", file=sys.stderr)
        return 1
    print(f"服务：{resolution.provider.name}（密钥来自 {resolution.source_kind}: {resolution.source_name}）")
    print()

    registry = OperatorRegistry()
    register_builtins(registry)

    cases = [case for case in CASES if args.pattern in case.name]
    if not cases:
        print("没有匹配的用例", file=sys.stderr)
        return 1

    passed = 0
    for case in cases:
        result = run_case(resolution.provider, case, registry, retries=args.retries)
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {case.name}  (attempts={result.attempts})")
        if args.show:
            print(result.text)
        for reason in result.reasons():
            print(f"        · {reason}")
        if result.passed:
            passed += 1
    print()
    print(f"{passed}/{len(cases)} 通过")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
