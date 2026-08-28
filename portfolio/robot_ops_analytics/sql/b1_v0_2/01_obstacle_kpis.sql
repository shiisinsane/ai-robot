-- 业务问题：固定4米路线下，不同障碍档位的完成能力和周期分布如何？
-- 输入粒度：fact_task_execution每任务一行；输出overall及每档一行。
WITH cohort AS (
 SELECT obstacle_profile, terminal_status, cycle_time_sec FROM fact_task_execution
 WHERE dataset_version='roa-validation-b1-v0.2' AND run_origin='natural' AND data_quality_valid=TRUE
)
SELECT CASE WHEN GROUPING(obstacle_profile)=1 THEN 'overall' ELSE obstacle_profile END obstacle_profile,
 COUNT(*) task_count, COUNT(*) FILTER (WHERE terminal_status='success') success_count,
 COUNT(*) FILTER (WHERE terminal_status<>'success') failure_count,
 COUNT(*) FILTER (WHERE terminal_status='success')::DOUBLE/COUNT(*) completion_rate,
 COUNT(*) FILTER (WHERE terminal_status<>'success')::DOUBLE/COUNT(*) failure_rate,
 AVG(cycle_time_sec) mean_cycle_time_sec, quantile_cont(cycle_time_sec,0.50) p50_cycle_time_sec,
 quantile_cont(cycle_time_sec,0.90) p90_cycle_time_sec, quantile_cont(cycle_time_sec,0.95) p95_cycle_time_sec
FROM cohort GROUP BY GROUPING SETS ((),(obstacle_profile))
ORDER BY CASE obstacle_profile WHEN 'overall' THEN 0 WHEN 'none' THEN 1 WHEN 'low' THEN 2 ELSE 3 END;
