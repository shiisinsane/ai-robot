-- 业务问题：不同障碍档位的横向偏移和观测护栏是否发生变化？
-- 最小雷达距离不是footprint物理净距；未停车不等于安全认证通过。
WITH telemetry AS (
 SELECT task_id, MAX(ABS(pose_y_m)) max_abs_lateral_deviation_m, BOOL_OR(COALESCE(safety_stop_active,0)<>0) safety_stop,
  BOOL_OR(stale_sensor_mask<>0) stale_sensor,
  AVG((required_topics_present AND timestamp_valid)::INTEGER) coverage
 FROM fact_task_telemetry_1s GROUP BY task_id
), features AS (
 SELECT t.obstacle_profile,t.minimum_obstacle_distance_m,m.* EXCLUDE(task_id)
 FROM fact_task_execution t JOIN telemetry m USING(task_id)
 WHERE t.dataset_version='roa-validation-b1-v0.2' AND t.run_origin='natural' AND t.data_quality_valid=TRUE
)
SELECT CASE WHEN GROUPING(obstacle_profile)=1 THEN 'overall' ELSE obstacle_profile END obstacle_profile,
 COUNT(*) task_count, quantile_cont(max_abs_lateral_deviation_m,0.50) p50_max_abs_lateral_deviation_m,
 quantile_cont(max_abs_lateral_deviation_m,0.90) p90_max_abs_lateral_deviation_m,
 MIN(minimum_obstacle_distance_m) observed_minimum_obstacle_distance_m,
 AVG(safety_stop::INTEGER) safety_stop_task_rate, AVG(stale_sensor::INTEGER) stale_sensor_task_rate,
 AVG(coverage) valid_telemetry_coverage_rate
FROM features GROUP BY GROUPING SETS ((),(obstacle_profile))
ORDER BY CASE obstacle_profile WHEN 'overall' THEN 0 WHEN 'none' THEN 1 WHEN 'low' THEN 2 ELSE 3 END;
