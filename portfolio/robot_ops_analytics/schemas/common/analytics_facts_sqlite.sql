-- W5 SQLite分析事实层v1.0；只承载当前原始记录可证明的字段。

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS fact_etl_checkpoint (
    pipeline_name TEXT PRIMARY KEY,
    last_raw_record_id INTEGER NOT NULL CHECK (last_raw_record_id >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_task_execution (
    task_id TEXT PRIMARY KEY,
    dataset_version TEXT NOT NULL,
    source_batch_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    route_id TEXT NOT NULL,
    environment_profile TEXT NOT NULL,
    obstacle_profile TEXT NOT NULL,
    localization_perturbation_level TEXT NOT NULL,
    parameter_version TEXT NOT NULL,
    run_origin TEXT NOT NULL,
    fault_injection_type TEXT,
    timeout_sec DOUBLE NOT NULL CHECK (timeout_sec > 0),
    start_x_m DOUBLE NOT NULL,
    start_y_m DOUBLE NOT NULL,
    start_yaw_rad DOUBLE NOT NULL,
    target_x_m DOUBLE NOT NULL,
    target_y_m DOUBLE NOT NULL,
    target_yaw_rad DOUBLE NOT NULL,
    requested_at_sim DOUBLE NOT NULL,
    accepted_at_sim DOUBLE NOT NULL,
    terminal_at_sim DOUBLE NOT NULL,
    started_at_wall TEXT NOT NULL,
    finished_at_wall TEXT NOT NULL,
    accepted BOOLEAN NOT NULL CHECK (accepted IN (0, 1)),
    terminal_status TEXT NOT NULL CHECK (terminal_status IN ('success', 'failed', 'canceled', 'timeout')),
    success BOOLEAN NOT NULL CHECK (success IN (0, 1)),
    error_code INTEGER NOT NULL,
    result_message TEXT,
    cycle_time_sec DOUBLE NOT NULL CHECK (cycle_time_sec >= 0),
    telemetry_bucket_count INTEGER NOT NULL CHECK (telemetry_bucket_count >= 0),
    valid_telemetry_bucket_count INTEGER NOT NULL CHECK (valid_telemetry_bucket_count >= 0),
    max_abs_linear_speed_mps DOUBLE,
    minimum_obstacle_distance_m DOUBLE,
    data_quality_valid BOOLEAN NOT NULL CHECK (data_quality_valid IN (0, 1)),
    max_source_raw_record_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_task_event (
    source_raw_record_id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES fact_task_execution(task_id) ON DELETE CASCADE,
    event_sequence INTEGER NOT NULL CHECK (event_sequence >= 1),
    event_time_sim DOUBLE NOT NULL,
    event_type TEXT NOT NULL,
    phase_code INTEGER,
    progress DOUBLE,
    error_code INTEGER,
    message TEXT,
    request_id TEXT NOT NULL,
    UNIQUE (task_id, event_sequence)
);

CREATE TABLE IF NOT EXISTS fact_task_telemetry_1s (
    source_raw_record_id INTEGER NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES fact_task_execution(task_id) ON DELETE CASCADE,
    bucket_start_sim DOUBLE NOT NULL,
    bucket_end_sim DOUBLE NOT NULL,
    sample_count_odom INTEGER NOT NULL,
    sample_count_pose INTEGER NOT NULL,
    sample_count_scan INTEGER NOT NULL,
    sample_count_safety INTEGER NOT NULL,
    required_topics_present BOOLEAN NOT NULL CHECK (required_topics_present IN (0, 1)),
    timestamp_valid BOOLEAN NOT NULL CHECK (timestamp_valid IN (0, 1)),
    pose_x_m DOUBLE,
    pose_y_m DOUBLE,
    pose_yaw_rad DOUBLE,
    pose_covariance_x DOUBLE,
    pose_covariance_y DOUBLE,
    pose_covariance_yaw DOUBLE,
    mean_linear_speed_mps DOUBLE,
    max_abs_linear_speed_mps DOUBLE,
    mean_angular_speed_rps DOUBLE,
    max_abs_angular_speed_rps DOUBLE,
    minimum_valid_scan_range_m DOUBLE,
    safety_stop_active BOOLEAN,
    stale_sensor_mask INTEGER NOT NULL,
    PRIMARY KEY (task_id, bucket_start_sim)
);

CREATE INDEX IF NOT EXISTS idx_fact_task_status ON fact_task_execution(terminal_status);
CREATE INDEX IF NOT EXISTS idx_fact_task_route ON fact_task_execution(route_id);
CREATE INDEX IF NOT EXISTS idx_fact_event_task_time ON fact_task_event(task_id, event_time_sim);
CREATE INDEX IF NOT EXISTS idx_fact_telemetry_task_time ON fact_task_telemetry_1s(task_id, bucket_start_sim);
