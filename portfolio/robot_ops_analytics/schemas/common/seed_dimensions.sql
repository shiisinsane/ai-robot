-- 来自 config/common/m6_task_contract.yaml 的错误码分析维度种子。
INSERT INTO dim_error_code VALUES
    (0,   'none',                   'success',    NULL,         'success',  '任务成功'),
    (100, 'invalid_task_id',        'validation', 'unknown',    'rejected', '任务标识非法'),
    (101, 'unsupported_task',       'validation', 'unknown',    'rejected', '任务类型不受支持'),
    (102, 'invalid_target',         'validation', 'planning',   'rejected', '目标非法'),
    (103, 'busy',                   'admission',  NULL,         'rejected', '存在活动任务，并发请求被拒绝'),
    (200, 'navigation_unavailable', 'navigation', 'planning',   'failed',   '导航能力不可用'),
    (201, 'navigation_failed',      'navigation', 'planning',   'failed',   '导航执行失败'),
    (202, 'navigation_canceled',    'navigation', 'control',    'canceled', '导航被取消'),
    (203, 'task_timeout',           'timeout',    'unknown',    'timeout',  '任务总超时'),
    (300, 'sensor_unavailable',     'perception', 'perception', 'failed',   '关键感知数据不可用'),
    (301, 'sensor_stale',           'perception', 'perception', 'failed',   '关键感知数据过期'),
    (400, 'safety_stop',            'safety',     'safety',     'failed',   '安全停车终止任务'),
    (500, 'internal',               'internal',   'unknown',    'failed',   '内部错误');

