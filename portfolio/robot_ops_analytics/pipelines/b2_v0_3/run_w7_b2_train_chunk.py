#!/usr/bin/env python3
"""连续执行已授权训练区组1的一段槽位；任一槽位失败即停。"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT.parents[1] / "artifacts/roa_b2/roa-risk-b2-v0.3/train-block-01/valid_slots.jsonl"
OUTPUT = STATE.parent


def next_slot() -> int:
    if not STATE.is_file():
        return 1
    return sum(bool(line.strip()) for line in STATE.read_text(encoding="utf-8").splitlines()) + 1


def next_attempt(slot: int) -> int:
    prefix = f"b2-train-b01-slot-{slot:03d}-attempt-"
    attempts = [int(path.name.removeprefix(prefix)) for path in OUTPUT.glob(prefix + "*")
                if path.name.removeprefix(prefix).isdigit()]
    return max(attempts, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-slot", type=int, required=True)
    parser.add_argument("--end-slot", type=int, required=True)
    parser.add_argument("--start-domain", type=int, default=160)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.start_slot <= args.end_slot <= 45:
        parser.error("槽位范围必须位于1～45")
    if next_slot() != args.start_slot:
        raise SystemExit(f"只能从首个未完成槽位{next_slot()}开始")
    if not args.execute:
        for slot in range(args.start_slot, args.end_slot + 1):
            domain = args.start_domain + slot - args.start_slot
            print(f"预览槽位{slot}：ROS域{domain}")
        print("当前仅预览；执行时每槽位成功落盘后才进入下一槽位。")
        return 0
    for slot in range(args.start_slot, args.end_slot + 1):
        domain = args.start_domain + slot - args.start_slot
        if not 0 <= domain <= 232:
            raise SystemExit("ROS域超出0～232")
        command = [sys.executable, "-m",
                   "portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_train_block",
                   "--slot", str(slot), "--attempt", str(next_attempt(slot)),
                   "--domain-id", str(domain)]
        command.append("--execute")
        print(f"===== 小批次槽位{slot}/{args.end_slot} =====", flush=True)
        result = subprocess.run(command, cwd=ROOT.parents[1], check=False)
        if result.returncode:
            print(f"槽位{slot}失败，小批次停止；槽位{slot + 1}及以后未启动", flush=True)
            return result.returncode
    print(f"小批次完成：槽位{args.start_slot}～{args.end_slot}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
