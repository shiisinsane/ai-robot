-- 业务问题：成功与失败任务经历了哪些阶段，各阶段近似停留多久？
-- 输入粒度：fact_task_event每事件一行，fact_task_execution每任务一行。
-- 过滤条件：正式自然运行有效任务；事件先按task_id和event_sequence排序。
-- 输出粒度：每任务×event_type一行，附任务终态和场景字段。
-- 限制：approx_dwell_sec将每条事件到下一条事件的间隔归给当前event_type，是事件采样下的
--       近似停留时间；终态事件记0秒。它不等同于Nav2内部规划器或控制器的真实执行时长。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
ordered_events AS (
    SELECT
        e.task_id,
        e.event_sequence,
        e.event_time_sim,
        e.event_type,
        e.phase_code,
        e.progress,
        e.error_code,
        LEAD(e.event_time_sim) OVER (
            PARTITION BY e.task_id ORDER BY e.event_sequence) AS next_event_time_sim
    FROM fact_task_event e
    JOIN cohort c USING (task_id)
),
event_intervals AS (
    SELECT
        *,
        CASE
            WHEN next_event_time_sim IS NULL THEN 0.0
            ELSE GREATEST(next_event_time_sim - event_time_sim, 0.0)
        END AS interval_to_next_event_sec,
        CASE
            WHEN next_event_time_sim IS NOT NULL AND next_event_time_sim < event_time_sim
            THEN 1 ELSE 0
        END AS negative_interval_flag
    FROM ordered_events
),
task_stage AS (
    SELECT
        task_id,
        event_type,
        MIN(event_sequence) AS first_event_sequence,
        MAX(event_sequence) AS last_event_sequence,
        MIN(event_time_sim) AS stage_first_time_sim,
        MAX(event_time_sim) AS stage_last_time_sim,
        COUNT(*) AS event_count,
        SUM(interval_to_next_event_sec) AS approx_dwell_sec,
        SUM(negative_interval_flag) AS negative_interval_count,
        MAX(progress) AS max_progress,
        MAX(error_code) FILTER (WHERE error_code IS NOT NULL) AS stage_error_code
    FROM event_intervals
    GROUP BY task_id, event_type
)
SELECT
    s.task_id,
    c.terminal_status,
    c.route_id,
    c.obstacle_profile,
    c.localization_perturbation_level,
    c.cycle_time_sec,
    s.event_type,
    s.first_event_sequence,
    s.last_event_sequence,
    s.stage_first_time_sim,
    s.stage_last_time_sim,
    s.event_count,
    s.approx_dwell_sec,
    s.negative_interval_count,
    s.max_progress,
    s.stage_error_code
FROM task_stage s
JOIN cohort c USING (task_id)
ORDER BY s.task_id, s.first_event_sequence, s.event_type;
