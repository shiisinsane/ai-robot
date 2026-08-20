"""与 ROS 2 通信解耦的确定性采集核心。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


PHASE_NAMES = {1: "accepted", 2: "validating", 3: "navigating", 4: "sensing", 5: "canceling"}
TERMINAL_BY_ERROR = {0: "success", 202: "canceled", 203: "timeout"}


class JsonlSink:
    """逐行写入稳定 JSON；每条记录自带类型和 schema 版本。"""

    def __init__(self, path: Path | str, schema_version: str = "roa-schema-v1.0"):
        self.path = Path(path)
        self.schema_version = schema_version
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record_type: str, payload: Dict[str, Any]) -> None:
        row = {"record_type": record_type, "schema_version": self.schema_version, **payload}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


@dataclass
class TaskRecorder:
    experiment_id: str
    task_id: str
    request_id: str
    requested_at_sim: float
    event_sequence: int = 0
    last_event_time_sim: Optional[float] = None
    last_phase: Optional[str] = None
    events: list[Dict[str, Any]] = field(default_factory=list)
    clock_valid: bool = True

    def add_event(self, event_time_sim: float, event_type: str, **values: Any) -> Dict[str, Any]:
        if self.last_event_time_sim is not None and event_time_sim < self.last_event_time_sim:
            self.clock_valid = False
        self.event_sequence += 1
        event = {
            "task_event_id": f"{self.task_id}-e{self.event_sequence:04d}",
            "task_id": self.task_id,
            "event_sequence": self.event_sequence,
            "event_time_sim": event_time_sim,
            "event_type": event_type,
            **values,
        }
        self.events.append(event)
        self.last_event_time_sim = event_time_sim
        self.last_phase = event_type
        return event

    def add_feedback(self, event_time_sim: float, phase_code: int, progress: float, message: str) -> Optional[Dict[str, Any]]:
        phase = PHASE_NAMES.get(phase_code, "unknown")
        # 高频反馈只有阶段变化才成为事件；进度留给原始 Action/rosbag。
        if phase == self.last_phase:
            return None
        return self.add_event(event_time_sim, phase, phase_code=phase_code,
                              progress=max(0.0, min(1.0, float(progress))), message=message)


@dataclass
class _Bucket:
    task_id: str
    start: int
    odom_linear: list[float] = field(default_factory=list)
    odom_angular: list[float] = field(default_factory=list)
    pose: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    scans: list[float] = field(default_factory=list)
    safety: list[bool] = field(default_factory=list)
    timestamps_valid: bool = True


class TelemetryBucketAggregator:
    """按 ROS 仿真时间生成左闭右开的一秒遥测桶。"""

    def __init__(self, required_topics: Iterable[str] = ("odom", "pose", "scan", "safety")):
        self.required_topics = frozenset(required_topics)
        self._buckets: Dict[tuple[str, int], _Bucket] = {}
        self._last_stamp: Dict[str, float] = {}

    def _bucket(self, task_id: str, stamp: float, topic: str) -> _Bucket:
        if not math.isfinite(stamp) or stamp < 0:
            raise ValueError("ROS 时间戳必须是非负有限数")
        key = (task_id, math.floor(stamp))
        bucket = self._buckets.setdefault(key, _Bucket(task_id, key[1]))
        previous = self._last_stamp.get(topic)
        if previous is not None and stamp < previous:
            bucket.timestamps_valid = False
        self._last_stamp[topic] = stamp
        return bucket

    def add_odom(self, task_id: str, stamp: float, linear: float, angular: float) -> None:
        bucket = self._bucket(task_id, stamp, "odom")
        bucket.odom_linear.append(float(linear)); bucket.odom_angular.append(float(angular))

    def add_pose(self, task_id: str, stamp: float, x: float, y: float, yaw: float,
                 covariance_x: float, covariance_y: float, covariance_yaw: float) -> None:
        self._bucket(task_id, stamp, "pose").pose.append(
            (x, y, yaw, covariance_x, covariance_y, covariance_yaw))

    def add_scan(self, task_id: str, stamp: float, ranges: Iterable[float], range_min: float, range_max: float) -> None:
        valid = [float(v) for v in ranges if math.isfinite(v) and range_min <= v <= range_max]
        bucket = self._bucket(task_id, stamp, "scan")
        if valid:
            bucket.scans.append(min(valid))

    def add_safety(self, task_id: str, stamp: float, active: bool) -> None:
        self._bucket(task_id, stamp, "safety").safety.append(bool(active))

    def rows(self) -> list[Dict[str, Any]]:
        result = []
        for _, bucket in sorted(self._buckets.items()):
            present = set()
            if bucket.odom_linear: present.add("odom")
            if bucket.pose: present.add("pose")
            if bucket.scans: present.add("scan")
            if bucket.safety: present.add("safety")
            pose = bucket.pose[-1] if bucket.pose else (None,) * 6
            result.append({
                "task_id": bucket.task_id,
                "bucket_start_sim": float(bucket.start),
                "bucket_end_sim": float(bucket.start + 1),
                "sample_count_odom": len(bucket.odom_linear),
                "sample_count_pose": len(bucket.pose),
                "sample_count_scan": len(bucket.scans),
                "sample_count_safety": len(bucket.safety),
                "required_topics_present": self.required_topics <= present,
                "timestamp_valid": bucket.timestamps_valid,
                "pose_x_m": pose[0], "pose_y_m": pose[1], "pose_yaw_rad": pose[2],
                "pose_covariance_x": pose[3], "pose_covariance_y": pose[4], "pose_covariance_yaw": pose[5],
                "mean_linear_speed_mps": _mean(bucket.odom_linear),
                "max_abs_linear_speed_mps": _absmax(bucket.odom_linear),
                "mean_angular_speed_rps": _mean(bucket.odom_angular),
                "max_abs_angular_speed_rps": _absmax(bucket.odom_angular),
                "minimum_valid_scan_range_m": min(bucket.scans) if bucket.scans else None,
                "safety_stop_active": any(bucket.safety) if bucket.safety else None,
                "stale_sensor_mask": 0,
            })
        return result


def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _absmax(values: list[float]) -> Optional[float]:
    return max((abs(v) for v in values), default=None)
