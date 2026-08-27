-- 业务问题：成功与失败任务在接受后早期及终态前窗口中的遥测是否存在差异？
-- 输入粒度：fact_task_telemetry_1s每任务每仿真秒一行，任务事实每任务一行。
-- 过滤条件：正式自然运行有效任务；窗口固定为接受后前3秒和终态前3秒。
-- 输出粒度：每任务一行，遥测在连接任务事实前完成条件聚合。
-- 限制：窗口按遥测桶与时间区间是否相交选择；周期小于6秒时两个窗口可能重叠并显式标记。
--       结果只用于形成候选预警特征，不证明遥测差异导致导航失败。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        accepted_at_sim,
        terminal_at_sim,
        cycle_time_sec,
        telemetry_bucket_count AS declared_telemetry_bucket_count,
        valid_telemetry_bucket_count AS declared_valid_telemetry_bucket_count
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
windowed AS (
    SELECT
        m.*,
        c.accepted_at_sim,
        c.terminal_at_sim,
        m.bucket_start_sim < c.accepted_at_sim + 3.0
            AND m.bucket_end_sim > c.accepted_at_sim AS in_early_window,
        m.bucket_start_sim < c.terminal_at_sim
            AND m.bucket_end_sim > c.terminal_at_sim - 3.0 AS in_preterminal_window
    FROM fact_task_telemetry_1s m
    JOIN cohort c USING (task_id)
),
task_telemetry AS (
    SELECT
        task_id,
        COUNT(*) AS telemetry_bucket_count,
        COUNT(*) FILTER (
            WHERE required_topics_present = TRUE AND timestamp_valid = TRUE
        ) AS valid_telemetry_bucket_count,
        COUNT(*) FILTER (WHERE in_early_window) AS early_bucket_count,
        COUNT(*) FILTER (
            WHERE in_early_window
              AND required_topics_present = TRUE AND timestamp_valid = TRUE
        ) AS early_valid_bucket_count,
        AVG(ABS(mean_linear_speed_mps)) FILTER (WHERE in_early_window)
            AS early_mean_abs_linear_speed_mps,
        MAX(max_abs_linear_speed_mps) FILTER (WHERE in_early_window)
            AS early_max_abs_linear_speed_mps,
        MIN(minimum_valid_scan_range_m) FILTER (WHERE in_early_window)
            AS early_minimum_scan_range_m,
        COUNT(*) FILTER (WHERE in_early_window AND safety_stop_active = TRUE)
            AS early_safety_stop_bucket_count,
        COUNT(*) FILTER (WHERE in_early_window AND stale_sensor_mask <> 0)
            AS early_stale_sensor_bucket_count,
        COUNT(*) FILTER (WHERE in_preterminal_window) AS preterminal_bucket_count,
        COUNT(*) FILTER (
            WHERE in_preterminal_window
              AND required_topics_present = TRUE AND timestamp_valid = TRUE
        ) AS preterminal_valid_bucket_count,
        AVG(ABS(mean_linear_speed_mps)) FILTER (WHERE in_preterminal_window)
            AS preterminal_mean_abs_linear_speed_mps,
        MAX(max_abs_linear_speed_mps) FILTER (WHERE in_preterminal_window)
            AS preterminal_max_abs_linear_speed_mps,
        MIN(minimum_valid_scan_range_m) FILTER (WHERE in_preterminal_window)
            AS preterminal_minimum_scan_range_m,
        COUNT(*) FILTER (WHERE in_preterminal_window AND safety_stop_active = TRUE)
            AS preterminal_safety_stop_bucket_count,
        COUNT(*) FILTER (WHERE in_preterminal_window AND stale_sensor_mask <> 0)
            AS preterminal_stale_sensor_bucket_count,
        COUNT(*) FILTER (WHERE in_early_window AND in_preterminal_window)
            AS overlapping_window_bucket_count
    FROM windowed
    GROUP BY task_id
)
SELECT
    c.task_id,
    c.terminal_status,
    c.route_id,
    c.obstacle_profile,
    c.localization_perturbation_level,
    c.cycle_time_sec,
    c.declared_telemetry_bucket_count,
    c.declared_valid_telemetry_bucket_count,
    COALESCE(t.telemetry_bucket_count, 0) AS telemetry_bucket_count,
    COALESCE(t.valid_telemetry_bucket_count, 0) AS valid_telemetry_bucket_count,
    COALESCE(t.valid_telemetry_bucket_count, 0)::DOUBLE
        / NULLIF(COALESCE(t.telemetry_bucket_count, 0), 0) AS valid_telemetry_coverage_rate,
    COALESCE(t.early_bucket_count, 0) AS early_bucket_count,
    COALESCE(t.early_valid_bucket_count, 0) AS early_valid_bucket_count,
    t.early_mean_abs_linear_speed_mps,
    t.early_max_abs_linear_speed_mps,
    t.early_minimum_scan_range_m,
    COALESCE(t.early_safety_stop_bucket_count, 0) AS early_safety_stop_bucket_count,
    COALESCE(t.early_stale_sensor_bucket_count, 0) AS early_stale_sensor_bucket_count,
    COALESCE(t.preterminal_bucket_count, 0) AS preterminal_bucket_count,
    COALESCE(t.preterminal_valid_bucket_count, 0) AS preterminal_valid_bucket_count,
    t.preterminal_mean_abs_linear_speed_mps,
    t.preterminal_max_abs_linear_speed_mps,
    t.preterminal_minimum_scan_range_m,
    COALESCE(t.preterminal_safety_stop_bucket_count, 0)
        AS preterminal_safety_stop_bucket_count,
    COALESCE(t.preterminal_stale_sensor_bucket_count, 0)
        AS preterminal_stale_sensor_bucket_count,
    COALESCE(t.overlapping_window_bucket_count, 0) AS overlapping_window_bucket_count,
    c.cycle_time_sec < 6.0 AS windows_may_overlap
FROM cohort c
LEFT JOIN task_telemetry t USING (task_id)
ORDER BY c.task_id;
