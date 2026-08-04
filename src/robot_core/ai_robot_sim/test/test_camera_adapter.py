from sensor_msgs.msg import CameraInfo, Image
from camera_adapter import RVIZ_QOS, SENSOR_QOS, normalize_message
from rclpy.qos import ReliabilityPolicy


def test_normalize_image_preserves_payload_and_replaces_frame():
    source = Image(); source.header.frame_id = 'scoped'; source.width = 2; source.data = [1, 2, 3]
    result = normalize_message(source, 'camera_color_optical_frame')
    assert result.header.frame_id == 'camera_color_optical_frame'
    assert result.width == 2 and list(result.data) == [1, 2, 3]
    assert source.header.frame_id == 'scoped'


def test_normalize_camera_info_preserves_calibration():
    source = CameraInfo(); source.width = 640; source.k[0] = 500.0
    result = normalize_message(source, 'camera_color_optical_frame')
    assert result.header.frame_id == 'camera_color_optical_frame'
    assert result.width == 640 and result.k[0] == 500.0


def test_public_and_rviz_qos_are_intentionally_separated():
    assert SENSOR_QOS.reliability == ReliabilityPolicy.BEST_EFFORT
    assert RVIZ_QOS.reliability == ReliabilityPolicy.RELIABLE
