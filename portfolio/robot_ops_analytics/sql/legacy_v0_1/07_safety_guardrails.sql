-- 业务问题：任务效率与失败分析是否伴随安全停车、传感器过期、覆盖不足或障碍距离恶化？
-- 输入粒度：遥测每任务每仿真秒一行，任务事实每任务一行。
-- 过滤条件：正式自然运行有效任务；遥测先聚合到每任务一行再与任务事实连接。
-- 输出粒度：整体、终态、障碍档位和路线×障碍场景；不同dimension_type不得相加。
-- 限制：当前未冻结最小安全距离验收阈值，因此只报告距离分布和观察到的停车事件，
--       不以“未停车”替代安全通过，也不将场景差异解释为因果关系。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        route_id,
        obstacle_profile,
        telemetry_bucket_count AS declared_telemetry_bucket_count,
        valid_telemetry_bucket_count AS declared_valid_telemetry_bucket_count
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
telemetry_per_task AS (
    SELECT
        m.task_id,
        COUNT(*) AS observed_telemetry_bucket_count,
        COUNT(*) FILTER (
            WHERE m.required_topics_present = TRUE AND m.timestamp_valid = TRUE
        ) AS valid_telemetry_bucket_count,
        COUNT(*) FILTER (WHERE m.safety_stop_active = TRUE) AS safety_stop_bucket_count,
        COUNT(*) FILTER (WHERE m.stale_sensor_mask <> 0) AS stale_sensor_bucket_count,
        MIN(m.minimum_valid_scan_range_m) AS minimum_obstacle_distance_m
    FROM fact_task_telemetry_1s m
    JOIN cohort c USING (task_id)
    GROUP BY m.task_id
),
task_guardrails AS (
    SELECT
        c.task_id,
        c.terminal_status,
        c.route_id,
        c.obstacle_profile,
        c.declared_telemetry_bucket_count,
        c.declared_valid_telemetry_bucket_count,
        COALESCE(t.observed_telemetry_bucket_count, 0) AS observed_telemetry_bucket_count,
        COALESCE(t.valid_telemetry_bucket_count, 0) AS valid_telemetry_bucket_count,
        COALESCE(t.safety_stop_bucket_count, 0) AS safety_stop_bucket_count,
        COALESCE(t.stale_sensor_bucket_count, 0) AS stale_sensor_bucket_count,
        t.minimum_obstacle_distance_m
    FROM cohort c
    LEFT JOIN telemetry_per_task t USING (task_id)
),
grouped AS (
    SELECT 'overall' AS dimension_type, 'overall' AS dimension_value,
           task_id, terminal_status, route_id, obstacle_profile,
           declared_telemetry_bucket_count, declared_valid_telemetry_bucket_count,
           observed_telemetry_bucket_count, valid_telemetry_bucket_count,
           safety_stop_bucket_count, stale_sensor_bucket_count,
           minimum_obstacle_distance_m
    FROM task_guardrails
    UNION ALL
    SELECT 'terminal_status', terminal_status,
           task_id, terminal_status, route_id, obstacle_profile,
           declared_telemetry_bucket_count, declared_valid_telemetry_bucket_count,
           observed_telemetry_bucket_count, valid_telemetry_bucket_count,
           safety_stop_bucket_count, stale_sensor_bucket_count,
           minimum_obstacle_distance_m
    FROM task_guardrails
    UNION ALL
    SELECT 'obstacle_profile', obstacle_profile,
           task_id, terminal_status, route_id, obstacle_profile,
           declared_telemetry_bucket_count, declared_valid_telemetry_bucket_count,
           observed_telemetry_bucket_count, valid_telemetry_bucket_count,
           safety_stop_bucket_count, stale_sensor_bucket_count,
           minimum_obstacle_distance_m
    FROM task_guardrails
    UNION ALL
    SELECT 'route_obstacle', route_id || ' × ' || obstacle_profile,
           task_id, terminal_status, route_id, obstacle_profile,
           declared_telemetry_bucket_count, declared_valid_telemetry_bucket_count,
           observed_telemetry_bucket_count, valid_telemetry_bucket_count,
           safety_stop_bucket_count, stale_sensor_bucket_count,
           minimum_obstacle_distance_m
    FROM task_guardrails
)
SELECT
    dimension_type,
    dimension_value,
    COUNT(*) AS task_count,
    COUNT(*) FILTER (WHERE terminal_status = 'success') AS success_count,
    COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
    COUNT(*) FILTER (WHERE safety_stop_bucket_count > 0) AS safety_stop_task_count,
    COUNT(*) FILTER (WHERE safety_stop_bucket_count > 0)::DOUBLE
        / NULLIF(COUNT(*), 0) AS safety_stop_task_rate,
    COUNT(*) FILTER (WHERE stale_sensor_bucket_count > 0) AS stale_sensor_task_count,
    COUNT(*) FILTER (WHERE stale_sensor_bucket_count > 0)::DOUBLE
        / NULLIF(COUNT(*), 0) AS stale_sensor_task_rate,
    SUM(valid_telemetry_bucket_count)::DOUBLE
        / NULLIF(SUM(observed_telemetry_bucket_count), 0)
        AS valid_telemetry_coverage_rate,
    SUM(observed_telemetry_bucket_count) AS observed_telemetry_bucket_count,
    SUM(declared_telemetry_bucket_count) AS declared_telemetry_bucket_count,
    MIN(minimum_obstacle_distance_m) AS minimum_obstacle_distance_m,
    quantile_cont(minimum_obstacle_distance_m, 0.05) AS p05_minimum_obstacle_distance_m,
    quantile_cont(minimum_obstacle_distance_m, 0.50) AS p50_minimum_obstacle_distance_m,
    CASE WHEN COUNT(*) < 10 THEN 'small_sample' ELSE 'adequate_for_exploration' END
        AS sample_size_flag
FROM grouped
GROUP BY dimension_type, dimension_value
ORDER BY
    CASE dimension_type
        WHEN 'overall' THEN 0 WHEN 'terminal_status' THEN 1
        WHEN 'obstacle_profile' THEN 2 ELSE 3
    END,
    dimension_value;
