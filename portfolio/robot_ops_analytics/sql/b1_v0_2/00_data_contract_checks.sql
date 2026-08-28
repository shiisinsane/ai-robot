-- 业务问题：B1冻结队列是否满足正式SQL分析的数据契约？
-- 输入粒度：任务、事件、整秒遥测三张事实表。
-- 输出粒度：单行门禁；quality_gate_passed=TRUE后才可运行后续查询。
WITH cohort AS (
 SELECT * FROM fact_task_execution WHERE dataset_version='roa-validation-b1-v0.2' AND run_origin='natural' AND data_quality_valid=TRUE
), task_checks AS (
 SELECT COUNT(*) task_count, COUNT(DISTINCT task_id) distinct_task_count,
  COUNT(*) FILTER (WHERE obstacle_profile='none') none_count,
  COUNT(*) FILTER (WHERE obstacle_profile='low') low_count,
  COUNT(*) FILTER (WHERE obstacle_profile='medium') medium_count,
  COUNT(*) FILTER (WHERE terminal_status<>'success') failure_count,
  SUM(telemetry_bucket_count) declared_telemetry_count FROM cohort
), event_checks AS (
 SELECT COUNT(*) event_count, COUNT(DISTINCT e.task_id) covered_tasks,
  COUNT(*) FILTER (WHERE t.task_id IS NULL) orphan_rows FROM fact_task_event e LEFT JOIN cohort t USING(task_id)
), telemetry_checks AS (
 SELECT COUNT(*) telemetry_count, COUNT(DISTINCT m.task_id) covered_tasks,
  COUNT(*) FILTER (WHERE t.task_id IS NULL) orphan_rows,
  COUNT(*) FILTER (WHERE NOT required_topics_present OR NOT timestamp_valid) invalid_rows
 FROM fact_task_telemetry_1s m LEFT JOIN cohort t USING(task_id)
), versions AS (
 SELECT COUNT(DISTINCT dataset_version) version_count,
  COUNT(*) FILTER (WHERE dataset_version<>'roa-validation-b1-v0.2') foreign_tasks FROM fact_task_execution
)
SELECT t.*, e.event_count, m.telemetry_count, e.covered_tasks event_covered_tasks,
 m.covered_tasks telemetry_covered_tasks, e.orphan_rows orphan_event_rows,
 m.orphan_rows orphan_telemetry_rows, m.invalid_rows invalid_telemetry_rows, v.foreign_tasks,
 (t.task_count=45 AND t.distinct_task_count=45 AND t.none_count=15 AND t.low_count=15
  AND t.medium_count=15 AND t.failure_count=0 AND e.event_count=9725 AND m.telemetry_count=1759
  AND e.covered_tasks=45 AND m.covered_tasks=45 AND t.declared_telemetry_count=m.telemetry_count
  AND e.orphan_rows=0 AND m.orphan_rows=0 AND m.invalid_rows=0
  AND v.version_count=1 AND v.foreign_tasks=0) quality_gate_passed
FROM task_checks t CROSS JOIN event_checks e CROSS JOIN telemetry_checks m CROSS JOIN versions v;
