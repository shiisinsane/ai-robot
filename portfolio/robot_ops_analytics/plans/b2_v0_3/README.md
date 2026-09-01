# B2 v0.3运行计划

- `w7_b2_qualification_plan_v0.1.jsonl`：5条路线×3档障碍，共15项GUI资格Pilot；已于
  2026-08-31完成15/15资格验收。
- 生成器：`pipelines/b2_v0_3/generate_w7_b2_qualification_plan.py`。
- 源配置：`config/w7_b2_design_draft_v0.1.yaml`与`config/w7_b2_qualification_v0.1.yaml`。
- 当前冻结SHA-256：`58bf086affc3137f29b3434d4ba62ff46c0295c2decb51e17aab542103a5318d`。

资格计划只用于资格证据追溯，不进入正式建模数据。

## 正式预注册计划

`w7_b2_formal_plan_v0.3.jsonl`共360项，SHA-256为
`3a2f2d79ab28949260f49572d061c61a5f93392a5f859a68af92fec1972ab643`。计划已冻结，但每行仍保留
`environment_ready=false`和`qualification_ready=false`，不得据此直接执行。正式采集需要用户
另行明确授权，首个授权单元限制为训练区组1的45项。
