from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from common import PlanAnvilError, load_json


class SchemaValidationError(PlanAnvilError):
    def __init__(self, errors: list[str]):
        super().__init__("Schema validation failed", code="SCHEMA_VALIDATION_FAILED", details=errors)
        self.errors = errors


def _resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise PlanAnvilError(f"Only local schema refs are supported: {ref}", code="UNSUPPORTED_SCHEMA_REF")
    node: Any = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    if not isinstance(node, dict):
        raise PlanAnvilError(f"Schema ref is not an object: {ref}", code="INVALID_SCHEMA_REF")
    return node


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _is_datetime(value: str) -> bool:
    if not value.endswith("Z"):
        return False
    try:
        dt.datetime.fromisoformat(value[:-1] + "+00:00")
        return True
    except ValueError:
        return False


def validate(instance: Any, schema: dict[str, Any], *, root_schema: dict[str, Any] | None = None, path: str = "$") -> list[str]:
    root_schema = root_schema or schema
    errors: list[str] = []

    if "$ref" in schema:
        return validate(instance, _resolve_ref(root_schema, schema["$ref"]), root_schema=root_schema, path=path)

    if "allOf" in schema:
        for item in schema["allOf"]:
            errors.extend(validate(instance, item, root_schema=root_schema, path=path))
    if "anyOf" in schema:
        if not any(not validate(instance, item, root_schema=root_schema, path=path) for item in schema["anyOf"]):
            errors.append(f"{path}: does not match anyOf")
    if "oneOf" in schema:
        matched = sum(not validate(instance, item, root_schema=root_schema, path=path) for item in schema["oneOf"])
        if matched != 1:
            errors.append(f"{path}: matches {matched} oneOf branches")
    if "not" in schema and not validate(instance, schema["not"], root_schema=root_schema, path=path):
        errors.append(f"{path}: matches forbidden schema")

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum")

    expected_type = schema.get("type")
    if expected_type:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        if not any(_type_matches(instance, item) for item in expected_types):
            errors.append(f"{path}: expected type {expected_types}, got {type(instance).__name__}")
            return errors

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = f"{path}.{key}"
            if key in properties:
                errors.extend(validate(value, properties[key], root_schema=root_schema, path=child))
            elif additional is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                errors.extend(validate(value, additional, root_schema=root_schema, path=child))
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append(f"{path}: fewer than {schema['minProperties']} properties")
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            errors.append(f"{path}: more than {schema['maxProperties']} properties")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in instance]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                errors.extend(validate(value, item_schema, root_schema=root_schema, path=f"{path}[{index}]"))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: string does not match {schema['pattern']!r}")
        if schema.get("format") == "date-time" and not _is_datetime(instance):
            errors.append(f"{path}: invalid RFC 3339 UTC timestamp")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: value above maximum {schema['maximum']}")

    return errors


def validate_file(instance_path: Path, schema_path: Path) -> list[str]:
    instance = load_json(instance_path)
    schema = load_json(schema_path)
    return validate(instance, schema)


def assert_valid_file(instance_path: Path, schema_path: Path) -> None:
    errors = validate_file(instance_path, schema_path)
    if errors:
        raise SchemaValidationError(errors)
