#!/usr/bin/env python3
"""验证测试证据清单包含复现和追溯所需字段。"""

import argparse
from pathlib import Path
from typing import Any

import yaml


class ManifestError(ValueError):
    """测试证据清单不完整。"""


REQUIRED_PATHS = (
    "evidence_version",
    "identity.evidence_id",
    "identity.milestone",
    "identity.test_name",
    "identity.executed_at",
    "source.git_commit",
    "source.interface_version",
    "environment.os",
    "environment.ros_distro",
    "execution.command",
    "execution.result",
    "artifacts",
)


def _get_path(data: dict[str, Any], dotted_path: str) -> Any:
    value: Any = data
    for key in dotted_path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ManifestError(f"缺少字段：{dotted_path}")
        value = value[key]
    return value


def validate_manifest(data: dict[str, Any]) -> list[str]:
    for path in REQUIRED_PATHS:
        value = _get_path(data, path)
        if value in (None, "", []):
            raise ManifestError(f"字段不能为空：{path}")

    result = _get_path(data, "execution.result")
    if result not in {"passed", "failed", "skipped"}:
        raise ManifestError("execution.result必须为passed、failed或skipped")

    commit = str(_get_path(data, "source.git_commit"))
    if len(commit) < 7:
        raise ManifestError("git_commit必须至少包含7位提交号")

    artifacts = _get_path(data, "artifacts")
    if not isinstance(artifacts, list):
        raise ManifestError("artifacts必须是列表")
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ManifestError(f"artifacts[{index}]必须是映射")
        for field in ("type", "location", "sha256"):
            if not artifact.get(field):
                raise ManifestError(f"artifacts[{index}]缺少{field}")

    return [
        "身份、源码、环境和执行信息完整",
        f"测试结果：{result}",
        f"证据文件数：{len(artifacts)}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    try:
        with args.manifest.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ManifestError("证据清单顶层必须是YAML映射")
        summary = validate_manifest(data)
    except (OSError, yaml.YAMLError, ManifestError) as error:
        print(f"证据清单检查失败：{error}")
        return 1

    print(f"证据清单检查通过：{args.manifest}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
