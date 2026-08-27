"""汇总W4批次运行结果；不把失败任务删除。"""

import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(x) for x in args.results.read_text(encoding="utf-8").splitlines()]
    summary = {
        "executed_tasks": len(rows),
        "runner_success": sum(x["return_code"] == 0 for x in rows),
        "runner_failure": sum(x["return_code"] != 0 for x in rows),
        "by_route": dict(Counter(x["route_id"] for x in rows)),
        "by_origin": dict(Counter(x["run_origin"] for x in rows)),
        "by_environment_profile": dict(Counter(x["environment_profile"] for x in rows)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
