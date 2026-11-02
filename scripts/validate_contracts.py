"""Validate every JSON schema and that each example validates against its schema.

Example naming: contracts/examples/<schema-name>[.<variant>].v1.example.json
maps to schema <schema-name>.v1.schema.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = ROOT / "contracts" / "examples"


def schema_for(example: Path) -> Path:
    stem = example.name.removesuffix(".example.json")  # e.g. command-envelope.remediation.v1
    base, _, version = stem.rpartition(".")
    name = base.split(".")[0]
    return SCHEMAS / f"{name}.{version}.schema.json"


def main() -> int:
    errors: list[str] = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        try:
            Draft202012Validator.check_schema(json.loads(path.read_text()))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: invalid schema: {exc}")
    for ex in sorted(EXAMPLES.glob("*.example.json")):
        sp = schema_for(ex)
        if not sp.exists():
            errors.append(f"{ex.name}: no schema {sp.name}")
            continue
        validator = Draft202012Validator(
            json.loads(sp.read_text()), format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        for err in validator.iter_errors(json.loads(ex.read_text())):
            errors.append(f"{ex.name}: {err.message} at {list(err.absolute_path)}")
    for y in sorted((ROOT / "contracts").rglob("*.yaml")):
        try:
            yaml.safe_load(y.read_text())
        except yaml.YAMLError as exc:
            errors.append(f"{y.name}: invalid YAML: {exc}")
    if errors:
        print("\n".join(errors))
        return 1
    print("contracts ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
