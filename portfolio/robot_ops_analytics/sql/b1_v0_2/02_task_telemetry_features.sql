-- 业务问题：每项任务的绕行、安全停车、传感器时效与遥测覆盖情况如何？
-- 遥测先聚合为每任务一行；ABS(pose_y_m)只适用于B1固定y=0路线。
WITH telemetry AS (
 SELECT task_id, MAX(ABS(pose_y_m)) max_abs_lateral_deviation_m,
  BOOL_OR(COALESCE(safety_stop_active,0)<>0) safety_stop,
  BOOL_OR(stale_sensor_mask<>0) stale_sensor,
  AVG((required_topics_present AND timestamp_valid)::INTEGER) valid_telemetry_coverage_rate,
  COUNT(*) observed_telemetry_bucket_count FROM fact_task_telemetry_1s GROUP BY task_id
), cohort AS (
 SELECT task_id, obstacle_profile, cycle_time_sec, minimum_obstacle_distance_m, telemetry_bucket_count
 FROM fact_task_execution WHERE dataset_version='roa-validation-b1-v0.2' AND run_origin='natural' AND data_quality_valid=TRUE
)
SELECT c.*, t.max_abs_lateral_deviation_m, t.safety_stop, t.stale_sensor,
 t.valid_telemetry_coverage_rate, t.observed_telemetry_bucket_count
FROM cohort c LEFT JOIN telemetry t USING(task_id) ORDER BY task_id;
