# 测试版本目录

- `common/`：采集核心、Schema、指标字典和版本契约测试；
- `legacy_v0_1/`：W3/W4/W5/A1历史流程及旧版数据口径回归；
- `b1_v0_2/`：当前B1实验设计和预注册统计测试。

统一执行：

```bash
python3 -m pytest portfolio/robot_ops_analytics/tests -q
```

Pytest递归发现三个目录。新增测试必须与被测流水线使用相同版本目录；真正跨版本的契约测试放入
`common/`。
