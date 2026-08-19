-- ROA 分析仓库 DDL v1.0
-- 目标引擎：DuckDB；当前保持 SQLite 兼容，便于无 DuckDB 环境进行结构验证。

PRAGMA foreign_keys = ON;

CREATE TABLE dim_robot (
    robot_id TEXT PRIMARY KEY,
    robot_name TEXT NOT NULL,
    platform_type TEXT NOT NULL DEFAULT 'differential_drive_sim',
    simulation_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (simulation_only IN (FALSE, TRUE)),
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE dim_scenario (
    scenario_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    map_id TEXT NOT NULL,
    start_region TEXT NOT NULL,
    target_region TEXT NOT NULL,
    route_class TEXT NOT NULL,
    obstacle_difficulty TEXT NOT NULL CHECK (obstacle_difficulty IN ('none', 'low', 'medium', 'high')),
    localization_perturbation_level TEXT NOT NULL CHECK (
        localization_perturbation_level IN ('none', 'low', 'medium', 'high')
    ),
    scenario_version TEXT NOT NULL,
    description TEXT
);

CREATE TABLE dim_route (
    route_id TEXT PRIMARY KEY,
    map_id TEXT NOT NULL,
    route_name TEXT NOT NULL,
    start_x_m DOUBLE NOT NULL,
    start_y_m DOUBLE NOT NULL,
    start_yaw_rad DOUBLE NOT NULL,
    target_x_m DOUBLE NOT NULL,
    target_y_m DOUBLE NOT NULL,
    target_yaw_rad DOUBLE NOT NULL,
    reference_path_length_m DOUBLE CHECK (reference_path_length_m IS NULL OR reference_path_length_m >= 0),
    turn_count INTEGER CHECK (turn_count IS NULL OR turn_count >= 0),
    route_version TEXT NOT NULL
);

CREATE TABLE dim_parameter_version (
    parameter_version TEXT PRIMARY KEY,
    navigation_config_path TEXT NOT NULL,
    navigation_config_sha256 TEXT NOT NULL,
    task_contract_version TEXT NOT NULL,
    interface_version TEXT NOT NULL,
    maximum_linear_velocity_mps DOUBLE NOT NULL CHECK (maximum_linear_velocity_mps > 0),
    maximum_angular_velocity_rps DOUBLE NOT NULL CHECK (maximum_angular_velocity_rps > 0),
    sensor_freshness_threshold_sec DOUBLE NOT NULL CHECK (sensor_freshness_threshold_sec > 0),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE dim_error_code (
    error_code INTEGER PRIMARY KEY,
    error_name TEXT NOT NULL UNIQUE,
    error_category TEXT NOT NULL,
    failure_stage TEXT CHECK (
        failure_stage IS NULL OR failure_stage IN (
            'localization', 'planning', 'control', 'perception', 'safety', 'unknown'
        )
    ),
    analytical_terminal_status TEXT NOT NULL CHECK (
        analytical_terminal_status IN ('success', 'failed', 'canceled', 'timeout', 'rejected')
    ),
    description TEXT NOT NULL
);

CREATE TABLE dim_experiment (
    experiment_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    metrics_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    git_commit TEXT NOT NULL,
    git_dirty BOOLEAN NOT NULL CHECK (git_dirty IN (FALSE, TRUE)),
    ros_domain_id INTEGER NOT NULL CHECK (ros_domain_id BETWEEN 0 AND 232),
    gazebo_partition TEXT NOT NULL,
    run_origin TEXT NOT NULL CHECK (run_origin IN ('natural', 'fault_injection')),
    fault_injection_type TEXT,
    started_at_sim DOUBLE NOT NULL,
    ended_at_sim DOUBLE NOT NULL,
    started_at_wall TIMESTAMP NOT NULL,
    ended_at_wall TIMESTAMP NOT NULL,
    experiment_valid BOOLEAN NOT NULL CHECK (experiment_valid IN (FALSE, TRUE)),
    invalid_reason TEXT,
    configuration_uri TEXT NOT NULL,
    evidence_manifest_uri TEXT NOT NULL,
    CHECK (ended_at_sim >= started_at_sim),
    CHECK (ended_at_wall >= started_at_wall),
    CHECK (
        (run_origin = 'natural' AND fault_injection_type IS NULL)
        OR (run_origin = 'fault_injection' AND fault_injection_type IS NOT NULL)
    ),
    CHECK (
        (experiment_valid = TRUE AND invalid_reason IS NULL)
        OR (experiment_valid = FALSE AND invalid_reason IS NOT NULL)
    )
);

CREATE TABLE fact_robot_operation_window (
    operation_window_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES dim_experiment(experiment_id),
    robot_id TEXT NOT NULL REFERENCES dim_robot(robot_id),
    window_start_sim DOUBLE NOT NULL,
    window_end_sim DOUBLE NOT NULL,
    ready_state_valid BOOLEAN NOT NULL CHECK (ready_state_valid IN (FALSE, TRUE)),
    clock_advanced_normally BOOLEAN NOT NULL CHECK (clock_advanced_normally IN (FALSE, TRUE)),
    exclusion_reason TEXT,
    CHECK (window_end_sim > window_start_sim),
    UNIQUE (experiment_id, robot_id, window_start_sim)
);

CREATE TABLE fact_task_execution (
    task_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    parent_task_id TEXT REFERENCES fact_task_execution(task_id),
    experiment_id TEXT NOT NULL REFERENCES dim_experiment(experiment_id),
    robot_id TEXT NOT NULL REFERENCES dim_robot(robot_id),
    scenario_id TEXT NOT NULL REFERENCES dim_scenario(scenario_id),
    route_id TEXT NOT NULL REFERENCES dim_route(route_id),
    parameter_version TEXT NOT NULL REFERENCES dim_parameter_version(parameter_version),
    task_type INTEGER NOT NULL,
    sensing_mode INTEGER NOT NULL,
    task_timeout_sec DOUBLE NOT NULL CHECK (task_timeout_sec > 0),
    target_frame TEXT NOT NULL,
    target_x_m DOUBLE NOT NULL,
    target_y_m DOUBLE NOT NULL,
    target_yaw_rad DOUBLE NOT NULL,
    requested_at_sim DOUBLE NOT NULL,
    accepted_at_sim DOUBLE,
    terminal_at_sim DOUBLE,
    accepted BOOLEAN NOT NULL CHECK (accepted IN (FALSE, TRUE)),
    rejection_reason TEXT,
    terminal_status TEXT CHECK (
        terminal_status IS NULL OR terminal_status IN ('success', 'failed', 'canceled', 'timeout', 'rejected')
    ),
    error_code INTEGER REFERENCES dim_error_code(error_code),
    failure_stage TEXT CHECK (
        failure_stage IS NULL OR failure_stage IN (
            'localization', 'planning', 'control', 'perception', 'safety', 'unknown'
        )
    ),
    cancel_origin TEXT CHECK (
        cancel_origin IS NULL OR cancel_origin IN ('user', 'policy', 'operator_simulated', 'system')
    ),
    effective_task BOOLEAN NOT NULL CHECK (effective_task IN (FALSE, TRUE)),
    data_quality_valid BOOLEAN NOT NULL CHECK (data_quality_valid IN (FALSE, TRUE)),
    cycle_time_sec DOUBLE CHECK (cycle_time_sec IS NULL OR cycle_time_sec >= 0),
    planned_path_length_m DOUBLE CHECK (planned_path_length_m IS NULL OR planned_path_length_m >= 0),
    actual_path_length_m DOUBLE CHECK (actual_path_length_m IS NULL OR actual_path_length_m >= 0),
    final_x_m DOUBLE,
    final_y_m DOUBLE,
    final_yaw_rad DOUBLE,
    position_error_m DOUBLE CHECK (position_error_m IS NULL OR position_error_m >= 0),
    heading_error_rad DOUBLE CHECK (heading_error_rad IS NULL OR heading_error_rad >= 0),
    recovery_count INTEGER NOT NULL DEFAULT 0 CHECK (recovery_count >= 0),
    replan_count INTEGER NOT NULL DEFAULT 0 CHECK (replan_count >= 0),
    simulated_intervention BOOLEAN NOT NULL DEFAULT FALSE CHECK (simulated_intervention IN (FALSE, TRUE)),
    intervention_type TEXT,
    safety_stop_count INTEGER NOT NULL DEFAULT 0 CHECK (safety_stop_count >= 0),
    safety_reason TEXT,
    stale_sensor_event_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_sensor_event_count >= 0),
    max_abs_linear_speed_mps DOUBLE CHECK (max_abs_linear_speed_mps IS NULL OR max_abs_linear_speed_mps >= 0),
    minimum_obstacle_distance_m DOUBLE CHECK (
        minimum_obstacle_distance_m IS NULL OR minimum_obstacle_distance_m >= 0
    ),
    telemetry_expected_bucket_count INTEGER NOT NULL DEFAULT 0 CHECK (telemetry_expected_bucket_count >= 0),
    telemetry_valid_bucket_count INTEGER NOT NULL DEFAULT 0 CHECK (telemetry_valid_bucket_count >= 0),
    scan_snapshot_available BOOLEAN CHECK (scan_snapshot_available IN (FALSE, TRUE)),
    image_snapshot_available BOOLEAN CHECK (image_snapshot_available IN (FALSE, TRUE)),
    pose_snapshot_available BOOLEAN CHECK (pose_snapshot_available IN (FALSE, TRUE)),
    result_message TEXT,
    CHECK (terminal_at_sim IS NULL OR accepted_at_sim IS NULL OR terminal_at_sim >= accepted_at_sim),
    CHECK (telemetry_valid_bucket_count <= telemetry_expected_bucket_count),
    CHECK (
        (accepted = FALSE AND terminal_status = 'rejected' AND rejection_reason IS NOT NULL)
        OR (accepted = TRUE AND terminal_status IS NOT NULL AND terminal_status <> 'rejected')
    )
);

CREATE TABLE fact_task_event (
    task_event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES fact_task_execution(task_id),
    event_sequence INTEGER NOT NULL CHECK (event_sequence >= 1),
    event_time_sim DOUBLE NOT NULL,
    event_time_wall TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'requested', 'accepted', 'rejected', 'validating', 'navigating', 'sensing',
            'canceling', 'succeeded', 'failed', 'canceled', 'timeout', 'recovery_started',
            'recovery_finished', 'replan', 'safety_stop_started', 'safety_stop_cleared',
            'simulated_intervention'
        )
    ),
    phase_code INTEGER,
    progress DOUBLE CHECK (progress IS NULL OR (progress >= 0 AND progress <= 1)),
    error_code INTEGER REFERENCES dim_error_code(error_code),
    message TEXT,
    source_topic TEXT NOT NULL,
    UNIQUE (task_id, event_sequence)
);

CREATE TABLE fact_task_telemetry_1s (
    task_id TEXT NOT NULL REFERENCES fact_task_execution(task_id),
    bucket_start_sim DOUBLE NOT NULL,
    bucket_end_sim DOUBLE NOT NULL,
    sample_count_odom INTEGER NOT NULL DEFAULT 0 CHECK (sample_count_odom >= 0),
    sample_count_pose INTEGER NOT NULL DEFAULT 0 CHECK (sample_count_pose >= 0),
    sample_count_scan INTEGER NOT NULL DEFAULT 0 CHECK (sample_count_scan >= 0),
    sample_count_safety INTEGER NOT NULL DEFAULT 0 CHECK (sample_count_safety >= 0),
    required_topics_present BOOLEAN NOT NULL CHECK (required_topics_present IN (FALSE, TRUE)),
    timestamp_valid BOOLEAN NOT NULL CHECK (timestamp_valid IN (FALSE, TRUE)),
    pose_x_m DOUBLE,
    pose_y_m DOUBLE,
    pose_yaw_rad DOUBLE,
    pose_covariance_x DOUBLE CHECK (pose_covariance_x IS NULL OR pose_covariance_x >= 0),
    pose_covariance_y DOUBLE CHECK (pose_covariance_y IS NULL OR pose_covariance_y >= 0),
    pose_covariance_yaw DOUBLE CHECK (pose_covariance_yaw IS NULL OR pose_covariance_yaw >= 0),
    mean_linear_speed_mps DOUBLE,
    max_abs_linear_speed_mps DOUBLE CHECK (max_abs_linear_speed_mps IS NULL OR max_abs_linear_speed_mps >= 0),
    mean_angular_speed_rps DOUBLE,
    max_abs_angular_speed_rps DOUBLE CHECK (max_abs_angular_speed_rps IS NULL OR max_abs_angular_speed_rps >= 0),
    minimum_valid_scan_range_m DOUBLE CHECK (
        minimum_valid_scan_range_m IS NULL OR minimum_valid_scan_range_m >= 0
    ),
    safety_stop_active BOOLEAN CHECK (safety_stop_active IN (FALSE, TRUE)),
    stale_sensor_mask INTEGER NOT NULL DEFAULT 0 CHECK (stale_sensor_mask >= 0),
    PRIMARY KEY (task_id, bucket_start_sim),
    CHECK (bucket_end_sim > bucket_start_sim)
);

CREATE INDEX idx_task_experiment ON fact_task_execution(experiment_id);
CREATE INDEX idx_task_scenario ON fact_task_execution(scenario_id);
CREATE INDEX idx_task_status ON fact_task_execution(terminal_status);
CREATE INDEX idx_event_task_time ON fact_task_event(task_id, event_time_sim);
CREATE INDEX idx_telemetry_task_time ON fact_task_telemetry_1s(task_id, bucket_start_sim);
CREATE INDEX idx_window_experiment_robot ON fact_robot_operation_window(experiment_id, robot_id);

