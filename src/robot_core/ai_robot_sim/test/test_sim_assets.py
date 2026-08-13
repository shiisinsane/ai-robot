from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_world_is_valid_sdf_with_required_systems():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm2_empty.sdf').getroot()
    assert root.tag == 'sdf'
    world = root.find("world[@name='m2_empty']")
    assert world is not None
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-physics-system' in filenames
    assert 'ignition-gazebo-user-commands-system' in filenames
    assert 'ignition-gazebo-scene-broadcaster-system' in filenames


def test_world_has_static_ground_and_expected_gravity():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm2_empty.sdf').getroot()
    world = root.find("world[@name='m2_empty']")
    assert world.findtext('gravity') == '0 0 -9.80665'
    ground = world.find("model[@name='ground_plane']")
    assert ground is not None
    assert ground.findtext('static') == 'true'


def test_launch_enables_control_without_motion_publisher():
    launch_text = (PACKAGE_ROOT / 'launch' / 'fortress.launch.py').read_text()
    assert "'/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'" in launch_text
    assert "'-topic', '/robot/robot_description'" in launch_text
    assert 'enable_control:=true' in launch_text
    assert "package='controller_manager'" in launch_text
    assert 'geometry_msgs' not in launch_text
    assert "executable='cmd_vel_safety_filter.py'" in launch_text


def test_lidar_world_and_launch_are_independent_and_one_way():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_lidar.sdf').getroot()
    world = root.find("world[@name='m3_lidar']")
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-sensors-system' in filenames
    assert world.find("model[@name='front_obstacle']") is not None
    assert world.find("model[@name='left_obstacle']") is not None
    launch_text = (PACKAGE_ROOT / 'launch' / 'lidar.launch.py').read_text()
    assert 'enable_lidar:=true' in launch_text
    assert '/ai_robot_internal/lidar_scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan' in launch_text
    assert "executable='scan_adapter.py'" in launch_text
    assert "package='controller_manager'" not in launch_text


def test_camera_world_and_launch_use_internal_one_way_topics():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_camera.sdf').getroot()
    assert root.find("world[@name='m3_camera']/model[@name='camera_target']") is not None
    text = (PACKAGE_ROOT / 'launch' / 'camera.launch.py').read_text()
    assert 'enable_camera:=true' in text
    assert '/ai_robot_internal/camera@sensor_msgs/msg/Image[gz.msgs.Image' in text
    assert "executable='camera_adapter.py'" in text


def test_imu_world_and_launch_are_independent_and_one_way():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_imu.sdf').getroot()
    world = root.find("world[@name='m3_imu']")
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-sensors-system' in filenames
    assert 'ignition-gazebo-imu-system' in filenames
    text = (PACKAGE_ROOT / 'launch' / 'imu.launch.py').read_text()
    assert 'enable_imu:=true' in text
    assert '/ai_robot_internal/imu@sensor_msgs/msg/Imu[gz.msgs.IMU' in text
    assert "executable='imu_adapter.py'" in text
    assert "package='controller_manager'" not in text
    motion = (PACKAGE_ROOT / 'launch' / 'imu_motion.launch.py').read_text()
    assert 'enable_control:=true enable_imu:=true' in motion
    assert "executable='cmd_vel_safety_filter.py'" in motion


def test_encoder_has_independent_launch_reusing_accepted_control_chain():
    text = (PACKAGE_ROOT / 'launch' / 'encoder.launch.py').read_text()
    assert "'launch', 'fortress.launch.py'" in text
    assert 'IncludeLaunchDescription' in text


def test_m4_integrated_world_has_all_runtime_systems():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm4_integrated.sdf').getroot()
    world = root.find("world[@name='m4_integrated']")
    assert world is not None
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-physics-system' in filenames
    assert 'ignition-gazebo-sensors-system' in filenames
    assert 'ignition-gazebo-imu-system' in filenames
    assert world.find("model[@name='ground_plane']") is not None
    assert world.find("model[@name='integration_target']") is not None


def test_m4_integrated_launch_unifies_units_and_preserves_contract_boundaries():
    text = (PACKAGE_ROOT / 'launch' / 'integrated_bringup.launch.py').read_text()
    for option in ('enable_control:=true', 'enable_lidar:=true',
                   'enable_camera:=true', 'enable_imu:=true'):
        assert option in text
    assert 'controllers_m4.yaml' in text
    assert 'controller_odom_topic:=internal/base_odom' in text
    assert "('/robot/cmd_vel', '/robot/safety_cmd_vel')" in text
    assert 'joint_state_broadcaster' in text
    assert 'diff_drive_base_controller' in text
    assert "executable='scan_adapter.py'" in text
    assert "executable='camera_adapter.py'" in text
    assert "executable='imu_adapter.py'" in text
    assert "DeclareLaunchArgument('enable_lidar_pipeline', default_value='true')" in text
    assert "IfCondition(LaunchConfiguration('enable_lidar_pipeline'))" in text
    assert "package='image_proc'" in text
    assert "executable='rectify_node'" in text
    assert "namespace='robot/camera/color'" in text
    assert "('image', 'image_raw')" in text
    assert "('image_rect', '/robot/internal/camera/color/image_rect')" in text
    assert "executable='image_qos_adapter.py'" in text
    assert "DeclareLaunchArgument('enable_image_processing', default_value='true')" in text
    assert "executable='safety_supervisor.py'" in text
    assert "executable='joint_state_qos_adapter.py'" in text
    assert "DeclareLaunchArgument('safety_scan_topic', default_value='/robot/scan')" in text


def test_m4_controller_config_reserves_tf_for_state_estimator():
    text = (PACKAGE_ROOT / 'config' / 'controllers_m4.yaml').read_text()
    assert 'enable_odom_tf: false' in text


def test_m4_ekf_fuses_internal_odom_and_imu_with_unique_tf_authority():
    config = (PACKAGE_ROOT / 'config' / 'ekf_m4.yaml').read_text()
    assert 'odom0: /robot/internal/base_odom' in config
    assert 'imu0: /robot/imu/data' in config
    assert 'world_frame: odom' in config
    assert 'base_link_frame: base_link' in config
    assert 'publish_tf: true' in config
    launch = (PACKAGE_ROOT / 'launch' / 'integrated_bringup.launch.py').read_text()
    assert "package='robot_localization'" in launch
    assert "('odometry/filtered', '/robot/odom')" in launch
    assert 'target_action=drive_spawner' in launch
    assert 'on_exit=[state_estimator, image_processor, image_qos_adapter]' in launch


def test_m5_slam_world_launch_and_config_preserve_m4_safety_chain():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm5_slam.sdf').getroot()
    world = root.find("world[@name='m5_slam']")
    assert world is not None
    for model in ('north_wall', 'south_wall', 'east_wall', 'west_wall',
                  'landmark_a', 'landmark_b'):
        assert world.find(f"model[@name='{model}']") is not None

    launch = (PACKAGE_ROOT / 'launch' / 'm5_slam.launch.py').read_text()
    assert 'integrated_bringup.launch.py' in launch
    assert "executable='async_slam_toolbox_node'" in launch
    assert "namespace='robot'" in launch
    assert "('scan', '/robot/scan')" in launch
    assert "('/map', '/robot/map')" in launch
    assert "('tf', '/tf')" in launch

    params = (PACKAGE_ROOT / 'config' / 'slam_mapping.yaml').read_text()
    assert 'mode: mapping' in params
    assert 'map_frame: map' in params
    assert 'odom_frame: odom' in params
    assert 'base_frame: base_link' in params
    assert 'scan_topic: /robot/scan' in params
    assert 'transform_publish_period: 0.05' in params


def test_m5_rviz_uses_map_frame_and_public_topics():
    rviz = (PACKAGE_ROOT / 'config' / 'slam_mapping.rviz').read_text()
    assert 'Class: rviz_common/Displays\n    Name: Displays' in rviz
    assert 'Fixed Frame: map' in rviz
    assert 'Value: /robot/map' in rviz
    assert 'Value: /robot/scan' in rviz


def test_m5_map_save_is_guarded_and_reload_is_separate():
    slam_launch = (PACKAGE_ROOT / 'launch' / 'm5_slam.launch.py').read_text()
    assert "executable='map_saver_server'" in slam_launch
    assert "executable='map_save_guard.py'" in slam_launch
    guard = (PACKAGE_ROOT / 'scripts' / 'map_save_guard.py').read_text()
    assert "'/robot/internal_map_saver/save_map'" in guard
    assert "DeclareLaunchArgument('map_directory'" in slam_launch
    reload_launch = (PACKAGE_ROOT / 'launch' / 'm5_map_reload.launch.py').read_text()
    assert "executable='map_server'" in reload_launch
    assert "'yaml_filename': LaunchConfiguration('map')" in reload_launch
    assert "('/map', '/robot/map')" in reload_launch


def test_m5_localization_excludes_slam_and_assigns_tf_to_amcl():
    launch = (PACKAGE_ROOT / 'launch' / 'm5_localization.launch.py').read_text()
    assert "executable='map_server'" in launch
    assert "executable='amcl'" in launch
    assert 'slam_toolbox' not in launch
    assert "('amcl_pose', '/robot/pose')" in launch
    config = (PACKAGE_ROOT / 'config' / 'amcl_localization.yaml').read_text()
    assert 'global_frame_id: map' in config
    assert 'odom_frame_id: odom' in config
    assert 'base_frame_id: base_link' in config
    assert 'tf_broadcast: true' in config
    assert 'max_beams: 120' in config
    # M6到点快照需要静止时持续获得带ROS时间戳的公共全局位姿。
    assert 'update_min_d: 0.0' in config
    assert 'update_min_a: 0.0' in config
    assert 'z_hit: 0.95' in config


def test_m5_global_planning_uses_localization_and_planner_only():
    launch = (PACKAGE_ROOT / 'launch' / 'm5_global_planning.launch.py').read_text()
    assert "'m5_localization.launch.py'" in launch
    assert "package='nav2_planner'" in launch
    assert "executable='planner_server'" in launch
    assert "'node_names': ['planner_server']" in launch
    assert 'controller_server' not in launch
    assert 'bt_navigator' not in launch
    config = (PACKAGE_ROOT / 'config' / 'nav2_global_planning.yaml').read_text()
    assert 'nav2_navfn_planner/NavfnPlanner' in config
    assert 'nav2_costmap_2d::StaticLayer' in config
    assert 'nav2_costmap_2d::ObstacleLayer' in config
    assert 'global_frame: map' in config
    assert 'robot_base_frame: base_link' in config
    assert 'map_topic: /robot/map' in config
    assert 'topic: /robot/scan' in config
    assert 'inflation_radius: 0.55' in config


def test_m5_local_control_uses_public_action_and_safety_command_input():
    launch = (PACKAGE_ROOT / 'launch' / 'm5_local_control.launch.py').read_text()
    assert "'m5_global_planning.launch.py'" in launch
    assert "package='nav2_controller'" in launch
    assert "package='nav2_bt_navigator'" in launch
    assert "('cmd_vel', '/robot/cmd_vel')" in launch
    assert "executable='navigate_action_adapter.py'" in launch
    assert "parameters=[{'use_sim_time': True}]" in launch
    adapter = (PACKAGE_ROOT / 'scripts' / 'navigate_action_adapter.py').read_text()
    assert "'/robot/navigate_to_pose'" in adapter
    assert "'/robot/navigation/navigate_to_pose'" in adapter
    config = (PACKAGE_ROOT / 'config' / 'nav2_local_control.yaml').read_text()
    assert 'nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController' in config
    assert 'xy_goal_tolerance: 0.10' in config
    assert 'yaw_goal_tolerance: 0.10' in config
    assert 'global_frame: odom' in config
    assert 'topic: /robot/scan' in config
    tree = (PACKAGE_ROOT / 'config' / 'behavior_trees' / 'navigate_static.xml').read_text()
    assert '<ComputePathToPose' in tree
    assert '<FollowPath' in tree
    assert 'RateController' not in tree
    assert 'RecoveryNode' not in tree
    assert 'BackUp' not in tree


def test_m5_recovery_navigation_is_bounded_and_cancelable():
    launch = (PACKAGE_ROOT / 'launch' /
              'm5_recovery_navigation.launch.py').read_text()
    assert "package='nav2_behaviors'" in launch
    assert "'behavior_server'" in launch
    assert "('cmd_vel', '/robot/internal/nav_cmd_vel')" in launch
    assert "executable='nav_cmd_vel_keepalive.py'" in launch
    assert "'navigate_recovery.xml'" in launch
    assert "parameters=[{'use_sim_time': True}]" in launch
    adapter = (PACKAGE_ROOT / 'scripts' /
               'navigate_action_adapter.py').read_text()
    assert 'CancelResponse.ACCEPT' in adapter
    assert 'cancel_goal_async' in adapter
    tree = (PACKAGE_ROOT / 'config' / 'behavior_trees' /
            'navigate_recovery.xml').read_text()
    assert '<RateController hz="1.0">' in tree
    assert '<RecoveryNode' in tree
    assert '<ClearEntireCostmap' in tree
    assert '<Wait wait_duration="2.0"/>' in tree
    assert '<Spin spin_dist="1.0"/>' in tree
    assert '<BackUp' not in tree
    world = (PACKAGE_ROOT / 'worlds' / 'm5_slam.sdf').read_text()
    assert '<model name="temporary_obstacle">' in world


def test_m5_navigation_adapter_aborts_on_safety_input_timeouts():
    adapter = (PACKAGE_ROOT / 'scripts' /
               'navigate_action_adapter.py').read_text()
    assert "'/robot/diagnostics'" in adapter
    for code in ('scan_timeout', 'odom_timeout', 'imu_timeout'):
        assert code in adapter
    assert 'self.safety_aborted.add(key)' in adapter
    assert 'if safety_aborted:' in adapter
    assert 'public_handle.abort()' in adapter
    assert "'map', 'odom'" in adapter
    assert 'if age > 1.0:' in adapter
    supervisor = (PACKAGE_ROOT / 'scripts' / 'safety_supervisor.py').read_text()
    assert "Odometry, '/robot/odom'" in supervisor
    assert "'navigation_odometry', 'odom_timeout'" in supervisor


def test_m5_dynamic_obstacle_gui_check_owns_timing_and_geometry():
    script = (PACKAGE_ROOT.parents[2] / 'scripts' /
              'check_m5_dynamic_obstacle_gui.py').read_text()
    assert 'temporary_obstacle' in script
    assert "f'/world/{world}/set_pose'" in script
    assert 'movement-before-injection' in script
    assert 'obstacle-ahead' in script
    assert 'bypass-timeout' in script
    assert 'minimum-lateral-clearance' in script
    assert 'pass-margin' in script
    assert 'projection' in script
    assert 'lateral' in script
    assert 'if result.done()' in script
    assert 'if passed and cleared_side:' in script
    assert 'GoalStatus.STATUS_SUCCEEDED' in script
    assert 'set_obstacle_pose(args.world, *PARKED_POSE)' in script


def test_m5_w10_regression_assets_exist():
    root = PACKAGE_ROOT.parents[2]
    runner = (root / 'scripts' / 'run_m5_regression.py').read_text()
    wrapper = (root / 'scripts' / 'run_m5_regression.sh').read_text()
    qos = (root / 'config' / 'common' / 'm5_rosbag_qos.yaml').read_text()
    assert "check_m5_repeated_navigation.py', '--count', '5'" in runner
    assert 'check_m5_dynamic_obstacle_gui.py' in runner
    for fault in ('scan', 'imu', 'odom', 'localization'):
        assert fault in runner
    assert "'ros2', 'bag', 'record'" in runner
    assert "'ros2', 'bag', 'play'" in runner
    assert 'sha256' in runner
    assert 'run_m5_regression.py' in wrapper
    assert '/robot/map:' in qos
    assert 'durability: transient_local' in qos
