"""不依赖ROS通信的M6任务目标校验与状态常量。"""

from dataclasses import dataclass
import math
import re


TASK_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


@dataclass(frozen=True)
class MapBounds:
    """地图轴对齐边界。"""

    minimum_x: float
    maximum_x: float
    minimum_y: float
    maximum_y: float


def map_bounds(message):
    """从无旋转OccupancyGrid提取边界；旋转地图由后续版本显式支持。"""
    origin = message.info.origin
    yaw_terms = (origin.orientation.x, origin.orientation.y,
                 origin.orientation.z, origin.orientation.w)
    if not all(math.isfinite(value) for value in yaw_terms):
        return None
    if (abs(origin.orientation.x) > 1e-6 or
            abs(origin.orientation.y) > 1e-6 or
            abs(origin.orientation.z) > 1e-6 or
            abs(origin.orientation.w - 1.0) > 1e-6):
        return None
    width = message.info.width * message.info.resolution
    height = message.info.height * message.info.resolution
    return MapBounds(origin.position.x, origin.position.x + width,
                     origin.position.y, origin.position.y + height)


def validate_goal(goal, task_type, sensing_mode, bounds=None):
    """返回(error_code, message)，0表示通过。"""
    if not TASK_ID_PATTERN.fullmatch(goal.task_id):
        return 100, 'task_id格式无效'
    if goal.task_type != task_type:
        return 101, 'task_type未准入'
    if goal.sensing_mode != sensing_mode:
        return 101, 'sensing_mode未准入'
    if not 10.0 <= goal.task_timeout_sec <= 300.0:
        return 102, 'task_timeout_sec超出10～300 s'
    pose = goal.target_pose
    if pose.header.frame_id != 'map':
        return 102, 'target_pose必须使用map Frame'
    values = (pose.pose.position.x, pose.pose.position.y, pose.pose.position.z,
              pose.pose.orientation.x, pose.pose.orientation.y,
              pose.pose.orientation.z, pose.pose.orientation.w)
    if not all(math.isfinite(value) for value in values):
        return 102, 'target_pose包含非有限数值'
    quaternion_norm = math.sqrt(sum(value * value for value in values[3:]))
    if abs(quaternion_norm - 1.0) > 0.001:
        return 102, 'target_pose四元数未规范化'
    if bounds is not None and not (
            bounds.minimum_x <= pose.pose.position.x < bounds.maximum_x and
            bounds.minimum_y <= pose.pose.position.y < bounds.maximum_y):
        return 102, 'target_pose超出地图边界'
    return 0, '目标校验通过'
