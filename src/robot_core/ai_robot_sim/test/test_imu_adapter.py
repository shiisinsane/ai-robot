from sensor_msgs.msg import Imu

from imu_adapter import IMU_QOS, normalize_imu
from rclpy.qos import ReliabilityPolicy


def test_normalize_imu_preserves_measurements_and_applies_contract():
    source = Imu()
    source.header.frame_id = 'scoped_imu'
    source.orientation.w = 1.0
    source.angular_velocity.z = 0.4
    source.linear_acceleration.z = 9.8
    orientation = [0.0001, 0.0, 0.0, 0.0, 0.0001, 0.0, 0.0, 0.0, 0.0001]
    angular = [0.000004, 0.0, 0.0, 0.0, 0.000004, 0.0, 0.0, 0.0, 0.000004]
    linear = [0.0004, 0.0, 0.0, 0.0, 0.0004, 0.0, 0.0, 0.0, 0.0004]
    result = normalize_imu(source, 'imu_link', orientation, angular, linear)
    assert result.header.frame_id == 'imu_link'
    assert result.orientation.w == 1.0 and result.angular_velocity.z == 0.4
    assert result.linear_acceleration.z == 9.8
    assert list(result.orientation_covariance) == orientation
    assert list(result.angular_velocity_covariance) == angular
    assert list(result.linear_acceleration_covariance) == linear
    assert source.header.frame_id == 'scoped_imu'


def test_imu_qos_matches_m1_contract():
    assert IMU_QOS.depth == 20
    assert IMU_QOS.reliability == ReliabilityPolicy.BEST_EFFORT
