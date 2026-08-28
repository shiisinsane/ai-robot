import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[4]
SCHEMAS = ROOT / "portfolio/robot_ops_analytics/schemas"


def test_schema_contracts_pin_existing_files_and_hashes():
    contracts = []
    for path in sorted((SCHEMAS / "versions").glob("*/contract.yaml")):
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "dataset_version" in contract:
            contracts.append(path)
    assert {path.parent.name for path in contracts} == {
        "roa-data-v0.1", "roa-validation-b1-v0.2"}
    for path in contracts:
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert contract["dataset_version"] == path.parent.name
        for key in ("raw_schema", "facts_schema"):
            target = ROOT / contract[key]["path"]
            assert target.is_file()
            assert hashlib.sha256(target.read_bytes()).hexdigest() == contract[key]["sha256"]


def test_only_b1_contract_is_current():
    statuses = {}
    for path in (SCHEMAS / "versions").glob("*/contract.yaml"):
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "dataset_version" not in contract:
            continue
        statuses[contract["dataset_version"]] = contract["status"]
    assert statuses == {
        "roa-data-v0.1": "retired",
        "roa-validation-b1-v0.2": "current",
    }
