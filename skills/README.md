# Project Skills

本目录用于保存 AI 机器人项目专用的可复用技能。

技能适合描述需要判断和上下文理解的标准流程，例如：

- 规划文件升级与历史版本归档；
- M0 环境和工程基线验收；
- ROS 2 软件包创建与最小测试；
- Topic、Service、Action、QoS 和 TF 契约检查；
- 仿真与实体接口一致性审查。

每项技能应使用独立子目录，并以 `SKILL.md` 作为入口：

```text
skills/
└── example-skill/
    ├── SKILL.md
    ├── references/
    └── scripts/
```

这里不存放 ROS 2 运行时代码。可直接执行、结果确定的工程命令优先放在项目根目录的
`scripts/` 中，由技能引用。
