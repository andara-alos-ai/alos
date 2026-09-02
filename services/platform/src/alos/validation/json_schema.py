import re
from collections.abc import Mapping
from typing import Any


class JsonSchemaValidationError(ValueError):
    pass


def validate_json_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    type_matches = {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    expected_types = [expected] if isinstance(expected, str) else expected
    if isinstance(expected_types, list) and not any(
        isinstance(item, str) and type_matches.get(item, False) for item in expected_types
    ):
        raise JsonSchemaValidationError(f"{path} wajib bertipe {expected_types}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise JsonSchemaValidationError(f"{path} berada di luar enum")
    active_type = next(
        (
            item
            for item in (expected_types if isinstance(expected_types, list) else [])
            if isinstance(item, str) and type_matches.get(item, False)
        ),
        None,
    )
    if active_type == "object":
        _validate_object(value, schema, path)
    elif active_type == "array":
        _validate_array(value, schema, path)
    elif active_type == "string":
        _validate_string(value, schema, path)
    elif active_type in {"number", "integer"}:
        _validate_number(value, schema, path)


def _validate_object(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(value, Mapping):
        raise JsonSchemaValidationError(f"{path} wajib bertipe object")
    required_value = schema.get("required", [])
    required = set(required_value) if isinstance(required_value, list) else set()
    missing = required - set(value)
    if missing:
        raise JsonSchemaValidationError(f"{path} kehilangan field: {sorted(missing)}")
    properties_value = schema.get("properties", {})
    properties = properties_value if isinstance(properties_value, Mapping) else {}
    additional = schema.get("additionalProperties")
    unexpected = set(value) - set(properties)
    if additional is False and unexpected:
        raise JsonSchemaValidationError(
            f"{path} memiliki field tidak diizinkan: {sorted(unexpected)}"
        )
    for key, item in value.items():
        child_schema = properties.get(key)
        if isinstance(child_schema, Mapping):
            validate_json_schema(item, child_schema, f"{path}.{key}")
        elif isinstance(additional, Mapping):
            validate_json_schema(item, additional, f"{path}.{key}")


def _validate_array(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(value, list):
        raise JsonSchemaValidationError(f"{path} wajib bertipe array")
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if isinstance(minimum, int) and len(value) < minimum:
        raise JsonSchemaValidationError(f"{path} minimal memiliki {minimum} item")
    if isinstance(maximum, int) and len(value) > maximum:
        raise JsonSchemaValidationError(f"{path} maksimal memiliki {maximum} item")
    if schema.get("uniqueItems") is True:
        normalized = [repr(item) for item in value]
        if len(normalized) != len(set(normalized)):
            raise JsonSchemaValidationError(f"{path} tidak boleh memiliki item duplikat")
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            validate_json_schema(item, item_schema, f"{path}[{index}]")


def _validate_string(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(value, str):
        raise JsonSchemaValidationError(f"{path} wajib bertipe string")
    minimum = schema.get("minLength")
    maximum = schema.get("maxLength")
    if isinstance(minimum, int) and len(value) < minimum:
        raise JsonSchemaValidationError(f"{path} terlalu pendek")
    if isinstance(maximum, int) and len(value) > maximum:
        raise JsonSchemaValidationError(f"{path} terlalu panjang")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
        raise JsonSchemaValidationError(f"{path} tidak sesuai pola")


def _validate_number(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise JsonSchemaValidationError(f"{path} wajib berupa angka")
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, int | float) and value < minimum:
        raise JsonSchemaValidationError(f"{path} kurang dari minimum")
    if isinstance(maximum, int | float) and value > maximum:
        raise JsonSchemaValidationError(f"{path} melebihi maksimum")
