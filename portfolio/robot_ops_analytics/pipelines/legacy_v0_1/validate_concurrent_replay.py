"""在临时SQLite库上验证W5完整清单的并发、乱序和中断恢复。"""

from __future__ import annotations

import argparse
import json
import multiprocessing
from pathlib import Path
import sqlite3
from typing import Any

from .ingest_sqlite import ingest_dataset


def _worker(database: str, manifest: str, batch_ids: list[str], reverse: bool,
            delay: float, queue: Any) -> None:
    try:
        queue.put({"ok": True, "report": ingest_dataset(
            Path(database), Path(manifest), batch_ids=batch_ids,
            reverse_batches=reverse, max_delay_seconds=delay)})
    except Exception as error:  # pragma: no cover - 集成运行的错误传递路径
        queue.put({"ok": False, "error": repr(error)})


def validate(database: Path, manifest_path: Path, workers: int,
             max_delay_seconds: float) -> dict[str, Any]:
    if workers < 2:
        raise ValueError("并发验证至少需要2个进程")
    if database.exists():
        raise ValueError(f"验证数据库必须不存在：{database}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch_ids = sorted({row["batch_id"] for row in manifest["tasks"]})
    task_count = len({row["task_id"] for row in manifest["tasks"]})

    # 首批事务中途失败必须完整回滚；随后由并发回放恢复。
    try:
        ingest_dataset(database, manifest_path, batch_ids=[batch_ids[0]],
                       fail_after_records=2)
    except RuntimeError as error:
        if "注入接入中断" not in str(error):
            raise
    else:
        raise AssertionError("中断注入没有生效")
    with sqlite3.connect(database) as connection:
        if connection.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0] != 0:
            raise AssertionError("中断事务留下了半成品记录")

    shards = [[] for _ in range(workers)]
    for index, batch_id in enumerate(batch_ids):
        shards[index % workers].append(batch_id)
    # 制造跨进程重复：每个后续进程额外回放第一个批次。
    for shard in shards[1:]:
        shard.append(batch_ids[0])

    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(target=_worker, args=(
            str(database), str(manifest_path), shard, index % 2 == 1,
            max_delay_seconds, queue))
        for index, shard in enumerate(shards)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=120)
        if process.exitcode != 0:
            raise RuntimeError(f"并发接入子进程失败：exitcode={process.exitcode}")
    worker_reports = [queue.get(timeout=5) for _ in processes]
    failures = [report for report in worker_reports if not report["ok"]]
    if failures:
        raise RuntimeError(f"并发接入失败：{failures}")

    with sqlite3.connect(database) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        stored_records = connection.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0]
        unique_tasks = connection.execute(
            "SELECT COUNT(DISTINCT task_id) FROM raw_record").fetchone()[0]
        checkpoints = connection.execute("SELECT COUNT(*) FROM etl_checkpoint").fetchone()[0]
        quality_issues = connection.execute(
            "SELECT COUNT(*) FROM data_quality_issue").fetchone()[0]
    passed = (
        integrity == "ok" and journal_mode == "wal" and unique_tasks == task_count
        and checkpoints == len(batch_ids) * 2 and quality_issues == 0
    )
    return {
        "dataset_version": manifest["dataset_version"],
        "quality_gate_passed": passed,
        "worker_count": workers,
        "source_batches": len(batch_ids),
        "unique_tasks": unique_tasks,
        "stored_records": stored_records,
        "checkpoints": checkpoints,
        "quality_issues": quality_issues,
        "journal_mode": journal_mode,
        "integrity_check": integrity,
        "interrupted_transaction_rolled_back": True,
        "overlap_replays": workers - 1,
        "worker_reports": worker_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-delay-seconds", type=float, default=0.05)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.database, args.manifest, args.workers, args.max_delay_seconds)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    if not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
