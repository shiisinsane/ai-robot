#!/usr/bin/env python3
"""离线审计B2正式预注册；不启动ROS、Gazebo或正式采集。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/w7_b2_preregistration_v0.3.yaml"


def audit(config: dict, root: Path = ROOT) -> dict:
    plan_path = root / config["frozen_plan"]["path"]
    payload = plan_path.read_bytes()
    rows = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    digest = hashlib.sha256(payload).hexdigest()
    split_expected = {name: int(value["tasks"])
                      for name, value in config["frozen_plan"]["split"].items()}
    split_actual = {name: sum(row["model_split"] == name for row in rows)
                    for name in split_expected}
    blocks_are_whole = all(len({row["model_split"] for row in rows
                                if row["randomized_block"] == block}) == 1
                           for block in range(1, config["frozen_plan"]["whole_blocks"] + 1))
    gates = {
        "status_frozen": config["status"] in {"frozen_pending_explicit_collection_authorization",
                                                "frozen_train_block_01_authorized",
                                                "train_block_01_accepted_waiting_next_authorization"},
        "authorization_bounded": (config["formal_collection_authorized"] is False or
                                  config["authorization_scope"] ==
                                  "train_block_01_only_slots_001_to_045"),
        "plan_hash_matches": digest == config["frozen_plan"]["sha256"],
        "plan_count_matches": len(rows) == config["frozen_plan"]["total_tasks"],
        "task_ids_unique": len({row["task_id"] for row in rows}) == len(rows),
        "split_counts_match": split_actual == split_expected,
        "whole_block_split": blocks_are_whole,
        "sealed_test_last": min(row["plan_index"] for row in rows
                                if row["model_split"] == "sealed_test") == 271,
        "snapshot_required": all(row["preacceptance_snapshot_required"] for row in rows),
        "plan_still_nonexecutable": all(not row["environment_ready"] and
                                        not row["qualification_ready"] for row in rows),
        "outcome_extension_forbidden":
            config["stopping_rules"]["outcome_based_sample_extension"] == "forbidden",
        "row_random_split_forbidden": config["frozen_plan"]["row_random_split"] == "forbidden",
        "qualification_complete": config["gates_before_collection"]["qualification_result"] ==
                                  "15_of_15_passed",
    }
    return {"version": config["version"], "passed": all(gates.values()),
            "formal_collection_authorized": config["formal_collection_authorized"],
            "plan_sha256": digest, "plan_rows": len(rows),
            "split_counts": split_actual, "gates": gates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    result = audit(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
