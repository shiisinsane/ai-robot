# 测试数据模板

- `evidence_manifest.yaml`：正式测试证据清单模板。

使用时复制到外部测试证据目录，替换示例字段，并执行：

```bash
python3 scripts/check_evidence_manifest.py <证据清单路径>
```

模板可以进入Git；实际rosbag、日志、图像和大型原始数据不得放入`test_data/`并提交。
