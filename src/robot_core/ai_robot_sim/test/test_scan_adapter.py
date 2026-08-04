"""雷达公共接口适配器单元测试。"""

from sensor_msgs.msg import LaserScan

from scan_adapter import normalize_scan


def test_normalize_scan_only_replaces_frame():
    source = LaserScan()
    source.header.frame_id = 'ai_robot/base_link/gpu_lidar'
    source.header.stamp.sec = 12
    source.angle_min = -1.0
    source.ranges = [1.0, 2.0, 3.0]

    normalized = normalize_scan(source, 'laser_link')

    assert normalized.header.frame_id == 'laser_link'
    assert normalized.header.stamp.sec == 12
    assert normalized.angle_min == -1.0
    assert list(normalized.ranges) == [1.0, 2.0, 3.0]
    assert source.header.frame_id == 'ai_robot/base_link/gpu_lidar'
